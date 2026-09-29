"""Every printed row and column of every adopted credit-institution Taxonomy version resolves through the declared
vocabulary (services.governance.taxonomy_vocabulary) — a new version, or a change to one, fails here naming the exact
printed segment the vocabulary does not know."""
import pytest

import services.regspec as R
from services.governance import taxonomy_vocabulary as V

_VERSIONS = [s for s in R.versions("bank_taxonomy") if s["status"] == "adopted"]


@pytest.mark.parametrize("spec", _VERSIONS, ids=[s["version"] for s in _VERSIONS])
def test_every_row_and_column_resolves(spec):
    problems = []
    for t in spec["templates"]:
        try:
            V.resolve(spec, t["id"])
        except V.Unresolved as e:
            problems.append(str(e))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("spec", _VERSIONS, ids=[s["version"] for s in _VERSIONS])
def test_every_computed_column_says_what_it_measures(spec):
    """A column of a computed template names an objective or measure (or is an entered figure) — never nothing."""
    empty = []
    for t in spec["templates"]:
        r = V.resolve(spec, t["id"])
        if r["kind"] in V.vocabulary()["inputs"]:
            continue
        empty += [f"{t['id']}.{cid}" for cid, f in r["columns"].items()
                  if not (set(f) & {"measure", "objective", "ratio", "coverage", "share_of_total", "input", "sector", "unit", "basis"})]
    assert not empty, empty
