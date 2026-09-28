"""Money is written with the symbol from the ISO 4217 / CLDR reference (international English, the same convention
the browser's Intl 'en-001' uses) — never a local table, never an ambiguous '$'."""
from services.governance.money_format import money, symbol


def test_symbols_come_from_the_reference_and_never_mistake_one_dollar_for_another():
    assert [symbol(c) for c in ("EUR", "USD", "CAD", "AUD", "JPY", "CNY", "GBP")] == ["€", "US$", "CA$", "A$", "JP¥", "CN¥", "£"]
    assert symbol("SEK") == "SEK " and symbol("CHF") == "CHF "          # no symbol of its own: the code, spaced
    assert money(1.25e9, "USD") == "US$1.25bn" and money(950_000, "SEK") == "SEK 950k"
    assert symbol("XYZ") == "XYZ "                                       # not a currency we know: shown as written
