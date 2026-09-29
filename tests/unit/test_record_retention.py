

def test_every_report_type_has_a_retention_mapping():
    """A report type added without one would show 'no retention mapping' on every filing of it (found live for the
    SFDR product reports, 2026-09-30)."""
    from services.governance.filings import FRAMEWORKS
    from services.governance.record_retention import rules
    assert not set(FRAMEWORKS) - set(rules()["documents"]), set(FRAMEWORKS) - set(rules()["documents"])
