import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import pandas as pd
except ImportError:
    print("缺少 pandas，请先安装：pip install pandas openpyxl", file=sys.stderr)
    raise


BASE_URL = "https://aitab.360.cn/aitab/api"
PAGE_URL = "https://aitab.360.cn/newtab.html?channel=woetne"
CITY_INDEX_URL = "https://s2.ssl.qhres2.com/static/f4eeef4ef5b35e79.json"
QUOTE_URL = "https://s1.ssl.qhres2.com/static/33012ae154044fa9.json"
WALLPAPER_TAG_URL = "https://mini.browser.360.cn/newtab/tagsx"
WEATHER_URL = "https://cdn.weather.hao.360.cn/api/weather_info.php"


def fetch_json(url: str, params: dict[str, Any] | None = None, timeout: int = 15) -> Any:
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(params)}"

    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Referer": PAGE_URL,
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace").strip()

    # Some old 360 endpoints can return JSONP. Keep the parser tolerant.
    match = re.match(r"^[\w$.]+\((.*)\);?$", raw, flags=re.S)
    if match:
        raw = match.group(1)
    return json.loads(raw)


def safe_fetch(logs: list[dict[str, Any]], name: str, url: str, params: dict[str, Any] | None = None) -> Any:
    started = time.time()
    try:
        data = fetch_json(url, params=params)
        logs.append(
            {
                "模块": name,
                "状态": "成功",
                "URL": url,
                "参数": json.dumps(params or {}, ensure_ascii=False),
                "耗时秒": round(time.time() - started, 2),
                "错误": "",
            }
        )
        return data
    except HTTPError as exc:
        logs.append(
            {
                "模块": name,
                "状态": "失败",
                "URL": url,
                "参数": json.dumps(params or {}, ensure_ascii=False),
                "耗时秒": round(time.time() - started, 2),
                "错误": f"HTTP {exc.code}: {exc.reason}",
            }
        )
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logs.append(
            {
                "模块": name,
                "状态": "失败",
                "URL": url,
                "参数": json.dumps(params or {}, ensure_ascii=False),
                "耗时秒": round(time.time() - started, 2),
                "错误": str(exc),
            }
        )
    return None


def find_city_id(city_name: str, logs: list[dict[str, Any]]) -> tuple[str, str]:
    cities = safe_fetch(logs, "城市编码", CITY_INDEX_URL)
    if not isinstance(cities, list):
        return "101280101", "广州"

    cleaned = city_name.strip().replace("市", "").replace("区", "")
    for city in cities:
        name = str(city.get("Location_Name_ZH", "")).strip()
        if name == city_name.strip() or name == cleaned:
            return str(city.get("Location_ID")), name
    return "101280101", "广州"


def collect_hot_lists(logs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    config = safe_fetch(logs, "热榜来源", f"{BASE_URL}/news/config")
    sources = []
    hot_rows = []

    if isinstance(config, dict):
        sources = config.get("data", {}).get("sources", []) or []

    source_rows = [
        {
            "来源ID": item.get("id"),
            "来源代码": item.get("source"),
            "来源名称": item.get("name"),
            "Logo": item.get("logo"),
        }
        for item in sources
    ]

    for source in sources:
        source_id = source.get("id")
        name = source.get("name")
        data = safe_fetch(
            logs,
            f"热榜-{name}",
            f"{BASE_URL}/news/hotList",
            {"sourceID": source_id, "page": 1, "size": 20},
        )
        items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
        for idx, item in enumerate(items, start=1):
            hot_rows.append(
                {
                    "来源ID": source_id,
                    "来源名称": name,
                    "排名": item.get("rank") or item.get("index") or idx,
                    "标题": item.get("title") or item.get("word") or item.get("name"),
                    "热度": item.get("hot") or item.get("heat") or item.get("score"),
                    "链接": item.get("url") or item.get("link"),
                    "摘要": item.get("desc") or item.get("summary"),
                    "原始数据": json.dumps(item, ensure_ascii=False),
                }
            )
    return source_rows, hot_rows


def collect_weather(city: str, logs: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    city_id, city_label = find_city_id(city, logs)
    data = safe_fetch(
        logs,
        "天气",
        WEATHER_URL,
        {
            "code": city_id,
            "app": "dev",
            "type": "area,air,airforecast,realtime,weather,weather_1h,life,rise,area,alarm",
            "format": "json",
        },
    )
    if not isinstance(data, dict):
        return [], [], [], []

    realtime = data.get("realtime", {}) or {}
    air = data.get("air", {}) or {}
    current = [
        {
            "城市": city_label,
            "城市编码": city_id,
            "发布时间": realtime.get("pubtime"),
            "天气": realtime.get("weather_name"),
            "温度": realtime.get("temperature"),
            "体感温度": realtime.get("feeling"),
            "湿度": realtime.get("humidity"),
            "风向": realtime.get("wind_name"),
            "风力": realtime.get("wind_power_name"),
            "风速": realtime.get("wind_speed"),
            "能见度": realtime.get("visibility"),
            "AQI": air.get("aqi"),
            "PM2.5": air.get("pm2.5"),
            "PM10": air.get("pm10"),
            "空气发布时间": air.get("pubtime"),
        }
    ]

    forecast = []
    for row in data.get("weather", []) or []:
        day = row.get("info", {}).get("day", {}) or {}
        night = row.get("info", {}).get("night", {}) or {}
        forecast.append(
            {
                "日期": row.get("date"),
                "白天天气": day.get("weather_name"),
                "白天温度": day.get("temperature"),
                "白天风向": day.get("wind_name"),
                "白天风力": day.get("wind_power_name"),
                "夜间天气": night.get("weather_name"),
                "夜间温度": night.get("temperature"),
                "夜间风向": night.get("wind_name"),
                "夜间风力": night.get("wind_power_name"),
            }
        )

    hourly = []
    for row in data.get("weather_1h", []) or []:
        info = row.get("info", {}) or {}
        hourly.append(
            {
                "时间": row.get("time"),
                "天气": info.get("weather_name"),
                "温度": info.get("temperature"),
                "湿度": info.get("humidity"),
                "风向": info.get("wind_name"),
                "风速": info.get("wind_speed"),
            }
        )

    life = []
    for row in data.get("life", []) or []:
        for key, values in (row.get("info", {}) or {}).items():
            values = values if isinstance(values, list) else []
            life.append(
                {
                    "日期": row.get("date"),
                    "类型": key,
                    "名称": values[0] if len(values) > 0 else "",
                    "等级": values[1] if len(values) > 1 else "",
                    "说明": values[2] if len(values) > 2 else "",
                }
            )
    return current, forecast, hourly, life


def collect_quotes(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = safe_fetch(logs, "名言", QUOTE_URL)
    if not isinstance(data, list):
        return []
    return [
        {"序号": idx, "内容": item.get("content", "").strip(), "作者": item.get("author", "").strip()}
        for idx, item in enumerate(data, start=1)
        if isinstance(item, dict)
    ]


def collect_wallpaper_tags(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = safe_fetch(logs, "壁纸标签", WALLPAPER_TAG_URL, {"uid": "codex-scraper"})
    tags = data.get("data", {}).get("tags", []) if isinstance(data, dict) else []
    return [
        {
            "标签ID": item.get("id"),
            "标签名称": item.get("title"),
            "层级": item.get("level"),
            "图片数量": item.get("img_num"),
            "Logo": item.get("logo"),
        }
        for item in tags
        if isinstance(item, dict)
    ]


def collect_game_status(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    data = safe_fetch(logs, "小游戏列表", f"{BASE_URL}/game/list", {"page": 1, "pageSize": 50})
    items = data.get("data", {}).get("list", []) if isinstance(data, dict) else []
    return [
        {
            "游戏ID": item.get("id"),
            "名称": item.get("name"),
            "分类": item.get("game_category_name"),
            "图标": item.get("icon_url"),
            "链接": item.get("game_url"),
        }
        for item in items
        if isinstance(item, dict)
    ]


def collect_builtin_sites() -> list[dict[str, Any]]:
    # These are visible page defaults extracted from the loaded JS bundle.
    sites = [
        ("AI办公", "豆包", "https://www.doubao.com/"),
        ("AI办公", "LiblibAI", "https://www.liblib.tv/"),
        ("AI办公", "千问", "https://www.qianwen.com/"),
        ("AI办公", "DeepSeek", "https://chat.deepseek.com/"),
        ("购物", "京东", "https://www.jd.com/"),
        ("购物", "天猫", "https://www.tmall.com/"),
        ("购物", "淘宝", "https://www.taobao.com/"),
        ("购物", "1688", "https://www.1688.com/"),
        ("生活", "BOSS直聘", "https://www.zhipin.com/"),
        ("休闲", "哔哩哔哩", "https://www.bilibili.com/"),
        ("休闲", "抖音", "https://www.douyin.com/"),
        ("休闲", "小红书", "https://www.xiaohongshu.com/"),
        ("出行", "百度地图", "https://map.baidu.com/"),
        ("出行", "高德地图", "https://www.amap.com/"),
        ("股票", "东方财富", "https://www.eastmoney.com/"),
        ("股票", "股吧", "https://guba.eastmoney.com/"),
    ]
    return [{"分类": category, "名称": name, "链接": url} for category, name, url in sites]


def write_excel(output: Path, sheets: dict[str, list[dict[str, Any]]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame([{"说明": "本次未抓取到数据"}])
            df.to_excel(writer, index=False, sheet_name=sheet_name[:31])

            worksheet = writer.sheets[sheet_name[:31]]
            worksheet.freeze_panes = "A2"
            for column_cells in worksheet.columns:
                max_len = max(len(str(cell.value or "")) for cell in column_cells)
                width = min(max(max_len + 2, 10), 60)
                worksheet.column_dimensions[column_cells[0].column_letter].width = width


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 AItab 页面接口数据并生成 Excel")
    parser.add_argument("--city", default="广州", help="天气城市名称，默认：广州")
    parser.add_argument("--output", default="outputs/aitab_data.xlsx", help="Excel 输出路径")
    args = parser.parse_args()

    logs: list[dict[str, Any]] = []
    hot_sources, hot_rows = collect_hot_lists(logs)
    weather_current, weather_forecast, weather_hourly, weather_life = collect_weather(args.city, logs)
    sheets = {
        "抓取概览": [
            {
                "页面URL": PAGE_URL,
                "抓取时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "天气城市": args.city,
                "热榜条数": len(hot_rows),
                "名言条数": 0,
                "壁纸标签数": 0,
            }
        ],
        "热榜来源": hot_sources,
        "热榜": hot_rows,
        "当前天气": weather_current,
        "天气预报": weather_forecast,
        "逐小时天气": weather_hourly,
        "生活指数": weather_life,
        "名言": collect_quotes(logs),
        "壁纸标签": collect_wallpaper_tags(logs),
        "常用导航": collect_builtin_sites(),
        "小游戏": collect_game_status(logs),
        "抓取日志": logs,
    }
    sheets["抓取概览"][0]["名言条数"] = len(sheets["名言"])
    sheets["抓取概览"][0]["壁纸标签数"] = len(sheets["壁纸标签"])

    output = Path(args.output)
    write_excel(output, sheets)
    print(f"已生成：{output.resolve()}")


if __name__ == "__main__":
    main()
