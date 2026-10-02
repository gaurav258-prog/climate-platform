"""Capture the narrative sections of the SFDR principal-adverse-impacts statement (Delegated Regulation (EU) 2022/1288,
Annex I, Table 1) as document templates — what each section must contain is set out in Articles 5 and 7 to 10; every
item is a slice of the stored official text (32022R1288), so each quote is exact by construction; check() proves it
again against services.reference.legal_texts.

  S1  Summary                                   Article 5
  S4  Policies to identify and prioritise PAIs  Article 7
  S5  Engagement policies                       Article 8
  S6  References to international standards     Article 9
  S7  Historical comparison                     Article 10

Tables 1-3 (rows and columns as printed), S2 and S3 are left as captured in data/reference/regspec/sfdr_pai/
rts_2022_1288.json; this script rewrites only the five templates above (re-signing the file is then due).

A table's columns are not printed by the act: each carries a note saying what it holds, never a label.

    venv/bin/python -m scripts.build_sfdr_pai_spec
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from services.reference import legal_texts as L

PATH = Path(__file__).resolve().parents[1] / "data" / "reference" / "regspec" / "sfdr_pai" / "rts_2022_1288.json"
CELEX = "32022R1288"


def _articles() -> str:
    t = L.text(CELEX)
    i, j = t.find("Article 5 Summary section"), t.find("SECTION 2 Financial advisers")
    if i < 0 or j < 0:
        raise SystemExit("Articles 5-10 not found in the stored text")
    return re.sub(r"\s+", " ", t[i:j])


def between(block: str, start: str, end: str | None) -> str:
    """The words from `start` up to (not including) `end` — one printed point, sentence or paragraph."""
    i = block.find(start)
    if i < 0:
        raise SystemExit(f"'{start[:50]}' not found")
    j = block.find(end, i + len(start)) if end else -1
    return block[i:j if j > 0 else len(block)].strip()


def _item(iid, kind, label=None, parent=None, **kw) -> dict:
    out = {"id": iid, "kind": kind, "parent": parent}
    if label:
        out["label"] = label
    return {**out, **kw}


def build(spec: dict) -> dict:
    a = _articles()
    art5 = between(a, "Article 5 Summary section", "Article 6 ")
    art7 = between(a, "Article 7 Description of policies", "Article 8 ")
    art8 = between(a, "Article 8 Engagement policies", "Article 9 ")
    art9 = between(a, "Article 9 References to international standards", "Article 10 ")
    art10 = between(a, "Article 10 Historical comparison", None)

    s1 = [
        _item("heading", "heading", "Summary"),
        _item("intro", "text", between(art5, "In the summary section", " (a) the name")),
        _item("a_name", "field", between(art5, "(a) the name", " (b) the fact")),
        _item("b_considered", "field", between(art5, "(b) the fact", " (c) the reference")),
        _item("c_period", "field", between(art5, "(c) the reference", " (d) a summary")),
        _item("d_summary", "table", between(art5, "(d) a summary", " The summary section in Table 1")),
        _item("d_language", "table_column", parent="d_summary",
              note="the language this text of the summary is drafted in (ISO 639-1 code)"),
        _item("d_meets", "table_column", parent="d_summary",
              note="which of the language requirements below this language meets, as the financial market participant states "
                   "it: home_official (point (a), an official language of the home Member State), international_finance "
                   "(point (a), a language customary in the sphere of international finance), host_official (point (b), an "
                   "official language of a host Member State — with that Member State)"),
        _item("d_member_state", "table_column", parent="d_summary",
              note="for host_official: the host Member State (ISO 3166-1 alpha-2) where a financial product is made available"),
        _item("d_text", "table_column", parent="d_summary", note="the summary of the principal adverse impacts, in that language"),
        _item("languages", "text", between(art5, "The summary section in Table 1 of Annex I shall be drafted", " (a) one of the")),
        _item("languages_a", "text", between(art5, "(a) one of the official languages", " (b) where a financial"),
              parent="languages"),
        _item("languages_b", "text", between(art5, "(b) where a financial product", " The summary section shall be of"),
              parent="languages"),
        _item("length", "text", between(art5, "The summary section shall be of", None)),
    ]
    s4 = [
        _item("heading", "heading", "Description of policies to identify and prioritise principal adverse impacts on "
                                    "sustainability factors"),
        _item("policies", "field", between(art7, "1. In the section", " (a) the date on which")),
        _item("a_approval_date", "field", between(art7, "(a) the date on which", " (b) how the responsibility"),
              parent="policies"),
        _item("b_responsibility", "field", between(art7, "(b) how the responsibility", " (c) the methodologies"),
              parent="policies"),
        _item("c_methodologies", "field", between(art7, "(c) the methodologies", " (d) any associated"), parent="policies"),
        _item("d_margin_of_error", "field", between(art7, "(d) any associated", " (e) the data sources"), parent="policies"),
        _item("e_data_sources", "field", between(art7, "(e) the data sources", " 2. Where information"), parent="policies"),
        _item("best_efforts", "field", between(art7, "2. Where information", None)),
    ]
    s5 = [
        _item("heading", "heading", "Engagement policies"),
        _item("intro", "text", between(art8, "1. In the section", " (a) where applicable")),
        _item("a_srd", "field", between(art8, "(a) where applicable", " (b) brief summaries")),
        _item("b_other", "field", between(art8, "(b) brief summaries", " 2. The brief summaries")),
        _item("describe", "text", between(art8, "2. The brief summaries", " (a) the indicators")),
        _item("2a_indicators", "field", between(art8, "(a) the indicators", " (b) how those"), parent="describe"),
        _item("2b_adaptation", "field", between(art8, "(b) how those", None), parent="describe"),
    ]
    s6 = [
        _item("heading", "heading", "References to international standards"),
        _item("adherence", "field", between(art9, "1. In the section", " 2. The description")),
        _item("describe", "text", between(art9, "2. The description", " (a) the indicators")),
        _item("2a_indicators", "field", between(art9, "(a) the indicators", " (b) the methodology"), parent="describe"),
        _item("2b_methodology", "field", between(art9, "(b) the methodology", " (c) whether a forward"), parent="describe"),
        _item("2c_scenario", "choice", between(art9, "(c) whether a forward", " (d) where no forward"), parent="describe",
              blank="text"),
        _item("2d_no_scenario", "field", between(art9, "(d) where no forward", None), parent="describe"),
    ]
    s7 = [
        _item("heading", "heading", "Historical comparison"),
        _item("comparison", "table", between(art10, "Financial market participants that have described", None)),
        _item("period", "table_column", parent="comparison",
              note="a previous period reported on (1 January to 31 December), most recent first, at most five"),
        _item("indicator", "table_column", parent="comparison", note="the indicator, as numbered in Table 1, 2 or 3"),
        _item("impact", "table_column", parent="comparison", note="the impact reported for that period, as reported"),
        _item("source", "table_column", parent="comparison",
              note="where the reported figure is held: the filed statement, or a previous statement uploaded and confirmed"),
    ]
    items = {"S1": s1, "S4": s4, "S5": s5, "S6": s6, "S7": s7}
    out = json.loads(json.dumps(spec))
    for t in out["templates"]:
        if t["id"] in items:
            for k in ("rows", "columns", "z_axis"):
                t.pop(k, None)
            t["structure"], t["source_form"], t["items"] = "document", "text", items[t["id"]]
            t["capture_notes"] = [
                "Annex I prints only the section's title; what it contains is set out in the Article named in ref. Every "
                "item is that Article's text, sliced from the stored act by scripts/build_sfdr_pai_spec.py; a table's "
                "columns are not printed and carry a note instead of a label."]
    out["capture"] = {**spec["capture"], "sections": {
        "method": "S1, S4-S7 rebuilt as document templates from Articles 5 and 7-10 (scripts/build_sfdr_pai_spec.py), "
                  "every item a slice of 32022R1288 and re-checked verbatim", "captured": "2026-10-02"}}
    return out


def check(spec: dict) -> list[str]:
    """Every item of the rebuilt sections is in the stored text, verbatim."""
    out = []
    for t in spec["templates"]:
        for i in t.get("items") or []:
            if i["kind"] != "heading" and i.get("label") and not L.contains(i["label"]):
                out.append(f"{t['id']}.{i['id']}: not verbatim")
    return out


if __name__ == "__main__":
    import services.regspec as R
    spec = build(json.loads(PATH.read_text()))
    problems = check(spec) + R.validate(spec)
    if problems:
        raise SystemExit("\n".join(problems))
    PATH.write_text(json.dumps(spec, indent=1, ensure_ascii=False) + "\n")
    print(f"{spec['version']}: {sum(len(t.get('items') or []) for t in spec['templates'])} section items, valid, verbatim")
