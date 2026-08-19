"""The assurance pack's two evidence extras — a self-contained data-lineage graph and a real, rendered
PDF cover (dependency-free writer). Pure: no DB, no third-party PDF library."""
import io

import pdfplumber

from services.governance.assurance_pack import (
    _lineage_html,
    _pdf_escape,
    _render_cover_pdf,
)

_SNAP = {"report_type": "bank_p3esg", "version": 4, "payload_sha256": "a" * 64,
         "hash_verified": True, "engine_versions": {
             "impact_version": "sc-impact-v0.5", "fit_versions": ["ranged-fit-v0.1"],
             "code_version": "3f90407", "ranged_floor": 0.4,
             "feed_maturity": {"climate_reanalysis": "live", "flood": "proxy", "wdpa": "planned"},
             "feed_freshness_at_freeze": {"climate_reanalysis": "fresh", "flood": "overdue"}}}
_BASIS = {"scenario": "baseline", "horizon": "current", "materiality_threshold": 0.05,
          "reporting_period_end": "2025-12-31"}


def test_pdf_escape_handles_pdf_delimiters():
    assert _pdf_escape("a(b)c\\d") == r"a\(b\)c\\d"


def test_render_cover_pdf_is_a_valid_openable_pdf():
    blob = _render_cover_pdf("Assurance evidence pack", [
        ("Entity X · bank_p3esg v4", "head"),
        ("Honesty gate", "head"),
        ("r2 >= 0.40 or the euro is withheld.", "normal"),
    ])
    assert blob[:5] == b"%PDF-"
    assert blob.rstrip().endswith(b"%%EOF")
    assert b"xref" in blob
    # it actually opens and the text is extractable (proves the xref offsets are correct)
    with pdfplumber.open(io.BytesIO(blob)) as pdf:
        assert len(pdf.pages) == 1
        txt = pdf.pages[0].extract_text() or ""
    assert "Assurance evidence pack" in txt
    assert "Honesty gate" in txt


def test_lineage_html_renders_chain_and_feed_provenance():
    html = _lineage_html("Entity X", _SNAP, _BASIS, _SNAP["engine_versions"])
    # the five-stage source→filing chain
    assert html.count("border-left:4px") == 5
    # feeds mapped to their authoritative source name + maturity/freshness
    assert "Copernicus / ECMWF ERA5" in html
    assert "JRC GloFAS" in html or "GloFAS" in html
    assert "planned" in html and "overdue" in html
    # engine + snapshot identity threaded through
    assert "sc-impact-v0.5" in html and "bank_p3esg v4" in html


def test_lineage_html_no_feed_maturity_is_safe():
    snap = {**_SNAP, "engine_versions": {}}
    html = _lineage_html("Entity X", snap, _BASIS, {})
    assert "No feed maturity recorded" in html
    assert html.count("border-left:4px") == 5  # the chain still renders
