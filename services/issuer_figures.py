"""Which row is read when several state an issuer's figure (issuer_emissions: enterprise value, revenue, emissions,
physical asset value). Each read keeps its own rules — the organisation's own row before a shared one, a vendor's last,
the latest year — and when rows still tie, one stated order of sources settles it, the same in every read (the product
owner's decision of 2026-10-22, E317): the organisation's own data, then the company's annual report, then its CDP
response, then an estimate, then a vendor's. Before it, two sources stating the same year were picked arbitrarily, and the
voluntary indicators read a vendor's enterprise value where the mandatory ones read the organisation's.

  SOURCE_TIE             the last ORDER BY key of every read of issuer_emissions that picks one row (interpolated as
                         {SOURCE_TIE}; tests/unit/test_issuer_figures_order.py fails a read without it)
  latest(col, issuer)    one issuer's latest stated `col` and its year — (v, y) — under the enterprise-value rules
"""
from __future__ import annotations

SOURCE_ORDER = ("client", "disclosed", "cdp", "estimated", "vendor")
SOURCE_TIE = f"array_position(ARRAY[{', '.join(repr(s) for s in SOURCE_ORDER)}]::varchar[], source)"


def latest(col: str, issuer: str, up_to_year: bool = False) -> str:
    """A subquery giving (v, y): the issuer's latest stated `col`, the organisation's own row first (:org), a vendor's
    last, the latest year, then the source order. up_to_year: only figures reported for the year :ry or earlier."""
    year = " AND (CAST(:ry AS int) IS NULL OR reporting_year <= CAST(:ry AS int))" if up_to_year else ""
    return f"""(SELECT CAST({col} AS FLOAT) AS v, reporting_year AS y FROM issuer_emissions
             WHERE issuer_id = {issuer} AND (org_id = CAST(:org AS uuid) OR org_id IS NULL) AND {col} IS NOT NULL{year}
             ORDER BY (org_id IS NULL), (source = 'vendor'), reporting_year DESC, {SOURCE_TIE} LIMIT 1)"""
