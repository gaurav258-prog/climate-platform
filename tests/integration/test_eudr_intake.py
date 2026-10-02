"""EUDR layer 2 (E92): the parties, the placings / exports and the plots they came from arrive through the governed intake —
checked, matched on the undertaking's own ids, landed; refused rows say why. One rolled-back transaction (Terra Foods).

  suppliers / customers   name, own id, postal address, email (Art. 9(1)(e)-(f)); a row without an email is refused
  plots                   a plot names its supplier; the decimals its coordinates were sent with are kept (Art. 2(28):
                          'at least six decimal digits')
  movements               customs goods without kilograms of net mass, an unknown supplier, a malformed HS code: refused;
                          a file sent again updates the movement (same id); a movement in a statement under review is not
                          changed by a file
  movement plots          the plots and production date range; reversed dates and unknown plots refused
  HTTP                    the template and the dry run of each book
"""
from __future__ import annotations

import uuid

import pandas as pd
import pytest
from sqlalchemy import text

from services.intake import pipeline
from tests.integration.conftest import login as _login

pytestmark = pytest.mark.integration
TERRA = "55555555-5555-4555-8555-555555555555"


def _csv(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


def _admin(s) -> str:
    return s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@terra.demo'")).scalar()


def _send(s, user, book, rows, tag, ok=True, reason=None):
    out = pipeline.submit(s, TERRA, book, _csv(rows), f"{tag}-{book}.csv", user_id=user, reason=reason)
    if ok:
        assert out["state"] == "imported", (out.get("controls", {}).get("gate"), out.get("errors"))
    return out


def _refused(s, user, book, rows, tag) -> dict:
    """Every row refused, with its reason: nothing is landed (an all-refused file is rejected outright)."""
    with pytest.raises(pipeline.IntakeError) as e:
        _send(s, user, book, rows, tag, ok=False, reason="checking what is refused and why")
    detail = e.value.body
    assert detail.get("state") == "rejected", detail
    return {x["row"]: " ".join(x["problems"]) for x in detail["errors"]}


def test_eudr_records_arrive_through_the_governed_intake(session_rolled_back):
    s, tag, user = session_rolled_back, uuid.uuid4().hex[:6], None
    user = _admin(s)
    sup, cus = f"SUP-{tag}", f"CUS-{tag}"

    # parties
    bad = _refused(s, user, "eudr_suppliers", [{"party_name": "No Mail Co-op", "party_ref": f"X-{tag}", "address": "Kumasi", "contact_email": ""}], tag)
    assert "Email is required" in bad[2]
    _send(s, user, "eudr_suppliers", [{"party_name": "Ashanti Cocoa Co-op", "party_ref": sup, "address": "PO Box 1, Kumasi, GH",
                                       "contact_email": "trade@ashanti.example", "country": "GH", "trade_name": "Golden Bean"}], tag)
    _send(s, user, "eudr_customers", [{"party_name": "Choco Fabriek BV", "party_ref": cus, "address": "Kade 1, Zaandam, NL",
                                       "contact_email": "buy@choco.example", "country": "NL"}], tag)
    sid = s.execute(text("SELECT supplier_id::text FROM sc_suppliers WHERE org_id = CAST(:o AS uuid) AND external_ref = :r"),
                    {"o": TERRA, "r": sup}).scalar()
    assert sid

    # plots: a supplier and the precision the coordinates were sent with
    plots = [{"plot_name": f"EUDR {tag} A", "latitude": "6.694400", "longitude": "-1.605500", "commodity": "Cocoa",
              "annual_spend_eur": "10000", "external_ref": f"PL-{tag}-A", "supplier_ref": sup, "country": "GH", "currency": "EUR", "book_date": "2025-12-31"},
             {"plot_name": f"EUDR {tag} B", "latitude": "6.69", "longitude": "-1.60", "commodity": "Cocoa",
              "annual_spend_eur": "5000", "external_ref": f"PL-{tag}-B", "supplier_ref": sup, "country": "GH", "currency": "EUR", "book_date": "2025-12-31"}]
    _send(s, user, "supply_plots", plots, tag)
    got = dict(s.execute(text("""SELECT external_ref, coordinate_decimals FROM sc_sourcing_plots WHERE org_id = CAST(:o AS uuid)
                                 AND external_ref LIKE :t AND supplier_id = CAST(:s AS uuid)"""),
                         {"o": TERRA, "t": f"PL-{tag}-%", "s": sid}).all())
    assert got == {f"PL-{tag}-A": 6, f"PL-{tag}-B": 2}

    # movements
    mv = {"movement_ref": f"SHP-{tag}", "movement_kind": "placing", "actor_role": "operator", "planned_on": "2027-01-15",
          "hs_code": "1801.00", "description": "Cocoa beans, whole, raw", "customs_flow": "true", "net_mass_kg": "25000",
          "supplier_ref": sup, "customer_ref": cus}
    bad = _refused(s, user, "eudr_movements", [{**mv, "movement_ref": f"B1-{tag}", "net_mass_kg": None},
                                               {**mv, "movement_ref": f"B2-{tag}", "supplier_ref": "NOBODY"},
                                               {**mv, "movement_ref": f"B3-{tag}", "hs_code": "18"}], tag)
    assert "kilograms of net mass" in bad[2] and "not in your suppliers" in bad[3] and "4, 6, 8 or 10 digits" in bad[4]
    _send(s, user, "eudr_movements", [mv], tag)
    m = s.execute(text("""SELECT movement_id::text, hs_code, CAST(net_mass_kg AS FLOAT), supplier_id::text FROM eudr_movement
                          WHERE org_id = CAST(:o AS uuid) AND external_ref = :r"""), {"o": TERRA, "r": f"SHP-{tag}"}).one()
    assert m[1:] == ("180100", 25000.0, sid)
    _send(s, user, "eudr_movements", [{**mv, "net_mass_kg": "26000"}], f"{tag}-2")          # sent again: the same movement
    assert s.execute(text("SELECT count(*), max(CAST(net_mass_kg AS FLOAT)) FROM eudr_movement WHERE external_ref = :r"),
                     {"r": f"SHP-{tag}"}).one() == (1, 26000.0)

    # the plots it came from
    links = [{"movement_ref": f"SHP-{tag}", "plot_ref": f"PL-{tag}-A", "production_from": "2025-10-01", "production_to": "2026-03-31"},
             {"movement_ref": f"SHP-{tag}", "plot_ref": f"PL-{tag}-B", "production_from": "2025-10-01", "production_to": "2026-03-31"}]
    bad = _refused(s, user, "eudr_movement_plots", [{**links[0], "production_to": "2025-01-01"},
                                                    {**links[0], "plot_ref": "NOWHERE"}], tag)
    assert "before produced from" in bad[2] and "not one of your plots" in bad[3]
    _send(s, user, "eudr_movement_plots", links, tag)
    assert s.execute(text("SELECT count(*) FROM eudr_movement_plot WHERE movement_id = CAST(:m AS uuid)"), {"m": m[0]}).scalar() == 2

    # once in a statement under review, a file does not change it
    s.execute(text("""INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, eudr_movement_id)
                      VALUES (CAST(:o AS uuid), 'eudr_dds', '2027-12-31', 'T · 2027-12-31', 'in_review', CAST(:m AS uuid))"""),
              {"o": TERRA, "m": m[0]})
    bad = _refused(s, user, "eudr_movements", [{**mv, "net_mass_kg": "1"}], f"{tag}-3")
    assert "under review or filed" in bad[2]
    bad = _refused(s, user, "eudr_movement_plots", [links[0]], f"{tag}-3")
    assert "its plots cannot change" in bad[2]


def test_each_eudr_book_has_its_template_and_dry_run(api):
    h = _login(api, "analyst@terra.demo", "Demo!analyst1")
    for book in ("eudr_suppliers", "eudr_customers", "eudr_movements", "eudr_movement_plots"):
        r = api.get(f"/v1/eudr/intake/{book}/template.xlsx", headers=h)
        assert r.status_code == 200 and r.content[:2] == b"PK", book
    assert api.get("/v1/eudr/intake/nope/template.xlsx", headers=h).status_code == 404
    row = {"movement_ref": "DRY-1", "movement_kind": "export", "actor_role": "operator", "planned_on": "2027-02-01",
           "hs_code": "090111", "description": "Coffee, not roasted", "customs_flow": "true", "net_mass_kg": "1200"}
    r = api.post("/v1/eudr/intake/eudr_movements/validate", headers=h, files={"file": ("m.csv", _csv([row]), "text/csv")})
    assert r.status_code == 200, r.text
    assert not api.s.execute(text("SELECT 1 FROM eudr_movement WHERE external_ref = 'DRY-1'")).first()    # nothing saved
    assert api.get("/v1/eudr/movements", headers=h).status_code == 200


@pytest.mark.parametrize("book", ["eudr_suppliers", "eudr_customers", "eudr_movements", "eudr_movement_plots"])
def test_an_eudr_book_in_the_customers_own_layout_gets_a_mapping_proposal(book, session_rolled_back):
    """The EUDR books are records, not located assets (outside the every-sector asset journey): a file in the customer's
    own column names is not refused blindly — each required field is proposed from its aliases."""
    from services.ingest.upload_validation import enrich_specs
    from services.intake.catalog import TEMPLATES
    specs = [x for x in enrich_specs(TEMPLATES[book].specs(None)) if x["required"]]
    row = {(x.get("aliases") or [x["label"]])[0]: x["example"] for x in specs}
    with pytest.raises(pipeline.IntakeError) as e:
        pipeline.preview(session_rolled_back, TERRA, book, _csv([row]), "theirs.csv")
    from services.intake import profiling
    body = e.value.body
    assert body["error"] == "missing_columns"
    proposal = profiling.column_map(body["suggestion"])
    assert {x["name"] for x in specs} <= set(proposal), {x["name"] for x in specs} - set(proposal)
