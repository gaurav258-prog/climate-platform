"""
Decision-rule test: should the flood model split by mechanism (riverine vs flash)?

We agreed to split a hazard into sub-models ONLY when a split measurably beats the
combined model on held-out events (criterion #3). This measures exactly that,
honestly — no re-fetch, reuses data/multievent_flood.parquet.

For each held-out flood it compares two leave-one-event-out predictions:
  combined — model trained on ALL other events (both mechanisms; today's approach)
  split    — model trained ONLY on other events of the SAME mechanism

If split wins consistently → the physics justify two models. If not → keep one
model (likely: we only have ~7-9 events per mechanism, below the ~15 floor).
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_multievent_flood import EVENTS

from ml.scoring.ensemble import EnsembleScorer

FEATS = ["precipitation_7d_mm", "soil_saturation_index", "glofas_discharge_m3s"]
MECH = {e["name"]: e["mech"] for e in EVENTS}


def _score(train, test):
    sc = EnsembleScorer(scale_pos_weight=10.0)
    sc.fit(train[FEATS].values, train.y.values.astype(int), feature_cols=FEATS)
    return (sc.score_dataframe(test[FEATS].copy())["score"] / 100.0).values


def main():
    data = pd.read_parquet("data/multievent_flood.parquet")
    data["mech"] = data.event.map(MECH)
    counts = {m: data[data.mech == m].event.nunique() for m in ("riverine", "flash")}
    print(f"events per mechanism: riverine={counts['riverine']}, flash={counts['flash']} "
          f"(decision-rule floor ≈15 each)\n")

    yc, sc_comb, ss_split = [], [], []
    print(f"{'held-out event':30s} {'mech':9s} {'combined':>9s} {'split':>7s}  winner")
    for held in data.event.unique():
        te = data[data.event == held]
        if te.y.sum() == 0:
            continue
        m = MECH[held]
        comb = _score(data[data.event != held], te)
        split = _score(data[(data.event != held) & (data.mech == m)], te)
        y = te.y.values.astype(int)
        a_c, a_s = roc_auc_score(y, comb), roc_auc_score(y, split)
        win = "split" if a_s > a_c + 0.02 else ("combined" if a_c > a_s + 0.02 else "tie")
        print(f"{held:30s} {m:9s} {a_c:>9.3f} {a_s:>7.3f}  {win}")
        yc += y.tolist(); sc_comb += comb.tolist(); ss_split += split.tolist()

    yc = np.array(yc)
    auc_c, auc_s = roc_auc_score(yc, sc_comb), roc_auc_score(yc, ss_split)
    ap_c, ap_s = average_precision_score(yc, sc_comb), average_precision_score(yc, ss_split)
    print(f"\nPOOLED   combined: AUC={auc_c:.3f} AP={ap_c:.3f}   "
          f"split: AUC={auc_s:.3f} AP={ap_s:.3f}")
    verdict = ("SPLIT wins — physics justify separate riverine/flash models"
               if auc_s > auc_c + 0.02 else
               "KEEP ONE MODEL — split does not beat combined (not enough events per mechanism yet)")
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
