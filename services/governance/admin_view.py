"""What the control center (web/src/pages/Admin.tsx) is told, in customer words (UI standard, 2026-10-16): every code it
shows is named from the message catalogue (core/messages.py, names "admin.*", "role", "scenario", "horizon.stop",
"filing.election", "dependence"), every explanation is a catalogue message, and every refusal a catalogue error. The
routers (api/routers/admin.py, calc_settings.py) stay thin; the words live here and in the catalogue."""
from __future__ import annotations

from typing import Optional

from core import messages
from core.errors import UserError


def name(kind: str, key: Optional[str]) -> Optional[str]:
    """A code's customer name, or None for no code; a code the catalogue does not name raises (the guard test
    enumerates every code each list can hold)."""
    return None if key is None else messages.name(kind, key)


# ── the reporting basis: the scenarios and horizons the platform computes, named ───────────────────────────────────

def basis_options() -> dict:
    """The scenario and horizon choices of a reporting basis — exactly the platform's own (core.types), with their
    names; a screen never types its own list."""
    from core.types import SCENARIO_VALUES, TIME_HORIZON_VALUES
    stops = messages.names().get("horizon.stop", {})
    return {"scenario": [{"value": s, "label": messages.name("scenario", s)} for s in SCENARIO_VALUES],
            "horizon": [{"value": h, "label": stops.get(h, h)} for h in TIME_HORIZON_VALUES]}


def check_basis(changes: dict) -> None:
    """Refuse a scenario or horizon the platform does not compute: one stored would leave every figure on it empty."""
    from core.types import SCENARIO_VALUES, TIME_HORIZON_VALUES
    if "scenario" in changes and changes["scenario"] not in SCENARIO_VALUES:
        raise UserError("admin.basis.bad_scenario")
    if "horizon" in changes and changes["horizon"] not in TIME_HORIZON_VALUES:
        raise UserError("admin.basis.bad_horizon")


def lei_refusal(lei: str, error: Exception, cls: type[UserError] = UserError) -> UserError:
    """Why an LEI was not stored, as a catalogue error: malformed, not in the registry, or the registry unreachable
    (services.reference.gleif.verified_lei raises one LeiError for all three; its cause tells them apart)."""
    from services.reference import gleif
    code = (lei or "").strip().upper()
    if not gleif.lei_check_digits_ok(code):
        return cls("admin.identity.invalid_lei", lei=code)
    if isinstance(error.__cause__, gleif.GleifError):
        return cls("admin.identity.lei_unverifiable", lei=code)     # refused, never stored unverified (E143)
    return cls("admin.identity.lei_not_found", lei=code)


# ── people, roles, permissions ─────────────────────────────────────────────────────────────────────────────────

def role_label(role: str, supervision_roles: Optional[dict] = None) -> str:
    """A role's name: the platform's (names.role), else a supervisory body's own (supervision_profiles.json)."""
    got = messages.names().get("role", {}).get(role)
    if got:
        return got
    if supervision_roles is None:
        from services.supervision.profiles import role_templates
        supervision_roles = role_templates()
    return (supervision_roles.get(role) or {}).get("label") or messages.name("role", role)


def permission_view(code: str, description: Optional[str]) -> dict:
    """A permission as the Roles tab shows it: its short name, its area and what it allows (its own description)."""
    return {"code": code, "name": messages.name("admin.permission", code),
            "area": messages.name("admin.permission_area", code.split(".")[0]), "description": description}


# ── the approval matrix ────────────────────────────────────────────────────────────────────────────────────────

# The changes an organisation sets its own approval rule for. The matrix also lists the platform's own rules (a crop
# calibration's publication, a reference release landing) on the platform operator's workspace: named, not settable.
POLICY_SETTABLE = frozenset({"supply.site.update", "supply.site.delete", "supply.plot.update", "supply.plot.delete",
                             "config.reporting_settings", "config.calc_settings", "config.kri_appetite", "risk.decision"})


def policy_actions() -> frozenset[str]:
    return POLICY_SETTABLE


def policy_label(action_key: str) -> str:
    return messages.name("admin.policy", action_key)


def material_view(fields: list[str]) -> list[dict]:
    return [{"key": f, "label": messages.name("admin.field", f)} for f in fields]


# ── the methodology choices ────────────────────────────────────────────────────────────────────────────────────

def _choice_names() -> dict:
    """An option's name: a methodology choice by names "filing.election", a scenario by its name, a dependence rule by
    names "dependence" — the same words a frozen filing prints its elections in (services.governance.filings)."""
    n = messages.names()
    return {**n.get("filing.election", {}), **n.get("scenario", {}), **n.get("dependence", {})}


def option_label(value) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    names = _choice_names()
    return names[value] if value in names else messages.name("filing.election", value)   # unnamed: raises


# A message code is dotted lower-case words (core/messages.check), so a switch whose key holds digits is named here.
SWITCH_CODE = {
    "orsa_scenario_below_2c": "orsa_below_two", "orsa_scenario_above_2c": "orsa_above_two",
    "taxonomy_2026_73_article_4": "taxonomy_first_year", "esrs_fy2026_version": "esrs_version",
    "p3esg_t1_emissions_estimation": "financed_emissions_scope", "p3esg_t1_attribution": "financed_emissions_attribution",
    "p3esg_t1_k_scope_1_2": "financed_emissions_share", "p3esg_t1_scope3_sector_average": "financed_emissions_sector_average",
}


def switch_code(key: str) -> str:
    return f"admin.switch.{SWITCH_CODE.get(key, key)}"


def switch_view(spec: dict) -> dict:
    """One interpretation choice for the Methodology tab: its catalogue message (name and explanation), its options
    named, and — for a Pillar 3 statement — the instructions it quotes."""
    key = spec["key"]
    about = messages.render(switch_code(key))
    out = {"key": key, "kind": spec["kind"], "default": spec["default"], "min": spec.get("min"), "max": spec.get("max"),
           "allowed": spec.get("allowed"), "name": about["label"], "about": about,
           "options": [{"value": v, "label": option_label(v)} for v in (spec.get("allowed") or [])]}
    if spec["kind"] == "int" and key == "pml_return_period":
        out["options"] = [{"value": v, "label": f"1-in-{v} years"} for v in spec.get("allowed") or []]
    if spec["kind"] == "enum" and not out["options"]:   # e.g. no curve family has passed its test yet
        out["no_option"] = messages.render("admin.methodology.no_option")
    law = _quoted_law(key)
    if law:
        out["law"] = law
    return out


def _quoted_law(key: str) -> list[str]:
    """The regulation text a Pillar 3 statement quotes (data/reference/pillar3/t1_financed_emissions.json)."""
    from services.governance import pillar3_t1
    st = pillar3_t1.reference()["statements"].get(key)
    return [pillar3_t1.quote(q) for q in st["quotes"]] if st else []


# ── tenants: kinds of organisation and what they are licensed to use ───────────────────────────────────────────

def sector_label(org_type: Optional[str]) -> Optional[str]:
    return name("admin.sector", org_type)


def report_name(framework: str | None) -> str | None:
    """A report in customer words with no legal reference on the main screen: the short names the KRI screens use
    (services.governance.kri), else the report's own name (services.governance.filings.FRAMEWORKS)."""
    if not framework:
        return None
    from services.governance.filings import FRAMEWORKS
    from services.governance.kri import _KRI_LABELS
    return _KRI_LABELS.get(framework) or (FRAMEWORKS.get(framework) or {}).get("label") \
        or messages.names()["admin.approval_value"].get(framework) or messages.label("admin.approvals.a_report")


def offering_view(offerings: list[str]) -> list[dict]:
    return [{"key": o, "label": messages.name("admin.offering", o)} for o in offerings]


# ── the stated method (web/src/components/MethodParameters.tsx) ──────────────────────────────────────────────────

_BAND_ORDER = {"L": 0, "M": 1, "H": 2, "VH": 3}       # bands low to severe, not by letter
# a breakdown's axes, in the order its members spell them ('flood/H', 'A01@baseline/2030')
_AXES = {"band": ["band"], "peril": ["peril"], "peril_band": ["peril", "band"], "epc_grade": ["epc"],
         "nace_division": ["division"], "scenario_horizon": ["scenario", "horizon"],
         "division_scenario_horizon": ["division", "scenario", "horizon"]}


def _axis_names(axis: str, values: list[str]) -> dict[str, str]:
    """Each value of a breakdown axis in customer words: perils by names.hazard, bands by names.admin.band, scenarios
    by names.scenario, horizons as today or the year, sectors by the NACE register, energy grades as they are."""
    n = messages.names()
    if axis == "peril":
        return {v: messages.name("admin.member", "any") if v == "any" else n["hazard"][v] for v in values}
    if axis == "band":
        return {v: n["admin.band"][v] for v in values}
    if axis == "scenario":
        return {v: n["scenario"][v] for v in values}
    if axis == "horizon":
        return {v: n.get("horizon.stop", {}).get(v, v) for v in values}
    if axis == "division":
        from services.reference import nace
        return {v: messages.name("admin.member", "any") if v == "any" else f"{nace.label(v)} ({v})" for v in values}
    return {v: v for v in values}            # an energy grade is its letter


def _split(breakdown: str, member: str) -> list[str]:
    if breakdown == "division_scenario_horizon":
        d, rest = member.split("@")
        return [d, *rest.split("/")]
    return member.split("/") if len(_AXES[breakdown]) > 1 else [member]


def method_view(datapoints: list[dict]) -> list[dict]:
    """The stated-method parameters named: each one's short name, its breakdown's axes with every value named, and
    what it is used for — the screen spells no code."""
    from services.money.params import parameters
    ps = parameters()
    out = []
    for dp in datapoints:
        p = ps[dp["key"]]
        b = dp.get("breakdown")
        axes = None
        if b:
            parts = [_split(b, m) for m in (dp.get("members") or {})]
            axes = [{"axis": a, "title": messages.name("admin.axis", a),
                     "names": _axis_names(a, sorted({x[i] for x in parts}, key=lambda v: (v != "any", _BAND_ORDER.get(v, 9), v)))}
                    for i, a in enumerate(_AXES[b])]
        out.append({**dp, "name": p["short"], "about": p["label"], "used_for": p.get("used_for"), "axes": axes})
    return out


def needed_view(needed: list[dict]) -> list[dict]:
    """The values the organisation's figures still need, named: the parameter's short name and, for a breakdown, the
    member in words."""
    from services.money.params import parameters
    ps = parameters()
    out = []
    for n in needed:
        p = ps.get(n["key"]) or {}
        member = n.get("member")
        b = p.get("breakdown")
        words = None
        if member and b:
            words = " · ".join(_axis_names(a, [v])[v] for a, v in zip(_AXES[b], _split(b, member)))
        out.append({**n, "name": p.get("short") or messages.name("admin.member", "parameter"), "member_label": words})
    return out
