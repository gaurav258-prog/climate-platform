"""Issue a reference, legal basis and letter for every request or finding raised before formal correspondence existed.

Idempotent: only requests without a reference are touched; numbering continues each authority's own sequence.
    .venv/bin/python -m scripts.backfill_correspondence
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session
from services.supervision.correspondence import issue
from services.supervision.engagement import kinds


def main() -> None:
    with get_session() as s:
        rows = s.execute(text("""SELECT request_id::text, regulator_org_id::text, supervised_org_id::text, kind, title, body, severity, due_date, source, raised_by::text
                                 FROM supervision_request WHERE reference IS NULL ORDER BY raised_at""")).mappings().all()
        for r in rows:
            issue(s, r["request_id"], regulator_org_id=r["regulator_org_id"], supervised_org_id=r["supervised_org_id"], kind=r["kind"], title=r["title"], body=r["body"],
                  severity=r["severity"], due_date=r["due_date"].isoformat() if r["due_date"] else None, source=r["source"], raised_by=r["raised_by"],
                  response_days=int((kinds().get(r["kind"]) or {}).get("default_due_days") or 20))
        s.commit()
        print(f"issued references and letters for {len(rows)} earlier requests")


if __name__ == "__main__":
    main()
