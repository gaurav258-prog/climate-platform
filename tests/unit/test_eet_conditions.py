"""EET Conditional fields are decided from the condition FinDatEx states for them — not left for a person to guess."""
from services.eet.generator import _conditional_applies as applies

TAX = "20600_Financial_Instrument_Minimum_Percentage_Investments_Aligned_EU_Taxonomy_Incl_Sovereign_Bonds"


def test_article_and_answer_driven_conditions():
    assert applies("20580_Financial_Instrument_Aligned_With_Paris_Agreement", "9") is True
    assert applies("20580_Financial_Instrument_Aligned_With_Paris_Agreement", "8") is False
    assert applies("20380_Financial_Instrument_Benchmark_Name", "8", values={"20370_x": "Y"}) is True
    assert applies("20380_Financial_Instrument_Benchmark_Name", "8", values={"20370_x": "N"}) is False
    assert applies("10020_Manufacturer_Code", "8", values={"10010_Manufacturer_Code_Type": "L"}) is True
    assert applies("80010_Use_Of_Derivative_Exposure_In_Taxonomy_And_SFDR_Alignment", "8") is False   # funds aren't structured


def test_taxonomy_minimums_wait_for_the_commitment_answer():
    assert applies(TAX, "8") is None                                                     # 20190 not answered yet
    assert applies(TAX, "8", values={"20190_x": "Y"}) is True
    assert applies(TAX, "8", values={"20190_x": "N"}) is False
    assert applies(TAX, "6") is False


def test_periodic_fields_need_periodic_data_in_the_file():
    f = "20690_Financial_Instrument_Percentage_Taxonomy_Aligned_Excl_Sovereign_Revenue"
    assert applies(f, "8", uses=("entity",)) is False and applies(f, "8", uses=("periodic",)) is True


def test_a_field_waits_only_on_the_answer_that_settles_it_for_this_product():
    from services.eet.rules import waiting_on
    ctx = {"sfdr": "8", "fund_type": "fund", "values": {}, "uses": ("entity",)}
    assert waiting_on(TAX, ctx) == [20190]                                               # Art 8: not the Art 9 question
    assert waiting_on(TAX, {**ctx, "sfdr": "9"}) == [20230]
    assert waiting_on(TAX, {**ctx, "values": {"20190_x": "N"}}) == []                    # settled
