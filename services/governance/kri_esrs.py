"""The ESRS KRIs — the headline figures of one undertaking's ESRS statement for the financial year, read from the
statement itself (services.governance.esrs_statement.compute and the undertaking's attested figures, provided values
family 'esrs'), never from another model:

  computed   the figures the platform computes (E1 assets and net revenue at material physical risk), short term as the
             value, the medium and long term in the hint; a gap is shown as a gap, never a zero
  stated     the undertaking's own attested figures (GHG, water, sites in or near biodiversity-sensitive areas, the
             financial-statement totals) — 'integrated': the platform does not compute them
  derived    the ratios the standards define, from the attested figures
  support    facts the platform supplies for an undertaking's own figure (sites in areas of water stress as the version
             defines them; sites inside a listed biodiversity-sensitive area) — each shown only with the figure it supports

Only concepts the governing version prints are shown (esrs_binding.concepts_of): the 2026 standards drop, among others,
the share of total assets at physical risk and the E4 site count. Each KRI is tagged with the item(s) that print it.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

# (concept, tier) in reading order; a KRI key is its concept (a derived pair: concept@member)
HEADLINE = (
    ("fs.total_assets", "support"), ("e1.physrisk.assets.amount", "core"), ("e1.physrisk.assets.pct", "core"),
    ("e1.physrisk.assets.acute", "core"), ("e1.physrisk.assets.chronic", "core"),
    ("e1.physrisk.assets.addressed_pct", "core"), ("e1.physrisk.assets.addressed_pct.v2026", "core"),
    ("fs.net_revenue", "support"), ("e1.physrisk.revenue.amount", "core"), ("e1.physrisk.revenue.pct", "core"),
    ("e1.ghg.scope1.gross", "core"), ("e1.ghg.scope2.location", "core"), ("e1.ghg.scope2.market", "core"),
    ("e1.ghg.scope3.total", "core"), ("e1.ghg.total.location", "core"), ("e1.ghg.total.market", "core"),
    ("e1.ghg.intensity_net_revenue", "core"),
    ("e3.water.consumption", "core"), ("e3.water.consumption_at_risk", "core"),
    ("e3.water.consumption_at_risk.v2026", "core"), ("e3.water.intensity", "core"),
    ("e4.sites.sensitive.count", "core"),
)
EXPOSURE = ("e1.physrisk.assets.amount", "e1.physrisk.assets.pct")      # broken down by hazard
FLOWS = frozenset({"fs.net_revenue", "e1.physrisk.revenue.amount"})
HISTORY = {"fs.total_assets": "total_value", "e1.physrisk.assets.amount": "value_at_risk", "e1.physrisk.assets.pct": "pct_at_risk"}
_FMT = {"monetary": "eur", "percent": "pct", "tCO2eq": "num", "m3": "num", "count": "num"}


class NoUndertaking(ValueError):
    """No single undertaking to show: the organisation has legal entities and none, or several, has a stated role. Its
    `notice` says which, in the catalogue's words (kri.esrs.*)."""

    def __init__(self, code: str, undertakings: list[dict], **params):
        from core import messages
        super().__init__(code)
        self.notice = messages.render(code, **params)
        self.undertakings = undertakings


def undertakings(session: Session, org_id: str, period_end: date) -> list[dict]:
    """The undertakings with a stated CSRD role for the year in which they prepare a statement (individual, group)."""
    rows = session.execute(text("""
        SELECT r.reporting_entity_id::text AS entity_id, e.name, r.role FROM v_csrd_reporting_role_live r
        JOIN reporting_entities e ON e.entity_id = r.reporting_entity_id
        WHERE r.org_id = CAST(:o AS uuid) AND r.period_end = CAST(:pe AS date) AND r.role IN ('individual', 'consolidated')
        ORDER BY e.name
    """), {"o": org_id, "pe": period_end}).mappings().all()
    return [dict(r) for r in rows]


def undertaking(session: Session, org_id: str, period_end: date, entity_id: str | None) -> dict:
    """The undertaking the KRIs are for: the one named; else the organisation when it has no legal entities; else the
    only one with a stated statement role for the year (NoUndertaking when there is none, or a choice)."""
    if entity_id:
        name = session.execute(text("SELECT name FROM reporting_entities WHERE org_id = CAST(:o AS uuid) AND entity_id = CAST(:e AS uuid)"),
                               {"o": org_id, "e": entity_id}).scalar()
        if name is None:
            raise NoUndertaking("kri.esrs.not_found", [])
        return {"entity_id": entity_id, "name": name}
    has = session.execute(text("SELECT 1 FROM reporting_entities WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": org_id}).first()
    if not has:
        return {"entity_id": None, "name": session.execute(text("SELECT name FROM organizations WHERE org_id = CAST(:o AS uuid)"),
                                                           {"o": org_id}).scalar()}
    us = undertakings(session, org_id, period_end)
    if len(us) == 1:
        return {"entity_id": us[0]["entity_id"], "name": us[0]["name"]}
    raise NoUndertaking("kri.esrs.choose" if us else "kri.esrs.no_role", us, year=f"FY{period_end.year}")


def _printed_by(version: str) -> dict[str, list[str]]:
    from services.governance.esrs_binding import binding
    out: dict[str, list[str]] = {}
    for k, t in binding(version).items():
        for c in (t["same_as"] if isinstance(t, dict) else [t]):
            out.setdefault(c, []).append(k.split(":")[0])
    return out


# the catalogue's explanation of each computed concept (kri.indicator.esrs_*): the carrying amounts, the share of them
# addressed by adaptation actions, or the net revenue at material physical risk
COMPUTED_ABOUT = {
    "e1.physrisk.assets.amount": "esrs_assets", "e1.physrisk.assets.pct": "esrs_assets", "e1.physrisk.assets.acute": "esrs_assets",
    "e1.physrisk.assets.chronic": "esrs_assets", "e1.physrisk.assets.addressed_pct": "esrs_addressed",
    "e1.physrisk.assets.addressed_pct.v2026": "esrs_addressed", "e1.physrisk.revenue.amount": "esrs_revenue",
    "e1.physrisk.revenue.pct": "esrs_revenue",
}


def _unit_words(unit: str) -> str:
    """A derived ratio's unit in words ('tCO2eq/EUR' → 'tonnes of CO₂ equivalent per EUR'): each part from the catalogue
    (names['kri.unit']); a currency code is its own name."""
    from core import messages
    names = messages.names().get("kri.unit", {})
    num, _, den = unit.partition("/")
    return names.get(num, num) + (f" per {names.get(den, den)}" if den else "")


def build(session: Session, org_id: str, entity_id: str | None = None) -> dict:
    from services.governance import esrs_document as D
    from services.governance import esrs_statement
    from services.governance.esrs_binding import concepts, concepts_of
    from services.governance.filings import reporting_period_end
    from services.governance.kri import _kpi, fact, msg
    pe = reporting_period_end(session, org_id)
    try:
        spec = D.governing(session, org_id, pe)
        who = undertaking(session, org_id, pe, entity_id)
    except D.DocumentError:
        n = msg("kri.esrs.no_version", period_end=pe.isoformat())
        return {"framework": "esrs_pack", "supported": False, "notice": n, "message": n["label"]}
    except NoUndertaking as e:
        return {"framework": "esrs_pack", "supported": False, "notice": e.notice, "message": e.notice["label"],
                "undertakings": e.undertakings}
    eid = who["entity_id"]
    st = esrs_statement.compute(session, org_id, entity_id=eid, period_end=pe, esrs_version=spec["version"])
    provided = D._provided(session, org_id, eid, pe)
    material = (D.answers(session, org_id, eid, pe).get("materiality") or {})
    cs, printed, by = concepts(), concepts_of(spec), _printed_by(spec["version"])

    def reg(c):
        items = by.get(c)
        return (f"ESRS {', '.join(sorted(set(items)))} — {cs[c]['label']}" if items
                else f"Input of the ESRS figures — {cs[c].get('why') or cs[c]['label']}")

    def not_material(c):
        t = material.get(c.split(".")[0].upper())
        return bool(t and t.get("material") is False)

    def gap(v):                    # the statement names each missing fact on its own page; here, that some are missing
        return msg("kri.esrs.gap") if v.get("gap") else None

    kpis = []
    for c, tier in HEADLINE:
        if c not in printed:
            continue
        d, fmt = cs[c], _FMT.get(cs[c]["unit"], "dec")
        topic = msg("kri.esrs.not_material") if not_material(c) else None
        if d["lane"] == "computed":
            v = st["concepts"].get(c) or {}
            bh = v.get("by_horizon") or {}
            unit = "eur" if fmt == "eur" else "pct" if fmt == "pct" else "num"
            later = [fact(f"{h}_term", bh.get(h), unit) for h in ("medium", "long") if h in bh]
            k = _kpi(c, d["label"], v.get("value"), fmt, about=msg(f"kri.indicator.{COMPUTED_ABOUT[c]}", concept=d["label"]),
                     facts=later, missing=topic or gap(v))
        elif d["lane"] == "derived":
            v = st["concepts"].get(c) or {}
            vals = v.get("value") if isinstance(v.get("value"), dict) else {None: v.get("value")}
            unit = _unit_words(v.get("unit") or d["unit"])
            inputs = " and ".join(cs[x]["label"].lower() for x in d.get("from") or [] if x in cs)
            for member, x in vals.items():
                key = c + (f"@{member}" if member else "")
                label = d["label"] + (f" ({member}-based)" if member else "")
                k = _kpi(key, label, x, "dec", about=msg("kri.indicator.esrs_derived", concept=d["label"], inputs=inputs, unit=unit),
                         missing=topic or gap(v))
                kpis.append(k | {"reg": reg(c), "reg_tier": tier})
            continue
        else:
            p = provided.get(c)
            val = None if p is None else (p["value_eur"] if fmt == "eur" and p.get("currency") else p["value"])
            k = _kpi(c, d["label"], val, fmt, integrated=True, about=msg("kri.indicator.esrs_stated", concept=d["label"]),
                     needs=msg("kri.provide.undertaking") if p is None else None, missing=topic)
        kpis.append(k | {"reg": reg(c), "reg_tier": tier, **({"flow": True} if c in FLOWS else {})})
    kpis += _support(st, printed)
    scope = msg("kri.esrs.scope", name=who["name"], period_end=pe.isoformat(), act=spec["act"]["short"])
    return {"framework": "esrs_pack", "supported": True,
            "label": f"ESRS statement indicators — {who['name']} · FY{pe.year}", "kpis": kpis,
            "by_hazard": _by_hazard(st), "history": _history(session, org_id, eid),
            "undertaking": {**who, "period_end": pe.isoformat(), "esrs_version": spec["version"], "act": spec["act"]["short"]},
            "undertakings": undertakings(session, org_id, pe),
            "scope": scope, "scope_note": scope["detail"]["what"]}


def _support(st: dict, printed: set) -> list[dict]:
    from services.governance.kri import _kpi, fact, msg
    out = []
    unscored = (st.get("assessment") or {}).get("unscored_sites") or []
    out.append(_kpi("support.e1.unscored_sites", "Own sites in scope without a climate hazard score", len(unscored), "num",
                    about=msg("kri.indicator.esrs_unscored_sites"),
                    facts=[fact("sites_unscored", ", ".join(unscored), "text")] if unscored else [])
               | {"reg": "Supports ESRS E1 physical risk", "reg_tier": "support"})
    if printed & {"e3.water.consumption_at_risk", "e3.water.consumption_at_risk.v2026"}:
        w = (st.get("support") or {}).get("water_stress") or {}
        sites = w.get("sites") or []
        in_area = [s["name"] for s in sites if s.get("in_area") is True]
        open_ = [s["name"] for s in sites if s.get("in_area") is None]
        term = (w.get("definition") or {}).get("term") or "areas of water stress"
        out.append(_kpi("support.e3.sites_water_stress", f"Own sites in {term}", len(in_area), "num",
                        about=msg("kri.indicator.esrs_water_stress_sites", definition=(w.get("definition") or {}).get("ref") or term),
                        facts=[fact("sites_unclassified", ", ".join(open_), "text")] if open_ else []) |
                   {"reg": "Supports ESRS E3 water consumption in areas at water risk / with water stress", "reg_tier": "support"})
    if "e4.sites.sensitive.count" in printed:
        b = (st.get("support") or {}).get("biodiversity_sensitive") or {}
        out.append(_kpi("support.e4.sites_in_sensitive", "Own sites inside a listed biodiversity-sensitive area",
                        len(b.get("sites") or []), "num", about=msg("kri.indicator.esrs_sensitive_sites"),
                        facts=[fact("layers_missing", ", ".join(b["not_assessed"]), "text")] if b.get("not_assessed") else []) |
                   {"reg": "Supports ESRS E4 sites in or near biodiversity-sensitive areas (the undertaking's figure)",
                    "reg_tier": "support"})
    return out


def _by_hazard(st: dict) -> list[dict]:
    """The carrying amount at material physical risk in the short term, by hazard (a site counts under each hazard
    material at it)."""
    agg: dict[str, dict] = {}
    for s in st.get("sites") or []:
        r = (s.get("risk") or {}).get("short") or {}
        for h in r.get("material") or []:
            g = agg.setdefault(h, {"value": 0.0, "score": 0.0})
            g["value"] += (s.get("carrying") or 0) * (s.get("weight") or 0)
            g["score"] = max(g["score"], (r.get("scores") or {}).get(h) or 0)
    return sorted(({"hazard": h, "value": round(v["value"]), "score": round(v["score"], 1)} for h, v in agg.items()),
                  key=lambda x: -x["value"])


def hazard_sites(session: Session, org_id: str, hazard: str, entity_id: str | None = None) -> list[dict]:
    """The undertaking's sites at which a hazard is material in the short term (the drill under a hazard bar)."""
    from services.governance import esrs_document as D
    from services.governance import esrs_statement
    from services.governance.filings import reporting_period_end
    pe = reporting_period_end(session, org_id)
    try:
        spec = D.governing(session, org_id, pe)
        eid = undertaking(session, org_id, pe, entity_id)["entity_id"]
    except (D.DocumentError, NoUndertaking):
        return []
    st = esrs_statement.compute(session, org_id, entity_id=eid, period_end=pe, esrs_version=spec["version"])
    out = []
    for s in st["sites"]:
        r = s["risk"].get("short") or {}
        if hazard in (r.get("material") or []):
            out.append({"name": s["name"], "value": round((s["carrying"] or 0) * s["weight"]), "h3_cell": None,
                        "country": None, "score": (r.get("scores") or {}).get(hazard)})
    return sorted(out, key=lambda x: -(x["value"] or 0))


def _history(session: Session, org_id: str, entity_id: str | None) -> list[dict]:
    """The figures as filed: each ESRS statement filing of this undertaking, in period order."""
    from services.governance.kri import _snapshot_history
    out = []
    for h in _snapshot_history(session, org_id, "esrs_pack"):
        doc = (h["payload"] or {}).get("document_report") or {}
        if doc.get("reporting_entity_id") != entity_id:
            continue
        c = (doc.get("statement") or {}).get("concepts") or {}
        ta = (doc.get("provided") or {}).get("fs.total_assets") or {}
        out.append({"label": h["label"], "filing_id": h["filing_id"],
                    "total_value": ta.get("value_eur") if ta.get("currency") else ta.get("value"),
                    "value_at_risk": (c.get("e1.physrisk.assets.amount") or {}).get("value"),
                    "pct_at_risk": (c.get("e1.physrisk.assets.pct") or {}).get("value")})
    return out
