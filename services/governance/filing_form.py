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
    if framework in ("bank_tcfd", "bank_p3esg", "reit_tcfd", "insurer_climate"):
        return _located_book_form(payload)
    if framework == "reit_taxonomy":
        return _reit_taxonomy_form(payload)
    if framework == "insurer_solvency":
        return _insurer_solvency_form(payload)
    if framework == "assetmgmt_tcfd":
        return _assetmgmt_tcfd_form(payload)
    if framework == "sfdr_pai":
        return _sfdr_form(payload)
    return _generic_form(payload)


def _assetmgmt_tcfd_form(payload: dict) -> list[dict]:
    """Asset-manager holdings-book TCFD physical-risk disclosure — climate VaR, concentration, top exposures,
    per-hazard. Rendered from the frozen snapshot (was falling through to the thin generic form)."""
    r = payload.get("rollup") or {}
    c = payload.get("concentration") or {}
    by_hz = payload.get("by_hazard") or {}
    e = lambda v: (f"€{round(v):,}" if isinstance(v, (int, float)) else "—")  # noqa: E731
    pct = lambda v: (f"{v}%" if isinstance(v, (int, float)) else "—")          # noqa: E731

    sections: list[dict] = [{
        "section": "Portfolio climate value-at-risk (holdings book)",
        "note": f"Method: {r.get('var_method', '—')}",
        "rows": [
            {"label": "Total portfolio value", "value": e(r.get("total_portfolio_value_eur"))},
            {"label": "Climate value-at-risk", "value": e(r.get("total_climate_var_eur")),
             "pct": pct(r.get("portfolio_climate_var_pct"))},
            {"label": "Holdings scored", "value": f"{r.get('n_scored', '—')} of {r.get('n_holdings', '—')}"},
            {"label": "Flagged (High+)", "value": str(r.get("n_flagged", "—"))},
        ],
    }]
    if r.get("by_bucket"):
        bb = r["by_bucket"]
        rows = [{"label": b, "value": (str(v) if not isinstance(v, dict) else e(v.get("value_eur")))}
                for b, v in (bb.items() if isinstance(bb, dict) else [])]
        if rows:
            sections.append({"section": "Value-at-risk by severity band", "rows": rows})
    sections.append({
        "section": "Concentration & diversification",
        "rows": [
            {"label": "Scored coverage", "value": pct(c.get("coverage_pct"))},
            {"label": "Geographic concentration (HHI)", "value": str(c.get("region_hhi", "—")),
             "note": f"effective regions {c.get('effective_regions', '—')} · top {c.get('top_region', '—')}"},
            {"label": "Hazard concentration (HHI)", "value": str(c.get("hazard_hhi", "—")),
             "note": f"effective hazards {c.get('effective_hazards', '—')} · top {c.get('top_hazard', '—')}"},
        ],
    })
    top = r.get("top_holdings") or []
    if top:
        sections.append({
            "section": "Most-exposed holdings",
            "rows": [{"label": h.get("name") or h.get("issuer") or h.get("holding_id") or "—",
                      "value": e(h.get("climate_var_eur") or h.get("value_eur")),
                      "note": h.get("headline_hazard") or h.get("hazard")} for h in top[:10]],
        })
    if by_hz:
        sections.append({
            "section": "Physical-risk exposure by hazard",
            "rows": [{"label": hz, "value": e(a.get("exposed_value_eur")),
                      "note": f"{a.get('n_exposed', 0)} holdings"} for hz, a in
                     sorted(by_hz.items(), key=lambda kv: -(kv[1].get("exposed_value_eur") or 0))[:12]],
        })
    return sections


def _insurer_solvency_form(payload: dict) -> list[dict]:
    """Render Solvency II S.26.01.01 NatCat SCR (Del. Reg. 2015/35) as filing sections."""
    s = payload.get("s2601") or {}
    if not s or s.get("available") is False:
        return [{"section": "Solvency II — Nat-Cat SCR (S.26.01.01)",
                 "rows": [{"label": "Status", "value": s.get("reason", "not available")}]}]
    scr = s.get("natcat_scr") or {}
    e = lambda v: (f"€{v:,}" if isinstance(v, (int, float)) else "—")  # noqa: E731
    return [{
        "section": "Nat-Cat SCR (S.26.01.01) — internal-model basis",
        "note": s.get("note"),
        "rows": [
            {"label": "NatCat SCR — gross (1-in-200, 99.5% VaR)", "value": e(scr.get("gross_1_in_200_eur"))},
            {"label": "NatCat SCR — net of reinsurance", "value": e(scr.get("net_of_reinsurance_1_in_200_eur"))},
            {"label": "Mean annual catastrophe loss", "value": e(scr.get("mean_annual_loss_eur"))},
            {"label": "Risk load", "value": e(scr.get("risk_load_eur"))},
            {"label": "SCR as % of sum insured",
             "value": (f"{scr['scr_pct_of_sum_insured']}%" if scr.get("scr_pct_of_sum_insured") is not None else "—")},
        ],
    }, {
        "section": "Natural-catastrophe sub-modules (exposure driving the aggregate)",
        "rows": [{"label": p["peril"], "value": e(p["exposed_value_eur"]),
                  "note": f"{p['n_exposed']} exposures · {', '.join(p['channels'])}"} for p in s.get("perils", [])],
    }, {
        "section": "Prescribed standard-formula cells",
        "note": (s.get("declared") or {}).get("note"),
        "rows": [{"label": it, "value": "declared — official factor tables required"}
                 for it in (s.get("declared") or {}).get("items", [])],
    }]


def _reit_taxonomy_form(payload: dict) -> list[dict]:
    """Render the EU Taxonomy Article 8 KPI block (Del. Reg. 2021/2178) as filing sections."""
    a = payload.get("art8") or {}
    to = a.get("turnover_kpi") or {}
    ev = to.get("alignment_evidence") or {}
    sections: list[dict] = [{
        "section": "Turnover KPI (Del. Reg. (EU) 2021/2178, Art. 8)",
        "note": to.get("basis"),
        "rows": [{"label": r["row"], "value": (f"€{r['eur']:,}" if r.get("eur") is not None else "—"),
                  "pct": (f"{r['pct']}%" if r.get("pct") is not None else None), "note": r.get("note")}
                 for r in to.get("rows", [])],
    }, {
        "section": "Alignment evidence (verifiable sub-signals — not an alignment claim)",
        "rows": [
            {"label": "Substantial contribution — EPC A/B (§7.7 TSC)", "pct": _fmt_pct(ev.get("substantial_contribution_epc_ab_pct"))},
            {"label": "Climate-adaptation DNSH favourable (our physical-risk assessment, Art. 17)", "pct": _fmt_pct(ev.get("climate_adaptation_dnsh_favourable_pct"))},
            {"label": "Minimum safeguards verified", "pct": _fmt_pct(ev.get("minimum_safeguards_verified_pct"))},
        ],
        "note": ev.get("note"),
    }, {
        "section": "CapEx / OpEx KPIs",
        "note": (a.get("capex_kpi") or {}).get("note"),
        "rows": [{"label": "CapEx KPI", "value": "declared — customer capex ledger required"},
                 {"label": "OpEx KPI", "value": "declared — customer opex ledger required"}],
    }]
    return sections


def _fmt_pct(v) -> str | None:
    return f"{v}%" if v is not None else None
