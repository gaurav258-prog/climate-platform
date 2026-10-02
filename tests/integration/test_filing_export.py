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
        "AND snapshot_id IS NOT NULL AND status NOT IN ('withdrawn', 'superseded') "   # a discarded draft is no filing
        "ORDER BY created_at DESC LIMIT 1"), {"o": BANK_ORG}).scalar()


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
def test_the_taxonomy_report_has_no_xbrl():
    """No official XBRL binding of the Annex VI templates is held: the bank_tcfd XBRL under a Tellumen-made namespace was
    removed (E95) — the report exports JSON and the templates in a workbook; an XBRL request is refused."""
    from services.governance.filing_export import _xbrl, formats_for
    assert formats_for("bank_tcfd") == ("json", "xlsx")
    with pytest.raises(ExportError):
        _xbrl(None, "x", "bank_tcfd", {}, {})
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        with pytest.raises(ExportError):
            export_filing(s, BANK_ORG, fid, "xbrl")


@pytest.mark.integration
def test_unavailable_format_is_refused():
    with get_session() as s:
        fid = _a_frozen_bank_filing(s)
        if not fid:
            pytest.skip("no frozen bank filing")
        with pytest.raises(ExportError):
            export_filing(s, BANK_ORG, fid, "pdf")


@pytest.mark.integration
def test_pillar3_has_no_xbrl_until_the_eba_taxonomy_is_bound():
    """E104: the Pillar 3 XBRL was an instance under a Tellumen-made namespace (taxonomy.tellumen.eu) — not a filing. It
    is removed, as E95 / E60 did: the report exports JSON and the templates in a workbook, and an XBRL request for a
    filing of any date is refused. The Pillar 3 Tellumen-made namespace is left nowhere in the code."""
    from pathlib import Path

    from services.governance.filing_export import _xbrl, formats_for
    assert formats_for("bank_p3esg") == ("json", "xlsx")
    with pytest.raises(ExportError):
        _xbrl(None, "x", "bank_p3esg", {}, {})
    root = Path(__file__).resolve().parents[2]
    assert not (root / "config" / "eba_p3esg_binding.json").exists()
    for d in ("services", "api", "ml"):
        for f in (root / d).rglob("*.py"):
            assert "taxonomy.tellumen.eu" not in f.read_text(), f      # no Tellumen-made taxonomy of any kind (E113)


@pytest.mark.integration
def test_sfdr_pai_has_no_xbrl_until_an_official_taxonomy_exists():
    """E113: the SFDR PAI XBRL / iXBRL were instances under a Tellumen-made namespace (taxonomy.tellumen.eu/sfdr/pai) —
    no official SFDR PAI taxonomy is held. Removed as E104 did for Pillar 3: the filing exports JSON and xlsx, an
    (i)XBRL request for a filing of any date is refused, and the fund routes answer 410."""
    from fastapi.testclient import TestClient

    from api.main import app
    from services.governance.filing_export import _ixbrl, _xbrl, formats_for
    assert formats_for("sfdr_pai") == ("json", "xlsx")
    for fn in (_xbrl, _ixbrl):
        with pytest.raises(ExportError):
            fn(None, "x", "sfdr_pai", {}, {})
    c = TestClient(app)
    for path in ("/v1/funds/00000000-0000-0000-0000-000000000000/sfdr-statement.xbrl",
                 "/v1/funds/00000000-0000-0000-0000-000000000000/sfdr-statement.ixbrl", "/v1/entity/sfdr-statement.xbrl"):
        r = c.get(path)
        assert r.status_code == 410 and "no official SFDR PAI XBRL taxonomy is held" in r.text, path


TERRA_ORG = "55555555-5555-4555-8555-555555555555"


@pytest.mark.integration
def test_esrs_statement_exports_json_only():
    """ESRS is tagged with EFRAG's ESRS XBRL taxonomy, whose binding is not built: no (i)XBRL with invented names."""
    from services.governance.filing_export import _ixbrl, _xbrl, formats_for
    assert formats_for("esrs_pack") == ("json",)
    for fn in (_xbrl, _ixbrl):
        with pytest.raises(ExportError):
            fn(None, "x", "esrs_pack", {}, {})
    with pytest.raises(ExportError):
        _ixbrl(None, "x", "bank_tcfd", {}, {})            # no iXBRL for any report type (E60, E113)
