"""Build the five lookalike customers end to end, through the door a customer uses (the product owner's decisions of
2026-10-23): each organisation and its two users (who sends, who approves), its standard file filled from
scripts/lookalike/books.py and kept as data/demo/lookalike/<firm>.xlsx, then the file sent through the intake
(services/intake/workbooks.submit) — the same checks, second-person approval and landing as any customer's, after which
the platform scores the new places and runs the losses by itself (services/intake/after_landing.py).

  python -m scripts.lookalike.build            write the files and send them (run with the background worker up:
                                               the scoring and loss jobs it queues outlive this command)
  python -m scripts.lookalike.build --files    write the files only
"""
from __future__ import annotations

import io
import json
import sys

from openpyxl import load_workbook
from sqlalchemy import text

from scripts.lookalike import books
from scripts.lookalike.places import ROOT
from scripts.seed_demo_population import TEMPLATES, upsert_user

OUT = ROOT / "data" / "demo" / "lookalike"


def filled(org_type: str, data: dict) -> bytes:
    """The sector's blank standard file with the rows under its own headers, as a customer fills it."""
    from services.intake import workbooks
    wb = load_workbook(workbooks.build(org_type))
    for tpl in workbooks.books(org_type):
        ws = wb[tpl.sheet_name]
        col = {str(c.value).removesuffix(" *"): c.column for c in ws[1]}
        for r, row in enumerate(data.get(tpl.key, []), start=2):
            for k, v in row.items():
                ws.cell(row=r, column=col[k], value=v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def organisation(s, slug: str, firm: dict) -> tuple[str, str]:
    """The firm onboarded as any client is (services/governance/tenant_provisioning.create_tenant) — no identifier it does
    not have (no LEI) — with its first admin, then a second user who approves; a firm already onboarded is reused."""
    from services.governance.tenant_provisioning import create_tenant
    name = f"{firm['name']} (demo)"
    org_id = s.execute(text("SELECT org_id::text FROM organizations WHERE name = :n"), {"n": name}).scalar()
    if org_id is None:
        org_id = create_tenant(s, actor_user_id=None, name=name, org_type=firm["type"], country=firm["country"],
                               legal_name=firm["name"], entitlements=TEMPLATES[firm["type"]][1],
                               admin_email=f"admin@{slug}.demo", admin_full_name=f"Admin ({firm['name']})",
                               admin_password="Demo!admin1")["org_id"]
    upsert_user(s, org_id, f"approver@{slug}.demo", f"Approver ({firm['name']})", "approver", "Demo!approve1")
    admin = s.execute(text("SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) AND email = :e"),
                      {"o": org_id, "e": f"admin@{slug}.demo"}).scalar()
    return org_id, admin


def main(files_only: bool = False) -> None:
    from core.db.session import get_session
    from services.intake import workbooks
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assumptions.json").write_text(json.dumps({k: {**books.FIRMS[k], "assumptions": v}
                                                     for k, v in books.ASSUMPTIONS.items()}, indent=1, ensure_ascii=False) + "\n")
    for slug, firm in books.FIRMS.items():
        data = books.rows(slug)
        raw = filled(firm["type"], data)
        path = OUT / f"{slug}_standard_file.xlsx"
        path.write_bytes(raw)
        print(f"{firm['name']}: {', '.join(f'{k} {len(v)}' for k, v in data.items())} → {path.relative_to(ROOT)}")
        if files_only:
            continue
        with get_session() as s:
            org_id, admin = organisation(s, slug, firm)
            s.commit()
            out = workbooks.submit(s, org_id, firm["type"], raw, path.name, user_id=admin, currency=firm["currency"],
                                   book_date=firm["book_date"])
            s.commit()
        for r in out["sheets"]:
            if r["state"] != "empty":
                print(f"   {r['sheet']}: {r['state']} · {r.get('n_valid')} valid · {r.get('n_error')} to fix")


if __name__ == "__main__":
    main(files_only="--files" in sys.argv)
