"""What an approver reads about a request, in customer words (UI standard, 2026-10-16): every field of the request is
named (names "admin.approval_field"), every coded value is named (a report, a scenario, a horizon, a decision, a step
— names "admin.approval_value" and the catalogue's own sets), and the identifiers a person cannot read are left out.
The approver still sees everything the request asks for: a field with no name is shown under its own words, and a guard
test keeps every field the requests hold named (tests/integration/test_admin_platform_words.py)."""
from __future__ import annotations

import re
from typing import Any

from core import messages

# identifiers and the platform's own bookkeeping: not something a person decides on
_HIDDEN = re.compile(r"^_|(^|_)ids?$|^datapoint_key$|^summary$")
# the values whose words come from a catalogue set rather than as typed
_CODED = {"scenario", "horizon", "direction", "kind", "path", "role", "source", "size_class", "action", "framework",
          "template"}
_CODE_LIKE = re.compile(r"^[a-z]+(_[a-z0-9]+)+$|^[A-Z]+(_[A-Z0-9]+)+$")


def _value(key: str, v: Any) -> str | None:
    n = messages.names()
    if v is None or v == "" or v == []:
        return None
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        if key.endswith("_eur"):
            return f"{v:,.0f} EUR"
        return f"{v:,.4f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"   # never 1.235e+05
    if isinstance(v, list):
        return " · ".join(str(x) for x in v if x is not None) or None
    s = str(v)
    if key == "scenario":
        return n["scenario"].get(s, s)
    if key == "horizon":
        return n.get("horizon.stop", {}).get(s, s)
    if key == "signal":                     # what raised a decision: a forward crossing or a tested loss
        return n["decision.signal"].get(s, s)
    if key == "framework":
        from services.governance.filings import FRAMEWORKS
        return (FRAMEWORKS.get(s) or {}).get("label") or n["admin.approval_value"].get(s) or messages.label("admin.approvals.a_report")
    if key == "kri_key":                    # an indicator by its catalogue name (kri.indicator.<key>)
        code = f"kri.indicator.{s}"
        return messages.label(code) if code in messages.catalogue() else messages.label("admin.approvals.an_indicator")
    if key == "template":
        from services.intake.catalog import TEMPLATES
        t = TEMPLATES.get(s)
        return t.label if t else messages.label("admin.approvals.a_template")
    if key in _CODED:
        return n["admin.approval_value"].get(s, s if not _CODE_LIKE.match(s) else messages.label("admin.approvals.a_choice"))
    return s


def _field(key: str) -> str:
    return messages.names()["admin.approval_field"].get(key) or key.replace("_", " ").capitalize()


def details(request_type: str, payload: dict) -> list[dict]:
    """The request's fields as {label, value} rows, in the order the request holds them: a change set or a nested
    group is opened up (a site's changed fields, the rows an import matched, the criteria an assessment weighed)."""
    out: list[dict] = []
    for k, v in (payload or {}).items():
        if _HIDDEN.search(k):
            continue
        if isinstance(v, dict):
            group = messages.names()["admin.approval_field"].get(k)
            for k2, v2 in v.items():
                field = (messages.names()["admin.field"].get(k2) or
                         (f"{group} {k2}" if group and len(k2) <= 2 else _field(k2)))
                if (val := _value(k2, v2)) is not None:
                    out.append({"label": field, "value": val})
            continue
        if request_type == "config.calc_settings" and k not in ("reason",):
            from services.governance.admin_view import option_label, switch_code
            try:
                out.append({"label": messages.label(switch_code(k)), "value": option_label(v)})
                continue
            except messages.MessageError:
                pass
        if (val := _value(k, v)) is not None:
            out.append({"label": _field(k), "value": val})
    return out


def title(stored: str | None) -> str | None:
    """The request's title, unless it carries internal language (old requests named a report by its code) — the
    screen then shows the request's kind alone."""
    if not stored:
        return None
    return None if messages.INTERNAL.search(stored) else stored
