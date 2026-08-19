"""Seed a realistic spread of parametric triggers for the demo insurer (Iberia Mutual).

The insurer's compliance surface (Parametric triggers) reads `insurance_policy_triggers`, which ships
empty — so the page was honestly blank for the demo. This attaches index-based cover to a handful of the
insurer's real, already-scored policies, choosing attachment/exhaustion bands off each policy's LIVE
headline hazard score so the "breached now" vs "armed" split is real, not hand-set:

  * 3 policies whose current score is well above the attachment  -> breached now (partial/full payout)
  * 2 mid-band policies whose attachment sits above the current score -> armed, not yet breached

Idempotent: re-running upserts the same policies. No fabricated scores — the trigger is evaluated live by
ml/scoring/parametric_trigger.py against the same canonical_scores every other insurance view reads.

    python scripts/seed_insurance_triggers.py
"""
from sqlalchemy import text

from api.routers.insurance import _policies_with_risk
from core.db.session import get_session


def main() -> None:
    with get_session() as s:
        org = s.execute(text(
            "SELECT org_id FROM organizations WHERE type = 'insurer' ORDER BY name LIMIT 1"
        )).scalar()
        if not org:
            print("No insurer org found — nothing to seed.")
            return
        updater = s.execute(text(
            "SELECT user_id FROM users WHERE org_id = :o ORDER BY created_at LIMIT 1"
        ), {"o": org}).scalar()

        policies = [p for p in _policies_with_risk(s, org, "baseline", "current")
                    if p["headline_score"] is not None and p["headline_hazard"]]
        policies.sort(key=lambda p: -p["headline_score"])
        if len(policies) < 3:
            print("Not enough scored policies to seed triggers.")
            return

        picks: list[tuple[dict, float, float]] = []
        # breached now: top 3 — attachment ~25 below current, exhaustion just above current
        for p in policies[:3]:
            sc = p["headline_score"]
            att = max(5.0, round(sc - 25))
            exh = min(100.0, round(sc + 10))
            if exh <= att:
                exh = min(100.0, att + 15)
            picks.append((p, att, exh))
        # armed, not breached: two mid-band policies — attachment above the current score
        used = {p["policy_id"] for p, _, _ in picks}
        mids = [p for p in policies if 35 <= p["headline_score"] <= 60 and p["policy_id"] not in used][:2]
        for p in mids:
            sc = p["headline_score"]
            att = min(90.0, round(sc + 12))
            exh = min(100.0, att + 20)
            picks.append((p, att, exh))

        for p, att, exh in picks:
            s.execute(text("""
                INSERT INTO insurance_policy_triggers
                    (policy_id, hazard_type, attachment_score, exhaustion_score, updated_by, updated_at)
                VALUES (:pid, :hz, :att, :exh, :u, now())
                ON CONFLICT (policy_id) DO UPDATE
                SET hazard_type = EXCLUDED.hazard_type, attachment_score = EXCLUDED.attachment_score,
                    exhaustion_score = EXCLUDED.exhaustion_score, updated_by = EXCLUDED.updated_by, updated_at = now()
            """), {"pid": p["policy_id"], "hz": p["headline_hazard"], "att": att, "exh": exh, "u": updater})
            state = "BREACHED" if p["headline_score"] >= att else "armed"
            print(f"  {state:8s} {p['policy_name'][:34]:34s} {p['headline_hazard']:10s} "
                  f"score {p['headline_score']:5.1f}  band {att:.0f}-{exh:.0f}")
        s.commit()
        print(f"Seeded {len(picks)} parametric triggers for insurer {org}.")


if __name__ == "__main__":
    main()
