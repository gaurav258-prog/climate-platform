"""Entity-structure import — the standard workflow for landing ANY institution's real org tree into
Tellumen, replacing the one-off hand-written script this session used to mirror ING Bank N.V.
(scripts/seed_ing_org_structure.py).

One shared staging model, two sources feeding it:
  - source='manual_csv': the customer (or an onboarding engineer) fills in a CSV template with their own
    known structure — available today.
  - source='document_extraction': an uploaded annual report / Pillar 3 disclosure is parsed by an LLM into
    the same staged-row shape — NOT built here. It needs an ANTHROPIC_API_KEY this deployment doesn't have
    configured (there is no LLM integration anywhere in this codebase yet); see
    services.governance.entity_extraction (a thin, honestly-unavailable stub) for where it plugs in once a
    key exists. Building the extraction call without a real key would mean faking or mocking it — this
    module never does that.

Whichever source fills it, the SAME review/confirm gate applies: nothing lands in `reporting_entities`
until a human explicitly confirms the staged batch. confirm_import() then calls
services.governance.entities.create_entity() — the same, already-validated function the one-at-a-time
Admin UI uses — in parent-before-child order, so there is exactly one path that actually creates a
reporting entity, no matter which source proposed it.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.entities import METHODS, EntityError, create_entity

VALID_SOURCES = {"manual_csv", "document_extraction"}
VALID_STATUSES = {"proposed", "edited", "rejected"}


class ImportError_(ValueError):
    """A staged-import rule was violated (bad source, cycle, dangling parent reference)."""


def _row_dict(r) -> dict:
    d = dict(r)
    if d.get("ownership_pct") is not None:
        d["ownership_pct"] = float(d["ownership_pct"])
    if d.get("confidence") is not None:
        d["confidence"] = float(d["confidence"])
    return d


def create_import(session: Session, org_id: str, actor_user_id: str | None, source: str,
                  rows: list[dict], source_document_name: str | None = None) -> dict:
    """Stage a proposed org tree. rows: [{name, parent_ref?, kind?, country?, ownership_pct?,
    consolidation_method?, source_note?, confidence?}, ...]. row_ref defaults to the row's own `name` (the
    natural key a CSV or an extraction will actually carry) unless the caller supplies one explicitly —
    lets parent_ref simply be another row's name, the most ergonomic authoring key for a human-filled file.
    Stages everything as-is; validation (cycles, dangling parents, ownership range) runs at confirm time,
    not here, so a reviewer can see and fix a bad row rather than have the whole upload silently rejected."""
    if source not in VALID_SOURCES:
        raise ImportError_(f"source must be one of {sorted(VALID_SOURCES)}")
    if not rows:
        raise ImportError_("no rows to stage")

    import_id = str(uuid.uuid4())
    session.execute(text("""
        INSERT INTO entity_structure_imports (import_id, org_id, source, source_document_name, status, created_by)
        VALUES (CAST(:i AS uuid), CAST(:o AS uuid), :src, :doc, 'staged', CAST(:u AS uuid))
    """), {"i": import_id, "o": org_id, "src": source, "doc": source_document_name, "u": actor_user_id})

    for idx, r in enumerate(rows):
        name = (r.get("name") or "").strip()
        if not name:
            continue   # an unnamed row can't be staged at all — skipped, not guessed
        row_ref = (r.get("row_ref") or name).strip()
        session.execute(text("""
            INSERT INTO entity_structure_import_rows
                (row_id, import_id, row_ref, parent_ref, parent_entity_id, name, kind, country,
                 ownership_pct, consolidation_method, source_note, confidence, status)
            VALUES (gen_random_uuid(), CAST(:i AS uuid), :ref, :pref, CAST(:peid AS uuid), :name, :kind,
                    :country, :pct, :method, :note, :conf, 'proposed')
        """), {"i": import_id, "ref": row_ref, "pref": (r.get("parent_ref") or "").strip() or None,
               "peid": r.get("parent_entity_id"), "name": name, "kind": (r.get("kind") or "legal_entity").strip(),
               "country": (r.get("country") or "").strip().upper() or None,
               "pct": r.get("ownership_pct"), "method": (r.get("consolidation_method") or "full").strip(),
               "note": r.get("source_note"), "conf": r.get("confidence")})
    return get_import(session, org_id, import_id)


def get_import(session: Session, org_id: str, import_id: str) -> dict:
    imp = session.execute(text("""
        SELECT import_id::text, org_id::text, source, source_document_name, status,
               created_by::text, created_at, confirmed_by::text, confirmed_at
        FROM entity_structure_imports WHERE org_id = CAST(:o AS uuid) AND import_id = CAST(:i AS uuid)
    """), {"o": org_id, "i": import_id}).mappings().first()
    if not imp:
        raise ImportError_("import not found")
    rows = session.execute(text("""
        SELECT row_id::text, row_ref, parent_ref, parent_entity_id::text, name, kind, country,
               ownership_pct, consolidation_method, source_note, confidence, status, created_entity_id::text
        FROM entity_structure_import_rows WHERE import_id = CAST(:i AS uuid) ORDER BY created_at
    """), {"i": import_id}).mappings().all()
    return {**dict(imp), "rows": [_row_dict(r) for r in rows]}


def list_imports(session: Session, org_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT i.import_id::text, i.source, i.source_document_name, i.status, i.created_at, i.confirmed_at,
               (SELECT count(*) FROM entity_structure_import_rows r WHERE r.import_id = i.import_id) AS n_rows
        FROM entity_structure_imports i WHERE i.org_id = CAST(:o AS uuid) ORDER BY i.created_at DESC
    """), {"o": org_id}).mappings().all()
    return [dict(r) for r in rows]


def update_row(session: Session, org_id: str, import_id: str, row_id: str, **fields) -> dict:
    """Edit a staged row before confirming (correct a name/ownership%/parent, or reject it outright).
    Refuses once the batch is no longer 'staged' — a confirmed or discarded import is final."""
    status = session.execute(text("""
        SELECT status FROM entity_structure_imports WHERE org_id = CAST(:o AS uuid) AND import_id = CAST(:i AS uuid)
    """), {"o": org_id, "i": import_id}).scalar()
    if status is None:
        raise ImportError_("import not found")
    if status != "staged":
        raise ImportError_(f"cannot edit a row in an import that is '{status}'")
    row = session.execute(text("SELECT 1 FROM entity_structure_import_rows WHERE row_id = CAST(:r AS uuid) AND import_id = CAST(:i AS uuid)"),
                          {"r": row_id, "i": import_id}).first()
    if not row:
        raise ImportError_("row not found")

    allowed = {"name", "kind", "country", "ownership_pct", "consolidation_method", "parent_ref",
              "parent_entity_id", "status", "source_note"}
    sets, params = [], {"r": row_id}
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "status" and v not in VALID_STATUSES:
            raise ImportError_(f"status must be one of {sorted(VALID_STATUSES)}")
        sets.append(f"{k} = CAST(:{k} AS uuid)" if k == "parent_entity_id" else f"{k} = :{k}")
        params[k] = v
    if not sets:
        raise ImportError_("nothing to update")
    # an edited field (other than a plain status flip) marks the row 'edited' so a reviewer can see what
    # changed from the original proposal, unless the caller explicitly set status themselves
    if "status" not in fields:
        sets.append("status = 'edited'")
    session.execute(text(f"UPDATE entity_structure_import_rows SET {', '.join(sets)} WHERE row_id = CAST(:r AS uuid)"), params)
    return get_import(session, org_id, import_id)


def discard_import(session: Session, org_id: str, import_id: str) -> dict:
    n = session.execute(text("""
        UPDATE entity_structure_imports SET status = 'discarded'
        WHERE org_id = CAST(:o AS uuid) AND import_id = CAST(:i AS uuid) AND status = 'staged'
    """), {"o": org_id, "i": import_id}).rowcount
    if not n:
        raise ImportError_("import not found or not in a discardable state")
    return {"ok": True}


def _topological_order(rows: list[dict]) -> list[dict]:
    """Order staged rows parent-before-child so create_entity() always has a real parent_entity_id to hand
    for an already-created row it references. Raises on a cycle (names the entities in it, never silently
    drops one) or a parent_ref that resolves to nothing in this batch and isn't an existing entity."""
    by_ref = {r["row_ref"]: r for r in rows}
    ordered: list[dict] = []
    visited: dict[str, str] = {}   # row_ref -> 'visiting' | 'done'

    def visit(ref: str, path: list[str]):
        r = by_ref.get(ref)
        if r is None:
            return   # not in this batch — resolved separately as an existing entity, or truly dangling (caught below)
        state = visited.get(ref)
        if state == "done":
            return
        if state == "visiting":
            cycle = " -> ".join(path + [ref])
            raise ImportError_(f"circular parent reference: {cycle}")
        visited[ref] = "visiting"
        if r.get("parent_ref"):
            visit(r["parent_ref"], path + [ref])
        visited[ref] = "done"
        ordered.append(r)

    for r in rows:
        visit(r["row_ref"], [])
    return ordered


def confirm_import(session: Session, org_id: str, import_id: str, actor_user_id: str) -> dict:
    """The real gate: validate the staged batch as a whole, then create every non-rejected row as a real
    reporting_entities row via entities.create_entity() — parents before children, so an in-batch parent
    reference always resolves to a real, already-created entity_id by the time its children are created.
    Refuses (names the exact problem) rather than partially creating a broken tree."""
    imp = get_import(session, org_id, import_id)
    if imp["status"] != "staged":
        raise ImportError_(f"cannot confirm an import that is '{imp['status']}'")

    live_rows = [r for r in imp["rows"] if r["status"] != "rejected"]
    if not live_rows:
        raise ImportError_("every row in this import is rejected — nothing to create")

    # duplicate row_ref (typically the entity name) inside one batch is ambiguous for parent resolution
    refs = [r["row_ref"] for r in live_rows]
    dupes = {x for x in refs if refs.count(x) > 1}
    if dupes:
        raise ImportError_(f"duplicate entity reference(s) in this batch: {sorted(dupes)}")

    # every parent_ref must resolve to another live row in THIS batch, or the row must instead carry a real
    # parent_entity_id already in reporting_entities — never a dangling reference
    by_ref = {r["row_ref"]: r for r in live_rows}
    existing_ids = {e["entity_id"] for e in session.execute(text(
        "SELECT entity_id::text AS entity_id FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"),
        {"o": org_id}).mappings().all()}
    for r in live_rows:
        if r.get("parent_entity_id"):
            if r["parent_entity_id"] not in existing_ids:
                raise ImportError_(f"'{r['name']}': parent_entity_id does not exist in this organisation")
        elif r.get("parent_ref") and r["parent_ref"] not in by_ref:
            raise ImportError_(f"'{r['name']}': parent '{r['parent_ref']}' is neither another row in this "
                              "batch nor an existing entity — reject or correct this row before confirming")
        if r.get("ownership_pct") is not None and not (0 <= r["ownership_pct"] <= 100):
            raise ImportError_(f"'{r['name']}': ownership_pct must be between 0 and 100")
        if r.get("consolidation_method") and r["consolidation_method"] not in METHODS:
            raise ImportError_(f"'{r['name']}': consolidation_method must be one of {sorted(METHODS)}")

    ordered = _topological_order(live_rows)   # raises on a cycle before anything is created

    created = []
    for r in ordered:
        parent_id = r.get("parent_entity_id")
        if not parent_id and r.get("parent_ref"):
            parent_row = by_ref[r["parent_ref"]]
            parent_id = parent_row.get("created_entity_id")   # filled in by an earlier iteration (parent-first order)
        try:
            e = create_entity(session, org_id, name=r["name"], kind=r["kind"] or "legal_entity",
                              parent_entity_id=parent_id, ownership_pct=r.get("ownership_pct") or 100.0,
                              consolidation_method=r.get("consolidation_method") or "full")
        except EntityError as exc:
            raise ImportError_(f"'{r['name']}': {exc}") from exc
        r["created_entity_id"] = e["entity_id"]
        session.execute(text("UPDATE entity_structure_import_rows SET created_entity_id = CAST(:e AS uuid) WHERE row_id = CAST(:r AS uuid)"),
                        {"e": e["entity_id"], "r": r["row_id"]})
        created.append({"name": r["name"], "entity_id": e["entity_id"]})

    session.execute(text("""
        UPDATE entity_structure_imports SET status = 'confirmed', confirmed_by = CAST(:u AS uuid), confirmed_at = now()
        WHERE import_id = CAST(:i AS uuid)
    """), {"u": actor_user_id, "i": import_id})
    return {"import_id": import_id, "status": "confirmed", "n_created": len(created),
           "n_rejected": len(imp["rows"]) - len(live_rows), "created": created}
