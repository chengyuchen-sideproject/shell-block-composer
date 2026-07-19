"""積木儲存:data/functions.json(單一 JSON 檔,原子寫入)。

格式:[{"id","name","description","content","builtin"}]
首次啟動自動放入內建範例;「還原內建」只補回名稱不存在的,不覆蓋使用者修改。
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from seeds import SEED_FUNCTIONS

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
FUNC_FILE = DATA_DIR / "functions.json"

for d in (DATA_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _seed_items() -> list[dict]:
    return [{"id": _new_id(), "builtin": True, **s} for s in SEED_FUNCTIONS]


def load_functions() -> list[dict]:
    if not FUNC_FILE.exists():
        funcs = _seed_items()
        save_functions(funcs)
        return funcs
    try:
        data = json.loads(FUNC_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def save_functions(funcs: list[dict]) -> None:
    tmp = FUNC_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(funcs, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    os.replace(tmp, FUNC_FILE)  # 原子替換,寫到一半斷電不會毀掉整個檔


def restore_defaults() -> tuple[list[dict], int]:
    """補回「名稱已不存在」的內建範例,回傳(清單, 補回數)。"""
    funcs = load_functions()
    existing = {f["name"] for f in funcs}
    added = 0
    for s in SEED_FUNCTIONS:
        if s["name"] not in existing:
            funcs.append({"id": _new_id(), "builtin": True, **s})
            added += 1
    if added:
        save_functions(funcs)
    return funcs, added
