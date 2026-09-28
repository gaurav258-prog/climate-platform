"""Units read from past filings (multi-currency phase 4): money → ISO code, magnitude words scale the value, XBRL unit
measures resolve, and nothing is guessed."""
import pytest

from services.ingest.filing_import import extract, parse_number
from services.ingest.units import from_measure, from_text, normalise


@pytest.mark.parametrize("s,unit,scale", [
    ("€12.3m", "EUR", 1e6), ("USD 5,000", "USD", 1), ("Total assets (USD thousands)", "USD", 1e3),
    ("£1.2bn", "£", 1e9), ("CHF 12 Mio.", "CHF", 1e6), ("12.5%", "%", 1), ("Scope 1 (tCO2e)", "tCO2e", 1),
    ("$450k", "$", 1e3), ("US$ 5m", "USD", 1e6), ("CA$ 3m", "CAD", 1e6), ("Energy (MWh)", "MWh", 1), ("try again", None, 1),
    ("Europe", None, 1), ("1,234", None, 1), ("Form 10", None, 1), ("kr 300", "kr", 1), ("euros 5m", "EUR", 1e6),
])
def test_units_and_scale_from_text(s, unit, scale):
    assert from_text(s) == (unit, scale)


def test_values_scale_and_measures_resolve():
    assert parse_number("€12.3m") == (12_300_000.0, "EUR")
    assert parse_number("$1,200") == (1200.0, "$")                       # which dollar: the file must say
    from services.ingest.units import resolve_declared
    assert resolve_declared("$", "CAD") == "CAD" and resolve_declared("EUR", "CAD") == "EUR"
    assert parse_number("€12.3m", apply_scale=False) == (12.3, "EUR")
    assert (from_measure("iso4217:USD"), from_measure("xbrli:pure"), from_measure("esrs:tCO2e")) == ("USD", "pure", "tCO2e")
    assert (normalise("usd"), normalise(" "), normalise("tco2e")) == ("USD", None, "tCO2e")


def test_xbrl_facts_take_the_unit_the_document_defines():
    doc = b"""<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:tb="http://t/b">
      <xbrli:unit id="u1"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
      <tb:TotalBookValue contextRef="d0" unitRef="u1" decimals="0">1200000</tb:TotalBookValue>
    </xbrli:xbrl>"""
    cells = extract("bank_p3esg", "f.xbrl", doc)["cells"]
    assert cells[0]["unit"] == "USD" and cells[0]["value_num"] == 1_200_000
