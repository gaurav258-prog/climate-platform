"""The holdings look-through of the loss engine (the product owner's decisions of 2026-10-22). A fund holding is a share in
a company, never a building (E307): its loss is looked through to the issuer's located sites.

  A  issuers(session, org_id, ids)   the share of each issuer's physical value lost per year: over its sites whose weight
                                     counts as a share of its value, the sum of weight × the site's tested share lost —
                                     tested figures only, read through the one door (services.loss.figures.tested). Not
                                     carried: a held or untested figure, a gap, and a figure whose curve gives only a
                                     building's share (a flood curve: the share of a building's value, not of the site's
                                     buildings, plant and contents — decided 2026-10-22). Sites with a tested figure cover
                                     their weights' share of the issuer; the rest is counted by why (the rule of the
                                     tested-yearly-loss indicator: the sum of what is tested, the withheld counted).
  B  holdings(session, org_id, ids)  euros per year on each holding: A × the issuer's physical asset value × the holding's
                                     share of the issuer (its value ÷ the issuer's enterprise value) — both provided data;
                                     until provided, a named gap, never estimated.

Which weights count (decided 2026-10-22): a weight on the 'assets' basis is a share of the issuer's value; the
organisation may state, as a governed method choice, the other bases it accepts (interpretation switches
loss_site_weight_<basis>: revenue, production capacity, headcount) — not stated, those sites are a named gap. An 'equal'
weight states no measure and never counts. An issuer whose only site is its head-office proxy (services.reference.
footprint) has no physical site located: a named gap. Today's climate only (baseline, current), the engine's
issuer-sites book.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from services.loss import curves
from services.loss import figures as door

BOOK = "issuer_sites"
PERILS = ("flood", "storm")
VALUE_BASIS = "assets"                                     # a weight on this basis is a share of value, always
STATED_BASES = ("revenue", "production_capacity", "headcount")
COUNTS = "counts_as_value"                                # the switch value that accepts a basis
CARRIED_BASIS = "asset_value"                             # a curve whose share is of the site's whole physical value
TOLERANCE = 1e-9                                          # weights stored to six decimals; a sum above 1 + this is over


def switch(basis: str) -> str:
    return f"loss_site_weight_{basis}"


def accepted_bases(settings: dict) -> list[str]:
    return [VALUE_BASIS, *[b for b in STATED_BASES if settings.get(switch(b)) == COUNTS]]


def held_sites(session: Session, org_id: str) -> list[dict]:
    """The engine's assets for the issuer-sites book: every site of the issuers the organisation's funds hold at each
    fund's latest holdings date, the head-office proxy marked."""
    from services.reference.footprint import is_hq_proxy
    rows = session.execute(text("""
        SELECT DISTINCT f.facility_id::text AS asset_id, f.issuer_id::text AS issuer_id, f.latitude, f.longitude,
               f.country, f.facility_type AS asset_type, f.source
        FROM fund_positions p
        JOIN funds fu ON fu.fund_id = p.fund_id
        JOIN securities s ON s.security_id = p.security_id
        JOIN issuer_facilities f ON f.issuer_id = s.issuer_id
        WHERE fu.org_id = CAST(:o AS uuid)
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
        ORDER BY 1"""), {"o": org_id}).mappings()
    return [{**dict(r), "asset_kind": "issuer_site", "table": "issuer_facilities.facility_type", "occupancy": None,
             "value": None, "per_unit": True, "proxy": is_hq_proxy(r["source"], r["asset_type"])} for r in rows]


def _msg(code: str, **params) -> dict:
    r = messages.render(code, **params)
    return {"code": code, "label": r["label"], "detail": r["detail"]}


def _damage_basis(curve_key: str) -> Optional[str]:
    return (curves.families().get(curve_key.split(":")[0]) or {}).get("damage_basis")


def _lead(f: dict, headline: Optional[str]) -> Optional[dict]:
    """The share that leads (services.loss.signals.lead, on the share columns): a storm figure's; for flood, the figure
    the institution states leads. None for flood while not stated."""
    from services.loss.signals import lead
    return lead({"peril": f["peril"], "eal_eur": f["eal_ratio"], "eal_low_eur": f["eal_ratio_low"],
                 "eal_high_eur": f["eal_ratio_high"], "eal_defended_eur": f["eal_defended_ratio"],
                 "eal_defended_low_eur": f["eal_defended_ratio_low"],
                 "eal_defended_high_eur": f["eal_defended_ratio_high"]}, headline)


def _not_carried(item: dict) -> dict:
    if item["gap_code"]:
        return _msg(item["gap_code"], **(item["gap_params"] or {}))
    return _msg(f"lookthrough.site.{item['standing']}")


def _sites(session: Session, issuer_ids: list[str]) -> dict[str, list[dict]]:
    from services.reference.footprint import is_hq_proxy
    out: dict[str, list[dict]] = {i: [] for i in issuer_ids}
    for r in session.execute(text("""
            SELECT facility_id::text AS facility_id, issuer_id::text AS issuer_id, name, facility_type, country, region,
                   CAST(materiality_weight AS FLOAT) AS weight, weight_basis, source
            FROM issuer_facilities WHERE issuer_id = ANY(CAST(:ids AS uuid[]))
            ORDER BY issuer_id, materiality_weight DESC, facility_id"""), {"ids": issuer_ids}).mappings():
        out[r["issuer_id"]].append({**dict(r), "proxy": is_hq_proxy(r["source"], r["facility_type"])})
    return out


def _issuer(sites: list[dict], run: Optional[dict], accepted: list[str], headline: Optional[str]) -> dict:
    """One issuer's share lost per year (A), its sites, and why any part is missing."""
    out = {"share": None, "share_low": None, "share_high": None, "covered": None, "counted": None, "why": None,
           "sites": [], "hazards": {p: {"share": 0.0, "covered": 0.0} for p in PERILS}, "not_carried": {}}
    if not sites:
        return {**out, "why": _msg("lookthrough.gap.no_sites")}
    real = [s for s in sites if not s["proxy"]]
    if not real:
        return {**out, "why": _msg("lookthrough.gap.head_office_only")}
    if run is None:
        return {**out, "why": _msg("lookthrough.gap.no_run")}
    tested = {(f["asset_id"], f["peril"]): f for f in run["figures"]}
    withheld = {(w["asset_id"], w["peril"]): w for w in run["not_carried"]}
    total = {"central": 0.0, "low": 0.0, "high": 0.0}
    counted = covered = 0.0
    waiting = carried = False
    for s in real:
        counts = s["weight_basis"] in accepted
        site = {k: s[k] for k in ("facility_id", "name", "facility_type", "country", "region", "weight", "weight_basis")}
        site.update(counts=counts, why=None, hazards=[])
        if not counts:
            site["why"] = _msg("lookthrough.site.basis_not_accepted",
                               basis=messages.name("lookthrough.basis", s["weight_basis"]))
            out["not_carried"][site["why"]["code"]] = out["not_carried"].get(site["why"]["code"], 0) + 1
            out["sites"].append(site)
            continue
        counted += s["weight"]
        site_carried = False
        for p in PERILS:
            f = tested.get((s["facility_id"], p))
            h = {"peril": p, "share": None, "low": None, "high": None, "lead": None, "why": None}
            if f is None:
                w = withheld.get((s["facility_id"], p))
                h["why"] = _not_carried(w) if w else _msg("lookthrough.site.not_in_run")
            elif _damage_basis(f["curve_key"]) != CARRIED_BASIS:
                h["why"] = _msg("lookthrough.site.building_only")
            else:
                lf = _lead(f, headline)
                if lf is None:
                    waiting = True
                    h["why"] = _msg("lookthrough.site.flood_lead_not_stated")
                else:
                    h.update(share=lf["eur"], low=lf["low"], high=lf["high"], lead=lf["basis"])
                    for k, v in (("central", lf["eur"]), ("low", lf["low"]), ("high", lf["high"])):
                        total[k] += s["weight"] * v
                    out["hazards"][p]["share"] += s["weight"] * lf["eur"]
                    out["hazards"][p]["covered"] += s["weight"]
                    site_carried = carried = True
            if h["why"]:
                out["not_carried"][h["why"]["code"]] = out["not_carried"].get(h["why"]["code"], 0) + 1
            site["hazards"].append(h)
        covered += s["weight"] if site_carried else 0.0
        out["sites"].append(site)
    out.update(counted=counted, covered=covered)
    if not any(s["counts"] for s in out["sites"]):
        return {**out, "why": _msg("lookthrough.gap.no_weighted_site")}
    if counted > 1 + TOLERANCE:
        return {**out, "why": _msg("lookthrough.gap.weights_exceed", total=f"{counted:.0%}")}
    if waiting:                    # a sum without the flood figures waiting for the stated lead would understate it
        return {**out, "why": _msg("lookthrough.gap.flood_lead_not_stated")}
    if not carried:
        return {**out, "why": _msg("lookthrough.gap.no_tested_figure")}
    return {**out, "share": total["central"], "share_low": total["low"], "share_high": total["high"]}


def issuers(session: Session, org_id: str, issuer_ids: list[str]) -> dict:
    """{run_id, as_of, headline, accepted_bases, issuers: {issuer_id: A and its sites}} — today's climate."""
    from services.calc_settings import get_calc_settings
    settings = get_calc_settings(session, org_id)
    run = door.tested(session, org_id, BOOK)
    accepted = accepted_bases(settings)
    headline = settings.get("loss_flood_headline")
    ids = sorted(set(issuer_ids))
    sites = _sites(session, ids) if ids else {}
    return {"run_id": run and run["run_id"], "as_of": run and run["as_of"], "headline": headline,
            "accepted_bases": accepted,
            "issuers": {i: _issuer(sites.get(i, []), run, accepted, headline) for i in ids}}


def holdings(session: Session, org_id: str, fund_ids: list[str]) -> dict:
    """Each holding of the funds (at each fund's latest holdings date) with its issuer's share lost (A) and the euros a
    year on the holding (B), or why not; the funds' total over the holdings with a figure, and the value it covers. The
    issuer's enterprise value and physical asset value: its latest stated figures (services.issuer_figures.latest)."""
    from services.issuer_figures import latest
    rows = [dict(r) for r in session.execute(text(f"""
        SELECT p.position_id::text AS position_id, p.fund_id::text AS fund_id, s.isin, s.name AS security_name,
               i.issuer_id::text AS issuer_id, i.name AS issuer_name, CAST(p.market_value_eur AS FLOAT) AS mv,
               ev.v AS evic_eur, ev.y AS evic_year, pv.v AS physical_value_eur, pv.y AS physical_value_year
        FROM fund_positions p
        JOIN securities s ON s.security_id = p.security_id
        JOIN issuers i ON i.issuer_id = s.issuer_id
        LEFT JOIN LATERAL {latest("evic_eur", "i.issuer_id")} ev ON TRUE
        LEFT JOIN LATERAL {latest("physical_asset_value_eur", "i.issuer_id")} pv ON TRUE
        WHERE p.fund_id = ANY(CAST(:f AS uuid[]))
          AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
        ORDER BY p.market_value_eur DESC, p.position_id"""), {"org": org_id, "f": fund_ids}).mappings()]
    a = issuers(session, org_id, [r["issuer_id"] for r in rows])
    out, total, covered, why = [], {"central": 0.0, "low": 0.0, "high": 0.0}, 0.0, {}
    for r in rows:
        iss = a["issuers"][r["issuer_id"]]
        h = {**r, "share": iss["share"], "share_low": iss["share_low"], "share_high": iss["share_high"],
             "covered": iss["covered"], "eur": None, "eur_low": None, "eur_high": None, "holding_share": None,
             "why": iss["why"]}
        if h["why"] is None:
            h["why"] = _euros(h)
        if h["why"] is None:
            for k, key in (("central", "eur"), ("low", "eur_low"), ("high", "eur_high")):
                total[k] += h[key]
            covered += r["mv"]
        else:
            why[h["why"]["code"]] = {**h["why"], "count": why.get(h["why"]["code"], {}).get("count", 0) + 1}
        out.append(h)
    value = sum(r["mv"] for r in rows)
    return {"run_id": a["run_id"], "as_of": a["as_of"], "headline": a["headline"], "accepted_bases": a["accepted_bases"],
            "issuers": a["issuers"], "positions": out, "value_eur": value, "covered_value_eur": covered,
            "eur": total["central"] if covered else None, "eur_low": total["low"] if covered else None,
            "eur_high": total["high"] if covered else None,
            "why": sorted(why.values(), key=lambda w: -w["count"])}


def _euros(h: dict) -> Optional[dict]:
    """B on one holding, filled in place — or why not."""
    if h["physical_value_eur"] is None:
        return _msg("lookthrough.gap.no_physical_value")
    if not h["evic_eur"]:
        return _msg("lookthrough.gap.no_enterprise_value")
    part = h["mv"] / h["evic_eur"]
    if part > 1:                   # a holding larger than the whole company: the figures disagree, never capped
        return _msg("lookthrough.gap.holding_exceeds_company")
    h["holding_share"] = part
    for share, key in (("share", "eur"), ("share_low", "eur_low"), ("share_high", "eur_high")):
        h[key] = h[share] * h["physical_value_eur"] * part
    return None
