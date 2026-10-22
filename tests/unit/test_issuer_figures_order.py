"""E317: a read that picks one issuer_emissions row (an enterprise value, a revenue, a set of emissions, a physical asset
value) ends its ORDER BY with the one stated order of sources (services.issuer_figures.SOURCE_TIE; the product owner's
decision of 2026-10-22) — before it, two sources stating the same year were picked arbitrarily, and the voluntary
indicators read a vendor's enterprise value where the mandatory ones read the organisation's own."""
from __future__ import annotations

import ast
import re
from pathlib import Path

from services.issuer_figures import SOURCE_ORDER, SOURCE_TIE, latest

ROOT = Path(__file__).resolve().parents[2]
CODE = ("services", "api", "ml", "core", "scripts")
PICKS = re.compile(r"\bissuer_emissions\b[\s\S]*ORDER BY[\s\S]*LIMIT 1", re.I)


def _ties(node: ast.JoinedStr) -> bool:
    return any(isinstance(v, ast.FormattedValue) and (
        (isinstance(v.value, ast.Name) and v.value.id == "SOURCE_TIE")
        or (isinstance(v.value, ast.Call) and getattr(v.value.func, "id", getattr(v.value.func, "attr", None)) == "latest"))
        for v in node.values)


def unordered_picks() -> list[str]:
    """Every query string that picks one issuer_emissions row without the source order (a year-count that groups rows
    picks no row)."""
    out = []
    for p in [f for d in CODE for f in (ROOT / d).rglob("*.py") if "migrations" not in f.parts]:
        tree = ast.parse(p.read_text(encoding="utf-8"))
        inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in inner:
                sql, ok = n.value, False
            elif isinstance(n, ast.JoinedStr):
                sql = "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in n.values)
                ok = _ties(n)
            else:
                continue
            if PICKS.search(sql) and "GROUP BY" not in sql.upper() and not ok:
                out.append(f"{p.relative_to(ROOT).as_posix()}:{n.lineno}")
    return sorted(out)


def test_every_read_that_picks_an_issuer_figure_ends_with_the_source_order():
    assert unordered_picks() == [], "end the ORDER BY with {SOURCE_TIE}, or read through services.issuer_figures.latest"


def test_the_order_is_the_decided_one():
    assert SOURCE_ORDER == ("client", "disclosed", "cdp", "estimated", "vendor")
    assert SOURCE_TIE.startswith("array_position(ARRAY['client', 'disclosed'") and SOURCE_TIE.endswith("source)")
    q = latest("evic_eur", "i.issuer_id")
    assert q.index("(org_id IS NULL)") < q.index("(source = 'vendor')") < q.index("reporting_year DESC") < q.index(SOURCE_TIE)


def test_the_scan_sees_a_read_without_the_order():
    bad = "SELECT evic_eur FROM issuer_emissions WHERE issuer_id = :i ORDER BY reporting_year DESC LIMIT 1"
    assert PICKS.search(bad)
    assert not PICKS.search("SELECT 1 FROM issuer_emissions WHERE issuer_id = :i")
