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
     "citation": "EUDR (EU) 2023/1115 · application-date amendment (EU) 2024/3234", "url": _EURLEX + "32024R3234"},
    {"sectors": ["manufacturer", "bank", "reit"], "framework": None,
     "affects": ["bank_tcfd", "reit_tcfd", "csrd_e1", "esrs_pack"], "title": "EU Taxonomy — environmental objectives",
     "date": "2024-01-01", "when": "1 Jan 2024 · first reported for FY2024",
     "whats_changing": "Taxonomy alignment extends beyond climate mitigation & adaptation to water, circular economy, pollution prevention and biodiversity.",
     "prepare": "Activity-level data against the four additional environmental objectives.",
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


def outlook(org_type: str | None, session=None) -> dict:
    """The customer's regulatory outlook: what's in force for this sector today, and what's coming — with the
    coming dates verified live against the EUR-Lex register, plus any changes the live detector has flagged."""
    # live-verified legal dates + auto-detected changes from the EUR-Lex (Cellar) detector
    verified: dict = {}
    detected: list[dict] = []
    checked_at = None
    if session is not None:
        try:
            from services.regulatory_monitoring.eurlex_detector import verified_dates, detected_changes
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
                       "whats_changing": dc["summary"], "prepare": None,
                       "citation": f"EUR-Lex · CELEX:{dc['celex']}", "url": dc["url"],
                       "source": "detected", "status": dc["status"], "detected_at": dc["detected_at"]})
    # confirmed exact dates first, chronologically; then the not-yet-fixed ones
    coming.sort(key=lambda c: (c["date"] is None, c["date"] or "9999"))
    return {"in_force": in_force, "coming": coming, "checked_at": checked_at,
            "summary": {"n_in_force": len(in_force), "n_coming": len(coming),
                        "n_prepare": sum(1 for c in coming if c.get("prepare")),
                        "n_dated": sum(1 for c in coming if c["date_fixed"]),
                        "n_detected": sum(1 for c in coming if c.get("source") == "detected"),
                        "n_verified": sum(1 for c in coming if c.get("verified_date"))}}
