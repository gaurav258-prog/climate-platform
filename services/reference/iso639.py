"""ISO 639 languages — the ONE place the platform learns which two-letter codes are languages
(data/reference/iso639.csv, built from the ISO 639-2 Registration Authority's list by scripts/build_iso639.py)."""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "iso639.csv"


@lru_cache(maxsize=1)
def _rows() -> dict[str, dict]:
    with _FILE.open() as f:
        return {r["alpha2"]: r for r in csv.DictReader(f)}


def is_language(code: str | None) -> bool:
    """Whether a two-letter code is an ISO 639-1 language code."""
    return (code or "").strip().lower() in _rows()


def name(code: str) -> str | None:
    r = _rows().get((code or "").strip().lower())
    return r["name"] if r else None
