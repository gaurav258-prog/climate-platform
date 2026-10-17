"""The UI standard's guard on the server (product owner, 2026-10-16): text the API sends to a screen is customer
language. An AST scan of api/ and services/ counts, per file, the strings in two places a screen shows:
  display  a value under a display key of a response or record (gap, reason, note, message, title, basis, caution,
           hint, summary, label, description, detail, headline, why, review, notice)
  error    the message of a raised exception — routers pass str(e) straight to the screen; a UserError carries a
           catalogue code instead, which must be in the catalogue
  rawError an exception's own text handed to the screen ({"message": str(e)}, detail=str(e)) — the technical cause
           belongs in the log; the screen gets a catalogue message (core/errors.py UserError)
that carry internal language (a snake_case code, an E-number, a file or API path, engineering jargon). Counts are held
per file in tests/ui_language_backend_baseline.json, the breaches when the standard came in; the guard
(tests/unit/test_ui_language_backend.py) fails when a file has more, and when a fix leaves fewer (lower the baseline,
so it only ever goes down):  venv/bin/python -m scripts.ui_language --write
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "tests" / "ui_language_backend_baseline.json"
INTERNAL = re.compile(r"\b[a-z]+_[a-z0-9_]+\b|\bE\d{2,3}\b|\.(?:py|json)\b|/v1/|named gap|append-only|golden (?:source|model)"
                      r"|product owner|\bseeded\b|\bstub\b|sha-?256|\bH3\b", re.I)
# "error" is not here: in an error response it holds the machine code ({error: code, message}), by design
DISPLAY = {"gap", "reason", "note", "message", "title", "basis", "caution", "hint", "summary", "label", "description",
           "detail", "headline", "why", "review", "notice"}


def _text(node: ast.AST) -> str | None:
    """The static text of a string or f-string (without its {…} parts)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return " ".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        parts = [_text(node.left), _text(node.right)]
        return " ".join(p for p in parts if p) or None
    return None


def _codes() -> set[str]:
    from core import messages
    return set(messages.catalogue())


def _is_str_of_exception(v: ast.AST) -> bool:
    return (isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == "str" and len(v.args) == 1
            and isinstance(v.args[0], ast.Name))


KINDS = ("display", "error", "rawError")


def scan(path: Path) -> dict[str, int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out = dict.fromkeys(KINDS, 0)
    for n in ast.walk(tree):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value in DISPLAY and (t := _text(v)) and INTERNAL.search(t):
                    out["display"] += 1
                if isinstance(k, ast.Constant) and k.value in ("message", "detail") and _is_str_of_exception(v):
                    out["rawError"] += 1
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "HTTPException":
            if any(kw.arg == "detail" and _is_str_of_exception(kw.value) for kw in n.keywords) or \
                    (len(n.args) > 1 and _is_str_of_exception(n.args[1])):
                out["rawError"] += 1
        elif isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call) and n.exc.args:
            if isinstance(n.exc.func, ast.Name) and n.exc.func.id == "UserError":
                # its argument is a catalogue code, not words: the words are the catalogue's (core/messages.check);
                # a code the catalogue lacks is a breach
                if (t := _text(n.exc.args[0])) and t not in _codes():
                    out["error"] += 1
            elif (t := _text(n.exc.args[0])) and INTERNAL.search(t) and t not in _codes():
                out["error"] += 1
    return out


def sources() -> list[Path]:
    return sorted(p for d in ("api", "services") for p in (ROOT / d).rglob("*.py") if "__pycache__" not in p.parts)


def scan_all() -> dict[str, dict[str, int]]:
    out = {}
    for p in sources():
        c = scan(p)
        if any(c.values()):
            out[str(p.relative_to(ROOT))] = c
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    got = scan_all()
    if a.write:
        BASELINE.write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    print(f"{len(got)} files —", {k: sum(c[k] for c in got.values()) for k in KINDS})
