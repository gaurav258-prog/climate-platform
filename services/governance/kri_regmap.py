"""Regulator-backwards mapping for the KRI dashboard — what each supervisor expects to see, and which
regulatory datapoint every KRI feeds. This turns the dashboard from 'here are some risk numbers' into
'here is what your regulator will look at when you file, and where you stand' (a pre-submission read).

REGULATOR: per framework → the authority + the disclosure it maps to (sourced from reg_reference).
KRI_REG:   per (framework, kri_key) → (regulatory datapoint it feeds, tier); a KRI may carry its own (reg, reg_tier). tier 'core' = a headline
           datapoint the regulator scrutinises; 'support' = a denominator / coverage / context figure.
"""
from __future__ import annotations

from services.governance.reg_reference import REFERENCE


def regulator(framework: str) -> dict | None:
    """The supervisor + disclosure a KRI set maps to — for the dashboard header."""
    ref = REFERENCE.get(framework)
    if not ref:
        return None
    return {"authority": ref["authority"], "disclosure": ref["official_name"],
            "legal_basis": ref["legal_basis"], "form_url": ref.get("form_url")}


# (regulatory datapoint the KRI feeds, tier)  — tier ∈ {'core', 'support'}
KRI_REG: dict[str, dict[str, tuple[str, str]]] = {
    "bank_tcfd": {
        "total_value":   ("Total exposure — Taxonomy Art. 8 denominator", "support"),
        "value_at_risk": ("TCFD — physical-risk exposure (value at or above the stated at-risk level)", "core"),
        "pct_at_risk":   ("TCFD — share of the book at risk", "core"),
        "acute_share":   ("TCFD — acute (event-driven) physical-risk share", "core"),
        "chronic_share": ("TCFD — chronic (gradual) physical-risk share", "core"),
        "forward_share": ("TCFD — forward-looking scenario share at risk", "core"),
        "sector_concentration": ("TCFD — concentration in high-climate-impact sectors", "support"),
        "coverage":      ("Data coverage / PCAF data quality", "support"),
        "fin_emissions": ("PCAF — financed emissions (Scope 1–3)", "core"),
        "taxonomy":      ("Taxonomy Art. 8 — eligible % (→ Green Asset Ratio)", "core"),
        "gar":           ("Taxonomy Art. 8 — Green Asset Ratio (aligned %)", "core"),
    },
    "bank_p3esg": {
        "total_value":   ("Banking-book exposures — Template 5 denominator", "support"),
        "value_at_risk": ("Template 5 — exposures sensitive to climate physical risk", "core"),
        "pct_at_risk":   ("Template 5 — share of the book at physical risk", "core"),
        "acute_share":   ("Template 5 — acute physical-risk column", "core"),
        "chronic_share": ("Template 5 — chronic physical-risk column", "core"),
        "forward_share": ("Template 5 — forward-looking scenario share at risk", "core"),
        "sector_concentration": ("Templates 1 & 5 — NACE-sector concentration", "support"),
        "coverage":      ("Data coverage / PCAF data quality", "support"),
        "fin_emissions": ("Template 1 col. i — financed emissions (gross Scope 1–3)", "core"),
        "p3_alignment":  ("Template 3 / EU CRFR4 (pending adoption) — alignment-metric distance to IEA NZE2050", "core"),
        "p3_top20":      ("Template 4 (deleted by the pending EBA/ITS/2026/02 amendment) — exposure to top-20 carbon-intensive firms", "core"),
        "taxonomy":      ("GAR + BTAR (Templates 7–8) — Taxonomy-eligible %", "core"),
        "gar":           ("GAR + BTAR (Templates 7–8) — aligned % (Green Asset Ratio)", "core"),
    },
    "reit_tcfd": {
        "total_value":   ("Property book value — Art. 8 denominator", "support"),
        "value_at_risk": ("TCFD — physical-risk exposure (value at or above the stated at-risk level)", "core"),
        "pct_at_risk":   ("TCFD — share of the portfolio at risk", "core"),
        "noi_impact":    ("TCFD — physical-risk impact on net operating income", "core"),
        "coverage":      ("Data coverage", "support"),
        "taxonomy":      ("Taxonomy Art. 8 — eligible %", "core"),
    },
    "insurer_climate": {
        "sum_insured":   ("Total sum insured — denominator", "support"),
        "eal":           ("EIOPA / IFRS S2 — expected annual loss (NatCat)", "core"),
        "loss_ratio":    ("EIOPA — NatCat loss ratio", "core"),
        "value_at_risk": ("Sum insured at or above the stated at-risk level by peril", "core"),
        "coverage":      ("Book priced / coverage", "support"),
    },
    "sfdr_pai": {
        "nav":            ("NAV in scope — denominator", "support"),
        "positions":      ("Holdings in scope", "support"),
        "pai_emissions":  ("SFDR PAI 1 — GHG emissions (Scope 1–3)", "core"),
        "carbon_footprint": ("SFDR PAI 2 — carbon footprint", "core"),
        "waci":           ("SFDR PAI 3 — GHG intensity (WACI)", "core"),
        "fossil_fuel":    ("SFDR PAI 4 — fossil-fuel exposure", "core"),
        "non_renewable":  ("SFDR PAI 5 — non-renewable energy share", "core"),
        "biodiversity":   ("SFDR PAI 7 — biodiversity-sensitive areas", "core"),
        "emissions_water": ("SFDR PAI 8 — emissions to water", "core"),
        "hazardous_waste": ("SFDR PAI 9 — hazardous/radioactive waste", "core"),
        "ungc_violations": ("SFDR PAI 10 — UNGC / OECD violations", "core"),
        "ungc_no_process": ("SFDR PAI 11 — no monitoring processes", "core"),
        "gender_pay_gap":  ("SFDR PAI 12 — unadjusted gender pay gap", "core"),
        "board_diversity": ("SFDR PAI 13 — board gender diversity", "core"),
        "controversial_weapons": ("SFDR PAI 14 — controversial weapons", "core"),
        "emissions_cov":  ("PAI data coverage", "support"),
        "indicators":     ("PAI indicators computed (of 14 mandatory)", "support"),
    },
}
# esrs_pack: each KRI carries its own tag — the item(s) of the governing ESRS version that print its concept
# (services.governance.kri_esrs), since the datapoints differ between the 2023 and 2026 standards.


def tags(framework: str) -> dict[str, tuple[str, str]]:
    """Every KRI a framework's set can carry → (the datapoint it feeds, tier) — for what a regulatory change touches. The
    ESRS set is declared by kri_esrs.HEADLINE (which of them a year shows depends on the governing version)."""
    if framework == "esrs_pack":
        from services.governance.esrs_binding import concepts
        from services.governance.kri_esrs import HEADLINE
        cs = concepts()
        return {c: (f"ESRS — {cs[c]['label']}", tier) for c, tier in HEADLINE}
    return KRI_REG.get(framework, {})


def annotate(framework: str, kpis: list[dict]) -> dict:
    """Attach the regulatory datapoint tag + tier to each KRI in place, and return a submission-readiness
    summary: of the CORE datapoints the regulator expects, how many we currently carry a value for."""
    tags = KRI_REG.get(framework, {})
    core = covered = 0
    integrated, gaps = [], []
    for k in kpis:
        t = tags.get(k.get("key")) or ((k["reg"], k["reg_tier"]) if k.get("reg") and k.get("reg_tier") else None)
        if not t:
            continue
        k["reg"] = t[0]
        k["reg_tier"] = t[1]
        if t[1] == "core":
            core += 1
            if k.get("value") is not None:
                covered += 1
            elif k.get("integrated"):        # a datapoint the regulator wants but the client provides externally
                integrated.append(k.get("label"))
            else:
                gaps.append(k.get("label"))
    return {"core": core, "covered": covered, "integrated": integrated, "gaps": gaps}
