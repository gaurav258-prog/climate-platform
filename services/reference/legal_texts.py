"""The official EU legal texts the platform quotes (data/sources/legal) — read here, nowhere else.

Each text is stored as retrieved from EUR-Lex / the Publications Office, normalised to plain text and gzipped, with its
source and checksum in manifest.json. A quote in the reference data stands only if it is found word for word in one of
them (`contains`); the checks that read this run in every test run — no downloaded copy outside the project is needed.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "data" / "sources" / "legal"


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((DIR / "manifest.json").read_text())["texts"]


@lru_cache(maxsize=None)
def text(celex: str) -> str:
    """The normalised text of one act (checked against its manifest checksum)."""
    entry = manifest()[celex]
    b = gzip.decompress((DIR / f"{celex}.txt.gz").read_bytes())
    if hashlib.sha256(b).hexdigest() != entry["sha256"]:
        raise ValueError(f"{celex}: the stored text does not match its manifest checksum")
    return b.decode("utf-8")


def title(celex: str) -> str:
    """The act's title as recorded with the stored text (its manifest entry)."""
    return manifest()[celex]["title"]


def normalise(s: str) -> str:
    """Compare as the texts are stored: whitespace collapsed, typographic apostrophes read as straight ones."""
    return re.sub(r"\s+", " ", s.replace("’", "'")).strip()


@lru_cache(maxsize=1)
def _all() -> tuple[tuple[str, str], ...]:
    return tuple((c, normalise(text(c))) for c in manifest())


def contains(quote: str) -> str | None:
    """The CELEX of the first stored text containing the quote word for word, else None."""
    q = normalise(quote)
    return next((c for c, t in _all() if q in t), None)
