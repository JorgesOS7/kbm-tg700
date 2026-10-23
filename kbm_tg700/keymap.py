"""Keyboard layouts (from the vendor KeyInfo_*.config files) and key-binding helpers."""
import json
import os

from .protocol import BIND_FN, BIND_KEY, BIND_MACRO, FN_CODE, MATRIX_COLS, MATRIX_ROWS

with open(os.path.join(os.path.dirname(__file__), "layouts.json"), encoding="utf-8") as _f:
    LAYOUTS = json.load(_f)

DEFAULT_MODEL = "TG700"


def default_entry(code):
    if code == FN_CODE:
        return [BIND_FN, 0, 0, 0]
    if 0 < code < 256:
        return [BIND_KEY, code, 0, 0]
    return [0, 0, 0, 0]


def build_keymap(model, bindings):
    """bindings: {"row,col": {"type": "key"|"macro"|"default", "value": int}} -> 132 entries."""
    entries = [[0, 0, 0, 0] for _ in range(MATRIX_ROWS * MATRIX_COLS)]
    for key in LAYOUTS[model]:
        idx = key["row"] * MATRIX_COLS + key["col"]
        entries[idx] = default_entry(key["code"])
        b = bindings.get(f'{key["row"]},{key["col"]}')
        if not b:
            continue
        if b["type"] == "key":
            entries[idx] = [BIND_KEY, b["value"] & 0xFF, 0, 0]
        elif b["type"] == "macro":
            entries[idx] = [BIND_MACRO, b["value"], 0, 0]
        elif b["type"] == "disabled":
            entries[idx] = [0, 0, 0, 0]
    return entries
