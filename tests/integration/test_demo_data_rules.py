"""E147: the demo never carries invented data for a real named company — no demo organisation holds data of its own
(emissions, ESG metrics, Taxonomy KPIs, voluntary PAI values, confirmations) about an issuer that is not one of the
fictional demo issuers (LEI beginning 'DEMO'), and no demo fund holds a real company's security. Reads the database
as it is (the demo seeds), changes nothing."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from services.issuer_client_data import issuers_with_own_data

pytestmark = pytest.mark.integration


def test_no_demo_organisation_holds_its_own_data_about_a_real_company(session_rolled_back):
    s = session_rolled_back
    found = {}
    for org_id, name in s.execute(text("SELECT org_id::text, name FROM organizations WHERE name LIKE '%(demo)%'")).all():
        real = [i["name"] for i in issuers_with_own_data(s, org_id) if not (i["lei"] or "").startswith("DEMO")]
        if real:
            found[name] = real[:5]
    assert not found, found


def test_no_demo_fund_holds_a_real_company(session_rolled_back):
    held = session_rolled_back.execute(text("""
        SELECT DISTINCT o.name || ': ' || i.name FROM fund_positions p JOIN funds f ON f.fund_id = p.fund_id
        JOIN organizations o ON o.org_id = f.org_id JOIN securities sec ON sec.security_id = p.security_id
        JOIN issuers i ON i.issuer_id = sec.issuer_id
        WHERE o.name LIKE '%(demo)%' AND i.lei NOT LIKE 'DEMO%' LIMIT 5""")).scalars().all()
    assert not held, held
