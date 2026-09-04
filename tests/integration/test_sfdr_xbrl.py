"""SFDR PAI XBRL export — well-formed instance with tagged facts. Requires PostgreSQL."""
from __future__ import annotations

import uuid
from xml.dom import minidom

import pytest
from sqlalchemy import text

from core.db.session import get_session
from ml.regulatory.sfdr_pai import sfdr_pai_statement
from ml.regulatory.sfdr_xbrl import TPAI_NS, XBRLI_NS, sfdr_pai_xbrl

DEMO_ORG = "44444444-4444-4444-8444-444444444444"


@pytest.mark.integration
def test_xbrl_is_wellformed_and_tags_waci():
    org = str(uuid.uuid4())
    created = {}
    with get_session() as s:
        s.execute(text("INSERT INTO organizations (org_id,name,type,country,lei,legal_name) "
                       "VALUES (:o,'XBRL Mgr','asset_manager','LU','529900T8BM49AURSDO55','XBRL Mgr SA')"), {"o": org})
        fid = str(s.execute(text("INSERT INTO funds (org_id,name,fund_type,sfdr_classification) "
                                 "VALUES (:o,'XBRL Fund','fund','article_8') RETURNING fund_id"), {"o": org}).scalar())
        iid = str(s.execute(text("INSERT INTO issuers (name,issuer_type,country,nace_code,source) "
                                 "VALUES ('XBRL Issuer','corporate','DE','35.11','manual') RETURNING issuer_id")).scalar())
        sid = str(s.execute(text("INSERT INTO securities (isin,name,issuer_id,asset_class,source) "
                                 "VALUES ('DE00XBRL0001','S',:i,'equity','manual') RETURNING security_id"), {"i": iid}).scalar())
        s.execute(text("INSERT INTO issuer_emissions (issuer_id,org_id,reporting_year,scope1_tco2e,scope2_tco2e,revenue_eur,source) "
                       "VALUES (:i,:o,2023,1000000,0,10000000000,'client')"), {"i": iid, "o": org})
        s.execute(text("INSERT INTO fund_positions (fund_id,security_id,market_value_eur,weight_pct,as_of_date) "
                       "VALUES (:f,:s,5000000,100,'2026-07-12')"), {"f": fid, "s": sid})
        created = {"fid": fid, "iid": iid, "org": org}

    try:
        with get_session() as s:
            stmt = sfdr_pai_statement(s, created["fid"])
            xml = sfdr_pai_xbrl(stmt)
        # well-formed
        dom = minidom.parseString(xml)
        assert dom.documentElement.localName == "xbrl"
        # WACI fact present with the value, and the manager LEI in the context
        assert "tpai:WACI" in xml
        assert "529900T8BM49AURSDO55" in xml
        assert TPAI_NS in xml and XBRLI_NS in xml
        # the WACI value (100.0) tagged
        waci = next(i for i in stmt["indicators"] if i["number"] == 3)["value"]
        assert f">{waci}<" in xml
    finally:
        with get_session() as s:
            s.execute(text("DELETE FROM funds WHERE fund_id=:f"), {"f": created["fid"]})
            s.execute(text("DELETE FROM securities WHERE isin='DE00XBRL0001'"))
            s.execute(text("DELETE FROM issuers WHERE issuer_id=:i"), {"i": created["iid"]})
            s.execute(text("DELETE FROM organizations WHERE org_id=:o"), {"o": created["org"]})


@pytest.mark.integration
def test_sfdr_ixbrl_is_wellformed_and_inline_tags_waci():
    """SFDR now also emits Inline XBRL (iXBRL) — one document a person reads and a machine parses — sharing
    the ESRS tagger's serialization core."""
    from xml.dom import minidom

    from ml.regulatory.sfdr_xbrl import sfdr_pai_ixbrl, sfdr_pai_xbrl
    with get_session() as s:
        fid = s.execute(text("SELECT fund_id::text FROM funds LIMIT 1")).scalar()
        if not fid:
            pytest.skip("no fund")
        st = sfdr_pai_statement(s, fid)
        if st.get("error"):
            pytest.skip("no SFDR statement")
        doc = sfdr_pai_ixbrl(st)
        dom = minidom.parseString(doc)                     # well-formed XHTML
        assert dom.documentElement.localName == "html"
        assert "ix:nonFraction" in doc and "tpai:" in doc  # facts are inline-tagged
        # the plain XBRL and the inline form tag the SAME value for a given indicator
        xml = sfdr_pai_xbrl(st)
        waci = next((i["value"] for i in st.get("indicators", []) if i.get("number") == 3 and i.get("value") is not None), None)
        if waci is not None:
            assert f">{waci}<" in xml and f">{waci}<" in doc
