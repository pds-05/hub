# -*- coding: utf-8 -*-
from __future__ import annotations

import pathlib

import export_postgresql_table_structure_cn as exporter


DESKTOP_DIR = pathlib.Path(r"D:\Users\asus\Desktop")
if not DESKTOP_DIR.exists():
    DESKTOP_DIR = pathlib.Path.home() / "Desktop"

exporter.OUTPUT_FILE = DESKTOP_DIR / "数据库pds.xlsx"
exporter.main()
