"""
Backtest the impact-function PRICE-RESPONSE chain against real climate-driven events.

Scope (honest): our golden source does not yet score West-Africa cocoa or Brazil coffee
(drought/heat pending), so the hazard -> yield link is NOT yet backtestable. What IS testable
now is the ECONOMIC half of the chain (methodology §1.3-1.4): given the REALISED production
shock, does our price-response model reproduce the realised price move — and does it need the
stock-to-use amplification the methodology insists on? Answer, per event, with attribution.

Anchors are published (ICCO / ICO / trade press); see SOURCES. Run:
    .venv/bin/python scripts/backtest_supply_impact.py
"""

# name, commodity, supply_shock% (climate-driven production loss), |demand elasticity|,
# stocks-to-use% (buffer), realised price move % as (annual_avg, peak), confounders
EVENTS = [
    {
        "name": "Cocoa 2023/24 (West Africa, El Niño)", "commodity": "Cocoa",
        "supply_shock": 12.9, "elasticity": 0.20, "stock_to_use": 26.4,
        "realised": (177, 300),
        "confounders": "EUDR-supply uncertainty, black-pod/swollen-shoot disease, 45-yr-low stocks, speculative flows",
    },
    {
        "name": "Coffee 2021 (Brazil drought + July frost)", "commodity": "Arabica coffee",
        "supply_shock": 20.0, "elasticity": 0.28, "stock_to_use": 40.0,
        "realised": (44, 60),
        "confounders": "much of the frost damage hit FUTURE crops (2022/23), so the 2021 spot move understates it; shipping/logistics",
    },
]

# A qualitative third case kept OUT of the quantified fit on purpose (attribution lesson):
WHEAT_NOTE = (
    "Wheat 2010 (Russia heat/wildfire, ~30% crop loss) saw prices +~50-90%, but the move was "
    "dominated by the Russian EXPORT BAN (policy), not the yield loss alone — a textbook case for "
    "why we decompose the climate-attributable share (§4) rather than credit climate with the whole move."
)


def naive_price_move(supply_shock, elasticity):
    """Constant-elasticity: %ΔP ≈ (%ΔQ) / |η|.  (linear approximation)"""
    return supply_shock / elasticity


def main():
    print("=" * 78)
    print("IMPACT-FUNCTION BACKTEST — price-response chain (economic half only)")
    print("=" * 78)
    rows = []
    for e in EVENTS:
        naive = naive_price_move(e["supply_shock"], e["elasticity"])
        r_ann, r_peak = e["realised"]
        implied_A_ann = r_ann / naive
        implied_A_peak = r_peak / naive
        direction_ok = naive > 0 and r_ann > 0
        rows.append((e, naive, implied_A_ann, implied_A_peak))
        print(f"\n▸ {e['name']}")
        print(f"    commodity            {e['commodity']}")
        print(f"    supply shock (clim)  -{e['supply_shock']}%   |elasticity| {e['elasticity']}   stocks/use {e['stock_to_use']}%")
        print(f"    NAIVE elasticity →   +{naive:.0f}%   (constant-η prediction)")
        print(f"    REALISED             +{r_ann}% annual avg  ·  +{r_peak}% peak")
        print(f"    direction hit        {'YES' if direction_ok else 'NO'}")
        print(f"    implied amplification A = realised/naive = {implied_A_ann:.1f}× (annual) … {implied_A_peak:.1f}× (peak)")
        print(f"    confounders (non-climate): {e['confounders']}")

    print("\n" + "-" * 78)
    print("VERDICT (honest)")
    print("-" * 78)
    print("  • Direction: 2/2 correct — supply down → price up.")
    print("  • Magnitude: a CONSTANT-elasticity model is wrong, and wrong in BOTH directions:")
    c = rows[0]; cof = rows[1]
    print(f"      - Cocoa: naive +{c[1]:.0f}% vs realised +{c[0]['realised'][0]}%  →  under-predicts ~{c[2]:.0f}×.")
    print(f"        Why: stocks-to-use at {c[0]['stock_to_use']}% (45-yr low) → highly NON-LINEAR price response.")
    print(f"      - Coffee: naive +{cof[1]:.0f}% vs realised +{cof[0]['realised'][0]}%  →  OVER-predicts the 2021 spot")
    print(f"        move (A≈{cof[2]:.1f}×): stocks buffered AND the frost's damage was largely deferred to 2022/23.")
    print("  • ⇒ The stock-to-use AMPLIFICATION term (methodology §1.3) is ESSENTIAL, and it is steep:")
    print(f"        implied A ≈ {c[2]:.0f}–{c[3]:.0f}× at {c[0]['stock_to_use']}% stocks  vs  A ≈ {cof[2]:.1f}× at {cof[0]['stock_to_use']}% stocks.")
    print("        BUT two points is a DIRECTION, not a calibrated curve — a full stocks-to-use panel is needed.")
    print(f"  • Attribution: even amplified, cocoa's +{c[0]['realised'][1]}% peak is not 100% climate — EUDR/disease/")
    print("        speculation contributed; we report the climate-attributable SHARE with a band, never the whole move.")
    print(f"  • {WHEAT_NOTE}")
    print("\n  GOVERNANCE OUTCOME: the v0 flat-transmission factor is not defensible for low-stock")
    print("  regimes → adopt A(stocks-to-use); keep euro outputs as RANGES; withhold a single-number")
    print("  COGS-at-risk per commodity until it passes a multi-event, held-out calibration.")
    print("\nSOURCES: ICCO Nov-2025 bulletin & Aug-2024 revision (cocoa -12.9%, 462-489kt deficit,")
    print("  26-28% stocks/grind, 45-yr low); ICO CMR Jul-2021 (arabica +43.8%, ~20% crop, frost 20-Jul-2021);")
    print("  trade press (cocoa +177% 2024, ~$2.5k→~$12k peak). Wheat 2010: FAO/USDA + Russia export ban.")


if __name__ == "__main__":
    main()
