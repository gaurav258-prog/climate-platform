"""Machine-readable exports must render from the FROZEN snapshot, not a live rebuild — the file you
download is provably the bytes that were attested. Requires PostgreSQL; read-only."""
from __future__ import annotations

import io
import json
import zipfile

import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.governance.filing_export import ExportError, export_filing

BANK_ORG = "11111111-1111-4111-8111-111111111111"


def _a_frozen_bank_filing(session):
    return session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND framework = 'bank_tcfd' "
        "AND snapshot_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"), {"o": BANK_ORG}).scalar()


@pytest.mark.integration
def test_json_export_carries_and_reverifies_the_frozen_hash():
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        name, media, content = export_filing(s, BANK_ORG, fid, "json")
        rec = json.loads(content)
        # the snapshot's own recorded hash, and it verified on read
        assert rec["payload_sha256"] and rec["hash_verified"] is True
        # filename ties the artifact to the exact frozen version + hash
        assert rec["payload_sha256"][:8] in name and f"v{rec['snapshot_version']}" in name
        assert media == "application/json"


@pytest.mark.integration
def test_xlsx_export_is_a_real_workbook():
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        name, media, content = export_filing(s, BANK_ORG, fid, "xlsx")
        assert name.endswith(".xlsx") and "spreadsheet" in media
        zf = zipfile.ZipFile(io.BytesIO(content))          # a .xlsx is a zip
        assert any(n.startswith("xl/") for n in zf.namelist())


@pytest.mark.integration
def test_xbrl_export_is_well_formed_and_reflects_frozen_figures():
    import xml.dom.minidom as minidom
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        name, media, content = export_filing(s, BANK_ORG, fid, "xbrl")
        assert name.endswith(".xbrl") and media == "application/xml"
        doc = minidom.parseString(content)                 # raises if not well-formed
        assert doc.documentElement.tagName.endswith("xbrl")
        # the total-book-value fact must equal the frozen payload's rollup, not a live recompute
        from services.governance.filings import get_filing
        payload = get_filing(s, BANK_ORG, fid, with_payload=True)["snapshot"]["payload"]
        frozen_total = round(payload["rollup"]["total_value_eur"])
        assert str(frozen_total) in content.decode()


@pytest.mark.integration
def test_unavailable_format_is_refused():
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        with pytest.raises(ExportError):
            export_filing(s, BANK_ORG, fid, "pdf")


def _a_frozen_p3esg_filing(session):
    return session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND framework = 'bank_p3esg' "
        "AND snapshot_id IS NOT NULL ORDER BY created_at DESC LIMIT 1"), {"o": BANK_ORG}).scalar()


@pytest.mark.integration
def test_pillar3_xbrl_export_is_well_formed_with_gar_and_emissions():
    import xml.etree.ElementTree as ET
    with get_session() as s:
        fid = _a_frozen_p3esg_filing(s)
        if not fid:
            pytest.skip("no frozen bank_p3esg filing")
        name, media, content = export_filing(s, BANK_ORG, fid, "xbrl")
        assert name.endswith(".xbrl") and media == "application/xml"
        root = ET.fromstring(content)                      # well-formed
        facts = {el.tag.rsplit("}", 1)[-1] for el in root if el.get("contextRef")}
        # the Pillar 3 headline figures are tagged as facts (GAR grid + financed emissions + physical risk)
        assert {"GARTotalAssets", "GAREligibleExposure", "GARAlignedExposure"} <= facts
        assert {"FinancedEmissionsScope3", "PhysicalRiskSensitiveExposure"} <= facts
        # every fact carries a unit reference (valid xbrli instance)
        assert all(el.get("unitRef") for el in root if el.get("contextRef"))


TERRA_ORG = "55555555-5555-4555-8555-555555555555"


@pytest.mark.integration
def test_esrs_pack_tags_the_pack_as_xbrl_and_ixbrl():
    """ESRS filings now export through the shared iXBRL engine, tagged from the (frozen) pack — WORM-faithful,
    like the bank path — under the official-intent EFRAG profile."""
    import xml.dom.minidom as minidom

    from services.governance.filing_export import _ixbrl, _xbrl
    from services.intelligence.esrs_nature import build_esrs_pack
    from services.intelligence.esrs_xbrl import build_facts
    with get_session() as s:
        pack = build_esrs_pack(s, TERRA_ORG)
        facts = build_facts(s, TERRA_ORG, pack=pack)["facts"]
        if not facts:
            pytest.skip("no ESRS facts for Terra Foods")
        basis = {"reporting_period_end": "2024-12-31"}
        val = str(facts[0]["value"])                      # a frozen figure that must survive into the tags
        xml = _xbrl(s, TERRA_ORG, "esrs_pack", pack, basis)
        minidom.parseString(xml)                          # well-formed XBRL
        assert "esrs:" in xml and val in xml and "2024-12-31" in xml
        doc = _ixbrl(s, TERRA_ORG, "esrs_pack", pack, basis)
        minidom.parseString(doc)                          # iXBRL is well-formed XHTML
        assert val in doc                                 # the frozen figure is inline-tagged, human + machine


@pytest.mark.integration
def test_ixbrl_is_offered_for_esrs_and_refused_elsewhere():
    from services.governance.filing_export import _ixbrl, formats_for
    assert "ixbrl" in formats_for("esrs_pack") and "xbrl" in formats_for("esrs_pack")
    with pytest.raises(ExportError):
        _ixbrl(None, "x", "bank_tcfd", {}, {})            # only ESRS emits iXBRL today
