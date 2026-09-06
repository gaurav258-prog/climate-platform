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
