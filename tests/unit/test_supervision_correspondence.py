"""Formal correspondence: references follow the authority's format, the legal basis always cites an act, letters render."""
from services.supervision.correspondence import render_letter
from services.supervision.mandates import registry


def test_correspondence_config_covers_every_kind_and_sector():
    c = registry()["correspondence"]
    from services.supervision.engagement import kinds
    from services.supervision.profiles import registry as profiles
    assert set(kinds()) <= set(c["kind_codes"])
    assert set(profiles()["sectors"]) <= set(c["supervisory_powers"])
    for p in c["supervisory_powers"].values():
        assert p["ref"] and p["url"]
    assert c["reference_format"].format(prefix="EBS", year=2026, kind_code="IR", seq=7) == "EBS-2026-IR-0007"


def test_letter_renders_with_reference_basis_and_signatory():
    pdf = render_letter({"reference": "EBS-2026-FN-0001", "issued_at": "2026-09-09T15:00:00+00:00", "regulator": "EU Banking Supervisor", "entity": "Bank",
                         "entity_legal_name": "Bank SA", "entity_lei": "5493000000000000TEST", "kind": "finding", "kind_label": "Finding", "title": "Sensitivity overstated",
                         "body": "Please explain.", "severity": "high", "due_date": "2026-11-08", "response_days": 60,
                         "legal_basis": {"ref": "Art. 104 CRD", "text": "Powers.", "url": "https://eur-lex.europa.eu/"}, "signatory": "S. Supervisor, Head"})
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1500
