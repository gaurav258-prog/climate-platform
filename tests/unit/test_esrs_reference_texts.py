"""The ESRS reference data says only what the texts say (feedback: facts only):

  ids     every item, disclosure requirement and standard a phase-in or a stated relation names is one the governing
          specification prints (so a renumbered text can never leave a rule pointing at nothing)
  quotes  every quote in data/reference/csrd/scope.json, data/reference/esrs/phase_ins.json and the CSRD mandate of
          data/reference/regulatory_mandates.json (its article, its deadline rule) appears word for word in one of the
          official texts stored in data/sources/legal (Directive 2004/109/EC among them) — checked on every run
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import services.regspec as R
from services.governance.esrs_checks import identities, phase_ins

ROOT = Path(__file__).resolve().parents[2] / "data" / "reference"
VERSIONS = ("dr_2023_2772", "dr_2023_2772_as_2025_1416", "dr_2026_1563")


def _printed(version: str) -> tuple[set, set, set]:
    spec = R.load("esrs", version)
    items = {i["id"] for t in spec["templates"] for i in t["items"]}
    drs = {i["id"] for t in spec["templates"] for i in t["items"] if i["kind"] == "heading"}
    return items, drs, {t["id"] for t in spec["templates"]}


@pytest.mark.parametrize("version", VERSIONS)
def test_every_phase_in_names_what_the_version_prints(version):
    items, drs, standards = _printed(version)
    for r in phase_ins(version):
        named = set(r.get("items", [])) | set(r.get("items_unclear", [])) | set(r.get("except_items", []))
        assert named <= items, (r["id"], sorted(named - items))
        assert set(r.get("drs", [])) <= drs, (r["id"], sorted(set(r.get("drs", [])) - drs))
        assert set(r.get("standards", [])) <= standards, r["id"]


@pytest.mark.parametrize("version", VERSIONS)
def test_every_stated_relation_is_printed_by_the_version(version):
    items, _, _ = _printed(version)
    for r in identities(version):
        assert r.get("printed") and set(r["printed"]) <= items, (r["id"], r.get("printed"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ").replace("’", "'").replace("‘", "'")).strip().lower()


def _quotes():
    scope = json.loads((ROOT / "csrd" / "scope.json").read_text())
    for p in scope["points"]:
        yield f"scope {p['id']}", p["quote"]
    yield "scope derogation", scope["member_state_derogation"]["quote"]
    csrd = next(m for m in json.loads((ROOT / "regulatory_mandates.json").read_text())["mandates"] if m["id"] == "csrd_esrs_e1")
    yield "mandate article", csrd["article"]["excerpt"]
    for branch in ("issuer", "otherwise"):
        yield f"mandate deadline {branch}", csrd["deliverable"]["due"][branch]["quote"]
    pins = json.loads((ROOT / "esrs" / "phase_ins.json").read_text())
    for v, rules in pins.items():
        if isinstance(rules, list):
            for r in rules:
                yield f"phase-in {v}/{r['id']}", r["quote"]


def test_every_quote_is_in_the_texts():
    from services.reference import legal_texts
    missing = []
    for where, q in _quotes():
        parts = [x for x in re.split(r"\s*(?:…|\.\.\.)\s*", q) if x.strip()]   # an elision quotes each part
        if not all(legal_texts.contains(part) for part in parts):
            missing.append(where)
    assert not missing, missing
