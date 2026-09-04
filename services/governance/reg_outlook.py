"""Regulatory outlook — the CUSTOMER's view of the regulation itself.

Strictly customer point-of-view: what applies to you today, what regulatory changes are coming (and when),
and whether YOU will need to provide new data or an integration. It says nothing about Tellumen's own build
process — that internal delivery pipeline lives elsewhere. Dates and citations are real; where a change is
proposed but not final, it says so rather than inventing a date.
"""
from __future__ import annotations

from services.governance.filings import FRAMEWORKS
from services.governance.reg_reference import REFERENCE

# Curated, real upcoming regulatory changes — customer-framed. `date` is the exact effective/application date
# FROM the cited Official-Journal text where the regulation legally fixes one (ISO, the nearest milestone);
# it is None only where the regulator has genuinely not set a date (a live proposal or a jurisdiction-by-
# jurisdiction adoption) — we never invent one. `when` is the human label (with the exact date when fixed, and
# any secondary milestone). `prepare` is what the CUSTOMER must ready (new data / integration) or None.
_EURLEX = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:"
COMING: list[dict] = [
    {"sectors": ["manufacturer"], "framework": "eudr_dds", "affects": ["eudr_dds"], "title": "EUDR obligations take effect",
     "date": "2026-12-30", "when": "30 Dec 2026 · large operators & traders (SMEs 30 Jun 2027)",
     "whats_changing": "Due-diligence and Due-Diligence-Statement submission become mandatory for in-scope commodities placed on the EU market.",
     "prepare": "Geolocation polygons for every covered plot, plus legality evidence.",
     "data_fields": [
         {"key": "eudr_geoloc", "field": "Plot geolocation — polygon vertices (lat/long), or a point for plots ≤ 4 ha", "note": "WGS-84; ≥ 6 decimal places"},
         {"key": "eudr_commodity_hs", "field": "Commodity + HS code, and production quantity", "note": "per plot / batch"},
         {"key": "eudr_country", "field": "Country & region of production", "note": "ISO country + sub-national area"},
         {"key": "eudr_production_date", "field": "Production date or time window", "note": "harvest / placing-on-market date"},
         {"key": "eudr_legality", "field": "Legality evidence", "note": "land-use rights, EUDR Annex-II legality documents"},
         {"key": "eudr_supplier", "field": "Supplier / operator identity", "note": "name, address, EORI where applicable"}],
     "citation": "EUDR (EU) 2023/1115 · application-date amendment (EU) 2024/3234", "url": _EURLEX + "32024R3234"},
    {"sectors": ["manufacturer", "bank", "reit"], "framework": None,
     "affects": ["bank_tcfd", "reit_tcfd", "csrd_e1", "esrs_pack"], "title": "EU Taxonomy — environmental objectives",
     "date": "2024-01-01", "when": "1 Jan 2024 · first reported for FY2024",
     "whats_changing": "Taxonomy alignment extends beyond climate mitigation & adaptation to water, circular economy, pollution prevention and biodiversity.",
     "prepare": "Activity-level data against the four additional environmental objectives.",
     "data_fields": [
         {"key": "taxo_nace", "field": "Economic activity per NACE code", "note": "map each activity to a Taxonomy activity"},
         {"key": "taxo_kpis", "field": "Turnover / CapEx / OpEx attributable to each activity", "note": "the three Art. 8 KPIs"},
         {"key": "taxo_sc", "field": "Substantial-contribution flag per objective", "note": "water · circular economy · pollution · biodiversity"},
         {"key": "taxo_dnsh", "field": "DNSH assessment per objective", "note": "‘do no significant harm’ screening"},
         {"key": "taxo_safeguards", "field": "Minimum-safeguards compliance", "note": "OECD MNE / UN Guiding Principles"}],
     "citation": "Environmental Delegated Act (EU) 2023/2486 (applies from 1 Jan 2024)", "url": _EURLEX + "32023R2486"},
    {"sectors": ["manufacturer"], "framework": "esrs_pack", "affects": ["csrd_e1", "esrs_pack"], "title": "ESRS digital tagging (XBRL)",
     "date": None, "when": "no fixed date · phased with ESAP go-live (from 2027)",
     "whats_changing": "Sustainability statements must be tagged in the EFRAG ESRS XBRL taxonomy for machine-readable filing to the European Single Access Point.",
     "prepare": None,
     "citation": "EFRAG ESRS XBRL taxonomy · ESAP Regulation (EU) 2023/2859", "url": _EURLEX + "32023R2859"},
    {"sectors": ["manufacturer", "bank", "insurer", "asset_manager", "reit"], "framework": None,
     "affects": ["csrd_e1", "esrs_pack"], "title": "CSRD / ESRS — Omnibus (‘stop-the-clock’)",
     "date": None, "when": "Dir. (EU) 2025/794 (Apr 2025) — next waves delayed to FY2027 / FY2028; scope still in negotiation",
     "whats_changing": "The ‘stop-the-clock’ Directive postpones the next CSRD reporting waves by two years; the substantive scope changes (Omnibus) are still under EU negotiation.",
     "prepare": "No action yet — you'll be told if your own obligations change.",
     "citation": "Directive (EU) 2025/794 · EC Omnibus proposal (Feb 2025)", "url": _EURLEX + "32025L0794"},
    {"sectors": ["bank"], "framework": "bank_p3esg", "affects": ["bank_p3esg"], "title": "Pillar 3 ESG — template revisions",
     "date": None, "when": "no fixed date · rolling EBA ITS updates",
     "whats_changing": "The EBA periodically revises the ESG disclosure templates (physical & transition risk, Green Asset Ratio).",
     "prepare": None,
     "citation": "EBA ITS (EU) 2022/2453, as revised", "url": _EURLEX + "32022R2453"},
    {"sectors": ["asset_manager"], "framework": "sfdr_pai", "affects": ["sfdr_pai"], "title": "SFDR RTS review — revised PAI methodology",
     "date": None, "when": "no adoption date set · ESAs proposal under EC review",
     "whats_changing": "The ESAs have proposed revisions to the SFDR RTS, including the Principal Adverse Impact indicators and disclosures.",
     "prepare": "Possibly new issuer-level attributes — the exact fields will be flagged once finalised.",
     "data_tbc": "New PAI indicators are in the ESAs' proposal but not yet adopted — we'll publish the exact fields the moment the RTS is final.",
     "citation": "ESAs SFDR RTS review (2023 final report)", "url": "https://www.esma.europa.eu/"},
    {"sectors": ["bank", "insurer", "asset_manager", "reit"], "framework": None,
     "affects": ["bank_tcfd", "reit_tcfd", "assetmgmt_tcfd", "insurer_climate"], "title": "IFRS S2 / ISSB adoption",
     "date": None, "when": "date set per jurisdiction on ISSB adoption",
     "whats_changing": "IFRS S2 climate-related disclosures become required where a jurisdiction adopts the ISSB standards.",
     "prepare": None,
     "citation": "IFRS S2 Climate-related Disclosures", "url": "https://www.ifrs.org/"},
]


def changes_affecting(org_type: str | None, framework: str, session=None) -> list[dict]:
    """Coming changes (for this sector) that touch a given framework — the single signal both the customer
    outlook and the supervisory-question 'review recommended' flags read from. Combines the curated library
    with anything the live EUR-Lex detector has flagged for this framework (session required for the latter)."""
    out = []
    for c in COMING:
        if org_type not in (c.get("sectors") or []):
            continue
        if c.get("framework") == framework or framework in (c.get("affects") or []):
            out.append({"title": c["title"], "when": c["when"], "date": c.get("date"),
                        "citation": c["citation"], "url": c.get("url"), "source": "curated"})
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import detected_changes
            for dc in detected_changes(session, framework):
                out.append({"title": dc["title"], "when": (dc["effective_date"] or f"detected {dc['detected_at']}"),
                            "date": dc["effective_date"], "citation": f"EUR-Lex · CELEX:{dc['celex']}",
                            "url": dc["url"], "source": "detected", "status": dc["status"]})
        except Exception:
            pass
    return out


def _short(fw: str) -> str:
    """A one-line 'what it requires' for a framework the org files today."""
    r = REFERENCE.get(fw) or {}
    return r.get("summary") or (FRAMEWORKS.get(fw, {}).get("label") or "")


def outlook(org_type: str | None, session=None, org_id: str | None = None) -> dict:
    """The customer's regulatory outlook: what's in force for this sector today, and what's coming — with the
    coming dates verified live against the EUR-Lex register, plus any changes the live detector has flagged."""
    # live-verified legal dates + auto-detected changes from the EUR-Lex (Cellar) detector
    verified: dict = {}
    detected: list[dict] = []
    checked_at = None
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import (
                detected_changes,
                verified_dates,
            )
            verified = verified_dates(session)
            detected = detected_changes(session)
            checked_at = next((v.get("checked_at") for v in verified.values() if v.get("checked_at")), None)
        except Exception:
            verified, detected = {}, []

    in_force = []
    for fw, meta in FRAMEWORKS.items():
        if org_type not in (meta.get("sectors") or ()):
            continue
        ref = REFERENCE.get(fw) or {}
        in_force.append({
            "framework": fw,
            "name": ref.get("official_name") or meta.get("label"),
            "authority": ref.get("authority") or meta.get("regulator"),
            "frequency": meta.get("frequency"),
            "requires": _short(fw),
            "citation": ref.get("legal_basis") or meta.get("basis"),
            "url": ref.get("url"),
        })
    in_force.sort(key=lambda x: x["name"] or "")

    coming = []
    for c in COMING:
        if org_type not in (c.get("sectors") or []):
            continue
        item = {k: c[k] for k in ("framework", "title", "date", "when", "whats_changing", "prepare", "citation", "url")}
        item["date_fixed"] = c.get("date") is not None
        item["source"] = "curated"
        item["data_tbc"] = c.get("data_tbc")
        # data-readiness: for each required field, check the client's own book (have / partial / needed)
        fields = []
        for f in (c.get("data_fields") or []):
            row = {"field": f["field"], "note": f.get("note", "")}
            if session is not None and org_id:
                try:
                    from services.governance.reg_readiness import field_readiness
                    row.update(field_readiness(session, org_id, f.get("key")))
                except Exception:
                    row["status"] = "needed"
            fields.append(row)
        item["data_fields"] = fields
        if session is not None and org_id and fields:
            item["data_summary"] = {"have": sum(1 for f in fields if f.get("status") == "have"),
                                    "partial": sum(1 for f in fields if f.get("status") == "partial"),
                                    "needed": sum(1 for f in fields if f.get("status") == "needed"),
                                    "total": len(fields)}
        # reconcile the curated date against the live EUR-Lex register — only for items that (a) carry a fixed
        # date and (b) are tied to a single governing act, so we compare like with like (not a sub-timeline).
        fw = c.get("framework")
        v = verified.get(fw) if fw else None
        if v and v.get("next_effective") and item["date_fixed"]:
            item["verified_date"] = v["next_effective"]
            item["verified_at"] = v.get("checked_at")
            if item["date"] != v["next_effective"]:
                item["date_moved"] = True   # our curated date differed from the register
                item["date"] = v["next_effective"]
        coming.append(item)
    # auto-detected changes from the live scan → new "pending review" items
    for dc in detected:
        # only surface those relevant to this sector's frameworks
        if not any(dc["framework"] in (c.get("affects") or []) or dc["framework"] == c.get("framework")
                   for c in COMING if org_type in (c.get("sectors") or [])) \
           and dc["framework"] not in [f for f in FRAMEWORKS if org_type in (FRAMEWORKS[f].get("sectors") or ())]:
            continue
        coming.append({"framework": dc["framework"], "title": dc["title"], "date": dc["effective_date"],
                       "date_fixed": dc["effective_date"] is not None, "when": (dc["effective_date"] or "newly detected"),
                       "whats_changing": dc["summary"], "prepare": None, "data_fields": [], "data_tbc": None,
                       "citation": f"EUR-Lex · CELEX:{dc['celex']}", "url": dc["url"],
                       "source": "detected", "status": dc["status"], "detected_at": dc["detected_at"]})
    # per-org impact (deadline urgency + record scope) on every coming change, from the client's own book
    if session is not None and org_id:
        try:
            from services.governance.reg_impact import change_impact
            for it in coming:
                imp = change_impact(session, org_id, it.get("framework"), it.get("date"))
                if imp:
                    it["impact"] = imp
        except Exception:
            pass
    # confirmed exact dates first, chronologically; then the not-yet-fixed ones
    coming.sort(key=lambda c: (c["date"] is None, c["date"] or "9999"))
    return {"in_force": in_force, "coming": coming, "checked_at": checked_at,
            "summary": {"n_in_force": len(in_force), "n_coming": len(coming),
                        "n_prepare": sum(1 for c in coming if c.get("prepare")),
                        "n_dated": sum(1 for c in coming if c["date_fixed"]),
                        "n_detected": sum(1 for c in coming if c.get("source") == "detected"),
                        "n_verified": sum(1 for c in coming if c.get("verified_date"))}}
