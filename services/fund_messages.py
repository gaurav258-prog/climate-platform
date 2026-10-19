"""The customer words a fund screen shows (UI standard, product owner 2026-10-16): the PAI analytics and statement as
messages of the catalogue (data/reference/messages.en.json, disclose.*) — what is still missing, what would complete an
indicator, how the Taxonomy share is read — and the outcome of a holdings upload. The engines keep their sentences for
the workbook and the filing services; a screen reads these."""
from __future__ import annotations

from core import messages

# the data an issuer-data indicator needs, by its Table 1 number (names.disclose.pai_data)
_DATA_NEEDS = ("issuer_data", "issuer_data_none", "real_estate_data")


def message(gap: dict | None) -> dict | None:
    """A {code, params} the engines give, rendered; an indicator number becomes the data it needs, by name."""
    if not gap:
        return None
    params = dict(gap.get("params") or {})
    kind = gap["code"].rsplit(".", 1)[-1]
    if kind in _DATA_NEEDS and "indicator" in params:
        params["data"] = messages.name("disclose.pai_data", str(params.pop("indicator")))
    if gap["code"].startswith("disclose.pai.gap.") and "section" in params:
        params["section_name"] = messages.name("disclose.pai_section", params["section"])
    for k in ("rest",):
        if isinstance(params.get(k), float):
            params[k] = f"{params[k]:g}"
    return messages.render(gap["code"], **params)


def _taxonomy(tax: dict, basis: str, name: str) -> dict:
    aligned, cov = tax.get(f"taxonomy_aligned_{basis}_pct"), tax.get(f"{basis}_alignment_coverage_pct")
    excluded = tax.get(f"{basis}_aligned_excluded_dnsh_pct") or 0
    if aligned is None and not excluded:
        return messages.render("disclose.fund.taxonomy.not_asserted", basis=name)
    if excluded:
        return messages.render("disclose.fund.taxonomy.excluded", basis=name, coverage=f"{cov or 0:g}",
                               excluded=f"{excluded:g}")
    return messages.render("disclose.fund.taxonomy.aligned", basis=name, coverage=f"{cov or 0:g}")


def statement_view(st: dict) -> dict:
    """The screen's words for a fund's PAI analytics or the manager's statement: readiness, indicator needs, Taxonomy.
    A record frozen before the engines named their gaps reads what it can (its identity) and no more."""
    if st.get("error"):
        return {"error": messages.render(_reason_code(st["error"]), **_reason_params(st["error"]))}
    fr = st.get("filing_readiness") or {}
    gaps = fr.get("gaps")
    if gaps is None:                                   # a record frozen before readiness carried its messages
        gaps = [{"code": f"disclose.identity.{k}", "params": {}} for k, s in
                (("lei", "manager LEI"), ("legal_name", "manager legal name"), ("contact", "filing contact email"))
                if s in (fr.get("missing") or [])]
    rows = (st.get("indicators") or []) + (st.get("sovereign_indicators") or []) + (st.get("real_estate_indicators") or [])
    tax = st.get("taxonomy") or {}
    return {
        "readiness": [message(g) for g in gaps],
        "needs": {str(r["number"]): message(r.get("need")) for r in rows if r.get("need")},
        "taxonomy": {"turnover": _taxonomy(tax, "turnover", "turnover"),
                     "capex": _taxonomy(tax, "capex", "CapEx")} if tax else None,
    }


# why a statement cannot be built (ml.regulatory.sfdr_pai's 'error'): by its own words, as a catalogue code
def _reason_code(error: str) -> str:
    if error == "fund has no positions to report on":
        return "disclose.fund.no_positions"
    if error.startswith("manager has no positions to report on"):
        return "filing.gap.sfdr_no_positions"
    if error == "manager has no funds":
        return "filing.gap.sfdr_no_funds"
    return "filing.gap.sfdr_unavailable"


def _reason_params(error: str) -> dict:
    if error.startswith("manager has no positions to report on"):
        tail = error[len("manager has no positions to report on"):].strip()
        return {"year": tail[len("in "):] if tail.startswith("in ") else "the period"}
    return {}


def reason(error: str) -> tuple[str, dict]:
    """(code, params) for a statement's 'error' — a refusal raises it as core.errors.UserError."""
    return _reason_code(error), _reason_params(error)


def source(prior: dict | None) -> dict:
    """Where the previous period's figures come from: a statement filed (with its status), or one uploaded and
    confirmed; none reported."""
    if not prior:
        return messages.render("disclose.pai.prior.none")
    if prior.get("source_kind") == "uploaded":
        return messages.render("disclose.pai.prior.uploaded", period=prior["period_end"][:4])
    status = prior.get("status") or "submitted"
    return messages.render("disclose.pai.prior.filed", period=prior["period_end"][:4],
                           status=messages.name("filing.status", status))


def onboarding(resp: dict) -> dict:
    """The outcome of a holdings upload, as messages: what was added, what was not matched or converted, what was
    refused — each with its detail one click away."""
    cov, fx = resp["coverage"], resp.get("fx") or {}
    out = {"summary": messages.render("disclose.fund.onboard.done", n=resp["positions_created"],
                                      matched=cov["matched"], isins=resp["distinct_isins"])}
    if cov.get("unmatched"):
        out["unmatched"] = messages.render("disclose.fund.onboard.unmatched", n=len(cov["unmatched"]),
                                           isins=", ".join(cov["unmatched"]))
    if cov.get("errored"):
        out["errored"] = messages.render("disclose.fund.onboard.errored", n=len(cov["errored"]),
                                         isins=", ".join(cov["errored"]))
    if fx.get("errors"):
        out["fx"] = messages.render("disclose.fund.onboard.fx", n=len(fx["errors"]))
    if cov.get("sector_gap_isins"):
        out["sector"] = messages.render("disclose.fund.onboard.sector", n=len(cov["sector_gap_isins"]),
                                        isins=", ".join(cov["sector_gap_isins"]))
    if (cov.get("footprints") or {}).get("failed"):
        out["located"] = messages.render("disclose.fund.onboard.not_located", n=cov["footprints"]["failed"])
    if cov.get("own_share_classes"):
        out["own"] = messages.render("disclose.fund.onboard.own_classes", n=len(cov["own_share_classes"]),
                                     isins=", ".join(c["isin"] for c in cov["own_share_classes"]))
    if resp.get("voluntary_rejected"):
        rej = resp["voluntary_rejected"]
        out["refused"] = messages.render("disclose.fund.onboard.refused", n=len(rej),
                                         items="; ".join(f"{r['isin']} — {messages.label(r['code'])}" for r in rej))
    return out
