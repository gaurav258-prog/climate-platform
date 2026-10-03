"""ISO 3166-1 alpha-2 country validation used to flag bogus codes on ingest."""
from services.reference.iso_country import ISO_ALPHA2, is_valid_country


def test_real_codes_valid():
    for c in ("NL", "de", "US", "br", "CI", "EU", "XK"):
        assert is_valid_country(c)


def test_bogus_codes_invalid():
    for c in ("ZZ", "XX", "QQ", "123", "Netherlands"):
        assert not is_valid_country(c)


def test_blank_or_none_is_valid():
    # country is optional metadata — only a non-empty bogus code is flagged
    assert is_valid_country(None) and is_valid_country("") and is_valid_country("  ")


def test_set_is_sane_size():
    assert 240 <= len(ISO_ALPHA2) <= 260


def test_the_eus_own_codes_map_to_iso_both_ways():
    """The EU writes Greece 'EL' and the United Kingdom 'UK' (Interinstitutional Style Guide 7.1.1); ISO 3166 writes
    'GR' and 'GB'. Stored countries are ISO (ck_<table>_country_iso); an EU-keyed table is read through to_eu."""
    from services.reference.iso_country import to_eu, to_iso2
    assert (to_iso2("el"), to_iso2("UK"), to_iso2(" de "), to_iso2(None)) == ("GR", "GB", "DE", None)
    assert (to_eu("GR"), to_eu("GB"), to_eu("DE")) == ("EL", "UK", "DE")


def test_a_grouping_is_accepted_on_uploads_but_is_not_a_country():
    """E154: 'EU' stays a valid upload value, but the country reference marks it is_country = false, so a reader of
    'the countries' (FAOSTAT, Eurostat) never takes the Union's total for a country."""
    from services.reference.countries import build
    from services.reference.iso_country import GROUPINGS, is_valid_country
    assert is_valid_country("EU") and "EU" in GROUPINGS
    names = {"en": {"EU": "European Union", "GR": "Greece", "XK": "Kosovo"}}
    codes = {"EU": {"_numeric": "967"}, "GR": {"_alpha3": "GRC", "_numeric": "300"}, "XK": {"_alpha3": "XKK", "_numeric": "983"}}
    countries, _ = build(names, codes, {})
    kind = {c["iso2"]: c["is_country"] for c in countries}
    assert kind == {"EU": False, "GR": True, "XK": True}
