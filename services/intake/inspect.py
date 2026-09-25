"""Inspect a customer file before anything is decided: its columns, a sample of each, and our proposal for how it
maps onto the template (profiling), plus any mapping the customer already confirmed for this layout. Read-only —
nothing is stored. Works for CSV and Excel alike (the header is read here, not in the browser), for every sector."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from services.ingest.upload_validation import enrich_specs
from services.intake import mapping, profiling, values
from services.intake.catalog import TEMPLATES
from services.intake.pipeline import IntakeError, _parse, _security


def inspect(session: Session, org_id: str, template: str, raw: bytes, filename: Optional[str]) -> dict:
    tpl = TEMPLATES[template]
    sec = _security(raw, filename, tpl, "upload")
    if sec["status"] == "blocked":
        raise IntakeError(422, {"error": "security_blocked", "message": sec["findings"][0]["message"], "security": sec})
    df = _parse(raw, sec["detected_type"], "upload")
    cols = [str(c) for c in df.columns]
    specs = [{**s, "allowed": s.get("allowed") or values.allowed(session, s["vocab"])} if s.get("vocab") else s
             for s in enrich_specs(tpl.specs(df))]
    layout = mapping.for_layout(session, org_id, template, cols)
    return {"template": template, "filename": filename, "n_rows": int(len(df)), "columns": cols,
            "fingerprint": mapping.fingerprint(cols),
            "in_our_layout": all(s["name"] in df.columns for s in specs if s.get("required")),
            "layout_mapping": {k: layout[k] for k in ("profile_id", "name", "version")} if layout else None,
            "closest_mapping": mapping.closest(session, org_id, template, cols),
            "suggestion": profiling.suggest(session, df, specs), "fields": specs}
