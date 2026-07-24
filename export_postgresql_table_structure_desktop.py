# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib
import sys
from typing import Any

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
except ModuleNotFoundError as exc:
    missing_package = exc.name
    print(f"缺少 Python 包：{missing_package}")
    print("请在 PyCharm 当前项目解释器里安装依赖：")
    print("pip install sqlalchemy psycopg2-binary")
    raise SystemExit(1) from exc

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


# ==================== 配置区域 ====================
# PostgreSQL 数据库连接信息
USERNAME = "read_only"
PASSWORD = "readuser@123"
HOST = "10.5.49.204"
PORT = 25432
DATABASE = "db_zhcsng"
SCHEMA = "public"

# 需要导出的表名。多个表这样写：["表1", "表2"]
# 如果留空：TABLES = []，程序会先列出当前 schema 下所有表。
TABLES: list[str] = ["gen_table_column"]

# 直接导出到桌面
DESKTOP_DIR = pathlib.Path(r"D:\Users\asus\Desktop")
if not DESKTOP_DIR.exists():
    DESKTOP_DIR = pathlib.Path.home() / "Desktop"
OUTPUT_FILE = DESKTOP_DIR / "数据库pds.txt"

# 是否输出标题行：序号 中文名称 英文名称 数据类型 长度 精度
INCLUDE_HEADER = False
# =================================================


COLUMNS_QUERY = text(
    """
    SELECT
        c.ordinal_position,
        c.column_name AS column_name,
        COALESCE(
            pg_catalog.col_description(
                format('%I.%I', c.table_schema, c.table_name)::regclass::oid,
                c.ordinal_position
            ),
            ''
        ) AS column_comment,
        CASE
            WHEN c.data_type = 'character varying' THEN 'varchar'
            WHEN c.data_type = 'character' THEN 'char'
            WHEN c.data_type = 'timestamp without time zone' THEN 'timestamp'
            WHEN c.data_type = 'timestamp with time zone' THEN 'timestamptz'
            ELSE c.data_type
        END AS data_type,
        CASE
            WHEN c.character_maximum_length IS NOT NULL THEN c.character_maximum_length
            WHEN c.numeric_precision IS NOT NULL THEN c.numeric_precision
            WHEN c.datetime_precision IS NOT NULL THEN c.datetime_precision
            ELSE NULL
        END AS length_value,
        CASE
            WHEN c.numeric_scale IS NOT NULL THEN c.numeric_scale
            WHEN c.character_maximum_length IS NOT NULL THEN 0
            ELSE NULL
        END AS precision_value
    FROM information_schema.columns c
    WHERE c.table_catalog = :database
      AND c.table_schema = :schema
      AND c.table_name = :table_name
    ORDER BY c.ordinal_position;
    """
)

LIST_TABLES_QUERY = text(
    """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_catalog = :database
      AND table_schema = :schema
      AND table_type = 'BASE TABLE'
    ORDER BY table_name;
    """
)


def build_engine():
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=USERNAME,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        database=DATABASE,
    )
    return create_engine(url, pool_pre_ping=True)


def list_all_tables(engine) -> list[str]:
    with engine.connect() as conn:
        result = conn.execute(
            LIST_TABLES_QUERY,
            {"database": DATABASE, "schema": SCHEMA},
        )
        return [row[0] for row in result]


def to_chinese_data_type(data_type: str) -> str:
    normalized_type = data_type.lower()
    if normalized_type in {"varchar", "char", "bpchar", "character varying", "character", "uuid"}:
        return "字符型"
    if normalized_type in {"text", "json", "jsonb", "xml"}:
        return "文本型"
    if normalized_type in {
        "bigint",
        "bigserial",
        "int8",
        "integer",
        "int",
        "int4",
        "smallint",
        "smallserial",
        "int2",
        "serial",
    }:
        return "整数型"
    if normalized_type in {"real", "double precision", "float4", "float8"}:
        return "浮点型"
    if normalized_type in {"numeric", "decimal", "money"}:
        return "数字型"
    if normalized_type == "date":
        return "日期型"
    if normalized_type in {
        "time",
        "timetz",
        "time without time zone",
        "time with time zone",
        "timestamp",
        "timestamptz",
        "timestamp without time zone",
        "timestamp with time zone",
    }:
        return "时间戳"
    if normalized_type in {"bytea", "bit", "bit varying", "varbit"}:
        return "二进制"
    if normalized_type in {"geometry", "geography", "point", "line", "lseg", "box", "path", "polygon", "circle"}:
        return "地理坐标"
    if normalized_type in {"boolean", "bool"}:
        return "整数型"
    return "文本型"


def format_txt_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def build_txt_lines(rows: list[dict[str, Any]], start_index: int = 1) -> list[str]:
    lines: list[str] = []
    if INCLUDE_HEADER:
        lines.append("序号\t中文名称\t英文名称\t数据类型\t长度\t精度")

    for index, row in enumerate(rows, start=start_index):
        values = [
            index,
            row["column_comment"],
            row["column_name"],
            to_chinese_data_type(row["data_type"]),
            row["length_value"],
            row["precision_value"],
        ]
        lines.append("\t".join(format_txt_value(value) for value in values))
    return lines


def main() -> None:
    engine = build_engine()

    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
            print("PostgreSQL 连接成功")
            print(f"版本：{version[:80]}...")

        if not TABLES:
            print(f"\n未指定表名，正在列出 {DATABASE}.{SCHEMA} 下的表：")
            all_tables = list_all_tables(engine)
            if not all_tables:
                print("没有找到任何表，请检查 DATABASE 和 SCHEMA。")
                return

            for index, table_name in enumerate(all_tables, start=1):
                print(f"{index}. {table_name}")

            print("\n请把需要导出的表名填入 TABLES，例如：")
            print('TABLES = ["表名1", "表名2"]')
            return

        output_lines: list[str] = []
        exported_count = 0
        next_index = 1

        with engine.connect() as conn:
            for table in TABLES:
                if not table.strip():
                    continue

                result = conn.execute(
                    COLUMNS_QUERY,
                    {
                        "database": DATABASE,
                        "schema": SCHEMA,
                        "table_name": table,
                    },
                )
                rows = [dict(row) for row in result.mappings()]

                if not rows:
                    print(f"跳过：没有查到表结构，请检查表名或 schema：{SCHEMA}.{table}")
                    continue

                if len(TABLES) > 1:
                    if output_lines:
                        output_lines.append("")
                    output_lines.append(f"# {table}")

                table_lines = build_txt_lines(rows, start_index=next_index)
                output_lines.extend(table_lines)
                next_index += len(rows)
                exported_count += 1
                print(f"已导出：{table}，共 {len(rows)} 列")

        if exported_count == 0:
            print("\n没有导出任何表，请检查 TABLES、DATABASE、SCHEMA 是否正确。")
            return

        OUTPUT_FILE.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
        print(f"\n导出完成：{OUTPUT_FILE}")
        print(f"成功导出 {exported_count} 个表。")
    except Exception as exc:
        print(f"\n错误：{exc}")
        print("\n请重点检查：")
        print("1. PyCharm 使用的解释器是否已安装：sqlalchemy psycopg2-binary")
        print("2. HOST、PORT、DATABASE、SCHEMA 是否正确")
        print("3. 用户名和密码是否正确")
        print("4. 当前网络是否能访问 PostgreSQL 服务器")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

