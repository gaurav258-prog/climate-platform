"""
XBRL Instance Document builder for CSRD ESRS E1-9 Physical Risk.

Produces a valid XBRL 2.1 instance document that national competent authorities
(BaFin, AMF, AFM, etc.) can ingest directly via their ESEF/XBRL portals.

Standard references:
  - XBRL 2.1 Specification (XBRL International)
  - ESRS Set 1 XBRL Taxonomy (EFRAG, Delegated Regulation 2023/2772)
  - ESEF Reporting Manual (ESMA) — iXBRL wrapper for narrative reports
  - ESRS E1 — Climate Change (specifically E1-9: Physical risks)

What we produce:
  An XBRL instance document (.xbrl) containing:
    - Entity context (LEI code, reporting period)
    - Dimensional contexts (hazard × scenario × time_horizon)
    - Facts mapped from our CSRD package tables (E1-9A through E1-9F)
    - Extension facts carrying our regulatory fingerprints for audit traceability

Why not Inline XBRL (iXBRL):
  iXBRL embeds XBRL tags inside the company's HTML narrative report.
  We are a data provider, not the report author. We produce the structured
  data attachment; the company's reporting tool wraps it into iXBRL alongside
  their narrative text. Our output slots directly into tools like Workiva,
  Envision, or BIRD (ECB's Banks' Integrated Reporting Dictionary).

Namespace strategy:
  esrs     — EFRAG ESRS Set 1 taxonomy (E1-9 physical risk concepts)
  esrs-e1  — ESRS E1 extension (climate-specific concepts)
  vigil    — Platform extension namespace (fingerprint + ensemble provenance)
  xbrli    — XBRL 2.1 instance namespace
  xbrldt   — XBRL Dimensions 1.0 (for hazard/scenario axis)
  iso4217  — Currency codes
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from xml.dom import minidom
import xml.etree.ElementTree as ET

# ── Namespace URIs ─────────────────────────────────────────────────────
NS = {
    "xbrli":   "http://www.xbrl.org/2003/instance",
    "link":    "http://www.xbrl.org/2003/linkbase",
    "xlink":   "http://www.w3.org/1999/xlink",
    "xbrldt":  "http://xbrl.org/2005/xbrldt",
    "iso4217": "http://www.xbrl.org/2003/iso4217",
    # EFRAG ESRS Set 1 taxonomy (Delegated Regulation 2023/2772, published 2023-12-22)
    "esrs":    "http://xbrl.efrag.org/taxonomy/draft-esrs/2023-12-22",
    "esrs-e1": "http://xbrl.efrag.org/taxonomy/draft-esrs/e1/2023-12-22",
    # Platform provenance extension
    "vigil":   "http://climate-intelligence.platform/xbrl/provenance/2024",
}

# Register all prefixes with ElementTree
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

# Shorthand for tagging
def _tag(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


# ── ESRS E1-9 concept → XBRL element mapping ──────────────────────────
#
# Based on EFRAG ESRS Set 1 Data Point Model (DPM), ESRS E1-9
# Each entry: (esrs_concept, xbrl_type, unit_or_none)
#
ESRS_CONCEPTS = {
    # E1-9 paragraph 66: Physical risk type identification
    "PhysicalRiskType":                    ("esrs-e1", "stringItemType", None),
    "PhysicalRiskAcuteOrChronic":          ("esrs-e1", "stringItemType", None),
    "PhysicalRiskMaterialityLevel":        ("esrs-e1", "stringItemType", None),
    "PhysicalRiskDescription":             ("esrs-e1", "stringItemType", None),
    # E1-9 paragraph 67: Risk assessment methodology
    "PhysicalRiskAssessmentMethodology":   ("esrs",    "stringItemType", None),
    "ClimateScenarioUsed":                 ("esrs",    "stringItemType", None),
    "SpatialResolutionOfRiskAssessment":   ("esrs-e1", "stringItemType", None),
    # E1-9 paragraph 68: Location and exposure
    "LocationSubjectToPhysicalRisk":       ("esrs-e1", "stringItemType", None),
    "NumberOfLocationsAtRisk":             ("esrs-e1", "integerItemType", None),
    "PercentageOfLocationsAtRisk":         ("esrs-e1", "decimalItemType", None),
    "RiskScore":                           ("vigil",   "decimalItemType", None),
    "RiskBucket":                          ("vigil",   "stringItemType",  None),
    "EnsembleConfidenceIntervalLower":     ("vigil",   "decimalItemType", None),
    "EnsembleConfidenceIntervalUpper":     ("vigil",   "decimalItemType", None),
    # E1-9 paragraph 69: Financial amounts at risk
    "FinancialExposureToPhysicalRisk":     ("esrs-e1", "monetaryItemType", "iso4217"),
    "PercentageOfPortfolioAtHighRisk":     ("esrs-e1", "decimalItemType", None),
    # E1-9 time horizon materiality
    "TimeHorizonForRiskAssessment":        ("esrs",    "stringItemType", None),
    "MaterialityLevelAtTimeHorizon":       ("esrs-e1", "stringItemType", None),
    # Double materiality
    "FinancialMaterialityLevel":           ("esrs",    "stringItemType", None),
    "ImpactMaterialityLevel":              ("esrs",    "stringItemType", None),
    "OverallMaterialityConclusion":        ("esrs",    "stringItemType", None),
    # Provenance (platform extension)
    "RegulatoryFingerprint":               ("vigil",   "stringItemType", None),
    "ModelVersion":                        ("vigil",   "stringItemType", None),
    "ScoringTimestamp":                    ("vigil",   "stringItemType", None),
    "CompoundEventFlag":                   ("vigil",   "booleanItemType", None),
}


def build_xbrl(
    csrd_package: dict,
    lei_code: str,
    reporting_currency: str = "EUR",
    company_name: Optional[str] = None,
) -> str:
    """
    Convert a CSRD package dict (output of csrd.build()) into a valid
    XBRL 2.1 instance document string.

    Parameters
    ----------
    csrd_package      : dict returned by ml.regulatory.csrd.build()
    lei_code          : 20-char Legal Entity Identifier (ISO 17442)
                        e.g. "5493001KJTIIGC8Y1R12"
    reporting_currency: ISO 4217 code (default EUR)
    company_name      : Optional; used as a comment in the document

    Returns
    -------
    Formatted XBRL XML string (UTF-8, pretty-printed)
    """
    period_start = csrd_package.get("period_start", "")
    period_end   = csrd_package.get("period_end", "")
    customer_id  = csrd_package.get("customer_id", "")
    horizons     = csrd_package.get("horizons_covered", ["current"])

    # ── Root element ──────────────────────────────────────────────
    root = ET.Element(_tag("xbrli", "xbrl"))
    _add_schema_ref(root)

    # ── Contexts ──────────────────────────────────────────────────
    # One base context per time horizon (current / 2030 / 2050 / 2100)
    # Plus dimension contexts for hazard × scenario combinations
    horizon_to_year = {
        "current": period_end[:4] if period_end else "2024",
        "2030": "2030", "2050": "2050", "2100": "2100",
    }

    ctx_ids: dict[tuple, str] = {}

    # Base context for entity-level facts (no dimension)
    base_ctx_id = "ctx-entity-period"
    _add_context(root, base_ctx_id, lei_code, period_start, period_end)

    # Contexts per horizon
    for horizon in horizons:
        year = horizon_to_year.get(horizon, horizon)
        ctx_id = f"ctx-{horizon}"
        _add_context(root, ctx_id, lei_code, period_start,
                     f"{year}-12-31" if len(year) == 4 else period_end)
        ctx_ids[(horizon, None, None)] = ctx_id

    # Dimensional contexts: horizon × hazard × scenario
    hazard_scenarios = set()
    for row in csrd_package.get("e1_9b_exposure_by_class", []):
        for h in row.get("hazards_present", []):
            hazard_scenarios.add((h, "baseline"))
    for row in csrd_package.get("e1_9e_time_horizon", []):
        hazard_scenarios.add((row["hazard_type"], "baseline"))

    for hazard, scenario in hazard_scenarios:
        for horizon in horizons:
            year = horizon_to_year.get(horizon, horizon)
            ctx_id = f"ctx-{_safe_id(hazard)}-{_safe_id(scenario)}-{horizon}"
            _add_context_with_dims(
                root, ctx_id, lei_code,
                period_start, f"{year}-12-31" if len(year) == 4 else period_end,
                hazard=hazard, scenario=scenario,
            )
            ctx_ids[(horizon, hazard, scenario)] = ctx_id

    # ── Units ─────────────────────────────────────────────────────
    _add_unit(root, "u-pure",    "xbrli:pure")
    _add_unit(root, f"u-{reporting_currency}", f"iso4217:{reporting_currency}")

    # ── Facts — entity level ───────────────────────────────────────
    meth = csrd_package.get("methodology", {})

    _add_fact(root, "esrs", "PhysicalRiskAssessmentMethodology",
              meth.get("scoring_model", ""), base_ctx_id)
    _add_fact(root, "esrs", "ClimateScenarioUsed",
              "NGFS Phase 4", base_ctx_id)
    _add_fact(root, "esrs", "SpatialResolutionOfRiskAssessment",
              meth.get("spatial_framework", "H3 resolution 8 (~0.7 km²)"), base_ctx_id)
    _add_fact(root, "vigil", "ModelVersion",
              meth.get("scoring_model", "ensemble-v1"), base_ctx_id)
    _add_fact(root, "vigil", "ScoringTimestamp",
              meth.get("temporal_coverage", ""), base_ctx_id)

    # Double materiality
    dm = csrd_package.get("e1_9f_double_materiality", {})
    if dm:
        _add_fact(root, "esrs", "FinancialMaterialityLevel",
                  dm.get("financial_materiality", {}).get("level", ""), base_ctx_id)
        _add_fact(root, "esrs", "ImpactMaterialityLevel",
                  dm.get("impact_materiality", {}).get("level", ""), base_ctx_id)
        _add_fact(root, "esrs", "OverallMaterialityConclusion",
                  dm.get("overall_materiality", ""), base_ctx_id)

    # ── Facts — portfolio level by time horizon ───────────────────
    _add_fact(root, "esrs-e1", "PercentageOfPortfolioAtHighRisk",
              str(csrd_package.get("pct_locations_material", 0)),
              ctx_ids.get(("current", None, None), base_ctx_id),
              unit_ref="u-pure", decimals="2")

    # ── Facts — E1-9A: Material risks per hazard ─────────────────
    for risk in csrd_package.get("e1_9a_material_risks", []):
        hazard  = risk.get("hazard_type", "")
        horizon = risk.get("time_horizon", "current")
        ctx_id  = ctx_ids.get((horizon, hazard, "baseline"),
                               ctx_ids.get((horizon, None, None), base_ctx_id))

        _add_fact(root, "esrs-e1", "PhysicalRiskType",         hazard,                ctx_id)
        _add_fact(root, "esrs-e1", "PhysicalRiskAcuteOrChronic", risk.get("hazard_class", ""),  ctx_id)
        _add_fact(root, "esrs-e1", "PhysicalRiskMaterialityLevel", risk.get("materiality", ""), ctx_id)
        _add_fact(root, "esrs-e1", "PhysicalRiskDescription",  risk.get("hazard_label", ""),    ctx_id)
        _add_fact(root, "esrs-e1", "NumberOfLocationsAtRisk",
                  str(risk.get("n_locations_at_risk", 0)), ctx_id,
                  decimals="0")
        _add_fact(root, "vigil", "CompoundEventFlag",
                  str(risk.get("compound_risk", False)).lower(), ctx_id)

    # ── Facts — E1-9C: Financial exposure by hazard × bucket ─────
    for exp in csrd_package.get("e1_9c_financial_exposure", []):
        hazard  = exp.get("hazard_type", "")
        horizon = "current"
        ctx_id  = ctx_ids.get((horizon, hazard, "baseline"),
                               ctx_ids.get((horizon, None, None), base_ctx_id))

        val = exp.get("total_exposure")
        if val is not None:
            _add_fact(root, "esrs-e1", "FinancialExposureToPhysicalRisk",
                      str(round(val, 2)), ctx_id,
                      unit_ref=f"u-{reporting_currency}", decimals="2")
        _add_fact(root, "esrs-e1", "RiskBucket",
                  exp.get("risk_bucket", ""), ctx_id)

    # ── Facts — E1-9E: Time horizon materiality ───────────────────
    for th in csrd_package.get("e1_9e_time_horizon", []):
        hazard  = th.get("hazard_type", "")
        horizon = th.get("time_horizon", "current")
        ctx_id  = ctx_ids.get((horizon, hazard, "baseline"),
                               ctx_ids.get((horizon, None, None), base_ctx_id))

        _add_fact(root, "esrs", "TimeHorizonForRiskAssessment",  horizon,  ctx_id)
        _add_fact(root, "esrs", "MaterialityLevelAtTimeHorizon",
                  th.get("materiality_level", ""), ctx_id)
        _add_fact(root, "esrs-e1", "PercentageOfLocationsAtRisk",
                  str(th.get("pct_material", 0)), ctx_id,
                  unit_ref="u-pure", decimals="2")

    # ── Facts — Provenance fingerprints (vigil extension) ─────────
    # Every fingerprint in the package becomes a verifiable fact.
    # Regulators or auditors can use these to challenge individual scores.
    seen_fps = set()
    for table in ["e1_9a_material_risks"]:
        for row in csrd_package.get(table, []):
            fp = row.get("fingerprint")
            if fp and fp not in seen_fps:
                seen_fps.add(fp)
                _add_fact(root, "vigil", "RegulatoryFingerprint", fp, base_ctx_id)

    # ── Serialise ─────────────────────────────────────────────────
    return _pretty_print(root, csrd_package, company_name, lei_code)


# ── XML builder helpers ────────────────────────────────────────────────

def _add_schema_ref(root: ET.Element) -> None:
    """Add schemaRef pointing to EFRAG ESRS taxonomy."""
    link = ET.SubElement(root, _tag("link", "schemaRef"))
    link.set(_tag("xlink", "type"), "simple")
    link.set(_tag("xlink", "href"),
             "http://xbrl.efrag.org/taxonomy/draft-esrs/2023-12-22/esrs-all.xsd")
    link.set(_tag("xlink", "arcrole"),
             "http://www.w3.org/1999/xlink/properties/linkbase")


def _add_context(root: ET.Element, ctx_id: str,
                 lei: str, start: str, end: str) -> None:
    ctx = ET.SubElement(root, _tag("xbrli", "context"), id=ctx_id)
    entity = ET.SubElement(ctx, _tag("xbrli", "entity"))
    ident  = ET.SubElement(entity, _tag("xbrli", "identifier"))
    ident.set("scheme", "http://standards.iso.org/iso/17442")
    ident.text = lei
    period = ET.SubElement(ctx, _tag("xbrli", "period"))
    ET.SubElement(period, _tag("xbrli", "startDate")).text = start
    ET.SubElement(period, _tag("xbrli", "endDate")).text   = end


def _add_context_with_dims(
    root: ET.Element, ctx_id: str,
    lei: str, start: str, end: str,
    hazard: str, scenario: str,
) -> None:
    ctx = ET.SubElement(root, _tag("xbrli", "context"), id=ctx_id)

    entity = ET.SubElement(ctx, _tag("xbrli", "entity"))
    ident  = ET.SubElement(entity, _tag("xbrli", "identifier"))
    ident.set("scheme", "http://standards.iso.org/iso/17442")
    ident.text = lei

    seg = ET.SubElement(entity, _tag("xbrli", "segment"))
    # Hazard dimension
    hd = ET.SubElement(seg, _tag("xbrldt", "explicitMember"))
    hd.set("dimension", "esrs-e1:PhysicalHazardTypeDimension")
    hd.text = f"esrs-e1:{_xbrl_hazard(hazard)}"
    # Scenario dimension
    sd = ET.SubElement(seg, _tag("xbrldt", "explicitMember"))
    sd.set("dimension", "esrs:ClimateScenarioDimension")
    sd.text = f"esrs:{_xbrl_scenario(scenario)}"

    period = ET.SubElement(ctx, _tag("xbrli", "period"))
    ET.SubElement(period, _tag("xbrli", "startDate")).text = start
    ET.SubElement(period, _tag("xbrli", "endDate")).text   = end


def _add_unit(root: ET.Element, unit_id: str, measure: str) -> None:
    unit = ET.SubElement(root, _tag("xbrli", "unit"), id=unit_id)
    m = ET.SubElement(unit, _tag("xbrli", "measure"))
    m.text = measure


def _add_fact(
    root: ET.Element,
    ns_prefix: str,
    local_name: str,
    value: str,
    ctx_ref: str,
    unit_ref: Optional[str] = None,
    decimals: Optional[str] = None,
) -> None:
    if not value or value in ("None", "nan"):
        return
    el = ET.SubElement(root, _tag(ns_prefix, local_name))
    el.set("contextRef", ctx_ref)
    if unit_ref:
        el.set("unitRef", unit_ref)
    if decimals:
        el.set("decimals", decimals)
    el.text = value


# ── Dimension value mappers ────────────────────────────────────────────

def _xbrl_hazard(hazard: str) -> str:
    mapping = {
        "flood":      "RiverFloodingAndPluvialFlooding",
        "wildfire":   "WildfireAndForestFire",
        "heat_acute": "ExtremeHeatEvent",
        "drought":    "Drought",
        "storm":      "ExtremeWindAndStorm",
    }
    return mapping.get(hazard, f"OtherHazard_{_safe_id(hazard)}")


def _xbrl_scenario(scenario: str) -> str:
    mapping = {
        "baseline":    "NGFSCurrentPoliciesScenario",
        "orderly":     "NGFSNetZero2050Scenario",
        "disorderly":  "NGFSDisorderedTransitionScenario",
        "hot_house":   "NGFSHotHouseWorldScenario",
    }
    return mapping.get(scenario, f"Scenario_{_safe_id(scenario)}")


def _safe_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "_", s)


# ── Pretty printer ─────────────────────────────────────────────────────

def _pretty_print(
    root: ET.Element,
    csrd_package: dict,
    company_name: Optional[str],
    lei_code: str,
) -> str:
    raw = ET.tostring(root, encoding="unicode", xml_declaration=False)
    dom = minidom.parseString(f'<?xml version="1.0" encoding="UTF-8"?>{raw}')

    # Insert human-readable header comment
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    hdr  = (
        f"\n"
        f"  CSRD ESRS E1-9 Physical Risk Disclosure\n"
        f"  XBRL 2.1 Instance Document\n"
        f"\n"
        f"  Entity     : {company_name or 'See LEI'}\n"
        f"  LEI        : {lei_code}\n"
        f"  Period     : {csrd_package.get('period_start')} / {csrd_package.get('period_end')}\n"
        f"  Generated  : {now}\n"
        f"  Framework  : ESRS E1-9 (Delegated Regulation EU 2023/2772)\n"
        f"  Taxonomy   : EFRAG ESRS Set 1 (2023-12-22)\n"
        f"  Producer   : Climate Intelligence Platform\n"
        f"\n"
        f"  Each RegulatoryFingerprint fact is a SHA-256 hash of the\n"
        f"  underlying model inputs. Present to the platform operator\n"
        f"  to reproduce any score for audit or regulatory challenge.\n"
    )
    comment = dom.createComment(hdr)
    dom.documentElement.insertBefore(comment, dom.documentElement.firstChild)

    pretty = dom.toprettyxml(indent="  ", encoding=None)
    # minidom adds its own declaration; strip the duplicate
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + "\n".join(lines)


# ── File writer ────────────────────────────────────────────────────────

def write_xbrl(
    csrd_package: dict,
    output_path: str,
    lei_code: str,
    reporting_currency: str = "EUR",
    company_name: Optional[str] = None,
) -> str:
    """Write XBRL instance document to file. Returns the path."""
    content = build_xbrl(
        csrd_package=csrd_package,
        lei_code=lei_code,
        reporting_currency=reporting_currency,
        company_name=company_name,
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
