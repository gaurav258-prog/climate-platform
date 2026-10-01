"""The final form — the frozen snapshot flattened into the labelled DATAPOINTS a preparer views and submits.

Each datapoint has a STABLE key (so a cell-level manual override can target it), a human label, a value, a
unit/format, and a source tag ('book' = from the uploaded book, 'calculated' = derived on the golden source).
The frozen snapshot is immutable; overrides live in a separate audited layer and are merged at read time.
"""
from __future__ import annotations

from services.governance.money_format import money, presentation_of


def _dp(key, label, value, fmt="num", unit=None, source="calculated", note=None):
    return {"key": key, "label": label, "value": value, "fmt": fmt, "unit": unit, "source": source, "note": note}


def _num(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def _headline_block(framework: str, r: dict) -> list[dict]:
    """The book's headline exposure figures, per framework — NOT a generic shape. Fixed 2026-09-24 (platform
    E2E audit): insurer_climate used to be forced through the bank/REIT field names (total_value_eur/
    n_scored/n_assets/value_at_risk_eur), which insurance's own rollup (api/routers/insurance.py:_rollup)
    never populates — it has EAL/premium/priced-policy concepts, not a VaR/discount/scored-asset concept.
    That silently rendered "Assets scored: 0/0" and dropped the value/VaR rows entirely on a real,
    correctly-computed book. filing_annex.py's _insurer_annex() already read the raw payload directly and
    was never affected — only this plain-form headline block was wrong."""
    if framework == "insurer_climate":
        return [
            _dp("book.total_sum_insured_eur", "Total sum insured", r.get("total_sum_insured_eur"), "eur", source="book"),
            _dp("book.total_expected_annual_loss_eur", "Expected annual loss (NatCat)", r.get("total_expected_annual_loss_eur"), "eur"),
            _dp("book.total_technical_premium_eur", "Technical premium (modelled on the stated method)",
                r.get("total_technical_premium_eur"), "eur"),
            _dp("book.sum_insured_at_risk_eur", "Sum insured at material physical risk (at or above the stated level)",
                r.get("value_at_risk_eur"), "eur"),
            _dp("book.coverage", "Policies priced", f"{r.get('n_priced', 0)} / {r.get('n_policies', 0)}", "text", source="book"),
        ]
    return [
        _dp("book.total_value_eur", "Total book value", r.get("total_value_eur"), "eur", source="book"),
        _dp("book.value_at_risk_eur", "Value at material physical risk (at or above the stated level)", r.get("value_at_risk_eur"), "eur"),
        _dp("book.pct_value_at_risk", "Share of book at risk", r.get("pct_value_at_risk"), "pct"),
        _dp("book.total_discounted_value_eur", "Risk-adjusted (climate-discounted) value", r.get("total_discounted_value_eur"), "eur"),
        _dp("book.coverage", "Assets scored", f"{r.get('n_scored', 0)} / {r.get('n_assets', 0)}", "text", source="book"),
    ]


def _located_book_form(framework: str, payload: dict) -> list[dict]:
    """bank_tcfd / reit_tcfd / insurer_climate — all assembled by build_disclosure_snapshot (rollup + by_hazard
    + taxonomy + financed_emissions). The headline block is framework-specific (_headline_block); the rest
    (financed emissions / taxonomy / by-hazard) reads generic payload keys shared or gracefully absent."""
    r = payload.get("rollup", {}) or {}
    groups = []

    headline = _headline_block(framework, r)
    # every headline figure stays on the form: one that is not computed shows as a gap with its reason (E69) —
    # never silently left out
    for d in headline:
        if d["value"] is None:
            d["note"] = "not computed — " + (r.get("gap") or "not available for this book")
    groups.append({"group": "Headline exposure", "datapoints": headline})

    fe = payload.get("financed_emissions_tco2e") or {}
    if fe:
        s1, s2, s3 = fe.get("scope1"), fe.get("scope2"), fe.get("scope3")
        from services.scoring.pcaf import financed_total
        tot = financed_total(fe)                        # counterparties stating all three scopes (E79)
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
            groups.append({"group": "Exposure by hazard (value at or above the stated at-risk level)", "datapoints": haz})

    return groups


def _sfdr_form(payload: dict) -> list[dict]:
    """sfdr_pai — one datapoint per Annex I Table 1 row (GHG emissions as its Scope 1 / 2 / 3 / total rows) and per
    adopted Table 2 / 3 indicator. Keys: 'indicator.<n>' (the total for no. 1), 'indicator.1.scope_<k>', 'additional.<key>'."""
    def note(i):
        return f"{round(i['coverage_pct'])}% coverage" if i.get("coverage_pct") is not None else None

    def rows(inds):
        out = []
        for i in inds or []:
            v, n = i.get("value"), i.get("number")
            if isinstance(v, dict):
                for k in ("scope_1", "scope_2", "scope_3"):
                    out.append(_dp(f"indicator.{n}.{k}", f"{n}. {i.get('metric')} — {k.replace('_', ' ').title()}",
                                   v.get(k), "num", unit=i.get("unit"), note=note(i)))
                v = v.get("total")
            out.append(_dp(f"indicator.{n}", f"{n}. {i.get('metric')}" + (" — Total" if isinstance(i.get("value"), dict) else ""),
                           v, "num", unit=i.get("unit"), note=note(i)))
        return out
    groups = [{"group": "Mandatory PAI indicators (Annex I · Table 1)", "datapoints": rows(payload.get("indicators"))}]
    if payload.get("real_estate_indicators"):
        groups.append({"group": "Real-estate indicators", "datapoints": rows(payload.get("real_estate_indicators"))})
    if payload.get("sovereign_indicators"):
        groups.append({"group": "Sovereign indicators", "datapoints": rows(payload.get("sovereign_indicators"))})
    add = [i for i in ((payload.get("additional_indicators") or {}).get("indicators") or [])]
    if add:
        groups.append({"group": "Additional indicators adopted (Annex I · Tables 2 and 3)", "datapoints": [
            _dp(f"additional.{i['key']}", f"Table {i.get('table')}, {i.get('row') or ''} {i.get('name')}".replace("  ", " "),
                i.get("value"), "num", unit=i.get("unit"), note=note(i)) for i in add]})
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
        return _located_book_form(framework, payload)
    if framework == "reit_taxonomy":
        return _reit_taxonomy_form(payload)
    if framework == "insurer_solvency":
        return _insurer_solvency_form(payload)
    if framework in ("insurer_orsa_climate", "insurer_recovery_stress"):
        return _insurer_document_form(framework, payload)
    if framework == "assetmgmt_tcfd":
        return _assetmgmt_tcfd_form(payload)
    if framework == "esrs_pack" and payload.get("document_report") is not None:
        from services.governance.esrs_document import form
        return form(payload)
    if framework == "sfdr_pai":
        return _sfdr_form(payload)
    if framework in ("sfdr_precontractual", "sfdr_periodic"):
        return _sfdr_product_form(framework, payload)
    return _generic_form(payload)


def _sfdr_product_form(framework: str, payload: dict) -> list[dict]:
    """A fund's SFDR document — the figures computed from its frozen holdings (periodic) and how far the template is
    answered; the document itself is the official-form tab."""
    from services.governance import sfdr_product as S
    from services.governance.sfdr_product_forms import items, missing
    if not payload.get("fund"):
        return []
    spec, tid, built = items(payload, framework)
    todo = [i for i in built if i["source"] != "fixed"]
    groups = [{"group": f"{payload['fund']['name']} — {tid} of {spec['act']['short']}", "datapoints": [
        _dp("items.total", "Template items to fill", len(todo)),
        _dp("items.missing", "Items without an answer", len(missing(built))),
        _dp("holdings", "Investee holdings frozen", len({h['issuer_id'] for h in payload.get('holdings') or []}))]}]
    if S.document_of(tid) == "periodic":
        tax = S.taxonomy(payload)
        groups.append({"group": "EU Taxonomy alignment of investments (%, from investees' own KPIs)", "datapoints": [
            _dp(f"taxonomy.{scope}.{b}.{k}", f"{'incl.' if scope == 'incl' else 'excl.'} sovereign bonds · {b} · {k.replace('_', ' ')}",
                tax[scope][b][k], "num", unit="%")
            for scope in ("incl", "excl") for b in S.BASES for k in ("aligned", "fossil_gas", "nuclear", "kpi_coverage")]})
        sec = S.sectors(payload)
        groups.append({"group": "Sectors", "datapoints": [_dp("sectors.fossil_fuel", "Investments in the fossil fuel sector",
                                                              sec["fossil_fuel_pct"], "num", unit="%")]})
    return groups


def _assetmgmt_tcfd_form(payload: dict) -> list[dict]:
    """Asset-manager holdings-book TCFD physical-risk disclosure — climate VaR, concentration, top exposures,
    per-hazard. Rendered from the frozen snapshot (was falling through to the thin generic form)."""
    r = payload.get("rollup") or {}
    c = payload.get("concentration") or {}
    by_hz = payload.get("by_hazard") or {}
    e = lambda v: money(v, presentation_of(payload), compact=False)  # noqa: E731
    pct = lambda v: (f"{v}%" if isinstance(v, (int, float)) else "—")          # noqa: E731

    sections: list[dict] = [{
        "section": "Portfolio climate value-at-risk (holdings book)",
        "note": f"Method: {r.get('var_method', '—')}",
        "rows": [
            {"label": "Total portfolio value", "value": e(r.get("total_portfolio_value_eur"))},
            {"label": "Climate value-at-risk", "value": e(r.get("total_climate_var_eur")),
             "pct": pct(r.get("portfolio_climate_var_pct"))},
            {"label": "Holdings scored", "value": f"{r.get('n_scored', '—')} of {r.get('n_holdings', '—')}"},
            {"label": "Flagged (at or above the stated level)", "value": str(r.get("n_flagged", "—"))},
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
    """Solvency II nat-cat risk (S.27.01.01): the modelled figure and the standard formula, as filing sections."""
    from services.governance.insurer_solvency import TEMPLATE, natcat_block
    s = natcat_block(payload)
    if not s or s.get("available") is False:
        return [{"section": f"Solvency II — natural catastrophe risk ({TEMPLATE})",
                 "rows": [{"label": "Status", "value": s.get("reason", "not available")}]}]
    scr = s.get("natcat_scr") or {}
    e = lambda v: money(v, presentation_of(payload), compact=False)  # noqa: E731
    return [{
        "section": f"Natural catastrophe risk ({TEMPLATE}) — modelled 1-in-200 (stated method; not an approved internal model)",
        "note": s.get("note"),
        "rows": [
            {"label": "Modelled 1-in-200 loss — gross (99.5%)", "value": e(scr.get("gross_1_in_200_eur"))},
            {"label": "Modelled 1-in-200 loss — net of reinsurance", "value": e(scr.get("net_of_reinsurance_1_in_200_eur"))},
            {"label": "Mean annual catastrophe loss", "value": e(scr.get("mean_annual_loss_eur"))},
            {"label": "Risk load", "value": e(scr.get("risk_load_eur"))},
            {"label": "Modelled 1-in-200 as % of sum insured",
             "value": (f"{scr['scr_pct_of_sum_insured']}%" if scr.get("scr_pct_of_sum_insured") is not None else "—")},
        ],
    }, {
        "section": "Natural-catastrophe perils (exposure driving the aggregate)",
        "rows": [{"label": p["peril"], "value": e(p["exposed_value_eur"]),
                  "note": f"{p['n_exposed']} exposures · {', '.join(p['channels'])}"} for p in s.get("perils", [])],
    }, *_sf_natcat_sections(s.get("standard_formula_natcat"), e), {
        "section": "Out of scope",
        "note": (s.get("declared") or {}).get("note"),
        "rows": [{"label": it, "value": "declared"} for it in (s.get("declared") or {}).get("items", [])],
    }]


def _insurer_document_form(framework: str, payload: dict) -> list[dict]:
    """An insurer document report — how far it is computed and answered; the document itself is the official-form tab."""
    from services.governance.insurer_documents import _frozen_spec, build
    spec, doc = _frozen_spec(payload, framework), payload.get("document_report")
    if spec is None or not doc:
        return [{"section": "Specification", "rows": [{"label": "Status", "value": "no adopted specification governs this "
                                                                                "report's disclosure date"}]}]
    built = [i for i in build(spec, framework, doc) if i["source"] != "fixed"]
    return [{"section": "Items of the template", "rows": [
        {"label": f"{i['id']}", "value": {"filled": "computed" if i["source"] == "computed" else "answered",
                                          "missing": "missing", "printed": "not required"}[i["status"]],
         "note": (i.get("note") or i.get("needs") or "")} for i in built]}]


def _sf_natcat_sections(sf: dict | None, e) -> list[dict]:
    """The standard formula (Del. Reg. 2015/35 Arts 90b, 119-126), region by region, before and after mitigation."""
    from services.governance.solvency2_natcat import lines
    if not sf or sf.get("available") is False:
        return [{"section": "Natural catastrophe risk — standard formula",
                 "rows": [{"label": "Status", "value": "no exposure to a nat-cat region"}]}]
    if "version" not in sf:                                   # frozen before the rebuild: shown as frozen
        return [{"section": "Natural catastrophe risk — standard formula (as frozen)", "rows": [
            {"label": "Nat-cat SCR", "value": e(sf.get("natcat_scr_eur")),
             "note": "gross of reinsurance, country level — the method this filing was frozen with"}]}]
    head = [{"label": "Natural catastrophe risk — after risk mitigation", "value": e(sf.get("natcat_scr_eur")),
             "note": f"before mitigation {e(sf.get('natcat_scr_before_mitigation_eur'))} · reinsurance: "
                     f"{'attested treaty' if sf.get('treaty_basis') == 'attested' else 'none attested — no mitigation'}"},
            {"label": "Version of the Regulation", "value": sf.get("version_name") or sf.get("version"), "note": sf.get("version_source")}]
    if not sf.get("complete", True):
        head += [{"label": "Incomplete", "value": x} for x in sf.get("incomplete", [])]
    head += [{"label": f"Reading — {r['subject']}", "value": "declared", "note": r["reading"]} for r in sf.get("readings", [])]
    sections = [{"section": "Natural catastrophe risk — standard formula", "rows": head}]
    by: dict[str, list] = {}
    for ln in lines(sf):
        by.setdefault(ln["peril"], []).append(ln)
    for peril, rows in by.items():
        sections.append({"section": f"{peril} — before / after risk mitigation", "rows": [
            {"label": ln["line"], "value": e(ln.get("after_eur")),
             "note": " · ".join(x for x in (
                 f"exposure {e(ln['exposure_eur'])}" if ln.get("exposure_eur") is not None else "",
                 f"specified gross loss {e(ln['specified_gross_loss_eur'])}" if ln.get("specified_gross_loss_eur") is not None else "",
                 f"scenario {ln['scenario']}" if ln.get("scenario") else "",
                 f"before mitigation {e(ln['before_eur'])}" if ln.get("before_eur") is not None else "",
                 ln.get("note") or "") if x)} for ln in rows]})
    return sections


def _reit_taxonomy_form(payload: dict) -> list[dict]:
    """The EU Taxonomy Art. 8 turnover split of the property book (Del. Reg. 2021/2178 Annex I / II) — the same figures
    as the official Annex II templates (services.governance.taxonomy_nonfin)."""
    from services.governance.taxonomy_nonfin import summary_of
    sm = summary_of(payload)
    e = lambda v: money(v, presentation_of(payload), compact=False)  # noqa: E731
    rows = [{"label": lbl, "value": e(sm[k]) if k != "turnover" else e(sm["turnover"]),
             "pct": _fmt_pct(sm["pct"].get(k)) if k != "turnover" else "100%"} for k, lbl in (
        ("turnover", "Turnover"), ("eligible", "Taxonomy-eligible (A)"), ("aligned", "of which aligned (A.1)"),
        ("not_aligned", "of which not aligned (A.2)"), ("unknown", "of which alignment not determined"),
        ("phased", "of which eligibility only (phase-in, Art. 10(6))"),
        ("non_eligible", "Taxonomy-non-eligible (B)")) if k != "phased" or sm["n_phased"]]
    note = (f"{sm['n_unknown']} buildings lack facts to decide alignment: "
            + "; ".join(f"{r} ({n})" for r, n in sm["unknown_reasons"]) + ".") if sm["n_unknown"] else None
    return [{"section": "Turnover KPI (Del. Reg. (EU) 2021/2178, Art. 8)", "note": note, "rows": rows},
            {"section": "CapEx / OpEx KPIs", "rows": [{"label": "CapEx KPI", "value": "entered from the undertaking's ledger"},
                                                       {"label": "OpEx KPI", "value": "entered from the undertaking's ledger"}]}]


def _fmt_pct(v) -> str | None:
    return f"{v}%" if v is not None else None
