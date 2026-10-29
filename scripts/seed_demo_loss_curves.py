"""Demo data: choose the loss engine's damage curves for every demo organisation that holds a book (the product owner's
decision of 2026-10-21) — the choices the demo insurer Alpenrück made: river flood → the JRC global damage curves
(jrc_huizinga_2017); tropical cyclone → the Eberenz 2021 curves fitted to each storm's damage (eberenz_2021_rmsf);
coastal flood → the same JRC curves, which the coastal maps' publisher applies to coastal depths (the product owner's
decision of 2026-10-25) — every coastal figure untested until the curves are tested on observed coastal losses;
European windstorm → the Prahl 2015 curve for German homes (prahl_2015_h; the product owner's decision of 2026-10-29)
— every windstorm figure untested, no open European storm-loss record being held to test it; and, for a bank or a
property trust, the building share of a stated value from official statistics (2026-10-25: Spain by province,
Germany nationally as a lower bound — services/reference/building_share.py). A choice a sector cannot make is not offered.

Each choice goes through the route the Methodology page uses (services.governance.config_governance.
submit_or_apply_config), made by the organisation's own admin: applied and audited, or opened for a second approver
where the organisation's approval matrix asks for one. An organisation that has already chosen keeps its choice. With
--run, each book's loss run for today's climate is then submitted as a background job (services.tasks.jobs 'loss.run').

Demo only — organisations whose name ends '(demo)'. Books whose assets state no building value (an asset manager's
holdings, an insurer's investments, a manufacturer's sites) get their named gaps, never a figure.

    venv/bin/python -m scripts.seed_demo_loss_curves [--run]
"""
from __future__ import annotations

import sys

from sqlalchemy import text

from core.db.session import get_session
from services.loss import curves

CHOICES = {"loss_curve_family_flood": "jrc_huizinga_2017", "loss_curve_family_storm": "eberenz_2021_rmsf",
           "loss_curve_family_coastal_flood": "jrc_huizinga_2017", "loss_curve_family_windstorm": "prahl_2015_h",
           "loss_building_share": "official_statistics"}


def books(s, org_id: str) -> list[str]:
    """The books the organisation holds: its own portfolio verticals, and its sites."""
    out = [r[0] for r in s.execute(text("""SELECT DISTINCT vertical FROM portfolio_entities
                                           WHERE org_id = CAST(:o AS uuid) AND source = 'own' ORDER BY 1"""), {"o": org_id})]
    if s.execute(text("SELECT 1 FROM sc_company_sites WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": org_id}).first():
        out.append("company_sites")
    return out


def main(run: bool = False) -> int:
    from services.calc_settings import INTERPRETATION_SCHEMA as SETTINGS
    from services.calc_settings import get_calc_settings
    from services.governance.config_governance import submit_or_apply_config
    from services.loss.engine import BOOKS
    usable = curves.families()
    missing = [v for k, v in CHOICES.items() if k.startswith("loss_curve_family_") and v not in usable]
    if missing:
        print(f"refused: {missing} are not usable families ({curves.refused()})")
        return 1
    counts = {"applied": 0, "pending_approval": 0, "kept": 0, "no_book": 0, "no_admin": 0, "runs": 0}
    with get_session() as s:
        orgs = s.execute(text("""SELECT o.org_id::text, o.name FROM organizations o WHERE o.name LIKE '%(demo)'
                                 ORDER BY o.name""")).all()
        for org_id, name in orgs:
            held = [b for b in books(s, org_id) if b in BOOKS]
            if not held:
                counts["no_book"] += 1
                continue
            admin = s.execute(text("""SELECT user_id::text FROM users WHERE org_id = CAST(:o AS uuid) AND role = 'admin'
                                      ORDER BY created_at, user_id LIMIT 1"""), {"o": org_id}).scalar()
            if admin is None:
                counts["no_admin"] += 1
                print(f"  {name}: no admin user — left without a choice")
                continue
            current = get_calc_settings(s, org_id)
            org_type = s.execute(text("SELECT type FROM organizations WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
            todo = {k: v for k, v in CHOICES.items() if not current.get(k) and org_type in SETTINGS[k]["sectors"]}
            status = "kept"
            if todo:
                status = submit_or_apply_config(s, org_id=org_id, actor_user_id=admin,
                                                request_type="config.calc_settings", updates=todo)["status"]
                print(f"  {name}: {status} {sorted(todo)} · books {held}")
            counts[status] += 1
            s.commit()
            if run and status != "pending_approval":       # a choice awaiting its second approver is not in force yet
                from services.tasks import jobs
                for b in held:
                    jobs.submit("loss.run", org_id, b, "baseline", "current")
                    counts["runs"] += 1
    print(counts)
    return 0


if __name__ == "__main__":
    sys.exit(main(run="--run" in sys.argv))
