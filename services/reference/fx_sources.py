"""The FX source registry: which sources we hold, what kind of figure each is, how much we trust it, how old it may be.

Order is preference. For a currency and a book date, a conversion uses the FIRST source below that has a rate for
that date within the source's own max age; if none is fresh, the freshest rate found is used and marked STALE (a
stale conversion is a failed intake check, so a second person must accept it). Every conversion says which source,
which date, which kind of figure, and how old it was.

  ecb   ECB euro foreign exchange reference rates — daily, ~30 currencies, the euro area's official reference.
  peg   Rates fixed by law or treaty (fx_pegs) — exact: CFA and similar euro pegs, the Bosnian currency board, and the
        irrevocable conversion rates of the currencies the euro replaced.
  imf   IMF Exchange Rates (ER) dataset — month-end national currency per euro, ~180 countries; published with a lag
        of one to two months, so a month-end figure may be used up to ~2 months after it.
  seed  Rows loaded at first setup (offline / tests only) — always stale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FxSource:
    key: str
    name: str
    basis: Optional[str]            # the fx_rates.basis a spot conversion reads (None for pegs: fx_pegs)
    max_age_days: Optional[int]     # None = never stale
    attribution: str


SOURCES: tuple[FxSource, ...] = (
    FxSource("ecb", "ECB euro foreign exchange reference rates", "reference_daily", 7,
             "Source: European Central Bank (ECB) — euro foreign exchange reference rates"),
    FxSource("peg", "Rate fixed by law or treaty", None, None, "Legal basis stated per rate (fx_pegs)"),
    FxSource("imf", "IMF Exchange Rates (ER), month-end", "month_end", 62,
             "Source: International Monetary Fund, Exchange Rates (ER) dataset"),
    FxSource("seed", "Setup rows (offline/tests)", "seed", 0, "Not a live source"),
)
BY_KEY = {s.key: s for s in SOURCES}
