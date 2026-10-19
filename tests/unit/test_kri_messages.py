"""The KRI sets speak in the catalogue's words (UI standard, 2026-10-16; E234). Each indicator's explanation was a
sentence typed where it was built — nine places, with internal keys ('method.at_risk_level', 'golden source', raw scenario
codes, concept keys) and no guard could see them (keyword arguments, not dict literals). Now every indicator carries a
catalogue message (`about`), its numbers as named facts and its gaps in the one format the screens read; these checks hold
every builder to that, without a database."""
from __future__ import annotations

import ast
import json
from pathlib import Path

from core import messages
from services.governance import kri_esrs
from services.governance.kri import fact, method_gap

ROOT = Path(__file__).resolve().parents[2]
BUILDERS = sorted((ROOT / "services" / "governance").glob("kri*.py"))


def _calls(name: str):
    for path in BUILDERS:
        for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name:
                yield path.name, n


def test_every_indicator_is_built_with_a_catalogue_explanation_and_no_typed_sentence():
    calls = list(_calls("_kpi"))
    assert calls, "no KRI builder found"
    for file, c in calls:
        kws = {k.arg for k in c.keywords}
        assert "about" in kws, f"{file}:{c.lineno}: an indicator without its catalogue explanation (about=msg(...))"
        assert not kws & {"hint", "integrated_note"}, f"{file}:{c.lineno}: a typed sentence (hint / integrated_note) — use about / needs"


def test_every_code_a_builder_names_is_in_the_catalogue():
    codes = set(messages.catalogue())
    for file, c in _calls("msg"):
        arg = c.args[0]
        if isinstance(arg, ast.Constant):
            assert arg.value in codes, f"{file}:{c.lineno}: '{arg.value}' is not in the catalogue"
        elif isinstance(arg, ast.JoinedStr):                  # f"kri.indicator.{code}": checked by the live sets
            assert isinstance(arg.values[0], ast.Constant) and arg.values[0].value.startswith(("kri.", "coverage."))


def test_each_computed_esrs_figure_is_explained_by_what_it_measures():
    """The ESRS revenue figures were explained as carrying amounts (one sentence per lane). Each computed concept now
    names its own explanation; a computed concept added to the headline set without one fails here."""
    cs = json.loads((ROOT / "data" / "reference" / "esrs" / "concepts.json").read_text(encoding="utf-8"))
    cs = cs.get("concepts", cs)
    computed = {c for c, _ in kri_esrs.HEADLINE if cs[c]["lane"] == "computed"}
    assert computed == set(kri_esrs.COMPUTED_ABOUT)
    for c, code in kri_esrs.COMPUTED_ABOUT.items():
        assert f"kri.indicator.{code}" in messages.catalogue()
        assert (code == "esrs_revenue") == (".revenue." in c), c


def test_a_derived_ratio_states_its_unit_in_words():
    units = {cs["unit"] for cs in json.loads((ROOT / "data" / "reference" / "esrs" / "concepts.json").read_text(encoding="utf-8"))["concepts"].values()
             if cs.get("lane") == "derived"}
    named = messages.names()["kri.unit"]
    for u in units | {"tCO2eq/EUR", "tCO2eq/USD", "m3/EURm", "MWh/monetary unit"}:
        num, _, den = u.partition("/")
        assert num in named, u
        words = kri_esrs._unit_words(u)
        assert not messages.INTERNAL.search(words) and "/" not in words, words


def test_a_gap_reaches_the_screen_in_the_one_format_it_reads():
    assert method_gap("not stated: method.epc_discount_c (C); not stated: method.epc_discount_d (D)") == \
        "not stated: method.epc_discount_c, method.epc_discount_d"
    assert method_gap(None, "the PML return period is not chosen") is None
    assert method_gap("method.at_risk_level") == "not stated: method.at_risk_level"


def test_a_fact_is_named_by_the_catalogue():
    f = fact("largest_sector", "Manufacturing", "text")
    assert f["label"] == messages.name("kri.fact", "largest_sector") and f["unit"] == "text"
    for name in messages.names()["kri.fact"].values():
        assert not messages.INTERNAL.search(name), name
