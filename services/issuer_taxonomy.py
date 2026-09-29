"""An investee's own EU Taxonomy KPIs — the one store (issuer_taxonomy_kpi), read and written here for every user:
a bank valuing general-purpose lending (Annex V of Delegated Regulation 2021/2178), a fund's PAI statement and its
SFDR product templates (Art. 55 / 62 of Delegated Regulation 2022/1288).

Per issuer, reporting year and basis (turnover / CapEx / OpEx) the undertaking states its eligible, aligned,
transitional and enabling shares (%) and the fossil gas and nuclear parts of the aligned share — by objective, or as
one total ('all') when it does not split them. A reader gets one figure per basis: the organisation's own over a
shared vendor figure, the latest reporting year (up to a given one), a split by objective added up.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

BASES = ("turnover", "capex", "opex")
MEASURES = ("eligible", "aligned", "fossil_gas", "nuclear", "transitional", "enabling")
_COLUMN = {"eligible": "eligible_pct", "aligned": "aligned_pct", "fossil_gas": "fossil_gas_aligned_pct",
           "nuclear": "nuclear_aligned_pct", "transitional": "transitional_pct", "enabling": "enabling_pct"}


def kpis(session: Session, org_id: str | None, issuer_ids: list[str], up_to_year: int | None = None) -> dict:
    """{issuer_id: {basis: {measure: pct | None, 'year': int}}} for the issuers that state any."""
    if not issuer_ids:
        return {}
    cols = ", ".join(f"CAST({c} AS FLOAT) AS {m}" for m, c in _COLUMN.items())
    rows = session.execute(text(f"""
        SELECT DISTINCT ON (issuer_id, basis, objective) issuer_id::text AS issuer_id, basis, objective, reporting_year, {cols}
        FROM issuer_taxonomy_kpi
        WHERE issuer_id = ANY(CAST(:ids AS uuid[])) AND (org_id = CAST(:o AS uuid) OR org_id IS NULL)
          AND (CAST(:y AS int) IS NULL OR reporting_year <= CAST(:y AS int))
        ORDER BY issuer_id, basis, objective, (org_id IS NULL), reporting_year DESC"""),
        {"ids": list(issuer_ids), "o": org_id, "y": up_to_year}).mappings().all()
    parts: dict = {}
    for r in rows:
        parts.setdefault(r["issuer_id"], {}).setdefault(r["basis"], {})[r["objective"]] = r
    out: dict = {}
    for iid, bases in parts.items():
        for b, by_obj in bases.items():
            # a total ('all') stands only on its own; a split by objective is added up (never both counted)
            use = [by_obj["all"]] if set(by_obj) == {"all"} else [v for k, v in by_obj.items() if k != "all"]
            vals = {m: (sum(p[m] for p in use if p[m] is not None) if any(p[m] is not None for p in use) else None)
                    for m in MEASURES}
            out.setdefault(iid, {})[b] = {**vals, "year": max(p["reporting_year"] for p in use)}
    return out


def write_total(session: Session, issuer_id: str, org_id: str | None, year: int, basis: str, values: dict,
                source: str = "client") -> bool:
    """Record an issuer's stated KPI for a basis without a split by objective (objective 'all'): the given measures
    are set, the others kept. A vendor figure never overwrites the manager's own (source 'client'): it fills only what
    the manager left blank. Returns True when a vendor value differed from the manager's (counted by the caller)."""
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}")
    given = {m: v for m, v in values.items() if m in _COLUMN and v is not None}
    if not given:
        return False
    cols = ", ".join(_COLUMN[m] for m in given)
    key = {"i": issuer_id, "o": org_id, "y": year, "b": basis}
    mine = session.execute(text(f"""
        SELECT {cols} FROM issuer_taxonomy_kpi WHERE issuer_id = CAST(:i AS uuid) AND org_id IS NOT DISTINCT FROM CAST(:o AS uuid)
          AND reporting_year = :y AND basis = :b AND objective = 'all' AND source = 'client'"""), key).mappings().first()
    differs = bool(source != "client" and mine and any(
        mine[_COLUMN[m]] is not None and abs(float(mine[_COLUMN[m]]) - float(v)) > 1e-6 for m, v in given.items()))
    keep = "COALESCE(issuer_taxonomy_kpi.{c}, EXCLUDED.{c})" if source != "client" else "EXCLUDED.{c}"
    upd = ", ".join(f"{_COLUMN[m]} = CASE WHEN issuer_taxonomy_kpi.source = 'client' THEN {keep.format(c=_COLUMN[m])} "
                    f"ELSE COALESCE(EXCLUDED.{_COLUMN[m]}, issuer_taxonomy_kpi.{_COLUMN[m]}) END" for m in given)
    session.execute(text(f"""
        INSERT INTO issuer_taxonomy_kpi (issuer_id, org_id, reporting_year, basis, objective, {cols}, source, data_vintage)
        VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :y, :b, 'all', {", ".join(f":{m}" for m in given)}, :s, now())
        ON CONFLICT ON CONSTRAINT ux_issuer_taxonomy_kpi DO UPDATE SET {upd},
            source = CASE WHEN issuer_taxonomy_kpi.source = 'client' THEN 'client' ELSE EXCLUDED.source END,
            data_vintage = EXCLUDED.data_vintage"""), {**key, "s": source, **{m: float(v) for m, v in given.items()}})
    return differs


def write_stated(session: Session, issuer_id: str, org_id: str | None, year: int, stated: dict,
                 source: str = "client") -> bool:
    """The upload columns an issuer's KPIs arrive in (holdings upload, vendor feed) → the one store."""
    differs = False
    for basis, values in (("turnover", {"eligible": stated.get("taxonomy_eligible_pct"), "aligned": stated.get("taxonomy_aligned_pct")}),
                          ("capex", {"aligned": stated.get("taxonomy_aligned_capex_pct")})):
        differs |= write_total(session, issuer_id, org_id, year, basis, values, source)
    return differs


def gate_failures(session: Session, org_id: str | None, issuer_ids: list[str]) -> set[str]:
    """Issuers whose stated aligned share cannot count: a do-no-significant-harm or minimum-safeguards attestation on
    file that is explicitly false (a known controversy overrides the reported %). A flag not stated leaves the reported
    figure standing — the platform never infers DNSH or safeguards itself."""
    if not issuer_ids:
        return set()
    return {r[0] for r in session.execute(text("""
        SELECT DISTINCT ON (issuer_id) issuer_id::text, dnsh_ok, min_safeguards_ok FROM issuer_esg_metrics
        WHERE issuer_id = ANY(CAST(:ids AS uuid[])) AND (org_id = CAST(:o AS uuid) OR org_id IS NULL)
        ORDER BY issuer_id, (org_id IS NULL), (source = 'vendor'), reporting_year DESC"""),
        {"ids": list(issuer_ids), "o": org_id}) if r[1] is False or r[2] is False}
