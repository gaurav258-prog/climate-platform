"""Write the published European windstorm damage family of Prahl, Rybski, Burghoff & Kropp (2015), 'Comparison of storm
damage functions and their performance', Nat. Hazards Earth Syst. Sci. 15, 769–788, doi:10.5194/nhess-15-769-2015
(CC BY 3.0) — data/reference/vulnerability/prahl_2015_h.json (the product owner's decisions of 2026-10-25: model H,
the DWD row, German homes only, the printed spread as the range).

Transcribed from the paper's appendix A4 (pages 785–786): the damage of one building, Eq. (A14),
    g(v, vc) = 0 for v < vc;  ((v − vc) / H1)² for vc ≤ v ≤ vc + H1;  1 for v > vc + H1,
the buildings' critical gusts vc normal with mean µc and standard deviation H2 (Eq. A15), the loss ratio their
convolution (Eq. A16), and µc itself normal with mean H4 and standard deviation H3, whose expected loss ratio is Eq. (A17).
The parameters: Table A1 (page 786), absolute gust, row DWD, the unbracketed values (the bracketed ones are rescaled to
another source's H4): H4 = 42.3, H3 = 2.0, H2 = 6.2, H1 = 49.7 m/s.

Arithmetic, no fitting. With vc ~ N(µ, σ), c = v − µ, a = (c − H1)/σ, b = c/σ, Eq. (A16) integrates in closed form:
    L(v; µ, σ) = Φ(a) + [c²(Φ(b) − Φ(a)) − 2cσ(φ(a) − φ(b)) + σ²(Φ(b) − Φ(a) − bφ(b) + aφ(a))] / H1².
  central  Eq. (A17), the expected loss ratio over µc ~ N(H4, H3): the buildings' critical gusts are then normal with
           mean H4 and standard deviation √(H2² + H3²), so E[L](v) = L(v; H4, √(H2² + H3²))
  low      L(v; H4 + H3, H2) — the loss ratio at µc one printed standard deviation above its mean (its 15.9th percentile,
           L falling as µc rises)
  high     L(v; H4 − H3, H2) — one standard deviation below (its 84.1th percentile)
Points every 1 m/s from 0 to 120 m/s, ratios to six decimal places (as the cyclone curves).

Usage: PYTHONPATH=. venv/bin/python -m scripts.build_prahl_family <path to the paper's PDF>"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from math import erf, exp, pi, sqrt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Table A1, page 786: absolute gust, DWD, unbracketed — (H4, H3, H2, H1), m/s
H4, H3, H2, H1 = 42.3, 2.0, 6.2, 49.7
GUSTS = range(0, 121)
PLACES = 6


def _Phi(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def _phi(z: float) -> float:
    return exp(-z * z / 2.0) / sqrt(2.0 * pi)


def loss_ratio(v: float, mu: float, sigma: float, h1: float = H1) -> float:
    """Eq. (A16) in closed form: the loss ratio at gust v of buildings whose critical gusts are N(mu, sigma)."""
    c = v - mu
    a, b = (c - h1) / sigma, c / sigma
    inside = (c * c * (_Phi(b) - _Phi(a)) - 2.0 * c * sigma * (_phi(a) - _phi(b))
              + sigma * sigma * (_Phi(b) - _Phi(a) - b * _phi(b) + a * _phi(a)))
    return min(1.0, max(0.0, _Phi(a) + inside / (h1 * h1)))


def curve_points() -> tuple[list, list, list]:
    """(central, low, high) points [[gust, ratio], …]."""
    s_all = sqrt(H2 * H2 + H3 * H3)
    central = [[float(v), round(loss_ratio(v, H4, s_all), PLACES)] for v in GUSTS]
    low = [[float(v), round(loss_ratio(v, H4 + H3, H2), PLACES)] for v in GUSTS]
    high = [[float(v), round(loss_ratio(v, H4 - H3, H2), PLACES)] for v in GUSTS]
    return central, low, high


def document(sha: str, held: Path) -> dict:
    central, low, high = curve_points()
    return {
        "family": "prahl_2015_h", "kind": "published", "peril": "windstorm", "metric": "max_gust_3s_10m", "unit": "m/s",
        "damage_basis": "building",
        "metric_basis": "Prahl et al. (2015): 'daily maxima of the 3 s wind gust measured by the German weather service "
                        "DWD', measurements at other heights 'adjusted' to 10 m by the power law of Eq. (1) (page 771). The "
                        "hazard maps give each storm's highest 3-second gust at 10 m over 72 hours (one storm, read once), "
                        "where the curve was calibrated on each day's highest gust and that day's loss",
        "loss_basis": "'loss ratio (LR): the amount of insured loss per day and district, divided by the corresponding sum "
                      "of insured value' (page 771), from the German Insurance Association's (GDV) 'comprehensive "
                      "insurance on buildings' line of business, 1997–2007 (page 770): residential buildings",
        "calibrated_on": "the GDV data of all districts of Baden-Württemberg, pooled (page 786): 'we pooled the GDV data for "
                         "all districts in the state of Baden-Württemberg'",
        "source": {"authors": "Prahl, B. F., Rybski, D., Burghoff, O. and Kropp, J. P.", "year": 2015,
                   "title": "Comparison of storm damage functions and their performance",
                   "publisher": "Natural Hazards and Earth System Sciences 15, 769–788",
                   "url": "https://doi.org/10.5194/nhess-15-769-2015", "file": str(held.relative_to(ROOT)),
                   "sha256": sha},
        "licence": "CC BY 3.0 (Copernicus Publications): '© Author(s) 2015. CC Attribution 3.0 License.' (page 769)",
        "beyond_last": "hold", "spread_required": True,
        "discrepancy": "page 786 says 'only H2, which represents the wind gust range from beginning to total destruction, "
                       "shows a significant difference of approximately −15 %'; Eq. (A14) names H1 the gust range to "
                       "total destruction and Table A1's H1 column gives it (59.4 / 70.0 − 1 = −15.1 %; H2's is "
                       "7.4 / 7.8 − 1 = −5.1 %). The equations and the table agree with each other and are used; the "
                       "sentence's label is recorded here.",
        "decided": "the product owner's decisions of 2026-10-25: this curve (the DWD row), applied to residential "
                   "buildings in Germany only — the country it was calibrated in — and its printed spread as the range",
        "curves": [{
            "key": "prahl_2015_h:residential:DE", "occupancy": "residential",
            "region": "Germany (calibrated on Baden-Württemberg's districts)", "countries": ["DE"],
            "points": central,
            "range_points": {"low": low, "high": high,
                             "basis": "the loss ratio with the mean critical gust µc one printed standard deviation "
                                      "(H3 = 2.0 m/s) above (low) and below (high) its printed mean H4 — Eq. (A17)'s "
                                      "spread, read at its 15.9th and 84.1th percentiles"},
            "form": {"equation": "Prahl et al. (2015) Eqs. (A14)–(A17), model H after Heneka et al. (2006)",
                     "H4": H4, "H3": H3, "H2": H2, "H1": H1,
                     "central": "Eq. (A17): the expected loss ratio, critical gusts N(H4, √(H2² + H3²))",
                     "integration": "closed form of Eq. (A16) (scripts/build_prahl_family.py)"},
            "quote": {"table": "Table A1, absolute gust, DWD (unbracketed values); Eqs. (A14)–(A17)",
                      "page": "786 (Table A1, Eqs. A16–A17), 785 (Eqs. A14–A15)"}}]}


def main(pdf: str) -> None:
    held = ROOT / "data" / "datasets" / "sources" / "prahl_2015_nhess-15-769.pdf"
    held.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(pdf), held)
    sha = hashlib.sha256(held.read_bytes()).hexdigest()
    out = ROOT / "data" / "reference" / "vulnerability" / "prahl_2015_h.json"
    out.write_text(json.dumps(document(sha, held), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(out.name, sha)


if __name__ == "__main__":
    main(sys.argv[1])
