"""The stored legal texts are what the manifest says they are (data/sources/legal): every entry has its file, every file
its entry, and each file matches its checksum."""
from services.reference import legal_texts as L


def test_every_text_matches_its_manifest():
    files = {p.name.removesuffix(".txt.gz") for p in L.DIR.glob("*.txt.gz")}
    assert files == set(L.manifest())
    for celex, e in L.manifest().items():
        assert e["source"] and e["retrieved"] and e["title"], celex
        assert len(L.text(celex)) == e["chars"], celex          # raises on a checksum mismatch


def test_a_quote_is_found_only_word_for_word():
    assert L.contains("EU parent institutions shall comply with Part Eight on the basis of their consolidated situation.") \
        == "02013R0575-20250101"
    assert L.contains("EU parent institutions shall comply with Part Nine") is None
