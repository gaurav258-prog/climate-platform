"""Lane 2 — provided datapoints: bring-your-own-number, reconciled + attested.

A value computed on the customer's or a vendor's side (own-operations GHG from a carbon tool, a Taxonomy
alignment determination, an audited financed-emissions figure, an ESG indicator) is submitted here. We:
  1. accept it only for a 'provided'-lane datapoint in the canonical catalog (never an arbitrary key),
  2. preserve provenance (source client/vendor, provider name, data vintage),
  3. reconcile it against Tellumen's own computed value where a counterpart exists (delta vs tolerance),
  4. route it through the shared 4-eyes machinery — it is 'pending' until a second person attests it.

Precedence, matching the reference-data model, is client > vendor. Nothing lands in a filing unattested.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.datapoint_catalog import CATALOG

DEFAULT_TOL_PCT = 5.0     # a provided value within ±5% of our baseline reconciles clean, unless the catalog overrides


class ProvidedError(ValueError):
    pass


def _catalog_dp(framework: str, key: str) -> dict | None:
    return next((d for d in (CATALOG.get(framework) or []) if d["key"] == key), None)


def esrs_providable(session: Session, org_id: str, period_end) -> dict:
    """What the undertaking provides under the ESRS version governing the financial year ending period_end (with the
    organisation's FY 2026 election): every concept with its unit, period and breakdown (members of a closed list)."""
    import json as _json
    from pathlib import Path

    import services.regspec as R
    from services.calc_settings import get_calc_settings
    from services.governance import esrs_binding as B
    spec = R.governing(ESRS, period_end=period_end, elections=get_calc_settings(session, org_id))
    if spec is None:
        raise ProvidedError(f"no ESRS version governs the financial year ending {period_end}")
    bds = _json.loads((Path(__file__).resolve().parents[2] / "data/reference/esrs/breakdowns.json").read_text())
    items = [{"key": k, **c, "members": (bds[c["breakdown"]].get("members") if c["breakdown"] else None),
              "currency_required": c["unit"] in _MONETARY} for k, c in B.provided_catalog(spec).items()]
    return {"version": spec["version"], "act": spec["act"]["short"], "period_end": str(period_end)[:10], "datapoints": items}


def providable(framework: str) -> list[dict]:
    """The datapoints a customer/vendor can provide for a framework — every 'provided'-lane entry (you must
    supply it), plus 'reconcilable' computed entries (optional — bring your own figure to cross-check ours)."""
    return [{"key": d["key"], "label": d["label"], "provider": d["provider"], "note": d["note"],
             "source_category": d["source_category"],
             "kind": "required" if d["lane"] == "provided" else "reconcile"}
            for d in (CATALOG.get(framework) or []) if d["lane"] == "provided" or d.get("reconcilable")]


def _baseline(session: Session, org_id: str, framework: str, key: str) -> float | None:
    """Tellumen's own value for a provided datapoint, where we compute a counterpart — the recon anchor.
    Only the datapoints where we genuinely have a comparable number return a baseline; others reconcile to
    None (stored as provided, no divergence check) — honest, never invented."""
    try:
        from services.governance.reporting_settings import get_settings
        s = get_settings(session, org_id)
        # financed emissions: we compute a PCAF estimate a bank can reconcile its audited figure against
        if framework == "bank_tcfd" and key == "financed_emissions":
            from api.routers.bank import build_disclosure_snapshot
            em = build_disclosure_snapshot(session, org_id, s["scenario"], s["horizon"]).get("financed_emissions_tco2e", {})
            return sum((em.get(k) or 0) for k in ("scope1", "scope2", "scope3")) or None
        # E4 protected-area count: our free-feed (Natura 2000 + OSM) count a WDPA-holder can reconcile against
        if framework == "esrs_pack" and key == "e4_protected_area":
            from services.intelligence.protected_area import protected_area_exposure
            pa = protected_area_exposure(session, org_id)
            return (pa["sites"]["in_protected"] + pa["plots"]["in_protected"]) or None
    except Exception:
        return None
    return None


# ESRS figures are stated per undertaking and financial year under the family 'esrs', keyed by concept
# (data/reference/esrs/concepts.json) — one store whichever report prints them, and a concept keeps its key across
# versions so this year's figure is next year's comparative
ESRS = "esrs"
_ESRS_RANGE = {"percent": (0.0, 100.0), "tCO2eq": (0.0, None), "MWh": (0.0, None), "m3": (0.0, None), "ha": (0.0, None),
               "count": (0.0, None), "year": (1900.0, 2100.0), "monetary": (0.0, None), "monetary/tCO2eq": (0.0, None)}
_MONETARY = {"monetary", "monetary/tCO2eq"}


def _esrs_target(key: str, member: str | None, period_end, elections: dict | None) -> dict:
    """An ESRS concept the governing version (for the financial year ending period_end, with the organisation's
    election for FY 2026) asks the undertaking to provide, and — for a breakdown — a member of it."""
    import json as _json
    from pathlib import Path

    import services.regspec as R
    from services.governance import esrs_binding as B
    if period_end is None:
        raise ProvidedError("an ESRS figure is for a financial year: state its period end")
    spec = R.governing(ESRS, period_end=period_end, elections=elections)
    if spec is None:
        raise ProvidedError(f"no ESRS version governs the financial year ending {period_end}")
    c = B.provided_catalog(spec).get(key)
    if c is None:
        raise ProvidedError(f"'{key}' is not a figure the undertaking provides under {spec['act']['short']} "
                            f"(financial year ending {period_end})")
    label = c["label"]
    if c["breakdown"]:
        ref = _json.loads((Path(__file__).resolve().parents[2] / "data/reference/esrs/breakdowns.json").read_text())[c["breakdown"]]
        if not (member or "").strip():
            raise ProvidedError(f"'{key}' is reported per {c['breakdown'].replace('_', ' ')}: say which one")
        if ref.get("closed") and member not in ref["members"]:
            raise ProvidedError(f"'{member}' is not a {c['breakdown'].replace('_', ' ')} (one of {', '.join(ref['members'])})")
        label = f"{label} — {ref['members'][member] if ref.get('closed') else member}"
    elif member:
        raise ProvidedError(f"'{key}' is a single figure, not a breakdown")
    from services.governance.esrs_binding import concepts
    return {"key": key, "label": label, "lane": "provided", "unit": c["unit"], "period": c["period"], "recon_tol": None,
            "esrs_version": spec["version"], "signed": bool(concepts()[key].get("signed")), "member": member or None}


def _esrs_check(dp: dict, value_num: float | None, currency: str | None) -> None:
    if value_num is None:
        raise ProvidedError(f"'{dp['key']}' is a figure: give a number")
    lo, hi = _ESRS_RANGE.get(dp["unit"], (None, None))
    if dp.get("signed"):
        lo = None
    if (lo is not None and value_num < lo) or (hi is not None and value_num > hi):
        raise ProvidedError(f"'{dp['key']}' is in {dp['unit']}: the value must be "
                            + (f"between {lo:g} and {hi:g}" if hi is not None else f"at least {lo:g}"))
    if dp["unit"] in ("count", "year") and value_num != int(value_num):
        raise ProvidedError(f"'{dp['key']}' is a whole number")
    if dp["unit"] in _MONETARY and not (currency or "").strip():
        raise ProvidedError(f"'{dp['key']}' is an amount: say its currency (ISO 4217) — never assumed")
    if dp["unit"] not in _MONETARY and currency:
        raise ProvidedError(f"'{dp['key']}' is in {dp['unit']}, not an amount: it has no currency")


def _target(framework: str, key: str, period_end, elections: dict | None = None, member: str | None = None) -> dict:
    """What a supplied value is for: a catalog datapoint, an ESRS concept, or a template cell of the governing
    specification (with the organisation's elections, so the cell is checked against the version its filing is built to)."""
    if framework == ESRS:
        return _esrs_target(key, member, period_end, elections)
    if member:
        raise ProvidedError("only an ESRS figure is reported per breakdown member")
    if key.count(".") == 2:
        import services.regspec as R
        if period_end is None:
            raise ProvidedError("a template cell value needs the reporting period it is for")
        try:
            cell = R.supplied_cell(framework, key, period_end, elections=elections)
        except R.SpecError as e:
            raise ProvidedError(str(e)) from e
        return {"key": key, "label": cell["label"], "lane": "provided", "recon_tol": None, "cell": cell, "unit": cell.get("unit")}
    dp = _catalog_dp(framework, key)
    if not dp:
        raise ProvidedError(f"unknown datapoint '{key}' for {framework}")
    return dp


# the range a value in each catalog unit can take — checked where the value enters (a DIV of 5 or a negative premium
# would otherwise flow into a capital requirement)
_UNIT_RANGE = {"%": (0.0, 100.0), "ratio": (0.0, 1.0), "EUR": (0.0, None), "count": (0.0, None),
               "scr_ratio_%": (100.0, 10000.0)}   # an SCR coverage ratio trigger: at or above the breach level


def _check_unit(dp: dict, value_num: float | None) -> None:
    unit = dp.get("unit")
    if value_num is None or unit not in _UNIT_RANGE:
        return
    lo, hi = _UNIT_RANGE[unit]
    if value_num < lo or (hi is not None and value_num > hi):
        raise ProvidedError(f"'{dp.get('key')}' is in {unit}: the value must be "
                            + (f"between {lo:g} and {hi:g}" if hi is not None else f"at least {lo:g}"))
    if unit == "count" and value_num != int(value_num):
        raise ProvidedError(f"'{dp.get('key')}' is a count: give a whole number")


def submit(session: Session, org_id: str, actor: str, *, framework: str, datapoint_key: str,
           value_num: float | None = None, value_text: str | None = None, unit: str | None = None,
           source: str = "client", provider_name: str | None = None, data_vintage: str | None = None,
           period_label: str | None = None, reporting_period_end=None, reporting_entity_id: str | None = None,
           restatement_reason: str | None = None, currency: str | None = None, breakdown_member: str | None = None) -> dict:
    """Record a provided value for a reporting period, reconcile it, and raise a 4-eyes attest request. It supersedes
    only the earlier value for the same datapoint and period. For a closed period it is a restatement and needs its
    reason (the database refuses it otherwise — services.governance.period_close)."""
    from datetime import date
    if not reporting_period_end:
        raise ProvidedError("state the reporting period the value is for — a value without one never reaches a filing")
    pe = date.fromisoformat(str(reporting_period_end)[:10])
    from services.calc_settings import get_calc_settings
    dp = _target(framework, datapoint_key, pe, get_calc_settings(session, org_id), member=breakdown_member)
    if dp["lane"] != "provided" and not dp.get("reconcilable"):
        raise ProvidedError(f"datapoint '{datapoint_key}' cannot be provided (lane={dp['lane']}); it is computed by Tellumen")
    period_label = period_label or (f"FY{pe.year}" if pe and (pe.month, pe.day) == (12, 31) else pe.isoformat() if pe else None)
    if source not in ("client", "vendor"):
        raise ProvidedError("source must be 'client' or 'vendor'")
    if value_num is None and not (value_text or "").strip():
        raise ProvidedError("a value (numeric or text) is required")
    money = None
    if framework == ESRS:
        _esrs_check(dp, value_num, currency)
        unit = dp["unit"]
        if unit in _MONETARY:           # kept as sent; converted by the period's rule (closing for a position, average for a flow)
            from services.intake.money import MoneyError, convert_amount, field_entry
            try:
                conv = convert_amount(session, value_num, currency, pe, flow=dp.get("period") == "flow",
                                      label=datapoint_key, org_id=org_id)
            except MoneyError as e:
                raise ProvidedError(str(e)) from e
            money = {"currency": conv["currency"], "eur": conv["eur"],
                     "source": field_entry(conv["native"], conv["currency"], pe, conv["eur"], conv["rate"], origin="provided")}
    else:
        if currency or breakdown_member:
            raise ProvidedError("a currency or breakdown member is stated only with an ESRS figure")
        _check_unit(dp, value_num)
    entity = _entity_scope(session, org_id, framework, reporting_entity_id)
    from services.governance.period_close import is_closed
    if is_closed(session, org_id, entity, pe) and len((restatement_reason or "").strip()) < 10:
        raise ProvidedError(f"the period ending {pe} is closed for this undertaking — a new value is a restatement: "
                            "say why (at least 10 characters)")

    # reconcile against our baseline where one exists
    base = (_baseline(session, org_id, framework, datapoint_key)
            if value_num is not None and "cell" not in dp and framework != ESRS else None)
    tol = dp.get("recon_tol") or DEFAULT_TOL_PCT
    delta_pct = within = note = None
    if base is not None and base != 0 and value_num is not None:
        delta_pct = round(100 * (value_num - base) / base, 1)
        within = abs(delta_pct) <= tol
        note = f"Tellumen baseline {base:,.0f}; provided differs {delta_pct:+.1f}% ({'within' if within else 'beyond'} ±{tol:g}% tolerance)."
    elif value_num is not None:
        note = "No Tellumen counterpart to reconcile against — stored as provided, with provenance."

    # supersede the prior live value for this datapoint and period (another period's value is untouched)
    session.execute(text("""
        UPDATE provided_datapoint SET status='superseded'
        WHERE org_id=:o AND framework=:f AND datapoint_key=:k AND status IN ('pending','attested')
          AND reporting_period_end IS NOT DISTINCT FROM CAST(:pe AS date)
          AND reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid)
          AND breakdown_member IS NOT DISTINCT FROM :bm
    """), {"o": org_id, "f": framework, "k": datapoint_key, "pe": pe, "e": entity, "bm": breakdown_member or None})

    pid = session.execute(text("""
        INSERT INTO provided_datapoint (org_id, framework, datapoint_key, value_num, value_text, unit, source,
            provider_name, data_vintage, period_label, reporting_period_end, tellumen_value, delta_pct, within_tolerance,
            recon_note, submitted_by, reporting_entity_id, restatement_reason, value_currency, value_eur, money_source,
            breakdown_member)
        VALUES (:o,:f,:k,:vn,:vt,:u,:src,:pn, CAST(:dv AS date),:pl, CAST(:pe AS date),:tv,:dp,:wt,:rn,:by, CAST(:e AS uuid), :why,
                :ccy, :veur, CAST(:ms AS jsonb), :bm)
        RETURNING provided_id
    """), {"o": org_id, "f": framework, "k": datapoint_key, "vn": value_num, "vt": (value_text or None),
           "u": unit, "src": source, "pn": provider_name, "dv": data_vintage or None, "pl": period_label, "pe": pe,
           "tv": base, "dp": delta_pct, "wt": within, "rn": note, "by": actor, "e": entity,
           "why": (restatement_reason or "").strip() or None, "ccy": money and money["currency"],
           "veur": money and money["eur"], "ms": money and json.dumps(money["source"], default=str),
           "bm": breakdown_member or None}).scalar()

    # raise the shared 4-eyes request (checker ≠ maker enforced by the approvals router)
    payload = {"provided_id": str(pid), "framework": framework, "datapoint_key": datapoint_key,
               "value_num": value_num, "value_text": value_text, "source": source,
               "reporting_period_end": pe.isoformat() if pe else None, "reporting_entity_id": entity}
    title = f"Attest provided value · {dp['label'][:60]}"
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (:o,'provided.datapoint',:ti, CAST(:p AS jsonb), :m) RETURNING request_id
    """), {"o": org_id, "ti": title, "p": json.dumps(payload), "m": actor}).scalar()
    session.execute(text("UPDATE provided_datapoint SET approval_request_id=:r WHERE provided_id=:p"),
                    {"r": rid, "p": pid})
    return {"provided_id": str(pid), "status": "pending", "approval_request_id": str(rid),
            "tellumen_value": base, "delta_pct": delta_pct, "within_tolerance": within, "recon_note": note}


def attest(session: Session, org_id: str, payload: dict, decision: str, actor: str) -> dict:
    """Called from the approvals decide handler: attest or reject a provided value."""
    pid = (payload or {}).get("provided_id")
    status = "attested" if decision == "approved" else "rejected"
    session.execute(text("""
        UPDATE provided_datapoint SET status=:s, decided_by=:u, decided_at=now()
        WHERE provided_id=CAST(:p AS uuid) AND org_id=:o AND status='pending'
    """), {"s": status, "u": actor, "p": pid, "o": org_id})
    return {"provided_id": pid, "status": status}


def _entity_scope(session: Session, org_id: str, framework: str, reporting_entity_id: str | None) -> str | None:
    """The entity a value is stated for: one of the organisation's reporting entities, only for a report type whose
    figures belong to an undertaking (PER_ENTITY_REPORTS); None = the organisation as a whole."""
    if reporting_entity_id is None:
        return None
    from services.governance.datapoint_catalog import PER_ENTITY_REPORTS
    if framework not in PER_ENTITY_REPORTS:
        raise ProvidedError(f"{framework} values are stated for the organisation as a whole, not per entity")
    ok = session.execute(text("SELECT 1 FROM reporting_entities WHERE entity_id = CAST(:e AS uuid) AND org_id = :o"),
                         {"e": reporting_entity_id, "o": org_id}).first()
    if not ok:
        raise ProvidedError("no such reporting entity in this organisation")
    return str(reporting_entity_id)


def attested_values(session: Session, org_id: str, framework: str, period_end=None,
                    reporting_entity_id: str | None = None) -> list[dict]:
    """The ATTESTED provided values of one reporting period — the ones that passed 4-eyes and therefore land in that
    period's filing (frozen into its snapshot). A value for another period, or with no period, never does.
    reporting_entity_id: the entity the filing is for — a report type whose figures belong to an undertaking reads
    exactly that entity's values (None = the organisation's own); any other reads the organisation's.
    Returned in a form-datapoint shape so the filing form/annex surfaces them as provided datapoints."""
    from services.governance.datapoint_catalog import PER_ENTITY_REPORTS
    entity = str(reporting_entity_id) if (reporting_entity_id and framework in PER_ENTITY_REPORTS) else None
    rows = session.execute(text("""
        SELECT p.datapoint_key, p.value_num, p.value_text, p.unit, p.source, p.provider_name, p.reporting_period_end,
               p.tellumen_value, p.delta_pct, p.within_tolerance, p.decided_at, du.email AS attested_by,
               p.value_currency, p.value_eur, p.breakdown_member, p.money_source
        FROM provided_datapoint p
        LEFT JOIN users du ON du.user_id = p.decided_by
        WHERE p.org_id = :o AND p.framework = :f AND p.status = 'attested'
          AND p.reporting_period_end = CAST(:pe AS date)
          AND p.reporting_entity_id IS NOT DISTINCT FROM CAST(:e AS uuid)
        ORDER BY p.decided_at DESC
    """), {"o": org_id, "f": framework, "pe": period_end, "e": entity}).mappings().all()
    labels = {d["key"]: d["label"] for fw in CATALOG.values() for d in fw}
    units = {d["key"]: d.get("unit") for fw in CATALOG.values() for d in fw}
    if framework == ESRS:
        from services.governance.esrs_binding import concepts
        labels.update({k: c["label"] for k, c in concepts().items()})
        units.update({k: c["unit"] for k, c in concepts().items()})
    out = []
    for r in rows:
        val = r["value_num"] if r["value_num"] is not None else r["value_text"]
        member = r["breakdown_member"]
        out.append({
            "key": f"provided.{r['datapoint_key']}" + (f"@{member}" if member else ""),
            "concept": r["datapoint_key"], "member": member,
            "currency": r["value_currency"], "value_eur": r["value_eur"], "money_source": r["money_source"],
            "label": labels.get(r["datapoint_key"], r["datapoint_key"]) + (f" — {member}" if member else ""),
            "reporting_period_end": r["reporting_period_end"].isoformat() if r["reporting_period_end"] else None,
            "value": val, "unit": r["unit"] or units.get(r["datapoint_key"]), "source": "provided",
            "provider": r["provider_name"], "attested_by": r["attested_by"],
            "attested_at": r["decided_at"].isoformat() if r["decided_at"] else None,
            "tellumen_value": r["tellumen_value"], "delta_pct": r["delta_pct"],
            "within_tolerance": r["within_tolerance"], "reporting_entity_id": entity,
        })
    return out


def provided_list(session: Session, org_id: str, framework: str | None = None) -> list[dict]:
    """Live + recent provided values with their recon + attest status."""
    rows = session.execute(text("""
        SELECT p.provided_id::text AS provided_id, p.framework, p.datapoint_key, p.value_num, p.value_text,
               p.unit, p.source, p.provider_name, p.data_vintage, p.tellumen_value, p.delta_pct,
               p.within_tolerance, p.recon_note, p.status, p.submitted_at, su.email AS submitted_by,
               du.email AS decided_by, p.period_label, p.reporting_period_end, p.reporting_entity_id::text AS reporting_entity_id
        FROM provided_datapoint p
        LEFT JOIN users su ON su.user_id = p.submitted_by
        LEFT JOIN users du ON du.user_id = p.decided_by
        WHERE p.org_id = :o AND p.status <> 'superseded' AND (CAST(:f AS text) IS NULL OR p.framework = :f)
        ORDER BY p.submitted_at DESC
    """), {"o": org_id, "f": framework}).mappings().all()
    labels = {d["key"]: d["label"] for fw in CATALOG.values() for d in fw}
    for r in rows:
        if r["datapoint_key"].count(".") == 2 and r["datapoint_key"] not in labels and r["reporting_period_end"]:
            try:
                import services.regspec as R
                labels[r["datapoint_key"]] = R.supplied_cell(r["framework"], r["datapoint_key"], r["reporting_period_end"])["label"]
            except Exception:  # noqa: BLE001 — a cell the current spec no longer has keeps its key as label
                pass
    return [{"provided_id": r["provided_id"], "framework": r["framework"], "datapoint_key": r["datapoint_key"],
             "label": labels.get(r["datapoint_key"], r["datapoint_key"]),
             "value_num": r["value_num"], "value_text": r["value_text"], "unit": r["unit"],
             "source": r["source"], "provider_name": r["provider_name"],
             "data_vintage": r["data_vintage"].isoformat() if r["data_vintage"] else None,
             "tellumen_value": r["tellumen_value"], "delta_pct": r["delta_pct"],
             "within_tolerance": r["within_tolerance"], "recon_note": r["recon_note"], "status": r["status"],
             "submitted_by": r["submitted_by"], "decided_by": r["decided_by"],
             "submitted_at": r["submitted_at"].isoformat() if r["submitted_at"] else None,
             "period_label": r["period_label"],
             "reporting_period_end": r["reporting_period_end"].isoformat() if r["reporting_period_end"] else None,
             "reporting_entity_id": r["reporting_entity_id"]} for r in rows]
