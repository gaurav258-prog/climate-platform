"""The EET fields read from a product's SFDR pre-contractual template (data/reference/eet/sfdr_item_map.json): every
field is an EET field, every item and chart label exists in the governing Annex II / III, and a commitment is stated
once — an EET answer cannot override it."""
import services.regspec as R
from services.eet import fields as F
from services.eet.generator import computed_names
from services.eet.sfdr_items import _value, mapping, names

_ANNEX = {"article_8": "AII", "article_9": "AIII"}


def test_every_mapped_field_and_item_exists():
    assert names() <= set(F.by_name())
    for v in R.versions("sfdr_product"):
        if v["version"] != "rts_2022_1288_as_amended_2023_363":
            continue
        spec = R.load("sfdr_product", v["version"])
        for name, arts in mapping()["fields"].items():
            for art, rule in arts.items():
                ids = {i["id"] for i in R.template(spec, _ANNEX[art])["items"]}
                assert rule["item"] in ids and set(rule.get("labels", [])) <= ids, (name, art)


def test_template_fields_cannot_be_retyped_as_eet_answers():
    assert names() <= computed_names()


def test_values_convert_to_the_eet_formats():
    assert _value({"item": "a", "take": "percent"}, {"a": {"ticked": True, "percent": 15}}) == 0.15
    assert _value({"item": "a", "take": "ticked"}, {"a": {"ticked": False}}) == "N"
    assert _value({"item": "c", "take": "values", "labels": ["c.x", "c.y"]}, {"c": {"values": {"c.x": 3, "c.y": 7}}}) == 0.1
    assert _value({"item": "c", "take": "values", "labels": ["c.z"]}, {"c": {"values": {"c.x": 3}}}) is None


def test_an_eet_answer_to_a_template_field_is_refused():
    """The refusal needs no database: it happens before any write."""
    from services.eet.publication import set_answers

    class _S:
        def execute(self, *a, **k):
            raise AssertionError("no write may happen")
    name = sorted(names())[0]
    out = set_answers(_S(), "org", None, {name: "0.2"}, None)
    assert out["refused"][0]["field"] == name and "pre-contractual template" in out["refused"][0]["reason"]
