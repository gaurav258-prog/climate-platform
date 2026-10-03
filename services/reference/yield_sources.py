"""The crop-yield sources that land through review (E153) — one shape for every source, so a new source (USDA,
national statistics offices …) is a new entry here, not a new path into the store.

Each source says: its store label, where it is published, how to ask whether the publisher changed it (a cheap check
before any download), how to download it, which countries its areas are, how it is read into our rows, and the reader
fingerprint (how it is read — another reading of the same file is another release). Staging, review, landing and the
check log are the same for all of them (services.reference.crop_releases).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Optional


def store_round(x: float | None, places: int) -> float | None:
    """Rounded exactly as Postgres stores a float sent to numeric(…, places): the float as written (its shortest decimal
    form, which is what the driver sends), then half away from zero — one rule for every source and field, so the same
    figures are the same rows (Python's round() works on the binary value: 1563.35 → 1563.3, Postgres 1563.4)."""
    if x is None:
        return None
    return float(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class YieldSource:
    key: str                      # 'faostat'
    feed_key: str                 # the feed it refreshes under (services.data.feeds)
    label: Callable[[], str]      # the store's source label (crop_yield_observations.source)
    url: Callable[[], str]
    countries: Callable          # (session) -> {code: ISO alpha-2}
    reader: Callable             # (countries) -> fingerprint
    parse: Callable              # (data, countries) -> rows
    published: Callable          # (last_modified, etag) -> {changed, last_modified, etag}
    download: Callable           # () -> bytes


def _faostat() -> YieldSource:
    from services.reference import faostat_crops as F
    # every call goes through the module, so a test can stand in for the publisher (F.published / F.download)
    return YieldSource(key="faostat", feed_key="crop_production_faostat", label=lambda: F.source(), url=lambda: F.url(),
                       countries=lambda s: F.iso_by_m49(s), reader=lambda c: F.reader(c),
                       parse=lambda data, c: F.parse(data, c), published=lambda lm, et: F.published(lm, et),
                       download=lambda: F.download())


def _eurostat() -> YieldSource:
    from services.reference import eurostat_crops as E
    return YieldSource(key="eurostat", feed_key="crop_production_eurostat", label=lambda: E.SOURCE, url=lambda: E.BASE,
                       countries=lambda s: E.countries(s), reader=lambda c: E.reader(c),
                       parse=lambda data, c: E.parse(data, c), published=lambda lm, et: E.published(lm, et),
                       download=lambda: E.download())


def _usda_fas() -> YieldSource:
    from services.reference import fas_psd as U
    return YieldSource(key="usda_fas", feed_key="crop_production_usda_fas", label=lambda: U.SOURCE, url=lambda: U.BASE,
                       countries=lambda s: U.countries(s), reader=lambda c: U.reader(c),
                       parse=lambda data, c: U.parse(data, c), published=lambda lm, et: U.published(lm, et),
                       download=lambda: U.download())


_BUILDERS = {"faostat": _faostat, "eurostat": _eurostat, "usda_fas": _usda_fas}


def get(key: str) -> YieldSource:
    if key not in _BUILDERS:
        raise KeyError(f"unknown yield source '{key}' — one of {', '.join(_BUILDERS)}")
    return _BUILDERS[key]()


def all_sources() -> list[YieldSource]:
    return [b() for b in _BUILDERS.values()]


def by_label(label: str) -> Optional[YieldSource]:
    return next((s for s in all_sources() if s.label() == label), None)
