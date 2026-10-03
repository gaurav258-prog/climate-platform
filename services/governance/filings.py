"""Regulatory filing lifecycle — the reporting cockpit's engine.

A filing is one regulatory submission (a framework, for a reference period, for an entity). It moves
through a controlled lifecycle, each step logged append-only:

    generate → draft
    submit_for_review → in_review     (raises a 4-eyes approval request)
    approve  → approved               (a *different* user clears the approval; wired via approvals router)
    return   → returned / reject → rejected
    attest   → attested               (a named accountable person certifies the frozen numbers)
    submit   → submitted              (transmitted to the regulator, with a reference)
    accept   → accepted               (regulator acknowledgement)
    supersede→ superseded             (a restatement replaces it)
    withdraw → withdrawn              (a draft/returned filing discarded with a reason — terminal, never filed)

The frozen numbers behind a filing are a `report_snapshots` row (immutable, hashed, versioned) — this
service never re-implements freezing; it wraps `report_snapshots.create_snapshot`. Honesty carries through
untouched: a euro is firm only where the chain is validated, "—" otherwise, and freezing launders nothing.

Obligations are the filing calendar: what is due, for which entity, by when. They are derived live from the
frameworks that apply to the org's sector, so the calendar is never stale.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.money_format import presentation_of
from services.governance.report_snapshots import _BUILDERS, create_snapshot, get_snapshot

# A retired report type carries one declaration: "retired": {"since", "reason", "replaced_by": a framework key or None}.
# Its filings stay readable (register, form, annex, export, lineage, retention, assurance pack); nothing new is frozen or
# owed for it — no filing, refreshed draft, restatement, provided value or obligation. One helper: retirement_refusal().
_TCFD_RETIRED = {"since": "2026-10-01", "replaced_by": None,
                 "reason": "a TCFD-style report tied to no regulatory text (the TCFD disbanded in 2023), retired rather "
                           "than rebuilt"}

# framework (== report_snapshots report_type) -> filing metadata.
# The deadline is the mandate's (data/reference/regulatory_mandates.json, cited: due_for). `due` (month, day in the year
# after period_end) is kept ONLY for a report type no mandate dates by the calendar — the platform's planning date.
FRAMEWORKS = {
    # the credit institution's EU Taxonomy Art. 8 report, governed by the spec family bank_taxonomy
    # (data/reference/regspec_usage.json); the key keeps its historical name — filings and snapshots reference it
    "bank_tcfd": {"label": "EU Taxonomy Art. 8 — credit institutions", "sectors": ("bank",),
                  "frequency": "annual",
                  "regulator": "National competent authority / EBA",
                  "basis": "Reg. (EU) 2020/852 Art. 8 · Del. Reg. (EU) 2021/2178 Art. 4, Annexes V–VI"},
    "bank_p3esg": {"label": "Pillar 3 ESG risk disclosures", "sectors": ("bank",),
                   "frequency": "annual",
                   "regulator": "National competent authority / EBA", "basis": "CRR Art. 449a"},   # the implementing act: reg_reference.reference() from the governing spec
    "sfdr_pai": {"label": "SFDR Principal Adverse Impacts statement", "sectors": ("asset_manager",),
                 "frequency": "annual",
                 "regulator": "National competent authority (SFDR)", "basis": "SFDR Art. 4"},   # the RTS: reg_reference.reference() from the governing spec
    "assetmgmt_tcfd": {"label": "TCFD · physical-risk & concentration disclosure (holdings book)", "sectors": ("asset_manager",),
                       "frequency": "annual", "retired": _TCFD_RETIRED,
                       "regulator": "National competent authority / TCFD", "basis": "TCFD asset-manager guidance"},
    # ── agriculture (manufacturer) frameworks — builders already registered in report_snapshots._BUILDERS ──
    "csrd_e1": {"label": "CSRD · ESRS E1 physical-risk report", "sectors": ("manufacturer",),
                "frequency": "annual",
                "retired": {"since": "2026-09-30", "replaced_by": "esrs_pack",
                            "reason": "an ESRS statement is filed per undertaking as one esrs_pack filing (E1 is one of "
                                      "its standards)"},
                "regulator": "National competent authority (CSRD)", "basis": "ESRS E1"},
    # one undertaking's (or group's) ESRS statement for one financial year, on the version governing that year
    # (services.governance.esrs_document); its deadline is the mandate's (with the management report)
    "esrs_pack": {"label": "ESRS sustainability statement — E1, E3, E4", "sectors": ("manufacturer",),
                  "frequency": "annual",
                  "regulator": "National competent authority (CSRD)",
                  "basis": "Directive 2013/34/EU Art. 19a / 29a · ESRS (Del. Reg. (EU) 2023/2772 as amended; (EU) 2026/1563)"},
    "reit_tcfd": {"label": "TCFD · EU-Taxonomy disclosure (property book)", "sectors": ("reit",),
                  "frequency": "annual", "retired": _TCFD_RETIRED,
                  "regulator": "National competent authority / EBA", "basis": "CSRD Art. 8 · TCFD"},
    "reit_taxonomy": {"label": "EU Taxonomy Article 8 KPIs (property book)", "sectors": ("reit",),
                      "frequency": "annual",
                      "regulator": "National competent authority", "basis": "Del. Reg. (EU) 2021/2178 Art. 8"},
    "insurer_solvency": {"label": "Solvency II · natural catastrophe risk (S.27.01.01)", "sectors": ("insurer",),
                         "frequency": "annual",
                         "regulator": "EIOPA / national supervisor", "basis": "Del. Reg. (EU) 2015/35 Arts 119-126 · ITS (EU) 2023/894 S.27.01.01"},
    # an ORSA / a recovery plan runs from an event (the assessment's conclusion, a plan update): no calendar date — the
    # filing's disclosure date is the conclusion, and the ORSA report is due 2 weeks later (Del. Reg. 2015/35 Art. 312(1)(b))
    "insurer_orsa_climate": {"label": "ORSA — climate change scenario analysis (Art. 45a)", "sectors": ("insurer",),
                             "frequency": "annual", "regulator": "National competent authority (Solvency II supervisor)",
                             "basis": "Directive 2009/138/EC Art. 45a, 51(1b)(e) · Directive (EU) 2025/2"},
    "insurer_recovery_stress": {"label": "Pre-emptive recovery plan — nat-cat stress and capital indicators",
                                "sectors": ("insurer",), "frequency": "at least every two years",
                                "regulator": "National competent authority (Solvency II supervisor)",
                                "basis": "Directive (EU) 2025/1 Art. 5(7), (8)"},
    "insurer_climate": {"label": "Climate / NatCat exposure disclosure", "sectors": ("insurer",),
                        "frequency": "annual", "retired": _TCFD_RETIRED,
                        "regulator": "National competent authority / EIOPA", "basis": "Solvency II · IFRS S2"},
    # ── per financial product (services.governance.product_filings): the fund is the filing's subject ──
    # the pre-contractual document is annexed to the prospectus and kept current — no calendar deadline
    # EUDR (Regulation (EU) 2023/1115): one due diligence statement per placing on the market or export, submitted BEFORE
    # it (Art. 4(2): 'prior submission'); prepared from its movement (services/eudr/filing.py), not from the calendar
    "eudr_dds": {"label": "EUDR due diligence statement", "sectors": ("manufacturer",),
                 "frequency": "before each placing on the market or export", "due": None,
                 "frozen_by": "from its shipment (EUDR → the shipment → prepare the statement)",
                 "accepted_by": "when the reference number the information system made available is recorded (EUDR → the shipment)",
                 "own_page": "/eudr",
                 "regulator": "Competent authority (EUDR) via the EU information system",
                 "basis": "Regulation (EU) 2023/1115 Art. 4(2), Annex II · Implementing Regulation (EU) 2024/3084"},
    # EUDR Art. 4a (E115): the one-time simplified declaration of a micro or small primary operator, before placing on the
    # market or export, updated after major changes (Art. 4a(3)); prepared from the undertaking's records
    "eudr_simplified": {"label": "EUDR simplified declaration", "sectors": ("manufacturer",),
                        "frequency": "once, before the first placing on the market or export; updated after major changes",
                        "due": None,
                        "frozen_by": "from the undertaking's records (EUDR → simplified declaration → prepare)",
                        "accepted_by": "when the declaration identifier the information system assigned is recorded "
                                       "(EUDR → simplified declaration)",
                        "own_page": "/eudr",
                        "regulator": "Competent authority (EUDR) via the EU information system",
                        "basis": "Regulation (EU) 2023/1115 Art. 4a, Annex III · Implementing Regulation (EU) 2024/3084 Art. 4a"},
    "sfdr_precontractual": {"label": "SFDR pre-contractual disclosure", "sectors": ("asset_manager",),
                            "frequency": "on change", "due": None,
                            "regulator": "National competent authority (SFDR)", "basis": "SFDR Art. 8 / 9 · RTS 2022/1288 Annex II / III"},
    # the periodic document is annexed to the product's annual report (SFDR Art. 11(1)); its deadline is the annual
    # report's under the product's sectoral rules — declared here as four months after the year end (UCITS); an AIF's
    # longer deadline is not yet stored per fund
    "sfdr_periodic": {"label": "SFDR periodic disclosure", "sectors": ("asset_manager",),
                      "frequency": "annual", "due": (4, 30),
                      "regulator": "National competent authority (SFDR)", "basis": "SFDR Art. 11 · RTS 2022/1288 Annex IV / V"},
}

# machine-readable export formats available per framework (rendered from the FROZEN snapshot — see
# services/governance/filing_export.py). json is the universal record; xlsx/xbrl where a renderer exists.
EXPORT_FORMATS = {
    "bank_tcfd": ("json", "xlsx"),        # no official XBRL binding of the Annex VI templates is held (E95)
    "bank_p3esg": ("json", "xlsx"),       # no XBRL until the EBA's own Pillar 3 taxonomy is bound (E104)
    "sfdr_pai":  ("json", "xlsx"),        # no (i)XBRL: no official SFDR PAI taxonomy is held (E113)
    "assetmgmt_tcfd": ("json", "xlsx"),
    "reit_tcfd": ("json", "xlsx"),
    "reit_taxonomy": ("json", "xlsx"),
    "insurer_solvency": ("json", "xlsx", "xbrl"),     # xbrl: EIOPA's Solvency II taxonomy (services.governance.s2701_xbrl)
    "insurer_climate": ("json", "xlsx"),
    "insurer_orsa_climate": ("json",),
    "insurer_recovery_stress": ("json",),
    "csrd_e1":   ("json",),
    "esrs_pack": ("json",),
    "sfdr_precontractual": ("json", "html"),
    "sfdr_periodic": ("json", "html"),
}

# lifecycle: action -> (allowed from-states, resulting to-state)
_TRANSITIONS = {
    "submit_for_review": ({"draft", "returned"}, "in_review"),
    "approve":           ({"in_review"},         "approved"),
    "return":            ({"in_review"},         "returned"),
    "reject":            ({"in_review"},         "rejected"),
    "attest":            ({"approved"},          "attested"),
    "submit":            ({"attested"},          "submitted"),
    "accept":            ({"submitted"},         "accepted"),
    "supersede":         ({"submitted", "accepted", "rejected"}, "superseded"),
    "withdraw":          ({"draft", "returned"}, "withdrawn"),
}

# statuses that no longer hold the (framework, period, entity) slot — the live-slot index excludes the same two
NOT_LIVE = ("superseded", "withdrawn")
WITHDRAW_REASON_MIN = 10


class FilingError(ValueError):
    """A lifecycle rule was violated (bad transition, missing filing, duplicate slot)."""


# ── framework catalog ──────────────────────────────────────────────────

# Frameworks whose builder genuinely HONOURS entity scope — the located FIN books, where each asset carries a
# clear reporting-entity + value, so a group consolidates correctly (ownership-weighted), and the ESRS statement,
# filed by the reporting undertaking (its CSRD role, csrd_reporting_role; its scope, esrs_statement.scope). SFDR
# does NOT: it consolidates fund-side (the funds workspace — per-fund statements + the across-all-funds aggregate).
# Offering a per-entity scope for those would silently mislabel a whole-org number, so generate_filing refuses it.
from services.governance.product_filings import PRODUCT_SCOPED as _PRODUCT_SCOPED  # noqa: E402

_ENTITY_SCOPED = {"bank_tcfd", "bank_p3esg", "reit_taxonomy", "insurer_solvency",
                  "insurer_orsa_climate", "insurer_recovery_stress", "esrs_pack"}
# filed for a group by weighting each entity's book by the consolidation rule of data/reference/consolidation/regimes.json
# (the ESRS statement has its own scope, services.governance.esrs_statement.scope)
GROUP_FRAMEWORKS = _ENTITY_SCOPED - {"esrs_pack"}


def retirement(framework: str) -> dict | None:
    """The framework's retirement declaration ({"since", "reason", "replaced_by"}), or None while it is live."""
    return (FRAMEWORKS.get(framework) or {}).get("retired")


def retired_frameworks() -> list[str]:
    """Every retired framework key — for a query that leaves out what is no longer owed."""
    return sorted(k for k in FRAMEWORKS if retirement(k))


def retirement_refusal(framework: str) -> str | None:
    """Why nothing new can be made for a retired framework — the one message every caller refusing a new filing,
    a refreshed draft, a restatement or a provided value gives; None while the framework is live."""
    r = retirement(framework)
    if not r:
        return None
    label = FRAMEWORKS[framework]["label"]
    succ = r.get("replaced_by")
    then = (f"prepare a {FRAMEWORKS[succ]['label']} instead" if succ else
            "nothing replaces it, and no new filing, refreshed draft, restatement or provided value is made for it")
    return f"{label} is retired since {r['since']} — {r['reason']}. Its filings stay readable as filed; {then}."


def available_frameworks(org_type: str) -> list[dict]:
    """Frameworks that apply to this org-type sector, each with its cadence and statutory deadline shape."""
    out = []
    for key, f in FRAMEWORKS.items():
        if org_type in f["sectors"] and key in _BUILDERS and not retirement(key) and not f.get("frozen_by"):
            out.append({"framework": key, "label": f["label"], "frequency": f["frequency"],
                        "regulator": f["regulator"], "basis": f["basis"],
                        "entity_scoped": key in _ENTITY_SCOPED, "product_scoped": key in _PRODUCT_SCOPED})
    return out


_MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def form_view(session: Session, org_id: str, filing_id: str) -> dict | None:
    """The final form for a filing — the frozen snapshot flattened into labelled datapoints (see
    filing_form.build_form), each with a stable key so a manual override can target it."""
    from services.governance.filing_form import build_form
    from services.governance.reg_reference import reference
    r = session.execute(text("""
        SELECT rf.framework, rf.status, rf.period_label, rf.period_end, s.payload, s.version
        FROM regulatory_filing rf
        LEFT JOIN report_snapshots s ON s.snapshot_id = rf.snapshot_id
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    groups = build_form(r["framework"], r["payload"] or {})
    # per reported figure (phase 5): where the client's attested number and ours both exist, the form reports the one
    # the filing chose at freeze, with the other beside it — before manual overrides, which still apply on top
    from services.governance.figure_views import apply_to_form
    apply_to_form(groups, (r["payload"] or {}).get("_figures") or [])
    # merge the audited manual-override layer over the immutable snapshot: an APPROVED override replaces the
    # cell (flagged manual, original preserved); a PENDING one is surfaced awaiting 4-eyes.
    #
    # Fixed 2026-09-24 (platform-wide E2E audit): build_form() returns TWO incompatible shapes depending on
    # framework — {"group","datapoints"} (bank/reit/insurer_climate/sfdr/generic) vs {"section","rows"}
    # (insurer_solvency, reit_taxonomy, assetmgmt_tcfd — see filing_form.py's _insurer_solvency_form /
    # _reit_taxonomy_form / _assetmgmt_tcfd_form). This loop used to assume every group had "datapoints"
    # unconditionally — a real KeyError → 500 on EVERY filing review screen for those 3 frameworks,
    # reproduced live during the audit. Row-shaped sections use plain string labels, not filing_form._dp()'s
    # stable `key` — cell-level manual overrides were never wired for them (a real, separate, pre-existing
    # limitation, not newly introduced here), so they're skipped here rather than crashing.
    from services.governance.filing_overrides import overrides_for_filing
    ov = overrides_for_filing(session, org_id, filing_id)
    n_manual = n_pending = 0
    for g in groups:
        if "datapoints" not in g:
            continue
        for d in g["datapoints"]:
            o = ov.get(d["key"])
            if not o:
                continue
            if o["status"] == "approved":
                d["value"] = o["proposed_value"]
                d["manual"] = True
                d["original_value"] = o["original_value"]
                d["override"] = {"reason": o["reason"], "by": o["proposed_by"], "at": o["proposed_at"],
                                 "approved_by": o["decided_by"], "approved_at": o["decided_at"]}
                n_manual += 1
            elif o["status"] == "pending":
                d["pending"] = {"value": o["proposed_value"], "reason": o["reason"], "by": o["proposed_by"]}
                n_pending += 1
    # Lane 2 — attested "provided" (customer/vendor) values that passed 4-eyes now LAND in the filing: as their
    # own datapoint group AND an annex section, each with its reconciliation vs the Tellumen baseline. Previously
    # these dead-ended at the provided-data list view and never reached a disclosure.
    #
    # Fixed 2026-09-24 (platform E2E audit finding #6): this used to call attested_values() LIVE on every
    # read — so an already-accepted/attested filing's "Provided & attested" section could silently change
    # if someone attested a NEW value for the same framework afterward, breaking the immutability guarantee
    # every other section of a frozen filing has. report_snapshots.create_snapshot() now bakes the attested
    # values into the frozen payload (hash-verified, like the rest) at freeze time — read that instead. A
    # filing frozen BEFORE this fix has no "_provided_attested" key at all; it correctly shows nothing here
    # rather than being retroactively backfilled with data that was never actually part of what was frozen.
    provided = (r["payload"] or {}).get("_provided_attested") or []
    if provided:
        groups.append({
            "group": "Provided & attested (customer / vendor)",
            "note": "Values you or a vendor supplied and attested under 4-eyes — client > vendor precedence. Each shows "
                    "the reconciliation against Tellumen's own computed baseline where one exists.",
            "datapoints": [{"key": p["key"], "label": p["label"], "value": p["value"], "unit": p.get("unit"),
                            "fmt": "num" if isinstance(p["value"], (int, float)) else "text", "source": "provided",
                            "provided": {"provider": p.get("provider"), "attested_by": p.get("attested_by"),
                                         "attested_at": p.get("attested_at"), "delta_pct": p.get("delta_pct"),
                                         "tellumen_value": p.get("tellumen_value"), "within_tolerance": p.get("within_tolerance")}}
                           for p in provided],
        })

    # the official regulator-form layout (SFDR Annex I Table 1, Taxonomy Art.8 GAR, ESRS E1 …) built from the
    # SAME merged datapoints, so the official form and the datapoint list stay in lock-step (overrides included).
    from services.governance.filing_annex import build_annex
    dps_by_key = {d["key"]: d for g in groups if "datapoints" in g for d in g["datapoints"]}
    # the raw frozen payload is passed too — some official templates (e.g. EBA Pillar 3 Template 5) are
    # structured GRIDS computed from the per-asset book, not flat datapoints, and are rebuilt at read time.
    annex = build_annex(r["framework"], dps_by_key, groups, payload=r["payload"] or {})
    # surface attested provided values in the official annex too (a computed section, source-flagged 'provided')
    if provided and annex:
        prow = []
        for p in provided:
            recon = (f"Δ {p['delta_pct']}% vs baseline" if p.get("delta_pct") is not None else "no baseline")
            prow.append({"type": "row", "cells": [{"text": p["label"]},
                        {"text": f"{p['value']} {p.get('unit') or ''}".strip(), "num": isinstance(p["value"], (int, float)), "source": "provided"},
                        {"text": recon}, {"text": p.get("provider") or p.get("attested_by") or "—"}]})
        annex.setdefault("sections", []).append({
            "title": "Provided & attested values (customer / vendor, 4-eyes)",
            "columns": ["Datapoint", "Provided value", "Reconciliation", "Provider / attester"], "rows": prow,
            "note": "Values supplied and attested by the institution or a vendor under 4-eyes (client > vendor "
                    "precedence), reconciled against Tellumen's computed baseline. Source-flagged 'provided'."})
    if r["framework"] == "eudr_dds" and annex is not None:      # Annex II point 6, completed by the attestation
        from services.eudr.statement import sign_point_6
        sign_point_6(annex, r["payload"] or {}, attestation(session, filing_id))
    return {"framework": r["framework"], "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
            "period_label": r["period_label"], "status": r["status"], "snapshot_version": r["version"],
            "period_end": r["period_end"].isoformat() if r["period_end"] else None,
            "official_form_url": (reference(r["framework"]) or {}).get("form_url"),
            "n_manual": n_manual, "n_pending": n_pending, "groups": groups, "annex": annex,
            "reporting_entity_id": ((r["payload"] or {}).get("_scope") or {}).get("reporting_entity_id"),
            "currency": presentation_of(r["payload"]), "fx": _fx_view((r["payload"] or {}).get("_fx")),
            # a group filing: the rule its entities were weighted on, quoted, as frozen (and any declared reading)
            "consolidation": _consolidation_view(session, (r["payload"] or {}).get("_consolidation")),
            # the interpretations the filing was prepared under, as frozen in its payload (covered by its hash) — part of
            # the filing's record, beside the templates (the annex holds only what the templates print)
            "elections": (r["payload"] or {}).get("_elections")}


def _consolidation_view(session: Session, cons: dict | None) -> dict | None:
    """The consolidation record a group filing froze, with the sign-off of the exact rule file it was computed on."""
    if not cons:
        return None
    f = cons.get("rule_file")
    if not f:                                     # frozen before the rule file was on the change route
        return {**cons, "signoff": None}
    from services.regspec.signoff import signed_on
    return {**cons, "signoff": signed_on(session, f["framework"], f["version"], f["sha256"])}


def _fx_view(fx: dict | None) -> dict | None:
    """The currency record a reviewer needs beside the form: basis, rates, per-entity translation, eliminations."""
    if not fx or not fx.get("rates_used") and not fx.get("translation"):
        return None
    return {k: fx.get(k) for k in ("presentation_currency", "period_end", "basis", "rates_used", "n_stale_rates", "translation",
                                   "translation_difference_total", "n_eliminations", "value_eliminated_total",
                                   "unexplained_as_eur")} | {"eliminations": (fx.get("eliminations") or [])[:50]}


def reporting_requirements(session: Session, org_id: str, org_type: str) -> list[dict]:
    """Every mandatory reporting obligation for the org: what the regulation is (name, authority, summary,
    official link + form), how often + to which regulator + by when, what data to supply, when it was last
    filed, and the full list of prior filings (for access to previously submitted reports)."""
    from services.governance.filing_coverage import coverage as _coverage
    from services.governance.reg_reference import reference
    out = []
    for f in available_frameworks(org_type):
        fk = f["framework"]
        ref = reference(fk) or {}
        spec = FRAMEWORKS[fk]
        from services.governance.reporting_settings import get_settings
        pe_org = get_settings(session, org_id).get("reporting_period_end")
        due_on, due_why = due_for(fk, date.fromisoformat(str(pe_org)[:10])) if pe_org else (None, None)
        rows = session.execute(text("""
            SELECT rf.filing_id::text AS filing_id, rf.period_label, rf.status, rf.submission_ref,
                   rf.created_at, rf.updated_at, s.version AS snapshot_version,
                   rf.entity_id::text AS entity_id, re.name AS entity_name
            FROM regulatory_filing rf
            LEFT JOIN report_snapshots s ON s.snapshot_id = rf.snapshot_id
            LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
            WHERE rf.org_id = :o AND rf.framework = :fk
            ORDER BY rf.period_end DESC, rf.seq DESC
        """), {"o": org_id, "fk": fk}).mappings().all()
        filings = [{"filing_id": r["filing_id"], "period_label": r["period_label"], "status": r["status"],
                    "submission_ref": r["submission_ref"], "snapshot_version": r["snapshot_version"],
                    "entity_name": r["entity_name"], "filed_at": r["updated_at"].isoformat() if r["updated_at"] else None}
                   for r in rows]
        # "last filed" = the most-recent filing that actually reached the regulator — it carries a submission
        # ref (or is accepted), even if later superseded by a restatement.
        last = next((x for x in filings if x["submission_ref"] or x["status"] in ("submitted", "accepted")), None)
        out.append({
            **f, **ref,
            "due_label": (f"{spec['frequency']} · by {due_on.day} {_MONTHS[due_on.month]}" + (f" ({due_why})" if due_why else ""))
                         if due_on else (f"{spec['frequency']} · {due_why}" if due_why else spec["frequency"]),
            "n_filings": len(filings), "last_filed": last, "filings": filings,
            "coverage": _coverage(fk),
        })
    return out


def _mandate_of(framework: str) -> dict | None:
    from services.supervision.mandates import registry
    return next((m for m in registry()["mandates"] if (m.get("deliverable") or {}).get("framework") == framework), None)


def due_for(framework: str, period_end: date) -> tuple[date | None, str | None]:
    """(the deadline for a period, where it comes from): the mandate's cited rule where it fixes a calendar date, else
    the report type's planning date; (None, None) for a report with no calendar deadline."""
    from services.supervision.mandates import due_date
    m = _mandate_of(framework)
    d = due_date(m, period_end) if m else None
    if d is not None:
        return d, m["deliverable"]["due"].get("label")
    typed = FRAMEWORKS[framework].get("due")
    if typed:
        why = (m["deliverable"]["due"].get("label") + " — planning date") if m else "planning date"
        return date(period_end.year + 1, *typed), why
    if m and m["deliverable"]["due"].get("fact"):         # per undertaking: due_for_undertaking
        return None, m["deliverable"]["due"].get("label")
    return None, None


def due_for_undertaking(session: Session, org_id: str, framework: str, entity_id: str | None,
                        period_end: date) -> tuple[date | None, str | None]:
    """The deadline of a report whose rule reads a fact about the undertaking (the ESRS statement: an issuer under
    Directive 2004/109/EC Art. 4(1) within 4 months, otherwise within 12 months — Directive 2013/34/EU Art. 30(1)), from
    that undertaking's attested fact for the year; (None, what to state) while the fact is not stated."""
    from services.governance.provided_data import ESRS, attested_values
    from services.supervision.mandates import due_date
    m = _mandate_of(framework)
    rule = (m or {}).get("deliverable", {}).get("due") or {}
    if not rule.get("fact"):
        return due_for(framework, period_end)
    facts = {v["concept"]: v for v in attested_values(session, org_id, ESRS, period_end, reporting_entity_id=entity_id)
             if v["concept"] == rule["fact"] and not v.get("member")}
    d = due_date(m, period_end, facts)
    if d is None:
        return None, f"state {rule['fact']} for the year — {rule['label']}"
    branch = rule["issuer" if int(float(facts[rule["fact"]]["value"])) == 1 else "otherwise"]
    return d, branch["ref"]


def _due_date(framework: str, period_end: date) -> date | None:
    return due_for(framework, period_end)[0]


def due_for_filing(framework: str, period_end: date, disclosure_date: date | None) -> tuple[date | None, str | None]:
    """A filing's deadline: the calendar one, else — for a report that runs from its own event (the ORSA supervisory
    report: 'within 2 weeks after concluding the assessment', Art. 312(1)(b) Del. Reg. 2015/35) — its disclosure date
    plus the mandate's weeks."""
    from datetime import timedelta
    d, why = due_for(framework, period_end)
    if d is not None or disclosure_date is None:
        return d, why
    m = _mandate_of(framework)
    due = (m or {}).get("deliverable", {}).get("due") or {}
    if due.get("rule") == "weeks_after_orsa" and due.get("weeks_after_period_end"):
        return disclosure_date + timedelta(weeks=int(due["weeks_after_period_end"])), due.get("label")
    return None, due.get("label")


def period_label(period_end: date) -> str:
    """The one label of a reporting period — derived from its end, never typed (every period here is a financial year;
    the database checks period_label = 'FY' || year(period_end) on filings, obligations and supervisory deadlines)."""
    return f"FY{period_end.year}"


_period_label = period_label


# ── obligations calendar (derived live, upserted so history persists) ───

def ensure_obligations(session: Session, org_id: str, org_type: str) -> None:
    """Make sure an obligation row exists for every framework applicable to this org, for the current
    reference period (last completed year-end). Idempotent — safe to call on every calendar read.

    Fixed 2026-09-23 (the most severe finding in that day's independent consolidation-scope review): this
    used to insert ONLY one blanket whole-org obligation per framework, full stop — a bank group with
    unwaived subsidiaries had no way to see that CRR Art 6 requires each of them to ALSO file its own solo
    return, in parallel with (not instead of) the consolidated one. Now, for every _ENTITY_SCOPED framework,
    this also inserts one 'solo' obligation per entity in the org's tree whose requires_solo_filing is still
    true (the CRR-safe default — see entities.create_entity) — so "you owe N solo filings + 1 consolidated
    filing" is finally a real, visible fact in the calendar, not an implicit consequence of which entity_id
    someone happened to pick when generating a filing."""
    period_end = reporting_period_end(session, org_id)
    for f in available_frameworks(org_type):
        fk = f["framework"]
        if fk in _PRODUCT_SCOPED:
            _ensure_product_obligations(session, org_id, fk, period_end)
            continue
        if fk == "esrs_pack":
            _ensure_esrs_obligations(session, org_id, period_end)
            continue
        if _due_date(fk, period_end) is None:
            # runs from an event (an ORSA's conclusion, a recovery plan's update) — no calendar obligation to invent;
            # the filing's own disclosure date gives its deadline (due_for_filing)
            continue
        # entity_id is NULL for org-level obligations; a UNIQUE(...) treats NULLs as distinct, so we can't
        # rely on ON CONFLICT here — check existence explicitly (org-level obligation, entity_id IS NULL).
        exists = session.execute(text("""
            SELECT 1 FROM regulatory_obligation
            WHERE org_id = :o AND framework = :fk AND period_end = :pe AND entity_id IS NULL
        """), {"o": org_id, "fk": fk, "pe": period_end}).first()
        if not exists:
            session.execute(text("""
                INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, filing_role)
                VALUES (:o, :fk, :pe, :pl, :due, :freq, 'whole_org')
            """), {"o": org_id, "fk": fk, "pe": period_end, "pl": _period_label(period_end),
                   "due": _due_date(fk, period_end), "freq": FRAMEWORKS[fk]["frequency"]})

        if fk not in _ENTITY_SCOPED:
            continue
        solo_entities = session.execute(text("""
            SELECT entity_id::text AS entity_id FROM reporting_entities
            WHERE org_id = :o AND requires_solo_filing = true
        """), {"o": org_id}).scalars().all()
        for eid in solo_entities:
            exists = session.execute(text("""
                SELECT 1 FROM regulatory_obligation
                WHERE org_id = :o AND framework = :fk AND period_end = :pe AND entity_id = CAST(:e AS uuid)
            """), {"o": org_id, "fk": fk, "pe": period_end, "e": eid}).first()
            if exists:
                continue
            session.execute(text("""
                INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, entity_id, filing_role)
                VALUES (:o, :fk, :pe, :pl, :due, :freq, CAST(:e AS uuid), 'solo')
            """), {"o": org_id, "fk": fk, "pe": period_end, "pl": _period_label(period_end),
                   "due": _due_date(fk, period_end), "freq": FRAMEWORKS[fk]["frequency"], "e": eid})


def _ensure_esrs_obligations(session: Session, org_id: str, period_end: date) -> None:
    """One ESRS statement obligation per undertaking Art. 5(2) of Directive (EU) 2022/2464 requires for the year
    (services.governance.csrd_scope.undertakings — its stated role and attested facts), due on its own deadline
    (due_for_undertaking). The calendar follows the facts: an undertaking's own obligation takes the deadline its facts
    give now, and is removed once it is no longer required (a supervisor-set one is left as the supervisor set it). An
    undertaking whose requirement or deadline fact is not stated has none yet — the mandate names what is missing."""
    from services.calc_settings import get_calc_settings
    from services.governance import csrd_scope
    owed = {}
    for u in csrd_scope.undertakings(session, org_id, period_end, get_calc_settings(session, org_id)):
        due, _ = due_for_undertaking(session, org_id, "esrs_pack", u["entity_id"], period_end) if u["required"] else (None, None)
        if due is not None:
            owed[u["entity_id"]] = (due, "whole_org" if u["entity_id"] is None
                                    else "consolidated" if u["role"] == "consolidated" else "solo")
    have = {(r["entity_id"]): r for r in session.execute(text("""
        SELECT obligation_id, entity_id::text AS entity_id, due_date, source FROM regulatory_obligation
        WHERE org_id = :o AND framework = 'esrs_pack' AND period_end = :pe
    """), {"o": org_id, "pe": period_end}).mappings()}
    for eid, r in have.items():
        if r["source"] != "entity":
            continue
        if eid not in owed:
            session.execute(text("DELETE FROM regulatory_obligation WHERE obligation_id = :i"), {"i": r["obligation_id"]})
        elif r["due_date"] != owed[eid][0]:
            session.execute(text("UPDATE regulatory_obligation SET due_date = :d, filing_role = :fr WHERE obligation_id = :i"),
                            {"d": owed[eid][0], "fr": owed[eid][1], "i": r["obligation_id"]})
    for eid, (due, role) in owed.items():
        if eid not in have:
            session.execute(text("""
                INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, entity_id, filing_role)
                VALUES (:o, 'esrs_pack', :pe, :pl, :due, 'annual', CAST(:e AS uuid), :fr)
            """), {"o": org_id, "pe": period_end, "pl": _period_label(period_end), "due": due, "e": eid, "fr": role})


def _ensure_product_obligations(session: Session, org_id: str, fk: str, period_end: date) -> None:
    """One obligation per Art. 8 / 9 fund for a per-product report with a calendar deadline (the periodic document;
    the pre-contractual one has none)."""
    if _due_date(fk, period_end) is None:
        return
    from services.governance.product_filings import funds_owing
    for fund in funds_owing(session, org_id):
        exists = session.execute(text("""
            SELECT 1 FROM regulatory_obligation
            WHERE org_id = :o AND framework = :fk AND period_end = :pe AND fund_id = CAST(:f AS uuid)
        """), {"o": org_id, "fk": fk, "pe": period_end, "f": fund["fund_id"]}).first()
        if not exists:
            session.execute(text("""
                INSERT INTO regulatory_obligation (org_id, framework, period_end, period_label, due_date, frequency, fund_id, filing_role)
                VALUES (:o, :fk, :pe, :pl, :due, :freq, CAST(:f AS uuid), 'product')
            """), {"o": org_id, "fk": fk, "pe": period_end, "pl": _period_label(period_end),
                   "due": _due_date(fk, period_end), "freq": FRAMEWORKS[fk]["frequency"], "f": fund["fund_id"]})


def list_obligations(session: Session, org_id: str, org_type: str) -> list[dict]:
    """The filing calendar — each obligation with the live filing that satisfies it (if any) and its status.

    Fixed 2026-09-23 alongside ensure_obligations(): the filing-match JOIN used to key on
    (org_id, framework, period_end) only — harmless while every obligation was the single whole-org row per
    framework/period, but wrong the moment per-entity solo obligations exist (as they now do): every
    obligation for a given framework/period would have matched the SAME filing regardless of entity, so a
    subsidiary's still-unfiled solo return could show as satisfied by the parent's consolidated filing.
    Now keys on entity_id too (NULL-safe via IS NOT DISTINCT FROM, since entity_id is NULL for whole_org)."""
    ensure_obligations(session, org_id, org_type)
    rows = session.execute(text("""
        SELECT ob.obligation_id, ob.framework, ob.period_end, ob.period_label, ob.due_date, ob.frequency,
               ob.source, ob.set_by, ob.entity_id, ob.filing_role, re.name AS entity_name,
               ob.fund_id, fu.name AS fund_name, f.filing_id, f.status AS filing_status
        FROM regulatory_obligation ob
        LEFT JOIN reporting_entities re ON re.entity_id = ob.entity_id
        LEFT JOIN funds fu ON fu.fund_id = ob.fund_id
        LEFT JOIN LATERAL (
            SELECT filing_id, status FROM regulatory_filing rf
            WHERE rf.org_id = ob.org_id AND rf.framework = ob.framework
              AND rf.period_end = ob.period_end AND rf.status NOT IN ('superseded', 'withdrawn')
              AND rf.entity_id IS NOT DISTINCT FROM ob.entity_id AND rf.fund_id IS NOT DISTINCT FROM ob.fund_id
            ORDER BY rf.seq DESC LIMIT 1
        ) f ON TRUE
        WHERE ob.org_id = :o
        ORDER BY ob.due_date, (ob.filing_role = 'whole_org') DESC, (ob.filing_role = 'consolidated') DESC
    """), {"o": org_id}).mappings().all()
    today = date.today()
    out = []
    for r in rows:
        retired = retirement(r["framework"]) is not None
        if retired and not r["filing_id"]:
            continue                                   # a retired report is owed no more; one filed stays on record
        status = r["filing_status"] or "not_started"
        done = status in ("submitted", "accepted")
        days_left = (r["due_date"] - today).days
        out.append({
            "retired": retired,
            "obligation_id": str(r["obligation_id"]), "framework": r["framework"],
            "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
            "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
            "due_date": r["due_date"].isoformat(), "frequency": r["frequency"],
            "filing_id": str(r["filing_id"]) if r["filing_id"] else None,
            "filing_status": status, "days_to_due": days_left,
            "source": r["source"] or "entity", "set_by": r["set_by"],
            "overdue": (not done and not retired and days_left < 0),
            "entity_id": str(r["entity_id"]) if r["entity_id"] else None,
            "entity_name": r["entity_name"],
            "fund_id": str(r["fund_id"]) if r["fund_id"] else None, "fund_name": r["fund_name"],
            "filing_role": r["filing_role"] or "whole_org",
        })
    return out


# ── filing register ────────────────────────────────────────────────────

def _row_to_summary(r) -> dict:
    return {
        "filing_id": str(r["filing_id"]), "framework": r["framework"],
        "label": FRAMEWORKS.get(r["framework"], {}).get("label", r["framework"]),
        "period_end": r["period_end"].isoformat(), "period_label": r["period_label"],
        "status": r["status"], "snapshot_id": str(r["snapshot_id"]) if r["snapshot_id"] else None,
        "snapshot_version": r.get("snapshot_version"),
        "submission_ref": r["submission_ref"],
        "superseded_by": str(r["superseded_by"]) if r["superseded_by"] else None,
        "note": r["note"], "created_by": r.get("created_by_name"),
        "created_at": r["created_at"].isoformat(), "updated_at": r["updated_at"].isoformat(),
        "entity_id": str(r["entity_id"]) if r.get("entity_id") else None,
        "entity_name": r.get("entity_name"),
        "fund_id": str(r["fund_id"]) if r.get("fund_id") else None,     # a per-product filing's subject
        "fund_name": r.get("fund_name"),
        # filing_role is the real, stamped value (services.governance.entities.filing_role_for, set once at
        # generate_filing() time) — solo | consolidated | whole_org. NULL only for filings created before
        # this column existed (2026-09-23); never backfilled with a guess. `scope` is kept for any existing
        # caller reading the old inferred field, derived the same way it always was (entity_kind == 'group'
        # is a weaker signal than filing_role's actual has-children check, so prefer filing_role going forward).
        "filing_role": r.get("filing_role"),
        "presentation_currency": (r.get("presentation_currency") or "EUR").strip(),   # NULL = frozen before phase 3: EUR
        "scope": ("product" if r.get("fund_id") else
                  ("consolidated" if r.get("entity_kind") == "group" else "entity") if r.get("entity_id") else "organisation"),
        "view": r.get("view") or "joint",                       # which values of the asset facts it was computed on
    }


def list_filings(session: Session, org_id: str) -> list[dict]:
    """Every filing for the org — the register, newest first."""
    rows = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.submission_ref, rf.superseded_by, rf.note, rf.created_at, rf.updated_at, rf.filing_role,
               rf.presentation_currency, rf.view, rs.version AS snapshot_version, u.full_name AS created_by_name,
               rf.entity_id, re.name AS entity_name, re.kind AS entity_kind, rf.fund_id, fu.name AS fund_name
        FROM regulatory_filing rf
        LEFT JOIN funds fu ON fu.fund_id = rf.fund_id
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
        WHERE rf.org_id = :o
        ORDER BY rf.seq DESC
    """), {"o": org_id}).mappings().all()
    return [_row_to_summary(r) for r in rows]


def get_filing(session: Session, org_id: str, filing_id: str, with_payload: bool = True) -> dict | None:
    """One filing with its full lifecycle history and (optionally) the frozen report payload."""
    r = session.execute(text("""
        SELECT rf.filing_id, rf.framework, rf.period_end, rf.period_label, rf.status, rf.snapshot_id,
               rf.approval_request_id, rf.submission_ref, rf.superseded_by, rf.note, rf.filing_role, rf.presentation_currency, rf.view,
               rf.created_at, rf.updated_at, rs.version AS snapshot_version, u.full_name AS created_by_name,
               rf.entity_id, re.name AS entity_name, re.kind AS entity_kind, rf.fund_id, fu.name AS fund_name, rf.disclosure_date
        FROM regulatory_filing rf
        LEFT JOIN funds fu ON fu.fund_id = rf.fund_id
        LEFT JOIN report_snapshots rs ON rs.snapshot_id = rf.snapshot_id
        LEFT JOIN users u ON u.user_id = rf.created_by
        LEFT JOIN reporting_entities re ON re.entity_id = rf.entity_id
        WHERE rf.org_id = :o AND rf.filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        return None
    out = _row_to_summary(r)
    out["approval_request_id"] = str(r["approval_request_id"]) if r["approval_request_id"] else None
    out["regulator"] = FRAMEWORKS.get(r["framework"], {}).get("regulator")
    out["basis"] = FRAMEWORKS.get(r["framework"], {}).get("basis")
    # a framework that freezes and accepts its filings through its own page (EUDR: per shipment, by the reference number)
    fw_def = FRAMEWORKS.get(r["framework"], {})
    out["own_flow"] = ({k: fw_def.get(k) for k in ("frozen_by", "accepted_by", "own_page")} if fw_def.get("own_page") else None)
    out["disclosure_date"] = r["disclosure_date"].isoformat() if r["disclosure_date"] else None   # None: made when frozen
    _due, _why = (due_for_undertaking(session, org_id, r["framework"], out["entity_id"], r["period_end"])
                  if ((_mandate_of(r["framework"]) or {}).get("deliverable", {}).get("due") or {}).get("fact")
                  else due_for_filing(r["framework"], r["period_end"], r["disclosure_date"]))
    out["due_date"], out["due_rule"] = (_due.isoformat() if _due else None), _why

    events = session.execute(text("""
        SELECT e.from_status, e.to_status, e.action, e.detail, e.created_at, u.full_name AS actor_name, u.email AS actor_email
        FROM regulatory_filing_event e
        LEFT JOIN users u ON u.user_id = e.actor_user_id
        WHERE e.filing_id = :f
        ORDER BY e.seq
    """), {"f": filing_id}).mappings().all()
    out["events"] = [{"from": e["from_status"], "to": e["to_status"], "action": e["action"],
                      "detail": e["detail"], "at": e["created_at"].isoformat(),
                      "actor": e["actor_name"], "actor_email": e["actor_email"]} for e in events]

    # machine-readable exports are only meaningful once the report is frozen
    out["export_formats"] = list(EXPORT_FORMATS.get(r["framework"], ("json",))) if r["snapshot_id"] else []

    if with_payload and r["snapshot_id"]:
        snap = get_snapshot(session, org_id, str(r["snapshot_id"]))
        if snap:
            out["snapshot"] = {"version": snap["version"], "reporting_basis": snap["reporting_basis"],
                               "payload": snap["payload"], "payload_sha256": snap["payload_sha256"],
                               "hash_verified": snap["hash_verified"], "engine_versions": snap["engine_versions"],
                               "created_at": snap["created_at"]}
    if r["snapshot_id"] and r["status"] not in NOT_LIVE:
        out["fx_revisions"] = fx_revisions(session, org_id, str(r["snapshot_id"]))
    if r["snapshot_id"]:
        out["run"] = _run_of(session, org_id, str(r["snapshot_id"]))
    return out


def _run_of(session: Session, org_id: str, snapshot_id: str) -> dict | None:
    """The engine run the frozen snapshot came from — its inputs and output checks (intake phase 4). None for a snapshot
    frozen before runs were recorded."""
    from services.governance.engine_runs import get_run
    rid = session.execute(text("SELECT run_id::text FROM report_snapshots WHERE snapshot_id = :s AND org_id = :o"),
                          {"s": snapshot_id, "o": org_id}).scalar()
    return get_run(session, org_id, rid) if rid else None


def fx_revisions(session: Session, org_id: str, snapshot_id: str) -> list[dict]:
    """Exchange rates this filing froze that have changed since (multi-currency phase 3): each one a reason the money
    may need restating. Empty for a filing presented in EUR throughout, or one frozen before rates were recorded."""
    from services.governance.translation import revisions_since
    s = session.execute(text("SELECT payload->'_fx' AS fx, created_at FROM report_snapshots WHERE snapshot_id = :s AND org_id = :o"),
                        {"s": snapshot_id, "o": org_id}).mappings().first()
    return revisions_since(session, org_id, s["fx"], s["created_at"]) if s and s["fx"] else []


def _log_event(session: Session, filing_id: str, from_status: str | None, to_status: str,
               action: str, actor_user_id: str | None, detail: dict | None = None) -> None:
    session.execute(text("""
        INSERT INTO regulatory_filing_event (filing_id, from_status, to_status, action, actor_user_id, detail)
        VALUES (:f, :fs, :ts, :a, :u, CAST(:d AS jsonb))
    """), {"f": filing_id, "fs": from_status, "ts": to_status, "a": action,
           "u": actor_user_id, "d": json.dumps(detail or {}, default=str)})
    # Export & Connect (connect/push): every lifecycle transition flows through here, so this one hook fans
    # ALL of them out to the org's registered webhooks — best-effort and off-thread, so a receiver can never
    # break or slow a filing transition. filing.frozen additionally fires on the freeze actions.
    try:
        row = session.execute(text(
            "SELECT org_id::text AS org, framework FROM regulatory_filing WHERE filing_id = :f"),
            {"f": filing_id}).mappings().first()
        if row and row["org"]:
            from services.integrations.webhooks import emit_event
            base = {"filing_id": str(filing_id), "framework": row["framework"], "from": from_status,
                    "to": to_status, "action": action,
                    "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            emit_event(session, row["org"], "filing.status_changed", base)
            if action in ("generate", "refresh", "restate"):
                emit_event(session, row["org"], "filing.frozen", base)
    except Exception:  # never let a webhook concern touch the transition
        pass


# ── lifecycle operations ────────────────────────────────────────────────

def _confirm_token(org_id: str, framework: str, basis: dict, summary: dict, entity_id: str | None = None,
                   fund_id: str | None = None) -> str:
    """Bind a preflight result to a token generate_filing() can re-verify. Fixes a real race an independent
    architecture review found: `confirmed` used to be a bare boolean, completely disconnected from the
    specific preflight state a human actually looked at — a human could confirm a clean preflight, the
    underlying book could change seconds later (a concurrent upload, a recalibration), and the frozen filing
    would silently reflect the NEW, unreviewed state while still being logged as 'data_confirmed: true'.
    The token is a hash of exactly what the preparer saw (org, framework, scope, basis, coverage, gaps,
    headline figures) — generate_filing() recomputes the identical summary fresh and refuses unless the
    hash still matches, i.e. unless nothing relevant has changed since the preflight was shown."""
    # Bound to the scope too: the summary is computed on the filing's own book (entity, consolidation weights,
    # presentation currency), so a confirmation of one entity's figures can never freeze another scope.
    import hashlib
    scope = {"org_id": org_id, "framework": framework, "entity_id": entity_id, "basis": basis, "summary": summary}
    if fund_id is not None:
        scope["fund_id"] = fund_id
    payload = json.dumps(scope, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def preflight(session: Session, org_id: str, org_type: str, framework: str, entity_id: str | None = None,
              fund_id: str | None = None) -> dict:
    """The confirm-data step before freezing: shows the basis, the data coverage, the headline figures and
    any gaps, so a preparer confirms 'this is my data' before a filing is frozen. Computes but freezes
    nothing. Returns a confirm_token binding this exact result — see _confirm_token()."""
    _open_for_new(framework, org_type)
    period_end = reporting_period_end(session, org_id)
    if framework in _PRODUCT_SCOPED and fund_id is None and entity_id is None:
        # a per-product report: the preparer chooses which fund first (nothing is computed or confirmed yet)
        from services.governance.product_filings import funds_owing
        from services.governance.reporting_settings import get_settings
        return {"framework": framework, "label": FRAMEWORKS[framework]["label"], "period_label": _period_label(period_end),
                "basis": get_settings(session, org_id), "product_scoped": True, "needs_fund": True,
                "funds": funds_owing(session, org_id), "can_generate": False, "confirm_token": None,
                "entity_scoped": False, "coverage": None, "gaps": []}
    _check_scope(session, org_id, framework, entity_id, fund_id)
    existing = session.execute(text("""
        SELECT status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status NOT IN ('superseded', 'withdrawn')
              AND entity_id IS NOT DISTINCT FROM :ent AND fund_id IS NOT DISTINCT FROM CAST(:fund AS uuid)
    """), {"o": org_id, "fk": framework, "pe": period_end, "ent": entity_id, "fund": fund_id}).scalar()
    from services.governance.reporting_settings import get_settings
    basis = get_settings(session, org_id)
    summary = _summary_for(session, org_id, framework, basis, entity_id, fund_id, period_end)
    token = _confirm_token(org_id, framework, basis, summary, entity_id, fund_id)
    from services.governance.figure_views import figures_for
    from services.governance.provided_data import attested_values
    from services.intake.views import preview as views_preview
    attested = {p["key"].removeprefix("provided."): p for p in attested_values(session, org_id, framework, period_end)}
    figures = [{"datapoint": dp, "label": attested[dp]["label"], "unit": attested[dp].get("unit"),
                "client_value": attested[dp]["value"], "tellumen_value": attested[dp].get("tellumen_value"),
                "delta_pct": attested[dp].get("delta_pct"), "provider": attested[dp].get("provider")}
               for dp in figures_for(framework) if dp in attested]
    return {"framework": framework, "label": FRAMEWORKS[framework]["label"],
            "period_label": _period_label(period_end), "basis": basis,
            "can_generate": existing is None, "existing_status": existing,
            "entity_scoped": framework in _ENTITY_SCOPED, "entity_id": entity_id,
            "product_scoped": framework in _PRODUCT_SCOPED, "fund_id": fund_id, "confirm_token": token, **summary,
            # which values of the located asset facts to read: a fund's document reads its holdings, not that book
            "views": None if framework in _PRODUCT_SCOPED else views_preview(session, org_id), "figures": figures}


def _obligation_scope(session: Session, org_id: str, obligation_id: str, framework: str,
                      entity_id: str | None, fund_id: str | None = None) -> tuple[str | None, str | None]:
    """The entity (or, for a per-product report, the fund) a filing prepared for this obligation is scoped to — after
    checking the obligation is the organisation's, is for this framework, and falls in the configured reporting
    period."""
    import uuid
    try:
        uuid.UUID(obligation_id)
    except ValueError:
        raise FilingError("that obligation was not found") from None
    ob = session.execute(text("""SELECT framework, period_end, period_label, entity_id::text AS entity_id,
                                        fund_id::text AS fund_id
                                 FROM regulatory_obligation
                                 WHERE obligation_id = CAST(:i AS uuid) AND org_id = CAST(:o AS uuid)"""),
                         {"i": obligation_id, "o": org_id}).mappings().first()
    if ob is None:
        raise FilingError("that obligation was not found")
    if ob["framework"] != framework:
        raise FilingError("that obligation is for a different report")
    if entity_id is not None and entity_id != ob["entity_id"]:
        raise FilingError("the chosen scope is not the obligation's entity")
    if fund_id is not None and fund_id != ob["fund_id"]:
        raise FilingError("the chosen fund is not the obligation's")
    period = reporting_period_end(session, org_id)
    if ob["period_end"] != period:
        raise FilingError(f"this obligation is for {ob['period_label']} (period ending {ob['period_end'].isoformat()}), "
                          f"but your reporting period is set to end {period.isoformat()} — change the reporting "
                          f"period before preparing it")
    return ob["entity_id"], ob["fund_id"]


def reporting_period_end(session: Session, org_id: str) -> date:
    """The one reporting period end a filing is recorded for, built on and freezes supplied values of: the
    organisation's configured reporting period (reporting_settings; last calendar year-end when not set)."""
    from services.governance.reporting_settings import get_settings
    return date.fromisoformat(str(get_settings(session, org_id)["reporting_period_end"])[:10])


def _summary_for(session: Session, org_id: str, framework: str, basis: dict, entity_id: str | None,
                 fund_id: str | None, period_end: date) -> dict:
    """The confirm-data summary of exactly what the filing will freeze: the fund's document, or the entity's book."""
    if framework in _PRODUCT_SCOPED:
        from services.governance.product_filings import preflight_summary
        return preflight_summary(session, org_id, framework, fund_id, period_end)
    return _preflight_summary(session, org_id, framework, basis, _book_scope(session, org_id, framework, entity_id, period_end))


def _preflight_summary(session: Session, org_id: str, framework: str, basis: dict,
                       scope: tuple = (None, None, None)) -> dict:
    """Live coverage + headline for the confirm-data step, over exactly the book the filing will freeze: `scope` is
    (entity_ids, value_weights, translation) from _book_scope (whole organisation when all None). Honest gaps, no
    freeze."""
    entity_ids, value_weights, translation = scope
    gaps: list[str] = []
    if framework == "bank_tcfd":                       # the loan book the Taxonomy templates read (E95)
        from services.governance.bank_taxonomy_report import preflight
        return preflight(session, org_id, basis, entity_ids, value_weights, translation)
    if framework == "bank_p3esg":                      # the banking book the Pillar 3 templates read (E97)
        from services.governance.pillar3_report import preflight as p3_preflight
        return p3_preflight(session, org_id, basis, entity_ids, value_weights, translation)
    if framework == "sfdr_pai":                        # the statement for the period the filing will freeze
        from ml.regulatory.sfdr_pai import entity_pai_statement
        from ml.regulatory.sfdr_pai_period import PeriodError
        try:
            st = entity_pai_statement(session, org_id, reporting_period_end(session, org_id))
        except PeriodError as e:
            st = {"error": str(e)}
        if st.get("error"):
            return {"coverage": {"label": "positions", "done": 0, "total": 0, "pct": 0},
                    "total_value_eur": None, "noun": "positions", "gaps": [st["error"]]}
        cs, ent, fr = st["coverage_summary"], st["entity"], st.get("filing_readiness", {})
        if not fr.get("ready_to_file"):
            gaps += fr.get("missing", [])
        mand, done = cs.get("mandatory_indicators", 0), cs.get("computed", 0)
        if mand and done < mand:
            gaps.append(f"{done}/{mand} mandatory PAI indicators computed — the rest await issuer input")
        return {"coverage": {"label": "PAI indicators computed", "done": done, "total": mand,
                             "pct": round(100 * done / mand, 1) if mand else 0},
                "total_value_eur": ent.get("total_value_eur"), "value_at_risk_eur": None,
                "noun": "positions", "positions": ent.get("positions"), "gaps": gaps}
    if framework == "reit_taxonomy":                   # the property book it freezes (until E87 this was reit_tcfd's only)
        from api.routers.realestate import build_disclosure_snapshot
        r = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"], entity_ids=entity_ids,
                                      value_weights=value_weights, translation=translation)["rollup"]
        n_total, n_done = r.get("n_properties", 0), r.get("n_scored", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} properties not yet scored — excluded from exposure")
        return {"coverage": {"label": "properties scored", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_value_eur"), "value_at_risk_eur": None,
                "noun": "properties", "gaps": gaps}
    if framework in ("insurer_solvency", "insurer_orsa_climate", "insurer_recovery_stress"):
        from api.routers.insurance import build_disclosure_snapshot
        from services.governance.entities import root_of
        from services.insurer_capital import position, programme
        r = build_disclosure_snapshot(session, org_id, basis["scenario"], basis["horizon"], entity_ids=entity_ids,
                                      value_weights=value_weights, translation=translation)["rollup"]
        n_total, n_done = r.get("n_policies", 0), r.get("n_priced", 0)
        if n_total and n_done < n_total:
            gaps.append(f"{n_total - n_done} of {n_total} policies not yet priced")
        # figures stated per undertaking (or group) under Solvency II
        pe = reporting_period_end(session, org_id)
        who = root_of(session, org_id, entity_ids)
        if not position(session, org_id, pe, who).get("provenance"):
            gaps.append("own funds / SCR not attested for this undertaking and period")
        if programme(session, org_id, pe, who)[1] != "attested":
            gaps.append("reinsurance in force not attested for this undertaking and period")
        return {"coverage": {"label": "policies priced", "done": n_done, "total": n_total,
                             "pct": round(100 * n_done / n_total, 1) if n_total else 0},
                "total_value_eur": r.get("total_sum_insured_eur"), "value_at_risk_eur": None,
                "noun": "policies", "gaps": gaps}
    # the ESRS statement & any other framework — no single coverage ratio (its completeness is its checks: every item
    # filled or omitted with a reason), so present it cleanly (basis + confirm) rather than a fake 0%.
    return {"coverage": None, "total_value_eur": None, "noun": "sites & sourcing plots", "gaps": []}


def org_data_coverage_pct(session: Session, org_id: str, org_type: str, framework: str) -> float | None:
    """LIVE per-org data-completeness % for this framework right now (e.g. "312/340 assets scored") — the
    same number the preflight/confirm-data step shows, reused here for the supervisor oversight rollup.

    Deliberately NOT datapoint_catalog.coverage()'s "pct_computed": that is a STATIC, framework-architectural
    constant (what fraction of the framework's datapoints Tellumen's engine computes vs needs from the
    customer) — identical for every customer on a given framework regardless of how complete THEIR book
    actually is. Platform E2E audit (2026-09-24) finding #7: the oversight rollup was showing that static
    number next to per-org rows (last filed, KRI breaches), where a reader would reasonably — but wrongly —
    read it as "how complete is my filing." Returns None where no single completeness ratio applies (e.g.
    agri csrd_e1/esrs_pack), same honesty as preflight itself — never a fabricated 0%."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS or org_type not in FRAMEWORKS[framework]["sectors"]:
        return None
    if framework in _PRODUCT_SCOPED or retirement(framework):   # per fund: no single ratio; retired: nothing to prepare
        return None
    from services.governance.reporting_settings import get_settings
    basis = get_settings(session, org_id)
    cov = _preflight_summary(session, org_id, framework, basis).get("coverage")
    return cov.get("pct") if cov else None


def _open_for_new(framework: str, org_type: str) -> None:
    """A framework a new filing can be prepared for: known, built, for this sector and not retired."""
    if framework not in FRAMEWORKS or framework not in _BUILDERS:
        raise FilingError(f"unknown framework '{framework}'")
    if org_type not in FRAMEWORKS[framework]["sectors"]:
        raise FilingError(f"framework '{framework}' does not apply to a {org_type}")
    _not_retired(framework)


def _not_retired(framework: str) -> None:
    """A retired framework freezes nothing new — not a new filing, a refreshed draft or a restatement: its filings
    stay readable as frozen; a correction, where it has a successor, is prepared under that. A report frozen from its
    own subject (an EUDR statement from its shipment) is not frozen by these generic paths either."""
    why = retirement_refusal(framework)
    if why:
        raise FilingError(why)
    own = (FRAMEWORKS.get(framework) or {}).get("frozen_by")
    if own:
        raise FilingError(f"{FRAMEWORKS[framework]['label']} is prepared {own}")


def _book_basis(session: Session, org_id: str, framework: str, entity_id: str | None, period_end: date):
    """What a filing's book is: the reporting entities it covers, their consolidation weights, and how its money is
    presented (multi-currency phase 3: solo in the entity's functional currency, consolidated in the group's
    presentation currency, group-internal exposures eliminated). Shared by generate, refresh and restate so a
    re-freeze can never change the scope or currency of the filing it replaces."""
    entity_ids = value_weights = translation = None
    if framework == "esrs_pack":
        # the ESRS statement's scope is the undertaking's own (its sites, and a group's by consolidation and joint
        # arrangements — services.governance.esrs_statement.scope); its money is stated per value with its currency
        return ([entity_id] if entity_id else None), None, None
    if entity_id is not None:
        from services.governance import entities as _E
        entity_ids = _E.subtree_ids(session, org_id, entity_id)
        if len(entity_ids) > 1:   # a parent/group — consolidate the subtree, ownership-weighted
            value_weights = _E.ownership_weights(session, org_id, root_entity_id=entity_id, regime=_E.regime_for(framework))
    if framework in _ENTITY_SCOPED:
        from services.governance.translation import plan
        translation = plan(session, org_id, entity_id, period_end, scope=entity_ids, weights=value_weights)
    return entity_ids, value_weights, translation


def _book_scope(session: Session, org_id: str, framework: str, entity_id: str | None, period_end: date) -> tuple:
    """_book_basis for callers that report to a preparer: a book that cannot be presented is a FilingError."""
    from services.governance.translation import TranslationError
    try:
        return _book_basis(session, org_id, framework, entity_id, period_end)
    except TranslationError as e:
        raise FilingError(str(e)) from e


def _check_scope(session: Session, org_id: str, framework: str, entity_id: str | None,
                 fund_id: str | None = None) -> None:
    """A per-entity or consolidated scope only for a framework that honours it, and only for the org's own entity.
    Shared by the pre-filing check and generate, so both refuse the same scopes with the same reasons."""
    from services.governance.product_filings import ProductScopeError, check
    try:
        check(session, org_id, framework, entity_id, fund_id)
    except ProductScopeError as e:
        raise FilingError(str(e)) from e
    if framework in _PRODUCT_SCOPED:
        return
    # resolve the reporting scope — refuse a per-entity/consolidated scope for a framework that can't honour it
    # (would mislabel a whole-org number). SFDR consolidates by fund.
    if entity_id is not None and framework not in _ENTITY_SCOPED:
        raise FilingError(f"{FRAMEWORKS[framework]['label']} files at whole-organisation level — a per-entity or "
                          f"consolidated scope isn't available for it (SFDR consolidates by fund in the Funds "
                          f"workspace).")
    if entity_id is not None:
        from services.governance import entities as _E
        if not _E.get_entity(session, org_id, entity_id):
            raise FilingError("reporting entity not found")
    if framework == "esrs_pack":
        # an exempt subsidiary files no sustainability statement: it is included in its parent's consolidated report
        # (Directive 2013/34/EU Art. 19a(9) / 29a(8)) — nothing to confirm or freeze for it (E139)
        from services.governance.csrd_roles import live_role
        role = live_role(session, org_id, entity_id, reporting_period_end(session, org_id))
        if role and role["role"] == "exempt_subsidiary":
            raise FilingError(f"an exempt subsidiary files no ESRS statement — it is included in {role['parent_name']}'s "
                              f"consolidated report ({role['parent_report_ref']}); Directive 2013/34/EU Art. 19a(9) / 29a(8)")


def _previous_period_book(session: Session, org_id: str, framework: str, entity_id: str | None,
                          period_end: date) -> dict | None:
    """The previous period's frozen book for the same report and scope — embedded in the new filing when its templates
    print the previous disclosure reference date (regspec.embeds_previous_period). From the latest live filing of that
    period (never a superseded or withdrawn one); None when the organisation filed none."""
    from services.regspec import embeds_previous_period
    book_key = embeds_previous_period(framework)
    if not book_key:
        return None
    try:
        prev_end = period_end.replace(year=period_end.year - 1)
    except ValueError:                                     # 29 February
        prev_end = date(period_end.year - 1, 2, 28)
    row = session.execute(text("""
        SELECT f.filing_id::text AS filing_id, f.period_end, s.payload -> :key AS assets
        FROM regulatory_filing f JOIN report_snapshots s ON s.snapshot_id = f.snapshot_id
        WHERE f.org_id = CAST(:o AS uuid) AND f.framework = :fw AND f.period_end = :pe
          AND f.entity_id IS NOT DISTINCT FROM CAST(:e AS uuid) AND f.status NOT IN ('superseded', 'withdrawn')
        ORDER BY f.seq DESC LIMIT 1"""), {"o": org_id, "fw": framework, "pe": prev_end, "e": entity_id,
                                                 "key": book_key}).mappings().first()
    if not row or not row["assets"]:
        return None
    return {"filing_id": row["filing_id"], "period_end": row["period_end"].isoformat(), "assets": row["assets"]}


def _freeze(session: Session, org_id: str, framework: str, actor_user_id: str, note: str | None,
            entity_id: str | None, period_end: date, view: str = "joint",
            figure_sources: dict | None = None, fund_id: str | None = None,
            disclosure_date: date | None = None) -> tuple[dict, str]:
    from services.governance.engine_runs import RunCheckError
    from services.governance.report_snapshots import StatementRefused
    from services.governance.translation import TranslationError
    from services.intake.views import ViewError
    entity_ids, value_weights, translation = ((None, None, None) if framework in _PRODUCT_SCOPED
                                              else _book_scope(session, org_id, framework, entity_id, period_end))
    try:
        snap = create_snapshot(session, org_id, framework, actor_user_id, note=note, entity_ids=entity_ids,
                               value_weights=value_weights, translation=translation, view=view,
                               figure_sources=figure_sources,
                               previous_period=_previous_period_book(session, org_id, framework, entity_id, period_end),
                               fund_id=fund_id, disclosure_date=disclosure_date, period_end=period_end)
    except (TranslationError, RunCheckError, ViewError, StatementRefused) as e:
        raise FilingError(str(e)) from e
    return snap, (translation.presentation if translation is not None else "EUR")


def generate_filing(session: Session, org_id: str, org_type: str, framework: str,
                    actor_user_id: str, note: str | None = None, confirm_token: str | None = None,
                    entity_id: str | None = None, view: str = "joint", figure_sources: dict | None = None,
                    obligation_id: str | None = None, fund_id: str | None = None,
                    disclosure_date: date | None = None) -> dict:
    """Freeze the report at the org's current basis and open a DRAFT filing over it. One live filing per
    (framework, period, entity) — regenerating while one is live is refused (supersede it first).
    entity_id scopes the book: NULL = the whole org; a leaf entity = its own book (100%); a parent/group =
    its whole subtree CONSOLIDATED (proportional/equity lines value-weighted by ownership).

    confirm_token must be the exact token GET /filings/preflight?framework=... just returned for this same
    (org, framework) — recomputed and compared fresh here, not merely checked for presence. This closes the
    preflight->generate race: a bare `confirmed: bool` used to let a stale confirmation freeze data the
    preparer never actually looked at if the book changed in between."""
    _open_for_new(framework, org_type)
    if not confirm_token:
        raise FilingError("data must be confirmed (via the pre-filing check) before a filing is frozen")

    # prepared for a specific obligation: the filing takes that obligation's scope, and its period must be the one
    # the organisation reports for (the single period source) — never silently a different period or entity
    if obligation_id is not None:
        entity_id, ob_fund = _obligation_scope(session, org_id, obligation_id, framework, entity_id, fund_id)
        fund_id = ob_fund or fund_id

    _check_scope(session, org_id, framework, entity_id, fund_id)

    period_end = reporting_period_end(session, org_id)
    # the confirmation must be of this scope's book as it is now (see _confirm_token)
    from services.governance.reporting_settings import get_settings
    _basis = get_settings(session, org_id)
    _summary = _summary_for(session, org_id, framework, _basis, entity_id, fund_id, period_end)
    if confirm_token != _confirm_token(org_id, framework, _basis, _summary, entity_id, fund_id):
        raise FilingError("the data has changed since you last confirmed it (or the token is invalid, or was for "
                          "another scope) — re-run the pre-filing check and confirm again before freezing")
    existing = session.execute(text("""
        SELECT filing_id, status FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end = :pe AND status NOT IN ('superseded', 'withdrawn')
              AND entity_id IS NOT DISTINCT FROM :ent AND fund_id IS NOT DISTINCT FROM CAST(:fund AS uuid)
    """), {"o": org_id, "fk": framework, "pe": period_end, "ent": entity_id, "fund": fund_id}).mappings().first()
    if existing:
        raise FilingError(f"a live {framework} filing for {_period_label(period_end)} already exists "
                          f"(status {existing['status']}); withdraw it if it is an unfiled draft, or restate it if filed.")

    if disclosure_date is not None and disclosure_date <= period_end:
        raise FilingError(f"the disclosure date {disclosure_date} must be after the period it reports on ({period_end})")
    snap, ccy = _freeze(session, org_id, framework, actor_user_id, note, entity_id, period_end, view, figure_sources,
                        fund_id, disclosure_date)
    from services.governance.entities import filing_role_for
    role = "product" if fund_id else filing_role_for(session, org_id, entity_id)
    row = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by,
                                       entity_id, filing_role, presentation_currency, view, figure_sources, fund_id,
                                       disclosure_date)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u, :ent, :role, :ccy, :view, CAST(:figs AS jsonb),
                CAST(:fund AS uuid), :dd)
        RETURNING filing_id
    """), {"o": org_id, "fk": framework, "pe": period_end, "pl": _period_label(period_end),
           "snap": snap["snapshot_id"], "note": note, "u": actor_user_id, "ent": entity_id,
           "role": role, "ccy": ccy, "view": view, "figs": json.dumps(figure_sources or {}),
           "fund": fund_id, "dd": disclosure_date}).mappings().first()
    fid = str(row["filing_id"])
    _log_event(session, fid, None, "draft", "generate", actor_user_id,
               {"snapshot_id": snap["snapshot_id"], "version": snap["version"],
                "payload_sha256": snap["payload_sha256"], "data_confirmed": True,
                "confirm_token": confirm_token, "filing_role": role, "presentation_currency": ccy,
                "view": view, "figure_sources": figure_sources or {}, "run_id": snap.get("run_id")})
    return get_filing(session, org_id, fid, with_payload=False)


def refresh_filing(session: Session, org_id: str, filing_id: str, actor_user_id: str) -> dict:
    """Re-freeze a DRAFT filing's data snapshot from the current book — so newly provided inputs (e.g. per-loan
    EPC / IFRS-9 / maturity attributes) flow into the form. Only drafts can refresh; a submitted or accepted
    filing keeps its frozen snapshot (immutable — restate via a new version instead)."""
    r = session.execute(text("""
        SELECT framework, status, entity_id::text AS entity_id, snapshot_id::text AS snapshot_id, period_end, view,
               figure_sources, fund_id::text AS fund_id, disclosure_date
        FROM regulatory_filing WHERE filing_id = :f AND org_id = :o
    """), {"f": filing_id, "o": org_id}).mappings().first()
    if not r:
        raise FilingError("filing not found")
    if r["status"] != "draft":
        raise FilingError(f"only a draft filing can be refreshed — this one is '{r['status']}'. "
                          f"Restate it as a new version to bring in updated data.")
    _not_retired(r["framework"])

    snap, ccy = _freeze(session, org_id, r["framework"], actor_user_id, "draft data refreshed", r["entity_id"], r["period_end"],
                        r["view"], r["figure_sources"], r["fund_id"], r["disclosure_date"])
    session.execute(text("UPDATE regulatory_filing SET snapshot_id = :snap, presentation_currency = :ccy "
                         "WHERE filing_id = :f AND org_id = :o"),
                    {"snap": snap["snapshot_id"], "ccy": ccy, "f": filing_id, "o": org_id})
    _log_event(session, filing_id, "draft", "draft", "refresh", actor_user_id,
               {"snapshot_id": snap["snapshot_id"], "version": snap["version"],
                "payload_sha256": snap["payload_sha256"], "prev_snapshot_id": r["snapshot_id"], "run_id": snap.get("run_id")})
    session.commit()
    return get_filing(session, org_id, filing_id, with_payload=False)


def _load(session: Session, org_id: str, filing_id: str) -> dict:
    r = session.execute(text("""
        SELECT filing_id, status, framework, period_label, snapshot_id, approval_request_id
        FROM regulatory_filing WHERE org_id = :o AND filing_id = :f
    """), {"o": org_id, "f": filing_id}).mappings().first()
    if not r:
        raise FilingError("filing not found")
    return dict(r)


def _apply_transition(session: Session, org_id: str, filing_id: str, action: str,
                     actor_user_id: str, detail: dict | None = None,
                     extra_sets: dict | None = None) -> dict:
    allowed_from, to_status = _TRANSITIONS[action]
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in allowed_from:
        raise FilingError(f"cannot {action} a filing that is '{cur['status']}' "
                          f"(needs one of {sorted(allowed_from)})")
    sets = {"status": to_status}
    if extra_sets:
        sets.update(extra_sets)
    set_sql = ", ".join(f"{k} = :{k}" for k in sets)
    params = {**sets, "f": filing_id}
    session.execute(text(f"UPDATE regulatory_filing SET {set_sql} WHERE filing_id = :f"), params)
    _log_event(session, filing_id, cur["status"], to_status, action, actor_user_id, detail)
    return get_filing(session, org_id, filing_id, with_payload=False)


def submit_for_review(session: Session, org_id: str, filing_id: str, actor_user_id: str) -> dict:
    """Move a draft into review and raise a 4-eyes approval request. A *different* user must approve it.
    Refuses if the filing has an open BLOCKING validation issue — a broken filing never reaches a reviewer."""
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("draft", "returned"):
        raise FilingError(f"cannot submit a filing that is '{cur['status']}' for review")
    from services.governance.filing_validation import blocking_messages, validate_filing
    vr = validate_filing(session, org_id, filing_id)
    if not vr["passed"]:
        raise FilingError("cannot submit for approval — resolve the blocking validation issue(s): "
                          + "; ".join(blocking_messages(vr)))
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o, 'filing.approve', :ti, CAST(:p AS jsonb), :m)
        RETURNING request_id
    """), {"o": org_id, "ti": f"Approve {FRAMEWORKS[cur['framework']]['label']} · {cur['period_label']}",
           "p": json.dumps({"filing_id": filing_id, "framework": cur["framework"]}),
           "m": actor_user_id}).scalar()
    return _apply_transition(session, org_id, filing_id, "submit_for_review", actor_user_id,
                             detail={"approval_request_id": str(rid),
                                     "validation": {"blocking": vr["blocking"], "warnings": vr["warnings"],
                                                    "checks": vr["checks"]}},
                             extra_sets={"approval_request_id": rid})


def mark_approved(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None) -> dict:
    """Called by the approvals router when a filing.approve request is approved (checker ≠ maker enforced there)."""
    return _apply_transition(session, org_id, filing_id, "approve", checker_user_id,
                             detail={"reason": reason})


def mark_returned(session: Session, org_id: str, filing_id: str, checker_user_id: str,
                  reason: str | None = None, rejected: bool = False) -> dict:
    """Approval sent back (returned→draft) or rejected outright. Both re-open the draft for the preparer
    unless explicitly rejected (terminal-ish; a new filing supersedes)."""
    action = "reject" if rejected else "return"
    return _apply_transition(session, org_id, filing_id, action, checker_user_id, detail={"reason": reason})


def attest(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           attestor_name: str, statement: str, function: str | None = None) -> dict:
    """A named accountable person certifies the frozen numbers. Distinct from the 4-eyes approval:
    approval is process control; attestation is personal accountability for the filing. An EUDR due diligence
    statement is signed in the format of Annex II point 6 ('Signed for and on behalf of: Date: Name and function:
    Signature:'), so its signer states their function."""
    if not attestor_name or not statement:
        raise FilingError("attestation needs the accountable person's name and a certification statement")
    function = (function or "").strip() or None
    if _load(session, org_id, filing_id)["framework"] == "eudr_dds" and not function:
        raise FilingError("a due diligence statement is signed with the signer's name and function (Regulation (EU) "
                          "2023/1115, Annex II point 6) — state your function")
    return _apply_transition(session, org_id, filing_id, "attest", actor_user_id,
                             detail={"attestor_name": attestor_name, "statement": statement,
                                     **({"function": function} if function else {})})


def attestation(session: Session, filing_id: str) -> dict | None:
    """The filing's attestation as recorded (the latest attest event): who, their function, when, and their sign-in."""
    r = session.execute(text("""
        SELECT e.detail, e.created_at, u.email FROM regulatory_filing_event e LEFT JOIN users u ON u.user_id = e.actor_user_id
        WHERE e.filing_id = CAST(:f AS uuid) AND e.action = 'attest' ORDER BY e.seq DESC LIMIT 1"""),
        {"f": filing_id}).mappings().first()
    return {**(r["detail"] or {}), "at": r["created_at"].isoformat(), "email": r["email"]} if r else None


def submit(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           submission_ref: str | None = None) -> dict:
    """Transmit to the regulator. Records the submission reference; the record freezes here (guard trigger)."""
    return _apply_transition(session, org_id, filing_id, "submit", actor_user_id,
                             detail={"submission_ref": submission_ref},
                             extra_sets={"submission_ref": submission_ref})


def accept(session: Session, org_id: str, filing_id: str, actor_user_id: str,
           ack_ref: str | None = None) -> dict:
    """Record the regulator's acknowledgement — the filing is accepted. A framework accepted another way (an EUDR
    statement: the information system makes its reference number available) is not accepted here."""
    fw = session.execute(text("SELECT framework FROM regulatory_filing WHERE filing_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"),
                         {"f": filing_id, "o": org_id}).scalar()
    how = (FRAMEWORKS.get(fw) or {}).get("accepted_by")
    if how:
        raise FilingError(f"{FRAMEWORKS[fw]['label']} is accepted {how}")
    return _apply_transition(session, org_id, filing_id, "accept", actor_user_id,
                             detail={"ack_ref": ack_ref})


def restate_filing(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    """Restate a filed (submitted/accepted) filing: freeze a fresh snapshot at the current basis into a NEW
    draft, and supersede the old one pointing at the new. Both are preserved — the correction is a new
    version that runs the full lifecycle again, never an edit of the filed record."""
    if not reason:
        raise FilingError("a restatement needs a reason")
    cur = _load(session, org_id, filing_id)
    if cur["status"] not in ("submitted", "accepted"):
        raise FilingError(f"only a filed (submitted/accepted) filing can be restated — this is '{cur['status']}'")
    _not_retired(cur["framework"])

    # period_end of the filing being restated (restatement keeps the same reference period)
    #
    # Fixed 2026-09-26 (multi-currency phase 3): a restatement used to freeze the WHOLE organisation's book and file it
    # without the entity — a restated solo or consolidated filing silently became a whole-org one. It now keeps the
    # filing's entity, role and scope (and presents in the same currency rule) via the same _book_basis as generate.
    period = session.execute(text(
        "SELECT period_end, period_label, entity_id::text AS entity_id, filing_role, view, figure_sources, fund_id::text AS fund_id, "
        "disclosure_date FROM regulatory_filing WHERE filing_id = :f"),
        {"f": filing_id}).mappings().first()
    # a restatement is a new disclosure: made today, unless the original's planned date is still ahead
    dd = period["disclosure_date"] if period["disclosure_date"] and period["disclosure_date"] > date.today() else None
    snap, ccy = _freeze(session, org_id, cur["framework"], actor_user_id,
                        f"Restatement of {period['period_label']}: {reason}", period["entity_id"], period["period_end"],
                        period["view"], period["figure_sources"], period["fund_id"], dd)
    # supersede the old FIRST so the single-live-slot frees up before the restatement is inserted
    _apply_transition(session, org_id, filing_id, "supersede", actor_user_id, detail={"reason": reason})
    new_fid = session.execute(text("""
        INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, note, created_by,
                                       entity_id, filing_role, presentation_currency, view, figure_sources, fund_id,
                                       disclosure_date)
        VALUES (:o, :fk, :pe, :pl, 'draft', :snap, :note, :u, :ent, :role, :ccy, :view, CAST(:figs AS jsonb),
                CAST(:fund AS uuid), :dd)
        RETURNING filing_id
    """), {"o": org_id, "fk": cur["framework"], "pe": period["period_end"], "pl": period["period_label"], "dd": dd,
           "snap": snap["snapshot_id"], "note": f"Restates {period['period_label']}: {reason}",
           "u": actor_user_id, "ent": period["entity_id"], "role": period["filing_role"], "ccy": ccy,
           "view": period["view"], "figs": json.dumps(period["figure_sources"] or {}), "fund": period["fund_id"]}).scalar()
    _log_event(session, str(new_fid), None, "draft", "generate", actor_user_id,
               {"restates": filing_id, "reason": reason, "snapshot_id": snap["snapshot_id"]})
    # link the superseded old → the restatement (allowed: a superseded row is no longer guard-frozen)
    session.execute(text("UPDATE regulatory_filing SET superseded_by = :n WHERE filing_id = :f"),
                    {"n": new_fid, "f": filing_id})
    return get_filing(session, org_id, str(new_fid), with_payload=False)


def withdraw_filing(session: Session, org_id: str, filing_id: str, actor_user_id: str, reason: str) -> dict:
    """Discard a draft (or returned) filing generated by mistake — wrong scope, wrong period. Terminal: the filing is
    kept with its frozen snapshot (report_snapshots is WORM) and full history, but is no longer live, so the
    (framework, period, entity) slot is free to generate the right one. Only a filing nothing has signed off can be
    withdrawn (the guard trigger enforces the same in the database); a filed one is restated instead. A pending
    cell-override proposal on it is closed with it — override and approval request both 'withdrawn'."""
    reason = (reason or "").strip()
    if len(reason) < WITHDRAW_REASON_MIN:
        raise FilingError(f"a withdrawal needs a reason of at least {WITHDRAW_REASON_MIN} characters")
    status = _load(session, org_id, filing_id)["status"]
    if status not in _TRANSITIONS["withdraw"][0]:
        raise FilingError(f"only a draft or returned filing can be withdrawn — this one is '{status}'"
                          + (". Restate it to correct a filed report." if status in ("submitted", "accepted") else "."))
    pending = session.execute(text("""
        UPDATE filing_cell_override SET status = 'withdrawn', decided_by = :u, decided_at = now()
        WHERE org_id = :o AND filing_id = :f AND status = 'pending'
        RETURNING override_id::text AS override_id, approval_request_id
    """), {"o": org_id, "f": filing_id, "u": actor_user_id}).mappings().all()
    closed = [r["approval_request_id"] for r in pending if r["approval_request_id"]]
    if closed:
        session.execute(text("""
            UPDATE approval_requests SET status = 'withdrawn', withdrawn_cause = 'filing_withdrawn', reason = :r, decided_at = now()
            WHERE org_id = :o AND request_id = ANY(:ids) AND status = 'pending'
        """), {"o": org_id, "ids": closed, "r": f"The filing was withdrawn: {reason}"})
    return _apply_transition(session, org_id, filing_id, "withdraw", actor_user_id,
                             detail={"reason": reason, "overrides_withdrawn": [r["override_id"] for r in pending],
                                     "approvals_withdrawn": [str(i) for i in closed]})


def prior_filing_id(session: Session, org_id: str, filing_id: str) -> str | None:
    """The filing this one restates (i.e. the one it superseded), if any — for a variance comparison."""
    r = session.execute(text(
        "SELECT filing_id::text FROM regulatory_filing WHERE org_id = :o AND superseded_by = :f"),
        {"o": org_id, "f": filing_id}).scalar()
    if r:
        return r
    # else: the most recent accepted/submitted filing for the same framework with an EARLIER period
    # ... for the SAME reporting entity (fixed 2026-09-26: a solo filing used to be compared with whatever filing of the
    # framework came before — often the whole organisation's)
    cur = session.execute(text(
        "SELECT framework, period_end, entity_id FROM regulatory_filing WHERE filing_id = :f"), {"f": filing_id}).mappings().first()
    if not cur:
        return None
    return session.execute(text("""
        SELECT filing_id::text FROM regulatory_filing
        WHERE org_id = :o AND framework = :fk AND period_end < :pe AND status IN ('submitted','accepted','superseded')
              AND entity_id IS NOT DISTINCT FROM :ent
        ORDER BY period_end DESC, seq DESC LIMIT 1
    """), {"o": org_id, "fk": cur["framework"], "pe": cur["period_end"], "ent": cur["entity_id"]}).scalar()
