"""Agriculture crop-shock validators — the crop model vs observed production shocks.

The agri impact model is calibrated by EVENT REPRODUCTION: a commodity's sensitivity is fitted so the chain
reproduces a real, dated crop-year shock (e.g. West-Africa cocoa 2023/24 heat → FAOSTAT −8.9%). This validator
tests the modelled production shock against the observed one across the catalogued events in
`sc_model_validation` — a regression check (r²-gated like any continuous model).

Honest about data: with only a handful of curated events, most cuts return INSUFFICIENT — and that is the
correct answer, not a fabricated pass. The record grows automatically as more observed crop shocks (FAOSTAT /
IBGE / national statistics) are ingested; the same validator then yields a real skill number with no code
change. Registered per-hazard and as an aggregate.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

_SQL = """
    SELECT commodity, hazard, CAST(model_prod_shock_pct AS FLOAT)  AS model,
                              CAST(observed_prod_shock_pct AS FLOAT) AS observed
    FROM sc_model_validation
    WHERE model_prod_shock_pct IS NOT NULL AND observed_prod_shock_pct IS NOT NULL
    {where}
"""


def _crop_shock(hazard: str | None, source: str):
    def run(session: Session) -> ValidationResult:
        where = "AND hazard = :h" if hazard else ""
        rows = session.execute(text(_SQL.format(where=where)),
                               ({"h": hazard} if hazard else {})).mappings().all()
        pred = [r["model"] for r in rows]
        obs = [r["observed"] for r in rows]
        labels = [f"{r['commodity']}·{r['hazard']}" for r in rows]
        return ValidationResult(
            hazard_type=hazard or "agri_all", kind="regression",
            predicted=pred, observed=obs, labels=labels,
            target_source=source, scope="global", method="event_reproduction",
            data_vintage=f"{len(rows)} catalogued crop-shock events",
            notes=("modelled vs observed crop-year production shock over catalogued events; "
                   "grows as more observed shocks (FAOSTAT/IBGE) are ingested"),
        )
    return run


register("agri_drought")(_crop_shock("drought", "FAOSTAT / national crop statistics (drought events)"))
register("agri_heat")(_crop_shock("heat_acute", "FAOSTAT / national crop statistics (acute-heat events)"))
register("agri_crop_shock")(_crop_shock(None, "FAOSTAT / national crop statistics (all hazards)"))
