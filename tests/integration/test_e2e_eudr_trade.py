"""EUDR Article 5 end to end (E122), through the HTTP API in one rolled-back transaction (Terra Foods; a reporting entity
of the test's own, so the organisation's demo status never decides what it sees — E81):

  5(1)/(3)  a trader holds its supplier's name, postal address and email and — the supplier being an operator — the
            statements' reference numbers; and its customer's; the record cannot be kept until it does
  2(17)     a trader makes products available — not a placing or an export
  5(2)      a non-SME (large) trader states its registration in the information system
  5(4)      the kept record is frozen and hashed, kept five years from the movement's date (the retention rule eudr_5_4)
  5(5)      a concern blocks the record until the authorities are informed
  5(6)      a non-SME with a substantiated concern before the movement: not until verified negligible
  4(5)      an operator's statement shows an uninformed concern as a warning
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"


def _entity(s) -> str:
    return s.execute(text("""INSERT INTO reporting_entities (entity_id, org_id, name) VALUES (gen_random_uuid(),
                             CAST(:o AS uuid), 'E122 cocoa trader') RETURNING entity_id::text"""), {"o": TERRA}).scalar()


def _party(s, table, idc, name, address=None, email=None) -> str:
    return s.execute(text(f"""INSERT INTO {table} (org_id, name, address, contact_email) VALUES (CAST(:o AS uuid), :n, :a, :e)
                              RETURNING {idc}::text"""), {"o": TERRA, "n": name, "a": address, "e": email}).scalar()


def _movement(s, ent, *, kind="making_available", role="trader", supplier=None, customer=None, supplier_role=None, refs=None,
              on="2027-02-01") -> str:
    return s.execute(text("""
        INSERT INTO eudr_movement (org_id, reporting_entity_id, kind, actor_role, planned_on, hs_code, description, customs_flow,
                                   net_mass_kg, supplier_id, customer_id, supplier_role, upstream_refs)
        VALUES (CAST(:o AS uuid), CAST(:e AS uuid), :k, :r, :d, '180100', 'Cocoa beans', false, 1000, CAST(:s AS uuid),
                CAST(:c AS uuid), :sr, :refs) RETURNING movement_id::text"""),
        {"o": TERRA, "e": ent, "k": kind, "r": role, "d": on, "s": supplier, "c": customer, "sr": supplier_role,
         "refs": refs or []}).scalar()


def _status(api, maker, checker, ent, size="small", registration=None):
    r = api.post("/v1/eudr/status", headers=maker, json={"effective_from": "2026-01-01", "size_class": size, "country": "NL",
                                                        "address": "Kade 1, Rotterdam", "entity_id": ent,
                                                        "is_registration": registration})
    assert r.status_code == 202, r.text
    d = api.post(f"/v1/approvals/{r.json()['approval_request_id']}/decide", headers=checker, json={"decision": "approved", "reason": "ok"})
    assert d.status_code == 200, d.text


def _blocking(api, h, m) -> set[str]:
    st = api.get(f"/v1/eudr/movements/{m}/trade", headers=h).json()
    return {c["rule"].split(":")[0] for c in st["checks"] if not c["passed"] and c["severity"] == "blocking"}


def test_a_trader_holds_and_keeps_the_article_5_information(api):
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    ent = _entity(s)
    sup = _party(s, "sc_suppliers", "supplier_id", "Antwerp Cocoa NV")                   # no address, no email yet
    cus = _party(s, "sc_customers", "customer_id", "Rotterdam Chocolate BV", "Weena 2, Rotterdam", "buy@choc.example")
    m = _movement(s, ent, supplier=sup, customer=cus)

    # nothing held yet: the status, the supplier's address and email, its role
    assert {"status", "supplier_address", "supplier_email", "supplier_role"} <= _blocking(api, maker, m)
    _status(api, maker, checker, ent)
    s.execute(text("UPDATE sc_suppliers SET address = 'Haven 9, Antwerp', contact_email = 'ops@cocoa.example' "
                   "WHERE supplier_id = CAST(:s AS uuid)"), {"s": sup})
    s.execute(text("UPDATE eudr_movement SET supplier_role = 'operator' WHERE movement_id = CAST(:m AS uuid)"), {"m": m})
    assert _blocking(api, maker, m) == {"references"}                     # an operator supplier: its reference numbers
    refused = api.post(f"/v1/eudr/movements/{m}/trade/keep", headers=maker)
    assert refused.status_code == 409 and "reference numbers" in refused.text
    s.execute(text("UPDATE eudr_movement SET upstream_refs = ARRAY['26BEABC0001'] WHERE movement_id = CAST(:m AS uuid)"), {"m": m})
    assert _blocking(api, maker, m) == set()

    # kept: frozen, hashed, five years from the movement's date
    k = api.post(f"/v1/eudr/movements/{m}/trade/keep", headers=maker)
    assert k.status_code == 201, k.text
    rec = api.get(f"/v1/eudr/trade-records/{k.json()['record_id']}", headers=maker).json()
    assert rec["hash_verified"] and rec["keep_until"] == "2032-02-01"
    a = rec["payload"]["record"]["art5_3_a"]
    assert a["supplier"]["postal_address"] == "Haven 9, Antwerp" and a["references"] == ["26BEABC0001"]
    assert rec["payload"]["record"]["art5_3_b"]["customer"]["email"] == "buy@choc.example"
    with pytest.raises(Exception), s.begin_nested():                     # append-only
        s.execute(text("UPDATE eudr_trade_record SET keep_until = '2028-01-01' WHERE record_id = CAST(:r AS uuid)"),
                  {"r": rec["record_id"]})

    # a concern: inform the authorities before the record is kept again
    c = api.post(f"/v1/eudr/movements/{m}/concerns", headers=maker,
                 json={"kind": "new_information", "received_on": "2027-01-20", "detail": "satellite alert near the source plots"})
    assert c.status_code == 201, c.text
    assert "informed" in _blocking(api, maker, m)
    early = api.post(f"/v1/eudr/concerns/{c.json()['concern_id']}/steps", headers=maker,
                     json={"kind": "authorities_informed", "on_date": "2027-01-10"})
    assert early.status_code == 422                                       # not before it was received
    assert api.post(f"/v1/eudr/concerns/{c.json()['concern_id']}/steps", headers=maker,
                    json={"kind": "authorities_informed", "on_date": "2027-01-21", "detail": "NVWA notified"}).status_code == 201
    assert _blocking(api, maker, m) == set()
    assert len(api.get(f"/v1/eudr/movements/{m}/trade", headers=maker).json()["kept"]) == 1


def test_who_may_do_what_and_the_non_sme_rules(api):
    s = api.s
    maker, checker = _login(api, "analyst@terra.demo", "Demo!analyst1"), _login(api, "approver@terra.demo", "Demo!approve1")
    ent = _entity(s)
    sup = _party(s, "sc_suppliers", "supplier_id", "Ghent Beans NV", "Dok 3, Ghent", "x@beans.example")
    cus = _party(s, "sc_customers", "customer_id", "Delft Sweets BV", "Markt 1, Delft", "y@sweets.example")

    # a trader makes products available — it does not export
    exp = _movement(s, ent, kind="export", supplier=sup, customer=cus, supplier_role="trader")
    assert "trader_kind" in _blocking(api, maker, exp)

    # a large (non-SME) trader: its registration (5(2)); a substantiated concern before the movement needs a verification
    _status(api, maker, checker, ent, size="large")
    m = _movement(s, ent, supplier=sup, customer=cus, supplier_role="trader")
    assert "registration" in _blocking(api, maker, m)
    _status(api, maker, checker, ent, size="large", registration="EUDR-IS-REG-0042")
    assert _blocking(api, maker, m) == set()
    cid = api.post(f"/v1/eudr/movements/{m}/concerns", headers=maker, json={
        "kind": "substantiated_concern", "received_on": "2027-01-15", "detail": "NGO report on the supplier's sourcing"}).json()["concern_id"]
    api.post(f"/v1/eudr/concerns/{cid}/steps", headers=maker, json={"kind": "authorities_informed", "on_date": "2027-01-16"})
    assert _blocking(api, maker, m) == {"verified"}
    bad = api.post(f"/v1/eudr/concerns/{cid}/steps", headers=maker, json={"kind": "verified", "on_date": "2027-01-20"})
    assert bad.status_code == 422                                         # a verification states its conclusion
    api.post(f"/v1/eudr/concerns/{cid}/steps", headers=maker,
             json={"kind": "verified", "on_date": "2027-01-20", "conclusion": "not_negligible"})
    assert _blocking(api, maker, m) == {"verified"}                       # not placed unless negligible
    api.post(f"/v1/eudr/concerns/{cid}/steps", headers=maker,
             json={"kind": "verified", "on_date": "2027-01-25", "conclusion": "negligible", "detail": "audit of the supplier"})
    assert _blocking(api, maker, m) == set()

    # an operator's movement: Article 5 does not apply; its statement shows an uninformed concern as a warning (Art. 4(5))
    op = _movement(s, ent, kind="placing", role="operator", supplier=sup)
    assert "role" in _blocking(api, maker, op)
    api.post(f"/v1/eudr/movements/{op}/concerns", headers=maker, json={
        "kind": "new_information", "received_on": "2027-01-05", "detail": "the supplier changed farms"})
    st = api.get(f"/v1/eudr/movements/{op}/statement", headers=maker).json()
    warn = [c for c in st["checks"] if c["rule"].startswith("informed:")]
    assert warn and warn[0]["severity"] == "warning" and warn[0]["ref"] == "Art. 4(5)"
