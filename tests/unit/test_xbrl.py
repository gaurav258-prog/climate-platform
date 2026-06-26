"""
Unit tests for the XBRL 2.1 instance document builder.

All tests use synthetic CSRD package data — no DB required.
"""
import xml.etree.ElementTree as ET

import pytest

from ml.regulatory.xbrl import build_xbrl

NS = {
    "xbrli": "http://www.xbrl.org/2003/instance",
    "esrs":  "http://xbrl.efrag.org/taxonomy/draft-esrs/2023-12-22",
    "vigil": "http://climate-intelligence.platform/xbrl/provenance/2024",
}

SAMPLE_CSRD = {
    "company_name": "Test Bank SA",
    "framework": "CSRD",
    "period_start": "2024-01-01",
    "period_end": "2024-12-31",
    "e1_9a_material_risks": [
        {
            "h3_cell":           "881f1d4a13fffff",
            "hazard_type":       "flood",
            "risk_score":        72.5,
            "risk_bucket":       "HIGH",
            "materiality":       "very_material",
            "assessment_basis":  "satellite_ensemble_v1",
            # fingerprint required for the vigil:RegulatoryFingerprint fact
            "fingerprint":       "a" * 64,
        }
    ],
    "e1_9c_financial_exposure": [
        {
            "h3_cell":      "881f1d4a13fffff",
            "hazard_type":  "flood",
            "scenario":     "baseline",
            "time_horizon": "current",
            "risk_score":   72.5,
        }
    ],
    "e1_9e_time_horizons": [
        {"horizon": "current", "label": "Current (2024)", "n_locations": 1}
    ],
    "e1_9f_double_materiality": {
        "financial_materiality_assessed": True,
        "impact_materiality_assessed": True,
    },
    "methodology": {
        # scoring_model must be non-empty for PhysicalRiskAssessmentMethodology fact
        "scoring_model":     "XGBoost+LightGBM+LogisticRegression ensemble v1",
        "model_versions":    {"ensemble_v1": "xgb+lgbm+logistic"},
        "data_sources":      ["ERA5", "GloFAS"],
        "spatial_framework": "H3 resolution 8 (~0.7 km²)",
    },
}


@pytest.fixture()
def xbrl_string():
    return build_xbrl(SAMPLE_CSRD, lei_code="5493001KJTIIGC8Y1R12", company_name="Test Bank SA")


def test_output_is_valid_xml(xbrl_string):
    ET.fromstring(xbrl_string)  # raises if not well-formed


def test_root_element_is_xbrl(xbrl_string):
    root = ET.fromstring(xbrl_string)
    assert root.tag == "{http://www.xbrl.org/2003/instance}xbrl"


def test_entity_identifier_present(xbrl_string):
    root = ET.fromstring(xbrl_string)
    identifiers = root.findall(".//{http://www.xbrl.org/2003/instance}identifier")
    assert any("5493001KJTIIGC8Y1R12" in (i.text or "") for i in identifiers)


def test_period_start_end_present(xbrl_string):
    root = ET.fromstring(xbrl_string)
    starts = root.findall(".//{http://www.xbrl.org/2003/instance}startDate")
    ends   = root.findall(".//{http://www.xbrl.org/2003/instance}endDate")
    assert any("2024-01-01" in (s.text or "") for s in starts)
    assert any("2024-12-31" in (e.text or "") for e in ends)


def test_regulatory_fingerprint_fact_present(xbrl_string):
    root = ET.fromstring(xbrl_string)
    tag = "{http://climate-intelligence.platform/xbrl/provenance/2024}RegulatoryFingerprint"
    fingerprints = root.findall(f".//{tag}")
    assert len(fingerprints) >= 1


def test_esrs_methodology_fact_present(xbrl_string):
    root = ET.fromstring(xbrl_string)
    ns = "http://xbrl.efrag.org/taxonomy/draft-esrs/2023-12-22"
    methods = root.findall(f".//{{{ns}}}PhysicalRiskAssessmentMethodology")
    assert len(methods) >= 1


def test_no_empty_context_ids(xbrl_string):
    root = ET.fromstring(xbrl_string)
    contexts = root.findall("{http://www.xbrl.org/2003/instance}context")
    for ctx in contexts:
        assert ctx.attrib.get("id"), "Context missing id attribute"


def test_all_facts_reference_known_context(xbrl_string):
    root = ET.fromstring(xbrl_string)
    known_ctx = {
        c.attrib["id"]
        for c in root.findall("{http://www.xbrl.org/2003/instance}context")
    }
    for child in root:
        ctx_ref = child.attrib.get("contextRef")
        if ctx_ref is not None:
            assert ctx_ref in known_ctx, f"Fact {child.tag!r} refs unknown contextRef={ctx_ref!r}"


def test_unit_pure_declared(xbrl_string):
    root = ET.fromstring(xbrl_string)
    units = root.findall("{http://www.xbrl.org/2003/instance}unit")
    unit_ids = {u.attrib.get("id") for u in units}
    assert "u-pure" in unit_ids


def test_no_lei_means_unknown_entity(xbrl_string):
    """If lei is omitted, company name falls back gracefully — still valid XML."""
    xml_str = build_xbrl(SAMPLE_CSRD, lei_code="UNKNOWN", company_name=None)
    ET.fromstring(xml_str)  # must not raise


def test_different_lei_produces_different_xml():
    a = build_xbrl(SAMPLE_CSRD, lei_code="AAAAAAAAAAAAAAAAAAA1")
    b = build_xbrl(SAMPLE_CSRD, lei_code="BBBBBBBBBBBBBBBBBBB1")
    assert a != b


def test_xml_contains_hazard_label(xbrl_string):
    """Flood label should appear somewhere in the output."""
    assert "flood" in xbrl_string.lower() or "Flood" in xbrl_string
