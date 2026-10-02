"""What a manager answers in its principal-adverse-impacts statement, per reference period (Delegated Regulation (EU)
2022/1288, Articles 5 to 10) — and the previous periods' figures the statement compares with.

Answers live in the one store (services.governance.template_answers: family 'sfdr_pai', document 'pai_statement', the
organisation as subject, keyed by the period's 31 December), item ids '<section>.<item>' for the sections of the
governing spec (S1 Summary, S4 Policies, S5 Engagement, S6 International standards — each item quoted from its
Article) and '<datapoint>.expl' / '<datapoint>.action' for Table 1's columns 'Explanation' and 'Actions taken, and
actions planned and targets set for the next reference period', per row (Article 6(1)-(2): 'complete all the fields').

Computed, never answered:
  S1 (a)-(c)          the participant's name, the fact that PAIs are considered, the reference period
  Impact [year n-1]   the figure reported for the previous period — the filed statement for it (submitted or accepted),
                      else a previous statement uploaded and confirmed for the organisation and that period end (E123)
  S7 (Article 10)     every previous period reported on, up to five, as reported

What the text leaves to the manager is its statement (no default): whether an engagement policy under Article 3g of
Directive 2007/36/EC applies ('where applicable'), whether it has other engagement policies ('any other'), whether a
forward-looking climate scenario is used, and which language requirement each language of the summary meets.

Named gaps (not checked): a language code is checked for its shape only (no ISO 639 list is held); which language is
official in which Member State, and in which host Member States a product is made available, are the manager's
statements; the two-A4-sides limit on the summary (Article 5) depends on how it is printed and is not measured.
"""
from __future__ import annotations

import re
from datetime import date

from sqlalchemy import text

from services.governance.template_answers import AnswerError

FAMILY, DOCUMENT = "sfdr_pai", "pai_statement"
SECTIONS = ("S1", "S4", "S5", "S6", "S7")
# how each item of the sections is filled (services.governance.sfdr_binding binds these for coverage())
SECTION_BINDING = {
    "S1": {"a_name": "computed:manager_legal_name", "b_considered": "computed:pai_considered",
           "c_period": "computed:reference_period", "d_summary": "input:summary_by_language"},
    "S4": {"policies": "input:text", "a_approval_date": "input:date", "b_responsibility": "input:text",
           "c_methodologies": "input:text", "d_margin_of_error": "input:text", "e_data_sources": "input:text",
           "best_efforts": "input:where_not_readily_available"},
    "S5": {"a_srd": "input:where_applicable", "b_other": "input:where_applicable", "2a_indicators": "input:text",
           "2b_adaptation": "input:text"},
    "S6": {"adherence": "input:text", "2a_indicators": "input:text", "2b_methodology": "input:text",
           "2c_scenario": "input:choice", "2d_no_scenario": "input:where_no_scenario"},
    "S7": {"comparison": "computed:previous_periods"},
}
LANGUAGE_MEETS = ("home_official", "international_finance", "host_official")
REPORTED = ("submitted", "accepted")        # a statement 'reported on' (Article 10): sent to the regulator / published
MAX_PREVIOUS = 5                            # Article 10: 'up to the last five previous periods'


# ── the figures of a statement, by datapoint (the form's keys: services.governance.filing_form._sfdr_form) ─────────
def impact_rows(statement: dict) -> list[dict]:
    """Every impact row of a statement, Table 1 then the adopted Tables 2 / 3 indicators: {key, label, value}."""
    out = []
    for i in (statement.get("indicators") or []) + (statement.get("sovereign_indicators") or []) + \
            (statement.get("real_estate_indicators") or []):
        n, v = i.get("number"), i.get("value")
        if isinstance(v, dict):
            for k in ("scope_1", "scope_2", "scope_3"):
                out.append({"key": f"indicator.{n}.{k}", "label": f"{n}. {i.get('metric')} — {k.replace('_', ' ').title()}",
                            "value": v.get(k), "unit": i.get("unit")})
            v = v.get("total")
        out.append({"key": f"indicator.{n}", "label": f"{n}. {i.get('metric')}", "value": v, "unit": i.get("unit")})
    for i in ((statement.get("additional_indicators") or {}).get("indicators") or []):
        out.append({"key": f"additional.{i['key']}", "label": f"Table {i.get('table')}, {i.get('row') or ''} {i.get('name')}",
                    "value": i.get("value"), "unit": i.get("unit")})
    return out


# ── the answerable items ─────────────────────────────────────────────────────────────────────────────────────────
def template(spec: dict, statement: dict) -> dict:
    """The items a manager answers for this statement: the sections' input items (with their table columns) and, per
    impact row, its explanation and actions."""
    import services.regspec as R
    items = []
    for sid in SECTIONS:
        for i in R.template(spec, sid).get("items") or []:
            items.append({**i, "id": f"{sid}.{i['id']}", "parent": f"{sid}.{i['parent']}" if i.get("parent") else None,
                          "section": sid})
    for r in impact_rows(statement):
        items += [{"id": f"{r['key']}.expl", "kind": "field", "label": f"{r['label']} — Explanation", "parent": None},
                  {"id": f"{r['key']}.action", "kind": "field", "label": f"{r['label']} — Actions taken, and actions "
                   "planned and targets set for the next reference period", "parent": None}]
    return {"items": items}


def bound(tmpl: dict) -> dict:
    """{item id: 'input' | 'computed'} for template_answers.save — section items per SECTION_BINDING, row answers input."""
    out = {}
    for i in tmpl["items"]:
        if i.get("section"):
            sid, iid = i["id"].split(".", 1)
            src = SECTION_BINDING[sid].get(iid)
            if src:
                out[i["id"]] = src.split(":", 1)[0]
        else:
            out[i["id"]] = "input"
    return out


def _validate(item: dict, value) -> dict | None:
    """The stored answer for items whose shape is more than their kind's; None → the kind's shape."""
    iid = item["id"]
    if not isinstance(value, dict):
        raise AnswerError(f"{iid}: an answer is an object")
    if iid in ("S5.a_srd", "S5.b_other") and value.get("applicable") is False:
        return {"applicable": False}                 # 'where applicable' / 'any other': the manager states there is none
    if iid == "S4.a_approval_date":
        try:
            d = date.fromisoformat(str(value.get("text") or "")[:10])
        except ValueError:
            raise AnswerError(f"{iid}: the date the governing body approved the policies (YYYY-MM-DD)")
        if d > date.today():
            raise AnswerError(f"{iid}: an approval date cannot be in the future")
        return {"text": d.isoformat()}
    if iid == "S6.2c_scenario":
        if not isinstance(value.get("ticked"), bool):
            raise AnswerError(f"{iid}: state whether a forward-looking climate scenario is used (true / false)")
        if value["ticked"] and not str(value.get("text") or "").strip():
            raise AnswerError(f"{iid}: a scenario used needs its name, its provider and when it was designed")
        return {"ticked": value["ticked"], **({"text": str(value["text"]).strip()} if value["ticked"] else {})}
    if iid == "S1.d_summary":
        rows = value.get("rows")
        if not isinstance(rows, list) or not rows:
            raise AnswerError(f"{iid}: the summary, one row per language")
        out = []
        from services.reference.iso_country import is_valid_country
        for n, r in enumerate(rows, 1):
            lang = str(r.get("d_language") or "").strip().lower()
            meets = r.get("d_meets") or []
            ms = str(r.get("d_member_state") or "").strip().upper() or None
            body = str(r.get("d_text") or "").strip()
            if not re.fullmatch(r"[a-z]{2}", lang):
                raise AnswerError(f"{iid}: row {n} — the language as a two-letter ISO 639-1 code")
            if not isinstance(meets, list) or not meets or set(meets) - set(LANGUAGE_MEETS):
                raise AnswerError(f"{iid}: row {n} — which requirement the language meets: {', '.join(LANGUAGE_MEETS)}")
            if ("host_official" in meets) != bool(ms):
                raise AnswerError(f"{iid}: row {n} — a host Member State is stated exactly when the language is a host "
                                  "Member State's official language")
            if ms and not is_valid_country(ms):
                raise AnswerError(f"{iid}: row {n} — '{ms}' is not an ISO 3166-1 country code")
            if not body:
                raise AnswerError(f"{iid}: row {n} — the summary text")
            out.append({"d_language": lang, "d_meets": sorted(set(meets)), "d_member_state": ms, "d_text": body})
        return {"rows": out}
    return None


def read(session, org_id: str, period_end: date) -> dict:
    from services.governance import template_answers as T
    return T.read(session, org_id, FAMILY, DOCUMENT, period_end=period_end)


def save(session, org_id: str, period_end, answers: dict, user_id: str | None) -> dict:
    """Validate and store the answers for the period ({saved, refused}); the period must be a statement's (31 Dec)."""
    import services.regspec as R
    from ml.regulatory.sfdr_pai import entity_pai_statement
    from services.governance import template_answers as T
    st = entity_pai_statement(session, org_id, period_end)        # PeriodError on a non-31-December end
    if st.get("error"):
        raise AnswerError(st["error"])
    pe = date.fromisoformat(str(period_end)[:10])
    spec = R.governing(FAMILY, period_end=pe)
    tmpl = template(spec, st)
    return T.save(session, org_id, FAMILY, DOCUMENT, tmpl, bound(tmpl), answers, user_id, period_end=pe,
                  label="the principal adverse impacts statement", computed_from="the holdings and earlier filings",
                  validate=_validate)


# ── what is still to answer ──────────────────────────────────────────────────────────────────────────────────────
def _has(a: dict | None) -> bool:
    return bool(a) and (bool((a.get("text") or "").strip()) or a.get("applicable") is False or "ticked" in a
                        or bool(a.get("rows")))


def missing(spec: dict, answers: dict, statement: dict) -> list[str]:
    """The answers the text requires and the manager has not given — each named by its Article point."""
    import services.regspec as R
    out = []

    def need(item_id: str, ref: str):
        if not _has(answers.get(item_id)):
            sid, iid = item_id.split(".", 1)
            it = next((i for i in R.template(spec, sid)["items"] if i["id"] == iid), {})
            label = re.sub(r"^(\d+\.|\([a-z]\))\s*", "", it.get("label") or iid)
            out.append(f"{ref}: {label[:90]}")

    rows = (answers.get("S1.d_summary") or {}).get("rows") or []
    if not rows:
        out.append("Article 5(d): the summary of the principal adverse impacts")
    else:
        meets = {m for r in rows for m in r.get("d_meets") or []}
        if "home_official" not in meets:
            out.append("Article 5, languages (a): the summary in an official language of the home Member State")
        if "international_finance" not in meets:
            out.append("Article 5, languages (a): the summary in a language customary in the sphere of international "
                       "finance (or state that the home-language text is in one)")
    for iid, pt in (("policies", "(1)"), ("a_approval_date", "(1)(a)"), ("b_responsibility", "(1)(b)"),
                    ("c_methodologies", "(1)(c)"), ("d_margin_of_error", "(1)(d)"), ("e_data_sources", "(1)(e)")):
        need(f"S4.{iid}", f"Article 7{pt}")
    not_ready = [i for i in statement.get("indicators") or [] if i.get("method") != "computed"]
    if not_ready:                         # Article 7(2): 'Where information relating to any of the indicators … is not
        need("S4.best_efforts", f"Article 7(2) ({len(not_ready)} indicator(s) not computed in full)")   # readily available'
    need("S5.a_srd", "Article 8(1)(a)")
    need("S5.b_other", "Article 8(1)(b)")
    summaries = [answers.get("S5.a_srd") or {}, answers.get("S5.b_other") or {}]
    if any(_has(s) and s.get("applicable") is not False for s in summaries):
        need("S5.2a_indicators", "Article 8(2)(a)")
        need("S5.2b_adaptation", "Article 8(2)(b)")
    for iid, pt in (("adherence", "(1)"), ("2a_indicators", "(2)(a)"), ("2b_methodology", "(2)(b)"),
                    ("2c_scenario", "(2)(c)")):
        need(f"S6.{iid}", f"Article 9{pt}")
    if (answers.get("S6.2c_scenario") or {}).get("ticked") is False:
        need("S6.2d_no_scenario", "Article 9(2)(d)")
    unanswered = [r["label"] for r in impact_rows(statement)
                  for col in ("expl", "action") if not _has(answers.get(f"{r['key']}.{col}"))]
    if unanswered:
        out.append(f"Article 6(1)-(2), Table 1 columns 'Explanation' / 'Actions taken …': {len(unanswered)} field(s) "
                   f"to complete — first: {unanswered[0][:80]}")
    return out


# ── the previous periods ─────────────────────────────────────────────────────────────────────────────────────────
def previous(session, org_id: str, period_end: date) -> list[dict]:
    """The previous periods reported on, most recent first, at most five (Article 10): {period_end, source, filing_id,
    figures {datapoint key: value}} — a filed statement first, else a previous statement uploaded and confirmed."""
    from services.governance.prior_filings import reported_figures
    out = []
    for k in range(1, MAX_PREVIOUS + 1):
        pe = date(period_end.year - k, 12, 31)
        row = session.execute(text("""
            SELECT f.filing_id::text AS filing_id, f.status, s.payload
            FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
            WHERE f.org_id = CAST(:o AS uuid) AND f.framework = 'sfdr_pai' AND f.period_end = :pe
              AND f.entity_id IS NULL AND f.status = ANY(:st)
            ORDER BY f.seq DESC LIMIT 1"""), {"o": org_id, "pe": pe, "st": list(REPORTED)}).mappings().first()
        if row:
            out.append({"period_end": pe.isoformat(), "source": f"statement filed ({row['status']})",
                        "filing_id": row["filing_id"],
                        "figures": {r["key"]: r["value"] for r in impact_rows(row["payload"] or {})}})
            continue
        figs = reported_figures(session, org_id, "sfdr_pai", None, pe)
        if figs:
            out.append({"period_end": pe.isoformat(), "source": "previous statement uploaded and confirmed",
                        "filing_id": next(iter(figs.values()))["filing_id"],
                        "figures": {k_: v["value"] for k_, v in figs.items()}})
    return out


def attach(session, org_id: str, period_end: date, statement: dict) -> list[str]:
    """Add to a period's statement: the governing sections with their answers, the previous period's figure on every
    impact row (column 'Impact [year n-1]'), the explanation and actions answered per row, and the historical
    comparison. Returns what is still missing (for the statement's filing readiness)."""
    import services.regspec as R
    spec = R.governing(FAMILY, period_end=period_end)
    if spec is None:
        return ["no adopted specification of Delegated Regulation (EU) 2022/1288 governs this statement"]
    answers = read(session, org_id, period_end)
    prev = previous(session, org_id, period_end)
    last = prev[0] if prev and prev[0]["period_end"] == date(period_end.year - 1, 12, 31).isoformat() else None
    rows = {}
    for r in impact_rows(statement):
        rows[r["key"]] = {
            "prior": (last or {}).get("figures", {}).get(r["key"]),
            "expl": (answers.get(f"{r['key']}.expl") or {}).get("text"),
            "action": (answers.get(f"{r['key']}.action") or {}).get("text"),
        }
    entity = statement.get("entity") or {}
    statement["sections"] = {
        "spec": {"version": spec["version"], "sha256": spec["_sha256"]},
        "computed": {"S1.a_name": entity.get("manager_legal_name") or entity.get("manager"),
                     "S1.b_considered": "Principal adverse impacts of investment decisions on sustainability factors are "
                                        "considered.",
                     "S1.c_period": f"1 January {period_end.year} – 31 December {period_end.year}"},
        "answers": {k: v for k, v in answers.items() if "." in k and k.split(".", 1)[0] in SECTIONS},
    }
    statement["rows"] = rows
    statement["prior_period"] = ({"period_end": last["period_end"], "source": last["source"], "filing_id": last["filing_id"]}
                                 if last else None)
    statement["historical_comparison"] = {
        "applies": bool(prev),
        "periods": [{"period_end": p["period_end"], "source": p["source"], "filing_id": p["filing_id"]} for p in prev],
        "rows": [{"period": p["period_end"], "indicator": key, "impact": val, "source": p["source"]}
                 for p in prev for key, val in p["figures"].items() if val is not None],
    }
    return missing(spec, answers, statement)
