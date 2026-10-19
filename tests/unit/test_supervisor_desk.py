"""The supervisor's desk names things one way (UI standard, product owner 2026-10-16 and 2026-10-18):

  • a case file's sections carry the same words in the evidence pack, on every remittance screen and on the bearer-link
    page — 'Quick check' and 'Full rebuild', never 'Tier 1 plausibility' / 'Tier 2 independent lens' (the pack and the
    remittance list kept the old words after the checks were renamed);
  • a mandate's names (its short name and title, shown on the main screen) carry no legal citation — the article, the
    template number and the regulation sit with the mandate's article, one click away ('Pillar 3 ESG (CRR Art. 449a)',
    'Solvency II S.27.01.01' and 'EUDR (Reg. 2023/1115)' once headed the registry, the calendar and the request titles)."""
from __future__ import annotations

import re
from pathlib import Path

from core import messages
from services.supervision.evidence import SECTIONS, section_title
from services.supervision.mandates import registry

ROOT = Path(__file__).resolve().parents[2]
# The screen guard's legal-citation pattern (web/tests/uiLanguage.ts CITATION), for the names the server sends to a screen.
CITATION = re.compile("|".join([
    r"\bArt(?:icles?|s)?\.?\s?\d+[a-z]?(?=\s?\()",                       # Art. 449a(1), Article 5(2) — an article's paragraph
    r"\bArt(?:icles?|s)?\.?\s?(?![689]\b)\d+[a-z]?",                     # Art. 449a, Art. 45a — not an 'Article 8' category
    r"\bAnnex(?:es)?\s(?:[IVXL]+|\d+)\b",
    r"\b(?:Regulation|Directive|Decision|Reg\.|Dir\.|ITS|RTS)\s(?:\((?:EU|EC|EEC)\)\s)?(?:No\.?\s?)?\d{2,4}/\d+",
    r"\b[SE]\.\d{2}\.\d{2}\.\d{2}\b",
]))


def _section_label_on_screen() -> dict[str, str]:
    src = (ROOT / "web/src/components/Remittance.tsx").read_text(encoding="utf-8")
    block = re.search(r"export const SECTION_LABEL[^=]*=\s*\{(.*?)\}\n", src, re.S)
    assert block, "SECTION_LABEL is no longer a literal in web/src/components/Remittance.tsx"
    return dict(re.findall(r"(\w+):\s*'([^']*)'", block.group(1)))


def test_a_case_file_section_has_one_name_everywhere():
    names = messages.names()["case_file_section"]
    assert list(names) == SECTIONS, "every pack section is named in the catalogue, in the pack's order"
    assert _section_label_on_screen() == names, "web/src/components/Remittance.tsx SECTION_LABEL must say what the catalogue says"
    assert {section_title(s) for s in ("plausibility", "lens")} == {"Quick check", "Full rebuild"}


def test_the_citation_pattern_reads_as_the_screen_guard_does():
    for cited in ("Pillar 3 ESG (CRR Art. 449a)", "Solvency II S.27.01.01", "EUDR (Reg. 2023/1115)", "SFDR PAI (Art. 4)", "(Art. 45a)"):
        assert CITATION.search(cited), cited
    for plain in ("Taxonomy Art. 8 · GAR", "EU Taxonomy Article 8 disclosures", "Pillar 3 ESG", "CSRD · ESRS"):
        assert not CITATION.search(plain), plain


def test_a_mandate_is_named_without_a_legal_citation():
    cited = [f"{m['id']}: {name}" for m in registry()["mandates"] for name in (m["short"], m["title"]) if CITATION.search(name)]
    assert cited == [], f"name these in plain words; the citation belongs with the mandate's article: {cited}"
