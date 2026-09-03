"""Record the INDEPENDENT challenger's out-of-sample skill into the audit ledger — one `loo_cv_challenger`
run per published crop fit, each with an agree/partial/diverge verdict vs the OLS champion, out-of-sample.

    python -m scripts.record_challenger_oos            # record every reconstructable fit
    python -m scripts.record_challenger_oos --dry-run  # compute + print, write nothing
"""
from __future__ import annotations

import argparse

from core.db.session import get_session
from services.validation import challenger_oos as CH
from services.validation.champion_oos import _fits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with get_session() as s:
        if args.dry_run:
            rows = [CH.build_result(s, f) for f in _fits(s)]
            rows = [r for r in rows if r is not None]
            agree = sum(1 for r in rows if r["verdict"] == "agree")
            print(f"reconstructed {len(rows)} challengers · {agree} agree (dry-run, nothing written):")
            for r in sorted(rows, key=lambda x: x["champ_oos"] or -9, reverse=True):
                print(f"  {r['scope']:24} champ_oos={r['champ_oos']} chal_oos={r['chal_oos']} "
                      f"· {r['verdict']} (div {r['mad']}pp/tol {r['tol']}pp)")
            return 0
        results = CH.record_all(s, actor="scripts.record_challenger_oos")
        vc = {v: sum(1 for r in results if r["verdict"] == v) for v in ("agree", "partial", "diverge")}
        pub = [r for r in results if r["champ_pub"]]
        corrob = sum(1 for r in pub if r["chal_pub"])
        print(f"recorded {len(results)} challenger LOO runs · path: agree {vc['agree']} / partial {vc['partial']}"
              f" / diverge {vc['diverge']}")
        print(f"publish corroboration: challenger independently clears the gate for {corrob}/{len(pub)} "
              f"published crops")
        for r in sorted(results, key=lambda x: x["champ_oos"] or -9, reverse=True):
            tag = ("  ✓ corroborated" if r["champ_pub"] and r["chal_pub"]
                   else "  · champion retained (challenger weaker OOS)" if r["champ_pub"] else "")
            print(f"  {r['scope']:24} champ_oos={r['champ_oos']} chal_oos={round(r['chal_oos'],3)} "
                  f"· {r['verdict']}{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
