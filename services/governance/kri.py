"""Key Regulatory Indicator (KRI) dashboard — the regulator's-eye consolidated risk view.

One place for the headline physical-risk indicators of the book: how much value sits at or above the stated at-risk level, the
share of the book, coverage, financed emissions and taxonomy eligibility, plus the same figures over the
org's filed history so a trend is visible. Current figures come from the live engine (the same source the
disclosure uses); the history comes from the immutable filed snapshots, so the trend is auditable.
"""
from __future__ import annotations

import json
import re

from sqlalchemy import text
from sqlalchemy.orm import Session

# The money KRIs that are amounts PER YEAR (flows): a screen in another currency translates them at the average rate,
# every other money KRI (values, exposures, capital) at the closing rate — multi-currency decision 3.
FLOW_KRIS = frozenset({"eal", "expected_loss", "tested_yearly_loss", "fs.net_revenue", "e1.physrisk.revenue.amount"})


def _money_text(session: Session, org_id: str, v: float) -> str:
    """An engine (EUR) amount written into a hint, in the organisation's currency (closing rate)."""
    from services.governance.display_currency import balance, view
    return balance(v, view(session, org_id))


def _amount(v):
    """A KRI money value as computed — a gap stays None (shown as not computed), never 0."""
    return None if v is None else round(v)


def msg(code: str, **params) -> dict:
    """A KRI's explanation as a catalogue message (core/messages.py): its label for the screen, its detail for the drawer."""
    from core import messages
    return messages.render(code, **params)


def fact(key: str, value, unit: str) -> dict:
    """One fact behind a KRI, named in the catalogue's words (names['kri.fact']); the screen formats the value by its
    unit: eur (a balance), eur_flow (an amount per year), pct, num, bps, x (a ratio), text (written as it is)."""
    from core import messages
    return {"key": key, "label": messages.name("kri.fact", key), "value": value, "unit": unit}


_METHOD_KEY = re.compile(r"\bmethod\.[a-z0-9_]+")


def method_gap(*texts: str | None) -> str | None:
    """The method choices a gap names, in the one format the screens read ('not stated: method.a, method.b' — web
    lib/methodGap.ts), from any engine's gap text; None when it names none."""
    keys = sorted({k for t in texts if t for k in _METHOD_KEY.findall(t)})
    return ("not stated: " + ", ".join(keys)) if keys else None


def _kpi(key, label, value, fmt, tone=None, about=None, integrated=False, needs=None, facts=None, gap=None, missing=None):
    # `integrated` = a regulator datapoint whose value comes from OUTSIDE this engine (e.g. GHG from the
    # customer's carbon tool, or Taxonomy alignment flags) — shown honestly rather than fabricated or blanked.
    # `kind` makes the data provenance explicit for the dashboard's computed-vs-integrated legend/filter.
    # It mirrors the canonical datapoint catalog's `coverage_source(lane)`: our engine + processed uploads
    # (compute/granular) → "computed"; a pre-calculated value the customer/vendor brings in (provided) →
    # "integrated".
    # The words are the catalogue's (UI standard, 2026-10-16): `about` says what the figure is and how it is computed,
    # `needs` what a provided figure is waiting for, `missing` why a computed one is not shown, `gap` the method choices
    # it waits for (the screens name them), `facts` the numbers behind it. `hint` and `integrated_note` carry the same
    # words as plain text for the readers that print one line (board pack, supervisor questions).
    return {"key": key, "label": label, "value": value, "fmt": fmt, "tone": tone,
            "about": about, "hint": (about or {}).get("detail", {}).get("what"),
            "integrated": integrated, "needs": needs, "integrated_note": needs["label"] if needs else None,
            "kind": "integrated" if integrated else "computed", "facts": facts or [], "gap": gap, "missing": missing,
            **({"flow": key in FLOW_KRIS} if fmt == "eur" else {})}


# the frameworks with a KRI builder, and their short picker labels (one org-type can report several), in the words
# customers use for the report — its article lives in the regulator view, one click away (UI standard, 2026-10-18)
# (each set is anchored on its governed report — the bank's in services.governance.kri_bank, the REIT / insurer /
# asset-manager sets in services.governance.kri_sectors)
_KRI_LABELS = {"bank_tcfd": "EU Taxonomy", "bank_p3esg": "Pillar 3 ESG", "sfdr_pai": "SFDR adverse impacts",
               "reit_taxonomy": "EU Taxonomy", "insurer_solvency": "Solvency II nat-cat",
               "esrs_pack": "ESRS statement"}


def kri_frameworks(org_type: str | None) -> list[dict]:
    """The KRI frameworks an org-type can report on — the picker options on the KRI dashboard."""
    from services.governance.filings import available_frameworks
    return [{"framework": f["framework"], "label": _KRI_LABELS[f["framework"]]}
            for f in available_frameworks(org_type or "") if f["framework"] in _KRI_LABELS]


def framework_name(framework: str) -> str:
    """A KRI set's report in the customer's words (a task, a notification), never its code."""
    return _KRI_LABELS.get(framework, "this report")


def kri(session: Session, org_id: str, framework: str, entity_id: str | None = None, role: str | None = None) -> dict:
    """entity_id: the undertaking an ESRS KRI set is for (services.governance.kri_esrs.undertaking); for a report with
    filer rules, the filer whose book the set is on, with its role where one entity holds two reports (kri_scope — the
    board's own filer when None). Other sets are the organisation's book."""
    return _build(session, org_id, framework, entity_id, role)[0]


def appetite_set(session: Session, org_id: str, framework: str) -> dict:
    """The indicators a report's appetite bands are set for (Settings → KRI appetite): the board's own set; while the
    report has no one filer to show (kri_scope.NoFiler), its indicators listed without a value — a band is set per report,
    whoever files it, and no figure is shown that is no filer's (E351)."""
    data = kri(session, org_id, framework)
    if data.get("supported") or "filers" not in data:
        return data
    result, _ = _build(session, org_id, framework, None, None, whole_book=True)
    for k in result.get("kpis") or []:
        k.update(value=None, status=None, breached=False, facts=[])
    return {**result, "breaches": 0, "notice": data["notice"]}


def _build(session: Session, org_id: str, framework: str, entity_id: str | None, role: str | None,
           whole_book: bool = False) -> tuple[dict, object]:
    """The KRI set and the filer scope it is on (None: the whole book — whole_book forces it, for appetite_set only)."""
    from services.governance import kri_scope
    scope = None
    if framework != "esrs_pack" and not whole_book:
        try:
            scope = kri_scope.resolve(session, org_id, framework, entity_id, role)
        except kri_scope.NoFiler as e:
            return {"framework": framework, "supported": False, "notice": e.notice, "message": e.notice["label"],
                    "filers": e.filers}, None
    if framework == "bank_tcfd":                       # anchored on the report each set belongs to (kri_bank, E95)
        from services.governance.kri_bank import taxonomy_kri
        result = taxonomy_kri(session, org_id, scope)
    elif framework == "bank_p3esg":
        from services.governance.kri_bank import pillar3_kri
        result = pillar3_kri(session, org_id, scope)
    elif framework == "sfdr_pai":
        from services.governance.kri_sectors import holdings_kpis, sfdr_kri
        result = sfdr_kri(session, org_id)
        held, by_hazard = holdings_kpis(session, org_id)          # the holdings book's KRIs: live only
        result["kpis"] = result["kpis"] + held
        result["by_hazard"] = result.get("by_hazard") or by_hazard
    elif framework == "reit_taxonomy":
        from services.governance.kri_sectors import reit_kri
        result = reit_kri(session, org_id, scope)
    elif framework == "insurer_solvency":
        from services.governance.kri_sectors import insurer_kri
        result = insurer_kri(session, org_id, scope)
    elif framework == "esrs_pack":
        from services.governance import kri_esrs
        result = kri_esrs.build(session, org_id, entity_id)
    else:
        n = msg("kri.unsupported")
        return {"framework": framework, "supported": False, "notice": n, "message": n["label"]}, None
    kri_scope.eur_only(result.get("history") or [])
    if scope is not None:                              # whose book: the filer, the others to choose from (E351)
        result.update(filer=scope.filer, filers=scope.filers, scope=kri_scope.message(scope))
    # grade every KPI against the org's appetite bands → green / amber / red (a monitored control, not a number)
    if result.get("supported") and result.get("kpis"):
        from services.governance import kri_regmap, kri_thresholds
        kri_thresholds.apply(session, org_id, result["framework"], result["kpis"])
        result["breaches"] = sum(1 for k in result["kpis"] if k.get("breached"))
        # regulator framing: name the supervisor/disclosure, tag each KRI with the datapoint it feeds, and
        # summarise submission-readiness (which core datapoints the regulator expects are covered)
        result["regulator"] = kri_regmap.regulator(result["framework"])
        result["readiness"] = kri_regmap.annotate(result["framework"], result["kpis"])
        # Fixed 2026-09-24 (platform-wide E2E audit finding #5, confirmed independently across bank,
        # insurer, agri and asset-manager KRI): the KPI cards above are live-recomputed from the CURRENT
        # book/basis on every call, not read from the last filed snapshot — only `history` reads frozen
        # data (this module's own docstring already disclosed the design in code, but nothing on the
        # dashboard itself said so). A viewer could read a live number as "what we told the regulator" when
        # it may have moved since. Surface it explicitly rather than silently — never hide the distinction.
        hist = result.get("history") or []
        basis = msg("kri.basis.live")
        result["basis"] = {
            "kpis": "live", "message": basis, "note": basis["detail"]["what"],
            "last_filed": ({"period_label": hist[-1]["label"], "filing_id": hist[-1]["filing_id"]}
                           if hist else None),
        }
        if scope is not None:                          # the basis line names whose figures they are
            result["basis"]["filer"] = result["scope"]
    return result, scope


def _by_hazard(snap: dict) -> list[dict]:
    return sorted([{"hazard": h, "value": b.get("exposed_value_eur", 0), "score": b.get("max_score", 0)}
                   for h, b in (snap.get("by_hazard") or {}).items() if (b.get("exposed_value_eur") or 0) > 0],
                  key=lambda x: -x["value"])


# noun per framework for the hazard drill
_NOUN = {"bank_tcfd": "assets", "bank_p3esg": "assets", "reit_taxonomy": "properties", "insurer_solvency": "policies",
         "sfdr_pai": "holdings"}


def _live_snapshot(session: Session, org_id: str, framework: str, scenario: str, horizon: str, scope=None) -> dict:
    """The live book a KRI set reads: the whole organisation's, or one filer's (kri_scope.Scope — its filing's book)."""
    if framework in ("bank_tcfd", "bank_p3esg"):
        from api.routers.bank import build_disclosure_snapshot
    elif framework == "reit_taxonomy":
        from api.routers.realestate import build_disclosure_snapshot
    elif framework == "insurer_solvency":
        from api.routers.insurance import build_disclosure_snapshot
    elif framework == "sfdr_pai":                       # the holdings book behind the asset manager's live KRIs
        from api.routers.assetmgmt import build_disclosure_snapshot
    else:
        return {}
    return build_disclosure_snapshot(session, org_id, scenario, horizon, **(scope.book() if scope is not None else {}))


def kri_hazard(session: Session, org_id: str, framework: str, hazard: str, entity_id: str | None = None,
               role: str | None = None) -> dict:
    """The entities contributing a hazard's exposure (live) — the drill under a KRI by-hazard bar, on the book the set
    is on (one filer's, kri_scope)."""
    from services.governance import kri_scope
    from services.governance.filing_lineage import _LIST_CFG
    from services.governance.reporting_settings import get_settings
    s = get_settings(session, org_id)
    cfg = _LIST_CFG.get("assetmgmt_tcfd" if framework == "sfdr_pai" else framework)   # sfdr_pai: its holdings book
    if cfg:
        try:
            scope = kri_scope.resolve(session, org_id, framework, entity_id, role)
        except kri_scope.NoFiler as e:
            return {"supported": False, "hazard": hazard, "entities": [], "notice": e.notice}
        snap = _live_snapshot(session, org_id, framework, s["scenario"], s["horizon"], scope)
        from services.governance.pillar3_templates import hazard_hit, stated_level
        level = stated_level(snap)
        if level is None:
            return {"supported": True, "hazard": hazard, "noun": _NOUN.get(framework, "items"), "entities": [],
                    "method_gap": method_gap("method.at_risk_level")}
        ents = []
        for e in snap.get(cfg["list"], []):
            hz = next((h for h in e.get("hazards", []) if h.get("hazard") == hazard and hazard_hit(h, level)), None)
            if hz:
                ents.append({"name": e.get(cfg["name"]), "value": e.get(cfg["value"]),
                             "h3_cell": e.get("h3_cell"), "country": e.get("country"), "score": hz.get("score")})
        ents.sort(key=lambda x: -(x["value"] or 0))
        return {"supported": True, "hazard": hazard, "noun": _NOUN.get(framework, "items"), "entities": ents[:100]}
    if framework == "esrs_pack":
        from services.governance import kri_esrs
        return {"supported": True, "hazard": hazard, "noun": "own sites (short term, carrying amount)",
                "entities": kri_esrs.hazard_sites(session, org_id, hazard, entity_id)[:100]}
    return {"supported": False, "hazard": hazard, "entities": []}


# ── KRI drill-down: the underlying data + methodology + trend + composition behind one KRI ──────────────
# Exposure KRIs decompose by hazard; the rest by their own natural breakdown (emissions by scope, coverage
# scored/unscored, taxonomy eligible/not). Everything here is derived from the SAME live snapshot the KRI
# tile is computed from — no separate or fabricated data.
_EXPOSURE_KEYS = {"total_value", "value_at_risk", "pct_at_risk", "sum_insured", "eal", "value_exposed",
                  "e1.physrisk.assets.amount", "e1.physrisk.assets.pct"}           # the ESRS ones: kri_esrs.EXPOSURE
_HIST_FIELD = {"total_value": "total_value", "value_at_risk": "value_at_risk", "pct_at_risk": "pct_at_risk"}


def _esrs_hist(key: str) -> str | None:
    from services.governance.kri_esrs import HISTORY
    return HISTORY.get(key)


# forward-looking + physical-split KRIs also earn the "explore forward in Analytics" action
_FORWARD_KEYS = {"forward_share", "acute_share", "chronic_share"}

def _filed_value(h: dict, kri_key: str, hf: str | None):
    """A KRI's value in one filed period: the legacy history slot, or the figure the anchor report printed."""
    if hf and h.get(hf) is not None:
        return h.get(hf)
    return next((f["value"] for f in h.get("figures") or [] if f["key"] == kri_key), None)


def kri_detail(session: Session, org_id: str, framework: str, kri_key: str, entity_id: str | None = None,
               role: str | None = None) -> dict:
    """The drill behind one KRI tile: the tile itself (value, appetite, provenance, regulator datapoint, and its
    catalogue explanation `about`), its trend across filed history where tracked, and its composition
    (by-hazard / by-scope / scored-unscored / eligible-not) — all from the same live snapshot."""
    result, scope = _build(session, org_id, framework, entity_id, role)
    if not result.get("supported"):
        n = result.get("notice") or msg("kri.unsupported")
        return {"supported": False, "notice": n, "message": n["label"]}
    kpi = next((k for k in result.get("kpis", []) if k["key"] == kri_key), None)
    if not kpi:
        n = msg("kri.unknown_indicator")
        return {"supported": False, "notice": n, "message": n["label"]}
    hf = _HIST_FIELD.get(kri_key) or (_esrs_hist(kri_key) if framework == "esrs_pack" else None)
    trend = [{"label": h["label"], "value": _filed_value(h, kri_key, hf), "filing_id": h.get("filing_id")}
             for h in (result.get("history") or []) if _filed_value(h, kri_key, hf) is not None]
    if kpi.get("live_only"):                          # no governed report prints it: no filed trend (E87)
        trend = []
    return {
        "supported": True, "framework": framework, "kpi": kpi,
        "regulator": result.get("regulator"),
        "trend": {"points": trend, "fmt": kpi.get("fmt"), "flow": bool(kpi.get("flow"))},
        "projection": _kri_projection(session, org_id, framework, kri_key, kpi, scope),
        "composition": _kri_composition(session, org_id, framework, kri_key, result, scope),
        "drivers": _kri_drivers(session, org_id, framework, kri_key, scope=scope),
        "actions": {
            "analytics": (kri_key in _EXPOSURE_KEYS or kri_key in _FORWARD_KEYS) and framework in ("bank_tcfd", "bank_p3esg", "reit_taxonomy"),
            "provide": kpi.get("kind") == "integrated",
        },
    }


def _hazard_name(h: str) -> str:
    """A hazard in the screens' own words (names['hazard'] of the catalogue)."""
    from core import messages
    return messages.name("hazard", h)


def _snapshot_history(session: Session, org_id: str, framework: str, scope=None) -> list[dict]:
    """The report's filings in period order, each with its frozen book and the currency it presents: every filing, or —
    on a filer's scope (kri_scope) — that filer's only (E351)."""
    from services.governance.kri_scope import history_filter
    from services.governance.money_format import presentation_of
    where, params = history_filter(scope)
    rows = session.execute(text(f"""
        SELECT rs.version, rs.reporting_basis, rs.payload, rf.period_label, rf.filing_id::text AS filing_id
        FROM report_snapshots rs
        JOIN regulatory_filing rf ON rf.snapshot_id = rs.snapshot_id
        WHERE rs.org_id = :o AND rs.report_type = :fw{where}
        ORDER BY rf.period_end, rs.version
    """), {"o": org_id, "fw": framework, **params}).mappings().all()
    out = []
    for r in rows:
        p = r["payload"]
        if isinstance(p, str):
            p = json.loads(p)
        out.append({"label": f'{r["period_label"]} v{r["version"]}', "payload": p, "filing_id": r["filing_id"],
                    "currency": presentation_of(p)})
    return out


# the drill behind one KRI (projection, drivers, composition) — its own module; kept importable from here
from services.governance.kri_drill import (  # noqa: E402,F401
    _kri_composition,
    _kri_drivers,
    _kri_projection,
)
