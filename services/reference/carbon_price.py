"""NGFS carbon prices in the money the figures are in (multi-currency phase 4, 2026-09-27).

NGFS scenario carbon prices are published in constant 2010 US dollars per tonne (US$2010/tCO2). The transition model
compares a carbon cost with a company's revenue, so the price must be in the revenue's money:

    price = price_US$2010 × deflator(Y) / deflator(2010)          → US dollars of year Y (US GDP deflator, WDI)
                          × units of the currency per US dollar     → the figures' currency, at year Y's average rate

Y is the latest year with both a published deflator and a full year of exchange rates. The basis is returned with
every figure it produces, so a reader can see exactly which year's money a carbon price is in.
"""
from __future__ import annotations

import csv
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "us_gdp_deflator.csv"
BASE_YEAR = 2010


class CarbonPriceError(ValueError):
    pass


@lru_cache(maxsize=1)
def deflators() -> dict[int, float]:
    with _FILE.open() as f:
        return {int(r["year"]): float(r["deflator"]) for r in csv.DictReader(f)}


def basis(session: Session, currency: str = "EUR", year: Optional[int] = None) -> dict:
    """How to turn US$2010 into `currency` at year-`year` prices. factor × a US$2010 price = the price to use."""
    from services.reference.fx import FxError, average_rate
    d = deflators()
    if BASE_YEAR not in d:
        raise CarbonPriceError("the US deflator table has no 2010 base year (scripts/build_us_gdp_deflator.py)")
    last_full_fx_year = date.today().year - 1
    y = year or max(k for k in d if k <= last_full_fx_year)
    if y not in d:
        raise CarbonPriceError(f"no US deflator for {y}")
    ratio = d[y] / d[BASE_YEAR]
    start, end = date(y, 1, 1), date(y, 12, 31)
    try:
        usd = average_rate(session, "USD", start, end)["units_per_eur"]
        tgt = 1.0 if currency == "EUR" else average_rate(session, currency, start, end)["units_per_eur"]
    except FxError as e:
        raise CarbonPriceError(f"no {y} average rate to convert US dollars to {currency}: {e}") from e
    fx = tgt / usd                                    # units of `currency` per US dollar, year-Y average
    return {"base": "US$2010/tCO2 (NGFS)", "price_year": y, "currency": currency,
            "deflator_ratio": round(ratio, 6), "fx_per_usd": round(fx, 6), "factor": ratio * fx,
            "label": f"{currency}/tCO2 at {y} prices",
            "source": f"US GDP deflator {y}/{BASE_YEAR} (World Bank WDI NY.GDP.DEFL.ZS) × {y} average {currency} per USD"}
