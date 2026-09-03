"""Re-fit the crop calibrations whose stored numbers have drifted from what the current ERA5 baselines + code
reproduce, then re-record their champion leave-one-out into the audit ledger so the fit table and the ledger
agree again.

A fit "drifts" when its stored r²_oos no longer matches a fresh recomputation (RECONCILE_TOL) — the baselines
or the fitting code moved since it was last written. This refresh brings the stale rows current using the SAME
canonical fitter the product uses (`services.intelligence.crop_calibration`), so nothing diverges. A refresh
can change a publish decision (a euro whose out-of-sample r² now crosses the 0.40 floor starts publishing);
those flips are printed explicitly.

    python -m scripts.refresh_drifted_fits --dry-run   # show what would change
    python -m scripts.refresh_drifted_fits             # re-fit drifted, re-record ledger
"""
from __future__ import annotations

import argparse

from core.db.session import get_session
from services.intelligence.crop_calibration import MIN_R2, fit_calibration, persist_fit
from services.validation import champion_oos as C


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with get_session() as s:
        drifted = [o for o in (C.build_result(s, f) for f in C._fits(s))
                   if o is not None and not o.reconciled and o.stored_oos is not None]
        if not drifted:
            print("no drifted fits — the fit table already matches current ERA5/code")
            return 0

        print(f"{len(drifted)} drifted fit(s) to re-fit:")
        flips = []
        for o in drifted:
            m = o.fit_meta
            fit = fit_calibration(s, source=o.source, **m)
            if fit is None:
                print(f"  {o.scope:24} could not re-fit (no panel) — skipped")
                continue
            was_pub = o.stored_oos >= MIN_R2
            now_pub = fit.r2_oos is not None and fit.r2_oos >= MIN_R2
            flip = ""
            if was_pub != now_pub:
                flip = "  ⚠ NOW PUBLISHES" if now_pub else "  ⚠ NOW HELD"
                flips.append((o.scope, was_pub, now_pub))
            print(f"  {o.scope:24} r2_oos {o.stored_oos:+.3f} → {fit.r2_oos:+.3f}"
                  f"  (r2 {fit.r2:.3f}, n={fit.n_years}){flip}")
            if not args.dry_run:
                persist_fit(s, fit, commodity=m["commodity"], origin=m["origin"], region=m["region"],
                            driver=m["driver"], spei_scale=m["spei_scale"], months=m["months"])

        if args.dry_run:
            print("\n--dry-run: nothing written")
            return 0

        # re-record champion LOO so the ledger reflects the refreshed fits (all should reconcile now)
        res = C.record_all(s, actor="scripts.refresh_drifted_fits")
        print(f"\nre-recorded ledger: {len(res['recorded'])} reconciled runs, {len(res['skipped'])} still drifted")
        if flips:
            print("publish changes:")
            for scope, was, now in flips:
                print(f"  {scope}: {'held→PUBLISHED' if now else 'published→held'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
