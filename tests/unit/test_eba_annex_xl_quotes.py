"""Every quote the platform takes from Annex XL of the EBA IT solutions (Implementing Regulation (EU) 2024/3172,
Article 24) is found word for word in its stored English original (data/sources/legal, EBA-ITS-2024-3172-AXL-EN): the
spec's instruction quotes and the Template 1 column i-k and phase-in quotes, which must also read the same in Annex XL
of 2022/2453 (E131)."""
import json
from pathlib import Path

import services.regspec as R
from services.reference import legal_texts as L

EBA = "EBA-ITS-2024-3172-AXL-EN"
REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "pillar3"


def _in(key: str, quote: str) -> bool:
    return L.normalise(quote) in L.normalise(L.text(key))


def test_the_spec_quotes_the_stored_it_solutions_word_for_word():
    spec = R.load("bank_p3esg", "its_2024_3172")
    quotes = [i["quote"] for t in spec["templates"] for i in t.get("instructions") or [] if "EBA IT solutions" in i.get("ref", "")]
    assert len(quotes) >= 50
    assert [q[:80] for q in quotes if not _in(EBA, q)] == []


def test_template_1_quotes_read_the_same_in_both_versions():
    t1 = json.loads((REF / "t1_financed_emissions.json").read_text())
    ph = json.loads((REF / "scope3_phase_in.json").read_text())
    quotes = [q["quote"] for q in t1["quotes"].values()] + [b["quote"] for b in ph["basis"]]
    assert [q[:80] for q in quotes if not (_in(EBA, q) and _in("32022R2453", q))] == []
    assert "32022R2453 only" not in json.dumps(t1)
