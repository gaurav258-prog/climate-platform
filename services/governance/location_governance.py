"""Governed edit/delete of locations (sites & plots) — the maker-checker apply layer.

Two entry points share ONE apply path so a change is identical whether it applied directly or
after approval:
  - needs_approval(session, org_id, action_key, changed_fields) reads the approval matrix
    (approval_policy) — org row overrides the platform default.
  - apply_location_change(session, request_type, payload, actor, org_id) performs the mutation
    (whitelisted columns only), re-snaps H3 + re-scores when coordinates move, and writes an
    audit row. Called by the supply endpoints for a direct change, and by approvals.decide()
    when a checker approves.

Every path writes access_audit_log — nothing mutates a location without an audit trail.
"""
from __future__ import annotations

import json

import h3
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.services.rbac import write_audit
from services.scoring.on_demand import schedule_scoring

# Whitelisted editable columns per entity — the ONLY keys an update will touch (SQL-injection safe:
# column names come from these sets, never from the request).
SITE_COLS = {"name", "site_type", "latitude", "longitude", "annual_value_eur",
             "annual_throughput_eur", "country", "region", "address"}
PLOT_COLS = {"plot_name", "latitude", "longitude", "annual_spend_eur", "plot_area_ha",
             "region", "country"}  # commodity handled specially (name → id)

_TABLE = {"site": ("sc_company_sites", "site_id"), "plot": ("sc_sourcing_plots", "plot_id")}

# The money a location edit can change: column → is it a yearly flow? (a flow converts at the 12-month average, a
# balance at the closing rate on the book date — the same policy as adding the location, services/intake/money.py)
MONEY_FIELDS = {"site": {"annual_value_eur": False, "annual_throughput_eur": True},
                "plot": {"annual_spend_eur": True}}


class LocationMoneyError(ValueError):
    pass


def convert_money_changes(session: Session, org_id: str, kind: str, changes: dict,
                          currency: str | None, book_date) -> tuple[dict, dict | None]:
    """An edit's amounts, sent in `currency` for `book_date`, → EUR for the engine, plus the money_source record of what
    was sent and the rate used. Converted when the edit is made, so an approver sees the figure that will be stored.
    An amount without a currency or book date is refused — never assumed EUR."""
    from services.intake.money import MoneyError, convert_amount, source_record
    money = {k: v for k, v in changes.items() if k in MONEY_FIELDS[kind]}
    if not money:
        return changes, None
    conv = {}
    try:
        for k, v in money.items():
            conv[k] = convert_amount(session, v, currency, book_date, flow=MONEY_FIELDS[kind][k],
                                     label=k.removesuffix("_eur").replace("_", " "), org_id=org_id)
    except MoneyError as e:
        raise LocationMoneyError(str(e)) from e
    out = {**changes, **{k: c["eur"] for k, c in conv.items()}}
    return out, source_record((currency or "").upper(), book_date, conv, origin="manual_edit")


def resolve_policy(session: Session, org_id: str, action_key: str) -> dict:
    """The org's rule for this action, falling back to the platform default (org_id NULL)."""
    row = session.execute(text("""
        SELECT requires_approval, material_fields FROM approval_policy
        WHERE action_key = :a AND (org_id = :o OR org_id IS NULL)
        ORDER BY org_id NULLS LAST LIMIT 1
    """), {"a": action_key, "o": org_id}).mappings().first()
    if not row:
        return {"requires_approval": False, "material_fields": []}
    return {"requires_approval": bool(row["requires_approval"]), "material_fields": list(row["material_fields"] or [])}


def needs_approval(session: Session, org_id: str, action_key: str, changed_fields: list[str] | None) -> bool:
    """A delete (no material_fields) needs approval iff requires_approval. An update needs it only
    when a MATERIAL field changed (empty material_fields = any change is material)."""
    pol = resolve_policy(session, org_id, action_key)
    if not pol["requires_approval"]:
        return False
    if action_key.endswith(".delete"):
        return True
    mats = pol["material_fields"]
    if not mats:
        return bool(changed_fields)
    return any(f in mats for f in (changed_fields or []))


def _rescore(session: Session, table: str, id_col: str, target_id: str, org_id: str) -> None:
    """After a coordinate move, re-snap the H3 cell and score it if the golden source hasn't reached it."""
    row = session.execute(text(f"SELECT CAST(latitude AS FLOAT) lat, CAST(longitude AS FLOAT) lon FROM {table} WHERE {id_col}=:i AND org_id=:o"),
                          {"i": target_id, "o": org_id}).mappings().first()
    if not row or row["lat"] is None:
        return
    cell = h3.latlng_to_cell(row["lat"], row["lon"], 8)
    session.execute(text(f"UPDATE {table} SET h3_cell=:c WHERE {id_col}=:i AND org_id=:o"),
                    {"c": cell, "i": target_id, "o": org_id})
    session.commit()
    schedule_scoring({cell: (row["lat"], row["lon"])})  # background — don't block the edit on a fresh cell


def _clean_changes(kind: str, changes: dict) -> dict:
    cols = SITE_COLS if kind == "site" else PLOT_COLS
    return {k: v for k, v in (changes or {}).items() if k in cols}


class LocationChangeError(ValueError):
    pass


def deletion_block(session: Session, kind: str, target_id: str) -> str | None:
    """Why an asset may not be deleted, or None. A site finance has stated year-end values for is part of the
    reporting history (comparatives, restatement — ESRS 1 §83, §96): it stops being held (held_until) instead."""
    if kind == "site" and session.execute(text("SELECT 1 FROM site_period_values WHERE site_id = CAST(:i AS uuid) LIMIT 1"),
                                          {"i": target_id}).first():
        return ("this site has year-end values for a reporting period — set the date the undertaking stopped holding "
                "it (held until) instead of deleting it")
    return None


def submit_or_apply(session: Session, *, org_id: str, actor_user_id: str, request_type: str,
                    target_id: str, changes: dict | None = None, commodity: str | None = None,
                    title: str, money_source: dict | None = None) -> dict:
    """The single entry the endpoints call. Reads the approval matrix: either applies the change
    directly (audited) or opens a 4-eyes approval request for a checker to clear."""
    import json
    verb = request_type.rsplit(".", 1)[1]
    if verb == "delete":
        block = deletion_block(session, request_type.split(".")[1], target_id)
        if block:
            raise LocationChangeError(block)
    changed = list((_clean_changes(request_type.split(".")[1], changes or {})).keys()) if verb == "update" else None
    payload = {"target_id": target_id, "changes": changes or {}, **({"commodity": commodity} if commodity else {}),
               **({"money_source": money_source} if money_source else {})}

    if needs_approval(session, org_id, request_type, changed):
        rid = session.execute(text("""
            INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
            VALUES (:o, :t, :ti, CAST(:p AS jsonb), :m) RETURNING request_id
        """), {"o": org_id, "t": request_type, "ti": title, "p": json.dumps(payload), "m": actor_user_id}).scalar()
        session.commit()
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action="approval.create",
                    target_type="approval", target_id=str(rid), detail={"request_type": request_type, "title": title})
        return {"status": "pending", "approval_id": str(rid), "requires_approval": True}

    result = apply_location_change(session, request_type, payload, actor_user_id=actor_user_id, org_id=org_id)
    return {"status": "applied", "requires_approval": False, **result}


def apply_location_change(session: Session, request_type: str, payload: dict,
                          actor_user_id: str, org_id: str) -> dict:
    """Perform a governed location mutation and audit it. request_type is
    supply.{site|plot}.{update|delete}; payload = {target_id, changes?, commodity?}."""
    _, kind, verb = request_type.split(".")   # supply / site|plot / update|delete
    table, id_col = _TABLE[kind]
    target_id = payload["target_id"]

    if verb == "delete":
        block = deletion_block(session, kind, target_id)
        if block:
            raise LocationChangeError(block)
        n = session.execute(text(f"DELETE FROM {table} WHERE {id_col}=:i AND org_id=:o"),
                            {"i": target_id, "o": org_id}).rowcount
        session.commit()
        write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action=request_type,
                    target_type=table, target_id=target_id, detail={"deleted": bool(n)})
        return {"applied": True, "deleted": bool(n)}

    # update
    changes = _clean_changes(kind, payload.get("changes", {}))
    # a plot may also re-tag its commodity (name → id)
    commodity = payload.get("commodity")
    sets, params = [], {"i": target_id, "o": org_id}
    for k, v in changes.items():
        sets.append(f"{k} = :{k}"); params[k] = v
    if payload.get("money_source") and any(k in MONEY_FIELDS[kind] for k in changes):
        from services.intake.money import money_source_merge_sql
        sets.append(f"money_source = {money_source_merge_sql()}"); params["ms"] = json.dumps(payload["money_source"], default=str)
    if kind == "plot" and commodity:
        cid = session.execute(text("SELECT commodity_id::text FROM sc_commodities WHERE name=:n"), {"n": commodity}).scalar()
        if cid:
            sets.append("commodity_id = :cid"); params["cid"] = cid
    if sets:
        from services.intake.observations import sync
        sync(session, org_id, asset_ids=[target_id], tables=[table])            # the book before this edit
        session.execute(text(f"UPDATE {table} SET {', '.join(sets)} WHERE {id_col}=:i AND org_id=:o"), params)
        sync(session, org_id, asset_ids=[target_id], tables=[table], method="manual_edit", origin=f"user:{actor_user_id}")
        session.commit()
    if "latitude" in changes or "longitude" in changes:
        _rescore(session, table, id_col, target_id, org_id)
    write_audit(session, org_id=org_id, actor_user_id=actor_user_id, action=request_type,
                target_type=table, target_id=target_id,
                detail={"changes": changes, **({"commodity": commodity} if commodity else {})})
    return {"applied": True, "changes": changes}
