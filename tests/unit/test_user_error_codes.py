"""Every message code the server names is in the catalogue (UI standard, 2026-10-16): a UserError("…") or a
messages.render/label("…") with a code that is not in data/reference/messages.en.json would reach a screen as a crash
instead of customer words — this catches it before it ships."""
from __future__ import annotations

import ast

from core import messages
from scripts import ui_language as U

CALLS = {"UserError", "render", "label", "_message"}


def _codes(path):
    for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Call) and n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
            f = n.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if name in CALLS and "." in n.args[0].value and " " not in n.args[0].value:
                yield n.args[0].value, n.lineno


def test_every_code_the_server_names_is_in_the_catalogue():
    known = set(messages.catalogue())
    missing = [f"{p.relative_to(U.ROOT)}:{line} {code}" for p in U.sources() for code, line in _codes(p) if code not in known]
    assert missing == [], f"Add these codes to data/reference/messages.en.json: {missing}"


def test_the_respondent_codes_render():
    for code in [c for c in messages.catalogue() if c.startswith("supervision.respondent.")]:
        r = messages.render(code, regulator="A supervisor", level="30", kind="finding", from_status="Open",
                            to_status="Closed", attribute="Total assets")
        assert r["label"] and r["detail"]["what"] and "{" not in r["label"] + r["detail"]["what"]
