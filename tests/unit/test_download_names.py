"""E111: a download's name comes from the data (a filing label, a fund, a supplier) — a header cannot carry it as-is, so
every Content-Disposition built from a variable goes through api.deps.attachment (ASCII fallback + RFC 5987 filename*)."""
from __future__ import annotations

import re
from pathlib import Path

from api.deps import attachment

ROOT = Path(__file__).resolve().parents[2]


def test_a_name_with_any_character_makes_a_valid_header():
    h = attachment("eudr_dds-SHIP-2027-001 · 2027-01-15-v1.json")
    h.encode("latin-1")                                             # what an HTTP header must be
    assert 'filename="eudr_dds-SHIP-2027-001-2027-01-15-v1.json"' in h and "filename*=UTF-8''" in h and "%C2%B7" in h
    assert 'filename="Sud-Comoe' in attachment("Sud-Comoé.pdf")


def test_no_download_name_is_written_into_the_header_raw():
    raw = re.compile(r'Content-Disposition"\s*:\s*f["\']')
    hits = [f"{p.relative_to(ROOT)}:{i}" for p in (ROOT / "api").rglob("*.py")
            for i, line in enumerate(p.read_text().splitlines(), 1) if raw.search(line)]
    assert not hits, f"use api.deps.attachment(name): {hits}"
