"""Build the ESRS specification files (family 'esrs': E1, E3, E4 — the platform's lane) from the official texts.

Three versions, by the financial years they govern (basis financial_year_start):
  dr_2023_2772               FY starting in 2024 — Delegated Regulation (EU) 2023/2772 as corrected
  dr_2023_2772_as_2025_1416  FY starting 2025-2026 — as amended by 2025/1416 (ESRS 1 Appendix C replaced); for FY 2026
                             the undertaking may elect the 2026/1563 standards (Art. 2 of 2026/1563)
  dr_2026_1563               FY starting on or after 2027-01-01 — Annexes I and II replaced by 2026/1563
E1/E3/E4 are identical in the first two (2025/1416 amends only ESRS 1 Appendix C), both taken from the consolidated
text 02023R2772-20250101.

Items come from scripts/capture_esrs_spec.py (machine-exact quotes, strict numbering, printed titles by structure);
their labels (kind, unit, obligation, condition, period, datapoints) from the independent second pass
(<scratch>/capture/<ver>_<std>.verify.json), which decided every item from the printed words.

    venv/bin/python -m scripts.build_esrs_spec <scratch dir with the downloaded HTML and capture/>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from scripts.capture_esrs_spec import check, extract, split

OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "regspec" / "esrs"
STANDARDS = {"E1": "Climate change", "E3": "Water and marine resources", "E4": "Biodiversity and ecosystems"}
HTML = {"2023": "02023R2772-20250101.html", "2026": "32026R1563.html"}
CONSOLIDATED_NOTE = ("E1, E3 and E4 as printed in the consolidated text 02023R2772-20250101 (EUR-Lex documentation tool; the "
                     "authentic text is the OJ act as corrected — the consolidated text carries its corrigenda, whose "
                     "►C1 markers were removed).")
# the words that make a quantitative item also ask for an explanation (the number and its narrative both reported)
_NARRATIVE = re.compile(r"\b(explanation|explain|describe|description)\b", re.I)

LEGAL_BASIS = {
    "article": "Article 29b of Directive 2013/34/EU; sustainability reporting under Articles 19a and 29a",
    "templates_in": "Annex I to Delegated Regulation (EU) 2023/2772 — ESRS E1, E3 and E4 (the disclosure requirements, "
                    "item by item)",
    "instructions_in": "the Application Requirements of each standard (Appendix A in the 2023 text; after each "
                       "disclosure requirement in the 2026 text)",
    "quote": "The sustainability reporting standards that undertakings are to use for carrying out their sustainability "
             "reporting in accordance with Articles 19a and 29a of Directive 2013/34/EU",
}

VERSIONS = {
    "dr_2023_2772": {
        "text": "2023",
        "act": {"celex": "32023R2772", "title": "Commission Delegated Regulation (EU) 2023/2772 of 31 July 2023 supplementing "
                "Directive 2013/34/EU of the European Parliament and of the Council as regards sustainability reporting "
                "standards", "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32023R2772",
                "short": "ESRS (Delegated Regulation (EU) 2023/2772)"},
        "applies": {"from": "2024-01-01", "until": "2024-12-31", "basis": "financial_year_start",
                    "quote": "It shall apply from 1 January 2024 for financial years beginning on or after 1 January 2024.",
                    "ref": "Article 2 of Delegated Regulation (EU) 2023/2772"},
    },
    "dr_2023_2772_as_2025_1416": {
        "text": "2023",
        "act": {"celex": "32023R2772", "amended_by": ["32025R1416"], "consolidated": "02023R2772-20250101",
                "title": "Delegated Regulation (EU) 2023/2772 as amended by Commission Delegated Regulation (EU) 2025/1416 "
                         "of 11 July 2025", "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02023R2772-20250101",
                "short": "ESRS as amended by Delegated Regulation (EU) 2025/1416"},
        "applies": {"from": "2025-01-01", "until": "2026-12-31", "basis": "financial_year_start",
                    "quote": "It shall apply with respect to financial years beginning on or after 1 January 2025.",
                    "ref": "Article 2 of Delegated Regulation (EU) 2025/1416"},
        "transitional_option": {
            "ref": "Article 2 of Delegated Regulation (EU) 2026/1563",
            "quote": "For the financial years starting between 1 January 2026 and 31 December 2026, undertakings falling "
                     "within the scope of Delegated Regulation (EU) 2023/2772 may apply either of the following: (a) the "
                     "sustainability reporting standards set out in Annex I to Delegated Regulation (EU) 2023/2772 as last "
                     "amended by Delegated Regulation (EU) 2025/1416 or the sustainability reporting standards set out in "
                     "Annex I to this Regulation;",
            "statement_quote": "Undertakings that choose to apply the sustainability reporting standards in the version "
                               "referred to in either point (a) or (b) of paragraph 1 shall clearly state in their "
                               "sustainability statement which version they apply for financial years beginning between "
                               "1 January 2026 and 31 December 2026.",
            "switch": "esrs_fy2026_version", "elected_value": "dr_2026_1563",
            "financial_year_starts": {"from": "2026-01-01", "until": "2026-12-31"}, "then_governed_by": "dr_2026_1563",
        },
    },
    "dr_2026_1563": {
        "text": "2026",
        "act": {"celex": "32026R1563", "title": "Commission Delegated Regulation (EU) 2026/1563 of 3 July 2026 amending "
                "Delegated Regulation (EU) 2023/2772 as regards the simplification of certain sustainability reporting "
                "standards", "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32026R1563",
                "short": "ESRS as amended by Delegated Regulation (EU) 2026/1563"},
        "applies": {"from": "2027-01-01", "until": None, "basis": "financial_year_start",
                    "quote": "It shall apply to the financial years beginning on or after 1 January 2027.",
                    "ref": "Article 3 of Delegated Regulation (EU) 2026/1563"},
    },
}


def _template(scratch: Path, text_ver: str, std: str) -> tuple[dict, dict]:
    t = extract((scratch / HTML[text_ver]).read_text(encoding="utf-8"), text_ver, std)
    cap = split(t, std)
    errs = check(t, cap)
    if errs:
        raise SystemExit(f"{text_ver} {std}: " + "; ".join(errs[:5]))
    ver = json.loads((scratch / "capture" / f"{text_ver}_{std}.verify.json").read_text())
    final, dps = ver["final"], ver["datapoints"]
    missing = [i["id"] for i in cap["items"] if i["id"] not in final]
    if missing:
        raise SystemExit(f"{text_ver} {std}: second pass has no decision for {missing[:5]}")
    items = []
    for i in cap["items"]:
        lab = final[i["id"]]
        it = {"id": i["id"], "kind": lab["kind"], "label": i["label"], "parent": i["parent"], "note": i.get("note"),
              "obligation": lab.get("obligation"), "conditional": lab.get("conditional")}
        if lab["kind"] == "field":
            it["datapoints"] = [{"key": d["key"], "words": d["words"], "unit": d["unit"], "period": d.get("period")}
                                for d in dps.get(i["id"], [])]
            if not it["datapoints"]:
                raise SystemExit(f"{text_ver} {std} {i['id']}: a field with no datapoint")
            if _NARRATIVE.search(i["label"]):
                it["narrative"] = True
        items.append(it)
    ars = [{"ref": a["ref"], "under": a["under"], "for": a["for"], "quote": a["quote"]} for a in cap["instructions"]]
    tpl = {"id": std, "code": f"ESRS {std}", "title": STANDARDS[std],
           "ref": f"Annex I to Delegated Regulation (EU) 2023/2772{' as replaced by Delegated Regulation (EU) 2026/1563' if text_ver == '2026' else ''}, ESRS {std}",
           "structure": "document", "source_form": "text", "items": items, "instructions": ars}
    review = {"changed": ver.get("changed_from_class", {}), "act_defects": ver.get("act_defects", []),
              "titles_removed": cap["printed_titles_removed"]}
    return tpl, review


def build(scratch: Path) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for vid, v in VERSIONS.items():
        templates, reviews = [], {}
        for std in STANDARDS:
            tpl, rev = _template(scratch, v["text"], std)
            templates.append(tpl)
            reviews[std] = rev
        doc = {"framework": "esrs", "version": vid, "act": v["act"], "status": "adopted", "legal_basis": LEGAL_BASIS,
               "applies": v["applies"], "templates": templates,
               "capture": {
                   "method": "machine split of the official text (scripts/capture_esrs_spec.py: strict paragraph / point / "
                             "AR numbering, printed titles and footnotes read from the HTML structure, every quote "
                             "checked verbatim) and item labels from a first reviewer, decided afresh by an independent "
                             "second reviewer from the printed words",
                   "source": CONSOLIDATED_NOTE if v["text"] == "2023" else "OJ L, 2026/1563, 21.9.2026 (32026R1563).",
                   "captured": "2026-09-30", "built_by": "scripts/build_esrs_spec.py",
                   "scope": "ESRS E1, E3 and E4 — the standards whose data this platform holds (climate physical risk, "
                            "water, biodiversity). ESRS 1 and 2 and the other topical standards are outside this family; "
                            "phase-ins (ESRS 1 Appendix C; 2026/1563 ESRS 1 transitional provisions) are captured with "
                            "their reader (the filing checks), not before.",
                   "second_pass": {std: {"changed_from_first": len(r["changed"]), "changes": r["changed"]}
                                   for std, r in reviews.items()},
                   "act_defects": {std: r["act_defects"] for std, r in reviews.items()},
                   "printed_titles_removed": {std: r["titles_removed"] for std, r in reviews.items()},
               }}
        if v.get("transitional_option"):
            doc["transitional_option"] = v["transitional_option"]
        path = OUT / f"{vid}.json"
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        written.append(path)
    return written


if __name__ == "__main__":
    for p in build(Path(sys.argv[1])):
        print(p)
