"""The reference period of an entity's principal-adverse-impacts statement and its impact figures (Delegated Regulation
(EU) 2022/1288):

  Article 4(1)  'That information shall cover the period of 1 January until 31 December of the preceding year'
  Article 6(3)  '… a figure on impact as the average of impacts on 31 March, 30 June, 30 September and 31 December of
                each period from 1 January to 31 December.'

So a statement is for a calendar year, and every impact (Tables 1-3) is the mean of the four impacts computed on the
holdings of those four dates. An impact not available on one of the dates is not available for the period — three
dates are never averaged as if they were four; the dates it is missing on are named.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

QUARTER_ENDS = ((3, 31), (6, 30), (9, 30), (12, 31))
METHOD_ORDER = ("computed", "partial", "estimated", "not_applicable", "not_available")   # best → worst


class PeriodError(ValueError):
    pass


def reference_dates(period_end) -> list[date]:
    """The four dates of Article 6(3) for the period ending `period_end` — which must be a 31 December (Article 4(1))."""
    pe = date.fromisoformat(str(period_end)[:10])
    if (pe.month, pe.day) != (12, 31):
        raise PeriodError("A principal adverse impacts statement covers 1 January to 31 December (Delegated Regulation "
                          f"(EU) 2022/1288, Article 4(1)) — its period ends on a 31 December, not {pe.isoformat()}.")
    return [date(pe.year, m, d) for m, d in QUARTER_ENDS]


def holdings_gaps(session, fund_ids: list[str], dates: list[date]) -> list[str]:
    """For each date, the funds holding positions on some date of the year but none on that one — their impact on that
    date is not known (a fund with no holdings on file for the date is a gap, never read as holding nothing)."""
    if not fund_ids:
        return []
    rows = session.execute(text("""
        SELECT f.name, array_agg(DISTINCT p.as_of_date) AS dates
        FROM fund_positions p JOIN funds f USING (fund_id)
        WHERE p.fund_id = ANY(CAST(:f AS uuid[])) AND p.as_of_date BETWEEN :s AND :e
        GROUP BY f.name ORDER BY f.name"""), {"f": fund_ids, "s": date(dates[0].year, 1, 1), "e": dates[-1]}).all()
    out = []
    for name, held in rows:
        missing = [d.isoformat() for d in dates if d not in set(held)]
        if missing:
            out.append(f"{name}: no holdings dated {', '.join(missing)}")
    return out


def _mean(values: list):
    """The mean of the same figure on each date: numbers averaged; a breakdown averaged part by part; None if any date
    lacks it. Text is kept only where every date says the same."""
    if any(v is None for v in values):
        return None
    if all(isinstance(v, bool) for v in values):
        return values[0] if len(set(values)) == 1 else None
    if all(isinstance(v, (int, float)) for v in values):
        return round(sum(values) / len(values), 4)
    if all(isinstance(v, dict) for v in values):
        keys = set(values[0]).intersection(*values[1:])
        return {k: _mean([v[k] for v in values]) for k in values[0] if k in keys}
    return values[0] if all(v == values[0] for v in values) else None


def _worst(methods: list[str]) -> str:
    return max(methods, key=lambda m: METHOD_ORDER.index(m) if m in METHOD_ORDER else len(METHOD_ORDER))


def average_rows(by_date: dict[date, list[dict]], key: str) -> list[dict]:
    """Indicator rows averaged over the dates, matched by `key` ('number' or 'key'). The rows are those of the latest
    date with any; a row's value is the mean when every date has one, else not available with the dates it lacks."""
    dates = sorted(by_date)
    last = next((by_date[d] for d in reversed(dates) if by_date[d]), [])
    index = {d: {r.get(key): r for r in (by_date[d] or [])} for d in dates}
    out = []
    for row in last:
        k = row.get(key)
        per = [index[d].get(k) for d in dates]
        quarters = [{"date": d.isoformat(), "value": (r or {}).get("value"), "coverage_pct": (r or {}).get("coverage_pct"),
                     "method": (r or {}).get("method", "not_available")} for d, r in zip(dates, per)]
        lacking = [q["date"] for q in quarters if q["value"] is None]
        avg = dict(row)
        avg["quarters"] = quarters
        if lacking:
            reasons = sorted({(r or {}).get("input_required") or "no holdings on file" for d, r in zip(dates, per)
                              if (r or {}).get("value") is None})
            avg.update(value=None, coverage_pct=None, method="not_available",
                       input_required=f"not available on {', '.join(lacking)} — " + "; ".join(reasons))
        else:
            avg["value"] = _mean([r["value"] for r in per])
            covs = [r.get("coverage_pct") for r in per]
            avg["coverage_pct"] = round(sum(covs) / len(covs), 1) if all(c is not None for c in covs) else None
            avg["method"] = _worst([r.get("method", "not_available") for r in per])
            for extra in ("coverage_by_scope", "value_scope_1_2", "coverage_scope_1_2", "consumption", "production",
                          "by_section"):
                if extra in row:
                    avg[extra] = _mean([r.get(extra) for r in per])
        out.append(avg)
    return out


def average_books(books: dict[date, dict]) -> dict:
    """The period's figures from the book of each date (ml.regulatory.sfdr_pai._entity_book; an empty book where no
    position is on file for the date). Composition and counts are those of the latest date with holdings."""
    dates = sorted(books)
    last = next((books[d] for d in reversed(dates) if books[d].get("positions")), books[dates[-1]])
    add = {d: (b.get("additional_indicators") or {}) for d, b in books.items()}
    return {
        **last,
        "indicators": average_rows({d: b["indicators"] for d, b in books.items()}, "number"),
        "sovereign_indicators": average_rows({d: b["sovereign_indicators"] for d, b in books.items()}, "number"),
        "real_estate_indicators": average_rows({d: b["real_estate_indicators"] for d, b in books.items()}, "number"),
        "additional_indicators": {**add[dates[-1]],
                                  "indicators": average_rows({d: a.get("indicators") or [] for d, a in add.items()}, "key")},
        "taxonomy": {**(_mean([b.get("taxonomy") or {} for b in books.values()]) or {}),
                     "quarters": [{"date": d.isoformat(), **(books[d].get("taxonomy") or {})} for d in dates]},
        "total_value_eur": _mean([b["total_value_eur"] for b in books.values()]),
        "positions": last["positions"],
        "emissions_coverage_pct": _mean([b.get("emissions_coverage_pct") for b in books.values()]),
        "emissions_estimated_pct": _mean([b.get("emissions_estimated_pct") for b in books.values()]),
        "pcaf_data_quality_score": _mean([b.get("pcaf_data_quality_score") for b in books.values()]),
    }
