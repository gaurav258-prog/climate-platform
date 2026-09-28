"""The EET rules for the field-list version in force (data/reference/eet/eet_rules_<version>.json).

  sfdr_product_type  our SFDR classification → the EET's 0 / 6 / 8 / 9
  pai_values         where each PAI field's value comes from in the fund's SFDR PAI statement (indicator, path, scale)
  taxonomy_values    the last-reported Taxonomy-aligned shares
  conditions         when a Conditional field applies — each rule quotes the FinDatEx condition it encodes

A condition is evaluated with three values: True (applies), False (does not), None (depends on an answer not given
yet → the field is listed for review). field_eq / field_gt on a blank field give None; all() is False if any part is
False, else None if any is None; any() is True if any part is True, else None if any is None.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from services.eet import fields as F

_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "eet"


class RulesError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def load(version: Optional[str] = None) -> dict:
    v = version or F.version()
    path = _DIR / f"eet_rules_{v}.json"
    if not path.exists():
        raise RulesError(f"no EET rules for field list {v} — add {path.name} (the conditions and PAI mapping for that version)")
    rules = json.loads(path.read_text())
    if rules.get("eet_version") != v:
        raise RulesError(f"{path.name} says it is for {rules.get('eet_version')}, not {v}")
    return rules


def use_flags() -> dict[str, str]:
    """use → the data-set field that says whether the file carries it (00060–00100 in V1.1.3)."""
    return dict(load()["use_flags"])


def sfdr_code(classification: Optional[str]) -> str:
    m = load()["sfdr_product_type"]
    return m.get(classification or "", m["default"])


def _get(row: dict, path: str):
    cur = row
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def read(spec: dict, indicators: dict) -> Optional[float]:
    """A value from the statement's indicators, as a pai_values rule describes it."""
    ind = indicators.get(spec["indicator"])
    if not ind or ind.get("value") is None or ind.get("method") == "not_applicable":
        return None
    r = spec["read"]
    if "sum" in r:
        parts = [_get(ind, p) for p in r["sum"]]
        v = sum(parts) if all(isinstance(x, (int, float)) for x in parts) else None
    else:
        v = _get(ind, r["path"])
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    if "times_ratio" in r:
        tr = r["times_ratio"]
        other = indicators.get(tr["indicator"]) or {}
        num = [_get(other, p) for p in tr["num"]]
        den = _get(other, tr["den"])
        if not all(isinstance(x, (int, float)) for x in num) or not den:
            return None
        v = v * sum(num) / den
    return v * r.get("scale", 1.0)


def _code(name: str) -> int:
    return int(name.split("_", 1)[0])


def _matches(match: dict, name: str) -> bool:
    c = _code(name)
    if "name_contains" in match and match["name_contains"] in name:
        return True
    if c in match.get("codes", []):
        return True
    return any(lo <= c <= hi for lo, hi in match.get("ranges", []))


def _field(values: dict, code: int) -> Optional[str]:
    return next((x for k, x in values.items() if k.startswith(f"{code}_") and x not in (None, "")), None)


def evaluate(expr, ctx: dict) -> Optional[bool]:
    if isinstance(expr, bool) or expr is None:
        return expr
    (op, arg), = expr.items()
    if op == "all":
        parts = [evaluate(e, ctx) for e in arg]
        return False if False in parts else (None if None in parts else True)
    if op == "any":
        parts = [evaluate(e, ctx) for e in arg]
        return True if True in parts else (None if None in parts else False)
    if op == "sfdr_in":
        return ctx["sfdr"] in arg
    if op == "fund_type":
        return ctx.get("fund_type") == arg
    if op == "use":
        return arg in ctx.get("uses", ())
    if op == "field_eq":
        v = _field(ctx["values"], arg[0])
        return None if v is None else v == arg[1]
    if op == "field_gt":
        v = _field(ctx["values"], arg[0])
        try:
            return None if v is None else float(v) > arg[1]
        except ValueError:
            return None
    raise RulesError(f"unknown condition operator {op!r}")


def _pending(expr, ctx: dict) -> tuple[Optional[bool], set[int]]:
    """(result, the field codes the result is waiting on) — only the answers that would actually settle it here."""
    if not isinstance(expr, dict):
        return expr, set()
    (op, arg), = expr.items()
    if op in ("all", "any"):
        parts = [_pending(e, ctx) for e in arg]
        vals = [v for v, _ in parts]
        decisive = False if op == "all" else True
        if decisive in vals:
            return decisive, set()
        waiting = set().union(*(p for v, p in parts if v is None))
        return (None if None in vals else (not decisive)), waiting
    v = evaluate(expr, ctx)
    return v, ({arg[0]} if v is None and op in ("field_eq", "field_gt") else set())


def waiting_on(name: str, ctx: dict) -> list[int]:
    """The field codes a Conditional field is waiting on in this row — the questions to answer first."""
    for rule in load()["conditions"]:
        if _matches(rule["match"], name):
            return sorted(_pending(rule["applies"], ctx)[1])
    return []


def applies(name: str, ctx: dict) -> Optional[bool]:
    """ctx: {sfdr, fund_type, values, uses}. The first rule whose match covers the field decides; no rule → None."""
    for rule in load()["conditions"]:
        if _matches(rule["match"], name):
            return evaluate(rule["applies"], ctx)
    return None
