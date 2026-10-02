"""Per reported figure: the client's attested number or Tellumen's computed one (intake phase 5).

Some figures both sides produce — financed emissions (a bank's audited PCAF figure vs our PCAF engine), the protected-
area count (a WDPA holder's count vs ours from Natura 2000 + OpenStreetMap). The client's number enters through Lane 2
(provided_data: submitted, reconciled against ours, attested under four eyes). Where both exist at freeze, the filing
records which one it REPORTS — the client's by default (principle 1), ours if the preparer chooses — and keeps the other
beside it with the difference. The choice is frozen in the payload (`_figures`, hash-verified) and, where the official
form carries the figure, the form reports the chosen value.

FIGURES: (framework, provided datapoint) → how to read OUR value from the frozen payload, and the form datapoint it is.
"""
from __future__ import annotations

from typing import Callable, Optional


def _scope3(p: dict) -> Optional[float]:
    """Our Scope 3 financed emissions: Template 1's total row, column j, on the institution's stated method (E103); a
    filing frozen before that, the PCAF figure it froze."""
    from services.governance.pillar3_t1 import RECORD
    if RECORD in p:
        from services.governance.pillar3_report import t1_total
        v = (t1_total(p) or {}).get("j")
    else:
        v = (p.get("financed_emissions_tco2e") or {}).get("scope3")
    return float(v) if v is not None else None


FIGURES: dict[tuple[str, str], dict] = {
    ("bank_p3esg", "p3_scope3"): {"ours": _scope3, "form_key": "emissions.scope3", "unit": "tCO2e"},
}
SOURCES = ("client", "tellumen")


def figures_for(framework: str) -> list[str]:
    return [dp for (fw, dp) in FIGURES if fw == framework]


def resolve(framework: str, payload: dict, requested: Optional[dict] = None) -> list[dict]:
    """The figures both sides produced for this frozen payload, and which one the filing reports."""
    requested = requested or {}
    attested = {p["key"].removeprefix("provided."): p for p in payload.get("_provided_attested") or []}
    out = []
    for dp in figures_for(framework):
        spec: dict = FIGURES[(framework, dp)]
        ours: Callable = spec["ours"]
        client = attested.get(dp)
        tellumen = ours(payload)
        if client is None:
            continue                                                  # no client figure: ours is simply the figure
        cv = client["value"]
        reported = requested.get(dp) if requested.get(dp) in SOURCES else "client"
        if reported == "tellumen" and tellumen is None:
            reported = "client"                                       # we have no number to report
        delta = (round(100.0 * (float(cv) - tellumen) / tellumen, 1)
                 if isinstance(cv, (int, float)) and tellumen not in (None, 0) else None)
        out.append({"datapoint": dp, "label": client.get("label", dp), "unit": client.get("unit") or spec["unit"],
                    "form_key": spec["form_key"], "reported": reported, "client_value": cv, "tellumen_value": tellumen,
                    "delta_pct": delta, "client_provider": client.get("provider"), "attested_by": client.get("attested_by")})
    return out


def apply_to_form(groups: list[dict], figures: list[dict]) -> None:
    """Put the reported value on the form datapoint each figure is, with both values beside it."""
    by_key = {f["form_key"]: f for f in figures if f.get("form_key")}
    for g in groups:
        for d in g.get("datapoints") or []:
            f = by_key.get(d.get("key"))
            if not f:
                continue
            d["figure"] = {k: f[k] for k in ("reported", "client_value", "tellumen_value", "delta_pct", "client_provider", "attested_by")}
            d["value"] = f["client_value"] if f["reported"] == "client" else f["tellumen_value"]
            d["source"] = "provided" if f["reported"] == "client" else d.get("source", "calculated")
