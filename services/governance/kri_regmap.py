"""Regulator-backwards mapping for the KRI dashboard — what each supervisor expects to see, and which
regulatory datapoint every KRI feeds. This turns the dashboard from 'here are some risk numbers' into
'here is what your regulator will look at when you file, and where you stand' (a pre-submission read).

REGULATOR: per framework → the authority + the disclosure it maps to (sourced from reg_reference).
KRI_REG:   per (framework, kri_key) → (regulatory datapoint it feeds, tier). tier 'core' = a headline
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
        "value_at_risk": ("TCFD — physical-risk exposure (value at High+)", "core"),
        "pct_at_risk":   ("TCFD — share of the book at risk", "core"),
        "coverage":      ("Data coverage / PCAF data quality", "support"),
        "fin_emissions": ("PCAF — financed emissions (Scope 1–3)", "core"),
        "taxonomy":      ("Taxonomy Art. 8 — eligible % (→ Green Asset Ratio)", "core"),
        "gar":           ("Taxonomy Art. 8 — Green Asset Ratio (aligned %)", "core"),
    },
    "reit_tcfd": {
        "total_value":   ("Property book value — Art. 8 denominator", "support"),
        "value_at_risk": ("TCFD — physical-risk exposure (value at High+)", "core"),
        "pct_at_risk":   ("TCFD — share of the portfolio at risk", "core"),
        "noi_impact":    ("TCFD — physical-risk impact on net operating income", "core"),
        "coverage":      ("Data coverage", "support"),
        "taxonomy":      ("Taxonomy Art. 8 — eligible %", "core"),
    },
    "insurer_climate": {
        "sum_insured":   ("Total sum insured — denominator", "support"),
        "eal":           ("EIOPA / IFRS S2 — expected annual loss (NatCat)", "core"),
        "loss_ratio":    ("EIOPA — NatCat loss ratio", "core"),
        "value_at_risk": ("Sum insured at High+ by peril", "core"),
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
    "csrd_e1": {
        "asset_value":           ("ESRS E1 — own-operations asset base", "support"),
        "asset_at_risk":         ("ESRS E1-9 — own-ops asset value at risk", "core"),
        "pct_at_risk":           ("ESRS E1 — share of sites at risk", "core"),
        "business_interruption": ("ESRS E1-9 — business interruption (v0)", "core"),
        "ingredient_spend":      ("ESRS E1 — upstream sourcing base", "support"),
        "cogs_at_risk":          ("ESRS E1-9 — COGS at risk (published)", "core"),
        "cogs_withheld":         ("ESRS E1-9 — exposure mapped, € withheld", "support"),
        "coverage":              ("Plot data coverage", "support"),
        "ghg_emissions":         ("ESRS E1-6 — GHG emissions (Scope 1–3)", "core"),
    },
}
# esrs_pack = E1 (same as csrd_e1) + E3 water + E4 biodiversity
KRI_REG["esrs_pack"] = {
    **KRI_REG["csrd_e1"],
    "water_plots_stressed":   ("ESRS E3 — plots water-stressed", "core"),
    "water_spend_exposed":    ("ESRS E3 — spend water-exposed", "core"),
    "water_peak":             ("ESRS E3 — peak water-stress score", "support"),
    "deforestation_free_pct": ("ESRS E4 / EUDR — deforestation-free %", "core"),
    "non_compliant":          ("ESRS E4 / EUDR — non-compliant plots", "core"),
    "forest_loss_ha":         ("ESRS E4 — post-cutoff forest loss", "support"),
}


def annotate(framework: str, kpis: list[dict]) -> dict:
    """Attach the regulatory datapoint tag + tier to each KRI in place, and return a submission-readiness
    summary: of the CORE datapoints the regulator expects, how many we currently carry a value for."""
    tags = KRI_REG.get(framework, {})
    core = covered = 0
    integrated, gaps = [], []
    for k in kpis:
        t = tags.get(k.get("key"))
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
