"""Capture the EUDR statement templates (Annex II, and Annex III from Regulation (EU) 2025/2650) as specification files —
every printed point is a slice of the stored official text, so each quote is exact by construction; check() proves it
again against services.reference.legal_texts.

  reg_2023_1115                Annex II as published (points 1-6)            in force 29.6.2023 - 25.12.2025
  reg_2023_1115_as_2025_2650   Annex II without point 4; Annex III added     in force from 26.12.2025

Annex I (the products in scope) is reference data by date (data/reference/eudr/annex_i.json), not a template.

    venv/bin/python -m scripts.build_eudr_spec            # writes data/reference/regspec/eudr/*.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from services.reference import legal_texts as L

OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "regspec" / "eudr"
MARKERS = re.compile(r"\s*[►▼][A-Z]\d*\s*|\s*◄\s*")

# the printed points, by number: id, kind ('text' = fixed wording printed as is; 'field' = what the statement fills)
AII_POINTS = {1: ("p1_operator", "field"), 2: ("p2_product", "field"), 3: ("p3_geolocation", "field"),
              4: ("p4_referenced_statement", "field"), 5: ("p5_confirmation", "text"), 6: ("p6_signature", "field")}
AIII_POINTS = {1: ("p1_operator", "field"), 2: ("p2_product_estimate", "field"), 3: ("p3_location", "field"),
               4: ("p4_confirmation", "text")}


def clean(text: str) -> str:
    """EUR-Lex's consolidation markers (▼B, ▼M2, ◄) are not words of the act."""
    return re.sub(r"\s+", " ", MARKERS.sub(" ", text)).strip()


def cut(celex: str, start: str, end: str | None) -> str:
    t = L.text(celex)
    i = t.find(start)
    if i < 0:
        raise SystemExit(f"{celex}: '{start}' not found")
    j = t.find(end, i + len(start)) if end else -1
    return t[i:j if j > 0 else len(t)]


def points(block: str, numbers: list[int]) -> dict[int, str]:
    """The printed points in order: point n runs from 'n. ' to the next listed point (a deleted point printed as a
    rule — '—————' — ends the one before it)."""
    out, pos = {}, 0
    starts = []
    for n in numbers:
        m = re.search(rf"(?:^|[\s:’.]){n}\. ", block[pos:])
        if not m:
            raise SystemExit(f"point {n} not found in order")
        s = pos + m.start() + (0 if block[pos + m.start()].isdigit() else 1)
        starts.append((n, s))
        pos = s + 2
    for k, (n, s) in enumerate(starts):
        e = starts[k + 1][1] if k + 1 < len(starts) else len(block)
        body = block[s + len(f"{n}. "):e]
        body = re.split(r"\s*—————", body)[0]            # a deleted point that follows
        out[n] = clean(re.split(r"\s*\(\s*1\s*\)\s+Directive", body)[0])   # the OJ footnotes after the last annex
    return out


def template(tid: str, code: str, title: str, ref: str, intro: str, instruction: dict, pts: dict[int, str],
             catalogue: dict) -> dict:
    items = [{"id": "heading", "kind": "heading", "label": f"{code.upper()} {title}", "parent": None},
             {"id": "intro", "kind": "text", "label": intro, "parent": None}]
    for n, body in pts.items():
        iid, kind = catalogue[n]
        items.append({"id": iid, "kind": kind, "number": n, "label": body, "parent": None})
    return {"id": tid, "code": code, "title": title, "ref": ref, "structure": "document", "source_form": "text",
            "items": items, "instructions": [instruction], "capture_notes": []}


def build() -> dict[str, dict]:
    orig = cut("32023R1115", "ANNEX II Due diligence statement", None)
    cons = "02023R1115-20251226"
    aii2 = cut(cons, "ANNEX II Due diligence statement", "ANNEX III Simplified")
    aiii = cut(cons, "ANNEX III Simplified declaration", None)
    intro_ii = "Information to be contained in the due diligence statement in accordance with Article 4(2):"
    intro_iii = ("Information to be contained in the one-time simplified declaration for micro or small primary operators "
                 "in accordance with Article 4a(3):")
    art42 = {"ref": "Article 4(2)", "quote": "Such electronically available and transmittable due diligence statement shall "
             "contain the information set out in Annex II for the relevant products and a declaration by the operator that the "
             "operator exercised due diligence and that no or only a negligible risk was found."}
    art4a3 = {"ref": "Article 4a(3)", "quote": "Micro or small primary operators shall provide the information set out "
              "in Annex III when submitting the simplified declaration in the information system referred to in Article 33."}
    v1 = {
        "framework": "eudr", "version": "reg_2023_1115", "status": "adopted",
        "act": {"celex": "32023R1115", "title": L.title("32023R1115"), "url": "https://eur-lex.europa.eu/eli/reg/2023/1115/oj",
                "short": "EUDR (EU) 2023/1115"},
        "legal_basis": {"article": "Article 4(2)", "templates_in": "Annex II to Regulation (EU) 2023/1115, OJ L 150, 9.6.2023",
                        "instructions_in": "Article 4(2) and the introductory words of Annex II",
                        "quote": art42["quote"]},
        "applies": {"from": "2023-06-29", "until": "2025-12-25", "basis": "period_end",
                    "quote": "This Regulation shall enter into force on the twentieth day following that of its publication "
                             "in the Official Journal of the European Union."},
        "templates": [template("AII", "Annex II", "Due diligence statement", "Annex II to Regulation (EU) 2023/1115",
                               intro_ii, art42, points(orig, [1, 2, 3, 4, 5, 6]), AII_POINTS)],
    }
    v2 = {
        "framework": "eudr", "version": "reg_2023_1115_as_2025_2650", "status": "adopted",
        "act": {"celex": "32025R2650", "title": L.title("32025R2650"), "url": "http://data.europa.eu/eli/reg/2025/2650/oj",
                "short": "EUDR (EU) 2023/1115 as amended by (EU) 2025/2650"},
        "legal_basis": {"article": "Article 1, points (27) and (28), of Regulation (EU) 2025/2650",
                        "templates_in": "Annexes II and III to Regulation (EU) 2023/1115 as amended by Annexes I and II to "
                                        "Regulation (EU) 2025/2650, OJ L, 23.12.2025",
                        "instructions_in": "Articles 4(2), 4a(3) and 4a(5) of Regulation (EU) 2023/1115 as amended, and the "
                                           "introductory words of Annexes II and III",
                        "quote": "(27) Annex II is amended in accordance with Annex I to this Regulation; (28) the text set "
                                 "out in Annex II to this Regulation is added as Annex III."},
        "applies": {"from": "2025-12-26", "until": None, "basis": "period_end",
                    "quote": "This Regulation shall enter into force on the third day following that of its publication in "
                             "the Official Journal of the European Union."},
        "templates": [
            template("AII", "Annex II", "Due diligence statement",
                     "Annex II to Regulation (EU) 2023/1115 as amended by Annex I to Regulation (EU) 2025/2650",
                     intro_ii, art42, points(aii2, [1, 2, 3, 5, 6]), AII_POINTS),
            template("AIII", "Annex III", "Simplified declaration for micro or small primary operators",
                     "Annex III to Regulation (EU) 2023/1115 as added by Annex II to Regulation (EU) 2025/2650",
                     intro_iii, art4a3, points(aiii, [1, 2, 3, 4]), AIII_POINTS),
        ],
    }
    v2["templates"][0]["capture_notes"].append(
        "Point 4 ('the reference number of such due diligence statement' for operators referring to an existing statement) "
        "is deleted: 'In Annex II, point 4 is deleted.' (Annex I to Regulation (EU) 2025/2650); points 5 and 6 keep their numbers.")
    v2["templates"][1]["capture_notes"].append(
        "Captured from the consolidated text (02023R1115-20251226), which prints point 4's confirmation in single quotes "
        "('The text: ‘By this declaration, …’.'). The amending act prints the inserted Annex inside single quotes and therefore "
        "the confirmation in double quotes (“…”) — the same words; the quotation marks follow the consolidation.")
    common_interp = [{
        "subject": "which version governs a statement",
        "reading": "A statement is governed by the annexes in force on the date of its shipment (the placing on the market, "
                   "making available or export; the filing's period_end). Whether the obligations apply on that date is a "
                   "separate check (Article 38(2)-(3); services/eudr/checks.py), not a choice of version.",
        "basis": "Article 4(2) requires the statement before the placing on the market or export ('prior submission'); "
                 "Article 38 sets when Articles 3 to 13 apply. No text settles which date fixes a statement's content: this "
                 "reading takes the shipment's date, not the submission date. It changes nothing in practice: Article 4 never "
                 "applied while the first version was in force — Regulation (EU) 2024/3234 (in force 26.12.2024) moved the "
                 "date to 'shall apply from 30 December 2025' and Regulation (EU) 2025/2650 (in force 26.12.2025) to 'shall "
                 "apply from 30 December 2026' — so every statement required under the Regulation falls under the second."}]
    for v in (v1, v2):
        v["interpretations"] = common_interp
        v["capture"] = {"method": "each printed point sliced from the stored official text (services.reference.legal_texts) "
                                  "by scripts/build_eudr_spec.py; consolidation markers removed; quotes re-checked verbatim",
                        "captured": "2026-10-02",
                        "second_pass": {"by": "independent agent reading the stored texts (32023R1115, 32024R3234, 32025R2650, "
                                              "02023R1115-20251226, -20260918, 32026R2102)", "checked": "2026-10-02",
                                        "changes": ["v2 legal_basis attributed to Article 1, points (27)-(28), of 2025/2650",
                                                    "Annex III quotation marks noted (consolidated vs amending act)",
                                                    "Article 4(2) quoted by the sentence that names Annex II",
                                                    "act urls and titles as printed",
                                                    "interpretation: moot first-version period stated; shipment vs submission "
                                                    "date named as the open choice"]}}
    return {v1["version"]: v1, v2["version"]: v2}


def check(spec: dict) -> list[str]:
    """Every printed point and quote is in the stored texts, verbatim."""
    out = []
    for t in spec["templates"]:
        for i in t["items"]:
            if i["kind"] != "heading" and not L.contains(i["label"]):
                out.append(f"{spec['version']} {t['id']}.{i['id']}: not verbatim")
        for ins in t["instructions"]:
            if not L.contains(ins["quote"]):
                out.append(f"{spec['version']} {t['id']} {ins['ref']}: not verbatim")
    for q in (spec["legal_basis"]["quote"], spec["applies"]["quote"]):
        if not L.contains(q):
            out.append(f"{spec['version']}: '{q[:40]}…' not verbatim")
    return out


if __name__ == "__main__":
    import services.regspec as R
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in build().items():
        problems = check(spec) + R.validate(spec)
        if problems:
            raise SystemExit("\n".join(problems))
        (OUT / f"{name}.json").write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
        print(f"{name}: {sum(len(t['items']) for t in spec['templates'])} items, valid, verbatim")
