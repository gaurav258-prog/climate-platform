"""The message catalogue (UI standard, product owner 2026-10-16): every explanation the server sends a screen — a reason
a figure is missing, the basis it rests on, a caution, an error — is a code with its values, never a sentence written
where it arises. One catalogue (data/reference/messages.en.json) gives each code its customer words:

  label    a short line for the main screen (eight words or fewer)
  detail   the structured explanation behind the screen's ⓘ: what (always), why, next (what the reader can do)

Values fill {placeholders}; a value that is itself a code (a scenario, a map) is passed already in customer words. The
catalogue is re-read when the file changes, so a running API sees an edit without a restart.

    render("loss.gap.no_curve", use="commercial", country="Algeria")
      → {"code": ..., "params": {...}, "label": "No curve for this use and country", "detail": {"what": "..."}}
"""
from __future__ import annotations

import json
import re
import string
from functools import lru_cache
from pathlib import Path
from typing import Any

FILE = Path(__file__).resolve().parents[1] / "data" / "reference" / "messages.en.json"
PARTS = ("what", "why", "next")
# what a customer never reads (the guards' list: scripts/ui_language.py, web/tests/uiLanguage.ts)
INTERNAL = re.compile(r"\b[a-z]+_[a-z0-9_]+\b|\bE\d{2,3}\b|\.(?:py|json)\b|/v1/|named gap|append-only|golden (?:source|model)"
                      r"|product owner|\bseeded\b|\bstub\b|sha-?256|\bH3\b", re.I)


class MessageError(KeyError):
    pass


@lru_cache(maxsize=4)
def _load(_version: int) -> dict:
    return json.loads(FILE.read_text(encoding="utf-8"))


def catalogue() -> dict[str, dict]:
    return _load(FILE.stat().st_mtime_ns)["messages"]


def names() -> dict[str, dict[str, str]]:
    """Customer names for the codes a message names: {'peril': {...}, 'scenario': {...}}."""
    return _load(FILE.stat().st_mtime_ns).get("names", {})


def name(kind: str, key: str) -> str:
    """A code's customer name ('scenario', 'orderly_1_5c' → 'Orderly 1.5 °C'); never the code itself."""
    got = names().get(kind, {}).get(key)
    if got is None:
        raise MessageError(f"no {kind} name for '{key}' in {FILE.name}")
    return got


def _fill(template: str, params: dict[str, Any]) -> str:
    return string.Formatter().vformat(template, (), {k: ("" if v is None else v) for k, v in params.items()})


def render(code: str, **params: Any) -> dict:
    """{code, params, label, detail} for a code — the label for the screen, the detail for its pop-up."""
    m = catalogue().get(code)
    if m is None:
        raise MessageError(f"message code '{code}' is not in {FILE.name}")
    detail = {p: _fill(m["detail"][p], params) for p in PARTS if m["detail"].get(p)}
    return {"code": code, "params": params, "label": _fill(m["label"], params), "detail": detail}


def label(code: str, **params: Any) -> str:
    return render(code, **params)["label"]


def check() -> list[str]:
    """Every problem in the catalogue; empty when it is sound."""
    out = []
    for code, m in catalogue().items():
        if not re.fullmatch(r"[a-z]+(\.[a-z_]+)+", code):
            out.append(f"{code}: a code is dotted lower-case words")
        lab = m.get("label") or ""
        if not lab or len(lab.split()) > 8:
            out.append(f"{code}: the label must be one to eight words")
        if not (m.get("detail") or {}).get("what"):
            out.append(f"{code}: the detail must say what it means")
        for part in [lab, *[(m.get("detail") or {}).get(p) or "" for p in PARTS]]:
            text = re.sub(r"\{[a-z_]+\}", "", part)          # placeholders are filled with customer words
            if INTERNAL.search(text):
                out.append(f"{code}: '{part[:60]}' carries internal language")
        if set(m) - {"label", "detail", "status"}:
            out.append(f"{code}: unknown fields {sorted(set(m) - {'label', 'detail', 'status'})}")
    return out
