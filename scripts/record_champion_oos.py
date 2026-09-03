"""Record the euro champion's leave-one-out out-of-sample skill into the audit ledger — one immutable
`validation_run` row per published crop fit, each reconciled against the number the product publishes on.

    python -m scripts.record_champion_oos            # record every reconstructable fit
    python -m scripts.record_champion_oos --dry-run  # reconcile + print, write nothing
"""
from __future__ import annotations

import argparse

from core.db.session import get_session
from services.validation import champion_oos as C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="reconcile and print without recording")
    args = ap.parse_args()

    with get_session() as s:
        if args.dry_run:
            outs = [C.build_result(s, f) for f in C._fits(s)]
            outs = [o for o in outs if o is not None]
            ok = [o for o in outs if o.reconciled]
            drift = [o for o in outs if not o.reconciled]
            print(f"reconstructed {len(outs)} champion fits · {len(ok)} reconciled · {len(drift)} drifted "
                  f"(dry-run, nothing written):")
            for o in drift:
                flip = " ⚠ PUBLISH-FLIP" if o.publish_flip else ""
                print(f"  DRIFT  {o.scope:24} stored={o.stored_oos} recomputed={o.recomputed_oos} "
                      f"gap={o.gap:.3f}{flip}")
            return 0
        res = C.record_all(s, actor="scripts.record_champion_oos")
        recorded, skipped = res["recorded"], res["skipped"]
        passed = sum(1 for r in recorded if r["passed_gate"])
        print(f"recorded {len(recorded)} reconciled champion LOO runs · {passed} clear the r²≥0.40 OOS gate "
              f"· {len(skipped)} skipped (drifted, not recorded)")
        for r in sorted(recorded, key=lambda x: x["metrics"].get("r2_oos") or -9, reverse=True):
            m = r["metrics"]
            print(f"  {r['scope']:26} r2_oos={m.get('r2_oos')} · gate {'PASS' if r['passed_gate'] else 'held'} "
                  f"· n={r['n']}")
        for sk in skipped:
            flip = " ⚠ PUBLISH-FLIP" if sk["publish_flip"] else ""
            print(f"  SKIP {sk['scope']:24} stored={sk['stored_oos']} recomputed={sk['recomputed_oos']}{flip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
