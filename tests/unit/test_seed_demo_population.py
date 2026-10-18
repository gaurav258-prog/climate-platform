"""The demo population's asset names (scripts/seed_demo_population.py): where the asset is, its type in customer
words, its number — never a type code or a map-grid code."""
import pytest

from core.messages import MessageError
from scripts.seed_demo_population import asset_name, type_words


def test_a_type_code_is_named_in_customer_words():
    assert type_words("residential_real_estate") == "residential property"
    assert type_words("commercial_real_estate") == "commercial property"
    assert type_words("light_industrial") == "light industrial"


def test_a_type_in_words_is_kept_and_a_missing_type_is_an_asset():
    assert type_words("Logistics & warehousing") == "Logistics & warehousing" and type_words("office") == "office"
    assert type_words(None) == "asset" and type_words("") == "asset"


def test_an_unnamed_type_code_stops_the_seed_rather_than_reach_a_screen():
    with pytest.raises(MessageError):
        type_words("mixed_use_tower")


def test_an_asset_is_named_by_place_type_and_number():
    assert asset_name("Brindisi", "residential_real_estate", 122) == "Brindisi residential property 122"
    assert asset_name("Malaysia", "retail", 42) == "Malaysia retail 42"
