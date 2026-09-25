"""Staging: every checked row, turned into exactly what the engine will receive, and matched to the live book.

    validated rows ─► build (engine-readiness) ─► match (new / update / unchanged) ─► staged records
                         │                           │
                         └─ cannot become an asset   └─ ambiguous, or a second row for the same asset
                            → rejected row, reason      → rejected row, reason

Rejected rows count toward the batch's reject limits exactly like validation failures, so the gate sees them.
Large changes to assets we already hold are a gate reason (principle 1: the client's value wins, but a big change
needs a second person). Nothing here writes to the book; land() does, from the same staged records.
"""
from __future__ import annotations

import json
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ingest import batch_controls as bc
from services.ingest import sector_ingest as si
from services.ingest.sector_contract import RowIssue, Sector
from services.ingest.upload_validation import validate_table
from services.intake import matching


def stage(session: Session, org_id: str, sector: Sector, df: pd.DataFrame, specs: list[dict]) -> dict:
    report = validate_table(df, specs)
    normalised = bc.normalise_rows(report["valid_rows"], specs)
    ctx = sector.prepare(session, org_id)
    row_nos = list(report["valid_row_numbers"])

    records: list[Optional[dict]] = []
    rejected: dict[int, str] = {}
    for rn, n in zip(row_nos, normalised):
        try:
            records.append(sector.build(ctx, n))
        except RowIssue as e:
            records.append(None)
            rejected[rn] = f"Not usable by the engine: {e}"
    n_not_ready = len(rejected)

    existing = sector.existing(session, org_id)
    results = matching.match(records, existing, name_field=sector.name_field, value_field=sector.value_field,
                             compare=sector.compare)
    for rn, res in zip(row_nos, results):
        if res.get("status") in ("ambiguous", "duplicate"):
            rejected[rn] = res["problem"] + (" — add your asset ID to say which one" if res["status"] == "ambiguous" else "")

    keep = [i for i, rn in enumerate(row_nos) if rn not in rejected]
    errors = sorted(report["errors"] + [{"row": rn, "problems": [p]} for rn, p in rejected.items()], key=lambda e: e["row"])
    report = {**report, "errors": errors, "n_error": len(errors), "n_valid": len(keep),
              "valid_rows": [report["valid_rows"][i] for i in keep], "valid_row_numbers": [row_nos[i] for i in keep]}
    names = [records[i].get(sector.name_field) if records[i] else None for i in range(len(records))]
    summary = matching.summarize(results, names)
    summary["n_not_ready"] = n_not_ready
    summary["ambiguous_rows"] = [rn for rn, res in zip(row_nos, results) if res.get("status") == "ambiguous"][:50]
    return {"report": report, "normalised": [normalised[i] for i in keep],
            "staged": [{"row_no": row_nos[i], "record": records[i], "match": results[i]} for i in keep],
            "rejected": rejected, "match_statuses": {rn: res.get("status") for rn, res in zip(row_nos, results)},
            "matching": summary, "ctx": ctx, "existing": {e["entity_id"]: e for e in existing},
            "value_staged": float(sum(records[i].get(sector.value_field) or 0 for i in keep))}


def large_change_reason(summary: dict) -> Optional[str]:
    large = summary.get("large_changes") or []
    if not large:
        return None
    eg = "; ".join(f"{c['name']}: {', '.join(c['reasons'])}" for c in large[:3])
    return f"Matching: {len(large)} existing asset(s) change a lot ({eg}{'; …' if len(large) > 3 else ''})."


def persist(session: Session, batch_id: str, st: dict) -> None:
    """Keep every row as it stood at check time: accepted rows as the engine will read them, rejected with why."""
    session.execute(text("DELETE FROM intake_staged_records WHERE batch_id = CAST(:b AS uuid)"), {"b": batch_id})
    rows = [{"b": batch_id, "r": s["row_no"], "st": "accepted", "rec": json.dumps(s["record"], default=str), "p": "[]",
             "m": s["match"]["status"], "t": s["match"].get("entity_id"), "d": json.dumps(s["match"].get("diff") or {}, default=str)}
            for s in st["staged"]]
    rows += [{"b": batch_id, "r": e["row"], "st": "rejected", "rec": "{}", "p": json.dumps(e["problems"]),
              "m": "ambiguous" if st["match_statuses"].get(e["row"]) == "ambiguous" else None, "t": None, "d": None}
             for e in st["report"]["errors"]]
    if rows:
        session.execute(text("""
            INSERT INTO intake_staged_records (batch_id, row_no, status, record, problems, match_status, target_entity_id, diff)
            VALUES (CAST(:b AS uuid), :r, :st, CAST(:rec AS jsonb), CAST(:p AS jsonb), :m, CAST(:t AS uuid), CAST(:d AS jsonb))
        """), rows)


def land(session: Session, org_id: str, sector: Sector, st: dict) -> dict:
    """Write the staged records: new assets inserted, existing assets updated with the values the file gives (a blank
    never clears a value), unchanged assets left alone. Then read the book back and reconcile what landed."""
    new, updates, unchanged_ids = [], [], []
    for s in st["staged"]:
        rec, m = dict(s["record"]), s["match"]
        if m["status"] == "new":
            new.append(rec)
        elif m["status"] == "update":
            target = st["existing"][m["entity_id"]]
            merged = {**target, **{k: v for k, v in rec.items() if v is not None}}
            merged["entity_id"], merged["_moved"] = m["entity_id"], m.get("moved", False)
            updates.append(merged)
        else:
            unchanged_ids.append(m["entity_id"])
    out = si.write(session, sector, org_id, st["ctx"], new, updates)
    ids = set(out["entity_ids"]) | {u["entity_id"] for u in updates} | set(unchanged_ids)
    after = {e["entity_id"]: e for e in sector.existing(session, org_id) if e["entity_id"] in ids}
    value_landed = float(sum(e.get(sector.value_field) or 0 for e in after.values()))
    notes: dict = {"n_new": len(new), "n_updated": len(updates), "n_unchanged": len(unchanged_ids)}
    needs_polygon = sum(1 for s in st["staged"] if s["record"].get("_needs_polygon"))
    if needs_polygon:
        notes["needs_polygon"] = needs_polygon
    if new and sector.key != "supply_plots" and not st["ctx"].get("default_entity"):
        notes["reporting_entity_gap"] = (f"{len(new)} new asset(s) have no reporting entity (this organisation has more "
                                         "than one), so they are not in any per-entity filing until assigned.")
    return {"n_landed": len(after), "value_landed": value_landed, "cell_coords": out["cell_coords"], "notes": notes}
