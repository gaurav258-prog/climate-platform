"""EUDR DDS assembler (services/intelligence/eudr_dds.py) — readiness + blocker gating.

A tiny fake session returns canned operator + plot rows so the assembly logic is tested without
a database. Pins the honesty gate: only deforestation-free plots are fileable, everything else is
an explicit blocker, and the operator's still-required fields are surfaced.
"""
from services.intelligence.eudr_dds import DD_STATEMENT, DD_STATEMENT_BASIS, assemble_dds
from services.intelligence.traces_client import build_submission


class _Result:
    def __init__(self, rows): self._rows = rows
    def mappings(self): return self
    def first(self): return self._rows[0] if self._rows else None
    def all(self): return self._rows


class _FakeSession:
    def __init__(self, operator, plots, customers=None):
        self._operator, self._plots, self._customers = operator, plots, customers or []
    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM organizations" in sql:
            return _Result([self._operator])
        if "FROM sc_customers" in sql:
            return _Result(self._customers)
        return _Result(self._plots)


OP_FULL = {"legal_name": "Terra Foods", "name": "Terra", "eori": "ES123",
           "operator_address": "Madrid", "country": "ES"}
OP_NO_EORI = {**OP_FULL, "eori": None}


def _plot(name, det, commodity="Cocoa", hs="1801", country="GH", area=2.0, year=None,
         supplier_name=None, supplier_address=None, supplier_contact_email=None, supplier_country=None):
    return {"plot_id": name, "plot_name": name, "country": country, "plot_geometry": None,
            "lat": 6.7, "lon": -1.6, "area_ha": area, "eudr_determination": det,
            "eudr_first_loss_year": year, "eudr_forest_source": "GFC-2024-v1.12",
            "commodity": commodity, "hs_code": hs,
            "supplier_name": supplier_name, "supplier_address": supplier_address,
            "supplier_contact_email": supplier_contact_email, "supplier_country": supplier_country}


def test_ready_when_all_free_and_operator_complete():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free"), _plot("B", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert dds["ready"] and dds["fileable_plots"] == 2 and not dds["blockers"]
    assert dds["items"][0]["hs_code"] == "1801" and dds["items"][0]["countries_of_production"] == ["GH"]


def test_non_compliant_plot_blocks_and_is_excluded():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free"), _plot("B", "non_compliant", year=2022)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["fileable_plots"] == 1
    assert len(dds["blockers"]) == 1 and dds["blockers"][0]["plot"] == "B"
    assert "2022" in dds["blockers"][0]["reason"]


def test_missing_operator_identity_blocks_readiness():
    s = _FakeSession(OP_NO_EORI, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert not dds["ready"]
    assert any("eori" in c for c in dds["operator_completes"])


def test_geolocation_incomplete_is_a_blocker():
    s = _FakeSession(OP_FULL, [_plot("A", "geolocation_incomplete", area=9.0)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["fileable_plots"] == 0
    assert "polygon" in dds["blockers"][0]["reason"]


def test_not_determined_plot_is_a_blocker():
    s = _FakeSession(OP_FULL, [_plot("A", None)])
    dds = assemble_dds(s, "org")
    assert not dds["ready"] and dds["blockers"][0]["determination"] == "not_determined"


def test_annex2_scientific_name_supplied_for_known_species():
    # Art. 9(1)(b): cocoa is a single-species commodity — we supply the canonical scientific name, not the operator
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free", commodity="Cocoa")])
    dds = assemble_dds(s, "org")
    it = dds["items"][0]
    assert it["scientific_name"] == "Theobroma cacao"
    assert it["trade_name"] == "Cocoa" and "Cocoa" in it["description"]
    # since the species is known, the operator is NOT asked to supply it
    assert not any("scientific name" in c for c in dds["operator_completes"])


def test_annex2_scientific_name_routed_to_operator_for_variable_species():
    # wood spans many tree species → we don't guess; the operator supplies the species name
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free", commodity="Wood", hs="4407")])
    dds = assemble_dds(s, "org")
    assert dds["items"][0]["scientific_name"] is None
    assert any("scientific name" in c and "Wood" in c for c in dds["operator_completes"])


def test_annex2_production_date_range_carried_and_flagged():
    # Art. 9(1)(d): the date/time-range column exists on every plot (operator fills it) and is flagged as a to-do
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert dds["items"][0]["plots"][0]["production_date_range"] is None
    assert any("date or time-range of production" in c for c in dds["operator_completes"])


def test_dd_statement_is_verbatim_annex_ii_item_5():
    # Regulation (EU) 2023/1115 Annex II item 5 — exact mandated text, character for character.
    # Must attest "no OR only a negligible risk" (either claim), never collapsed to just "negligible".
    assert DD_STATEMENT == (
        "By submitting this due diligence statement the operator confirms that due diligence in "
        "accordance with Regulation (EU) 2023/1115 was carried out and that no or only a negligible "
        "risk was found that the relevant products do not comply with Article 3, point (a) or (b), "
        "of that Regulation."
    )
    assert "no or only a negligible risk" in DD_STATEMENT
    assert "negligible risk exists" not in DD_STATEMENT


def test_dd_statement_has_no_appended_prose():
    # The statutory text must stand alone — supporting context belongs in a separate field only.
    assert DD_STATEMENT.strip().endswith(".")
    assert "geolocation" not in DD_STATEMENT and "satellite" not in DD_STATEMENT
    assert "geolocation" in DD_STATEMENT_BASIS


def test_assembled_dds_carries_statement_and_basis_separately():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert dds["statement"] == DD_STATEMENT
    assert dds["statement_basis"] == DD_STATEMENT_BASIS


def test_traces_submission_envelope_carries_verbatim_statement_unmodified():
    # traces_client.build_submission() must pass DD_STATEMENT through to dueDiligenceStatement
    # byte-for-byte — nothing concatenated onto it.
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    envelope = build_submission(dds, "org")
    assert envelope["dueDiligenceStatement"] == DD_STATEMENT


# ── Art. 9(1)(e)/(f): supplier + downstream-customer identity (build 1) ─────────────────────────

def test_supplier_identity_joined_and_carried_on_the_item():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free", supplier_name="Arabica Co-op",
                                     supplier_address="Rua X, Minas Gerais", supplier_contact_email="ops@coop.br",
                                     supplier_country="BR")])
    dds = assemble_dds(s, "org")
    sups = dds["items"][0]["suppliers"]
    assert len(sups) == 1
    assert sups[0] == {"name": "Arabica Co-op", "address": "Rua X, Minas Gerais",
                        "contact_email": "ops@coop.br", "country": "BR"}
    # complete supplier identity → not flagged as a to-do
    assert not any("Arabica Co-op" in c for c in dds["operator_completes"])


def test_plot_with_no_supplier_linked_is_flagged_not_silently_absent():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")])   # no supplier_name
    dds = assemble_dds(s, "org")
    assert dds["items"][0]["suppliers"] == []
    assert any("Art. 9(1)(e)" in c and "A" in c for c in dds["operator_completes"])


def test_supplier_missing_address_or_email_is_flagged():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free", supplier_name="Arabica Co-op",
                                     supplier_country="BR")])   # no address/email
    dds = assemble_dds(s, "org")
    assert any("Art. 9(1)(e)" in c and "Arabica Co-op" in c for c in dds["operator_completes"])


def test_multiple_plots_same_supplier_dedupe_to_one_record():
    s = _FakeSession(OP_FULL, [
        _plot("A", "deforestation_free", supplier_name="Arabica Co-op", supplier_address="X", supplier_contact_email="a@b.com"),
        _plot("B", "deforestation_free", supplier_name="Arabica Co-op", supplier_address="X", supplier_contact_email="a@b.com"),
    ])
    dds = assemble_dds(s, "org")
    assert len(dds["items"][0]["suppliers"]) == 1
    assert dds["items"][0]["plot_count"] == 2


def test_no_customers_on_file_is_flagged_not_silently_absent():
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")], customers=[])
    dds = assemble_dds(s, "org")
    assert dds["customers"] == []
    assert any("Art. 9(1)(f)" in c and "none on file" in c for c in dds["operator_completes"])


def test_customer_on_file_is_carried_and_not_flagged_when_complete():
    cust = {"name": "Nordic Retail AB", "address": "Stockholm", "contact_email": "buy@nordic.se", "country": "SE"}
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")], customers=[cust])
    dds = assemble_dds(s, "org")
    assert dds["customers"] == [cust]
    assert not any("Nordic Retail AB" in c for c in dds["operator_completes"])


def test_customer_on_file_missing_contact_is_flagged():
    cust = {"name": "Nordic Retail AB", "address": None, "contact_email": None, "country": "SE"}
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")], customers=[cust])
    dds = assemble_dds(s, "org")
    assert any("Art. 9(1)(f)" in c and "Nordic Retail AB" in c for c in dds["operator_completes"])


def test_legality_of_production_evidence_always_flagged_art_9_1_h():
    # Art. 9(1)(h) legality-of-production evidence is never computed by this platform — always surfaced,
    # never silently absent, exactly like every other honest gap in operator_completes.
    s = _FakeSession(OP_FULL, [_plot("A", "deforestation_free")])
    dds = assemble_dds(s, "org")
    assert any("Art. 9(1)(h)" in c and "legality" in c for c in dds["operator_completes"])
