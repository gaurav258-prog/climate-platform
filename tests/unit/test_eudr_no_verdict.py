"""E108 guard: a plot's forest information comes only from its kept satellite readings (services/eudr/reading.py) — a
risk the operator weighs (Art. 10), never a verdict. The per-plot verdict columns of sc_sourcing_plots are retired:
nothing reads or writes them, no screen labels a plot 'deforestation-free' or 'non-compliant', and the removed
information-system client (an invented request shape) does not come back."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RETIRED = re.compile(r"\beudr_(determination|determined_at|first_loss_year|loss_ha|forest_source|evidence)\b"
                     r"|\bdetermine_plot\b|\bassemble_dds\b|\btraces_client\b|/eudr/determine\b|/supply/eudr/")
VERDICT = re.compile(r"['\"]deforestation_free(_pct)?['\"]|Deforestation-free")
# ESRS packs frozen before the rebuild keep the checks they were frozen under (filing_validation._validate_esrs_pack):
# reading their stored keys is reading history, not stating a verdict
HISTORY = {("services/governance/filing_validation.py", 'e4.get("deforestation_free"')}


def _files():
    for base, exts in (("api", (".py",)), ("services", (".py",)), ("scripts", (".py",)), ("web/src", (".ts", ".tsx"))):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in exts and "migrations" not in p.parts:
                yield p


def test_retired_verdict_columns_and_client_are_not_used():
    hits = [f"{p.relative_to(ROOT)}:{i}: {line.strip()[:100]}"
            for p in _files() for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1) if RETIRED.search(line)]
    assert not hits, "a plot's forest information comes from services/eudr/reading.py only (E108):\n" + "\n".join(hits)


def test_no_screen_or_service_states_a_verdict():
    hits = [f"{p.relative_to(ROOT)}:{i}: {line.strip()[:100]}"
            for p in _files() for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1)
            if VERDICT.search(line) and not any(str(p.relative_to(ROOT)) == f and m in line for f, m in HISTORY)]
    assert not hits, "a satellite reading is a risk, never a verdict (E108):\n" + "\n".join(hits)
