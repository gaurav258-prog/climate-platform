"""The final form — the frozen snapshot flattened into the labelled DATAPOINTS a preparer views and submits.

Each datapoint has a STABLE key (so a cell-level manual override can target it), a human label, a value, a
unit/format, and a source tag ('book' = from the uploaded book, 'calculated' = derived on the golden source).
The frozen snapshot is immutable; overrides live in a separate audited layer and are merged at read time.
"""
from __future__ import annotations


def _dp(key, label, value, fmt="num", unit=None, source="calculated", note=None):
    return {"key": key, "label": label, "value": value, "fmt": fmt, "unit": unit, "source": source, "note": note}


def _num(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _located_book_form(payload: dict) -> list[dict]:
    """bank_tcfd / reit_tcfd / insurer_climate — all assembled by build_disclosure_snapshot (rollup + by_hazard
    + taxonomy + financed_emissions)."""
    r = payload.get("rollup", {}) or {}
    groups = []

    headline = [
        _dp("book.total_value_eur", "Total book value", r.get("total_value_eur"), "eur", source="book"),
        _dp("book.value_at_risk_eur", "Value at risk (High+)", r.get("value_at_risk_eur"), "eur"),
        _dp("book.pct_value_at_risk", "Share of book at risk", r.get("pct_value_at_risk"), "pct"),
        _dp("book.total_discounted_value_eur", "Risk-adjusted (climate-discounted) value", r.get("total_discounted_value_eur"), "eur"),
        _dp("book.coverage", "Assets scored", f"{r.get('n_scored', 0)} / {r.get('n_assets', 0)}", "text", source="book"),
    ]
    groups.append({"group": "Headline exposure", "datapoints": [d for d in headline if d["value"] is not None]})

    fe = payload.get("financed_emissions_tco2e") or {}
    if fe:
        s1, s2, s3 = fe.get("scope1"), fe.get("scope2"), fe.get("scope3")
        tot = sum(x for x in (s1, s2, s3) if isinstance(x, (int, float)))
        groups.append({"group": "Financed emissions (PCAF)", "datapoints": [
            _dp("emissions.scope1", "Scope 1", s1, "tco2e"),
            _dp("emissions.scope2", "Scope 2", s2, "tco2e"),
            _dp("emissions.scope3", "Scope 3", s3, "tco2e"),
            _dp("emissions.total", "Total financed emissions", tot, "tco2e"),
        ]})

    tx = payload.get("taxonomy") or {}
    if tx:
        groups.append({"group": "EU Taxonomy", "datapoints": [
            _dp("taxonomy.eligible_value_eur", "Taxonomy-eligible", _num(tx, "eligible", "value_eur"), "eur", source="book"),
            _dp("taxonomy.not_eligible_value_eur", "Not eligible", _num(tx, "not_eligible", "value_eur"), "eur", source="book"),
            _dp("taxonomy.not_assessed_value_eur", "Not assessed", _num(tx, "not_assessed", "value_eur"), "eur", source="book"),
        ]})

    bh = payload.get("by_hazard") or {}
    if bh:
        haz = [_dp(f"hazard.{h}", h, (v or {}).get("exposed_value_eur"), "eur", note=f"{(v or {}).get('n_exposed', 0)} exposed")
               for h, v in bh.items() if (v or {}).get("exposed_value_eur")]
        haz.sort(key=lambda d: -(d["value"] or 0))
        if haz:
            groups.append({"group": "Exposure by hazard (value at High+)", "datapoints": haz})

    return groups


def _sfdr_form(payload: dict) -> list[dict]:
    """sfdr_pai — the Annex I indicators are already a clean list; each becomes one datapoint."""
    def val(v):
        return v.get("total") if isinstance(v, dict) else v
    def rows(inds):
        return [_dp(f"indicator.{i.get('number')}", f"{i.get('number')}. {i.get('metric')}", val(i.get('value')),
                    "num", unit=i.get("unit"), note=(f"{round(i['coverage_pct'])}% coverage" if i.get("coverage_pct") is not None else None))
                for i in (inds or [])]
    groups = [{"group": "Mandatory PAI indicators (Annex I · Table 1)", "datapoints": rows(payload.get("indicators"))}]
    if payload.get("real_estate_indicators"):
        groups.append({"group": "Real-estate indicators", "datapoints": rows(payload.get("real_estate_indicators"))})
    if payload.get("sovereign_indicators"):
        groups.append({"group": "Sovereign indicators", "datapoints": rows(payload.get("sovereign_indicators"))})
    return groups


def _generic_form(payload: dict) -> list[dict]:
    """CSRD/ESRS and any other shape — surface the scalar headline figures so the form is never empty. A richer
    per-framework schema (and the regulator's exact layout) is a documented follow-on."""
    dps = []
    for k, v in payload.items():
        if isinstance(v, (int, float)):
            dps.append(_dp(f"root.{k}", k.replace("_", " "), v, "num"))
        elif isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, (int, float)):
                    dps.append(_dp(f"{k}.{kk}", f"{k.replace('_', ' ')} · {kk.replace('_', ' ')}", vv, "num"))
    return [{"group": "Reported figures", "datapoints": dps[:40]}] if dps else []


def build_form(framework: str, payload: dict) -> list[dict]:
    if not payload:
        return []
    if framework in ("bank_tcfd", "reit_tcfd", "insurer_climate"):
        return _located_book_form(payload)
    if framework == "sfdr_pai":
        return _sfdr_form(payload)
    return _generic_form(payload)
