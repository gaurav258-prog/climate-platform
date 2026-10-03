"""Demo data: a reference-period history for the demo asset managers' Art. 8 / 9 funds, so the SFDR periodic template
(RTS 2022/1288 Annex IV / V) has holdings over a whole financial year, and stated Taxonomy KPIs for the fictional demo
investees, so its alignment graphs have figures.

Demo only — organisations named '(demo)'. Deterministic. Declared demo assumptions:
  * the previous calendar year's quarter-end holdings are the fund's current holdings, each scaled by a fixed drift
    (Q1 0.91, Q2 0.94, Q3 0.97, Q4 1.00) — written only where the fund holds nothing in that year
  * Taxonomy KPIs only for the fictional demo issuers (LEI beginning 'DEMO'), by their activity: never for a real
    company, whose figures are its own to state. A value already on file is never overwritten.

    venv/bin/python -m scripts.seed_demo_sfdr_history
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text

from core.db.session import get_session

_DRIFT = {3: 0.91, 6: 0.94, 9: 0.97, 12: 1.00}
# NACE division of a fictional demo issuer -> its stated KPIs per basis (%): aligned, fossil gas part, eligible; the
# nuclear part of the aligned share is 0 for every one (none runs a nuclear activity) — a stated 0, never left blank
_DEMO_KPI = {
    "35": {"turnover": (22.0, 3.0, 64.0), "capex": (41.0, 2.0, 70.0), "opex": (18.0, 1.0, 52.0)},
    "62": {"turnover": (4.0, 0.0, 9.0), "capex": (6.0, 0.0, 11.0), "opex": (3.0, 0.0, 8.0)},
    "52": {"turnover": (7.0, 0.0, 30.0), "capex": (12.0, 0.0, 34.0), "opex": (5.0, 0.0, 22.0)},
    "10": {"turnover": (0.0, 0.0, 2.0), "capex": (1.0, 0.0, 3.0), "opex": (0.0, 0.0, 1.0)},
}


def main() -> None:
    from services.issuer_taxonomy import kpis as investee_kpis
    from services.issuer_taxonomy import write_total
    year = date.today().year - 1
    with get_session() as s:
        funds = s.execute(text("""
            SELECT f.fund_id::text, f.org_id::text FROM funds f JOIN organizations o USING (org_id)
            WHERE o.name LIKE '%(demo)' AND f.sfdr_classification IN ('article_8', 'article_9')""")).all()
        n_pos = 0
        for fund_id, org_id in funds:
            if s.execute(text("SELECT 1 FROM fund_positions WHERE fund_id = CAST(:f AS uuid) AND extract(year FROM as_of_date) = :y"),
                         {"f": fund_id, "y": year}).first():
                continue
            latest = s.execute(text("""
                SELECT security_id, market_value_eur, weight_pct FROM fund_positions WHERE fund_id = CAST(:f AS uuid)
                  AND as_of_date = (SELECT max(as_of_date) FROM fund_positions WHERE fund_id = CAST(:f AS uuid))"""),
                {"f": fund_id}).all()
            for month, k in _DRIFT.items():
                day = date(year, month, 30 if month in (6, 9) else 31)
                for sec, mv, w in latest:
                    s.execute(text("""INSERT INTO fund_positions (fund_id, security_id, market_value_eur, weight_pct, as_of_date)
                                      VALUES (CAST(:f AS uuid), :s, :mv, :w, :d)"""),
                              {"f": fund_id, "s": sec, "mv": round(float(mv or 0) * k, 2), "w": w, "d": day})
                    n_pos += 1
        n_kpi = 0
        for issuer_id, nace, org_id in s.execute(text("""
                SELECT DISTINCT i.issuer_id::text, i.nace_code, f.org_id::text
                FROM issuers i JOIN securities sec USING (issuer_id) JOIN fund_positions p USING (security_id)
                JOIN funds f USING (fund_id) JOIN organizations o ON o.org_id = f.org_id
                WHERE i.lei LIKE 'DEMO%' AND o.name LIKE '%(demo)'""")).all():
            on_file = investee_kpis(s, org_id, [issuer_id], year).get(issuer_id) or {}
            for basis, (aligned, gas, eligible) in (_DEMO_KPI.get((nace or "")[:2]) or {}).items():
                demo = {"eligible": eligible, "aligned": aligned, "fossil_gas": gas, "nuclear": 0.0}
                have = on_file.get(basis) if (on_file.get(basis) or {}).get("year") == year else {}
                todo = {m: v for m, v in demo.items() if have.get(m) is None}   # a stated value is never overwritten
                if todo:
                    write_total(s, issuer_id, org_id, year, basis, todo, source="client")
                    n_kpi += 1
        s.commit()
        print(f"SFDR demo history: {n_pos} quarter-end positions for {year}; {n_kpi} demo investee KPIs")


if __name__ == "__main__":
    main()
