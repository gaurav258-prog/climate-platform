"""Build the sector energy-intensity table used to ESTIMATE a company's energy consumption intensity (SFDR PAI 6)
when neither the company nor a data vendor gives it.

    intensity (GWh per €M revenue) = energy consumed by the activity, EU-27 (TJ ÷ 3.6)  ÷  its net turnover, EU-27 (€M)

  energy consumed = fuels and other energy products BURNED by the activity (Eurostat PEFA env_ac_pefasu, "emission-
                    relevant use", all energy products — fossil and biomass) + ELECTRICITY and HEAT it uses (PEFA "use",
                    P26 + P27). Energy products transformed rather than burned (crude oil into a refinery) are not
                    consumption and are left out — the same boundary ESRS E1-5 draws.
  net turnover    = Eurostat structural business statistics sbs_ovw_act (NETTUR_MEUR), the activity's divisions summed;
                    agriculture (not in SBS) uses its output at current prices (nama_10_a64 P1).

Kept at the finest level PEFA publishes (divisions or groups of them — steel C24 is not software J62), for the
high-climate-impact sections of RTS (EU) 2022/1288 (A–H, L) and M as the EET lists it. Every input is kept per row.
    python -m scripts.build_nace_energy_intensity
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import requests

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "nace_energy_intensity.csv"
SECTIONS = "ABCDEFGHLM"
YEARS = (2022, 2021, 2020)
SOURCE = ("Eurostat PEFA env_ac_pefasu (EU27_2020; ER_USE of P00 + USE of P26, P27) ÷ Eurostat SBS sbs_ovw_act "
          "NETTUR_MEUR (agriculture: nama_10_a64 P1)")


def _series(dataset: str, **params) -> dict[str, float]:
    """{nace_code: value} for one Eurostat query with every dimension fixed except nace_r2."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    d = requests.get(f"{API}{dataset}?format=JSON&lang=en&{q}", timeout=180).json()
    if "dimension" not in d:
        return {}
    idx = d["dimension"]["nace_r2"]["category"]["index"]
    pos = d["id"].index("nace_r2")
    stride = 1
    for s in d["size"][pos + 1:]:
        stride *= s
    out = {}
    for code, i in idx.items():
        v = d["value"].get(str(i * stride))
        if v is not None:
            out[code] = float(v)
    return out


def _divisions(code: str) -> list[str]:
    """PEFA activity code → the NACE divisions it covers: 'C10-C12' → C10,C11,C12; 'C31_C32'; 'L68A' → L68; 'D' → D."""
    code = code.replace("L68A", "L68")
    parts = []
    for chunk in code.split("_"):
        m = re.fullmatch(r"([A-U])(\d{2})-(?:[A-U])?(\d{2})", chunk)
        if m:
            parts += [f"{m.group(1)}{n:02d}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        else:
            parts.append(chunk)
    return parts


def build() -> int:
    for year in YEARS:
        burned = _series("env_ac_pefasu", geo="EU27_2020", time=year, unit="TJ", stk_flow="ER_USE", prod_nrg="P00")
        if burned:
            break
    else:
        raise SystemExit("no PEFA data for the recent years")
    elec = _series("env_ac_pefasu", geo="EU27_2020", time=year, unit="TJ", stk_flow="USE", prod_nrg="P26")
    heat = _series("env_ac_pefasu", geo="EU27_2020", time=year, unit="TJ", stk_flow="USE", prod_nrg="P27")
    turnover = _series("sbs_ovw_act", geo="EU27_2020", time=year, indic_sbs="NETTUR_MEUR")
    output = _series("nama_10_a64", geo="EU27_2020", time=year, unit="CP_MEUR", na_item="P1")
    rows = []
    for code in sorted(burned):
        sec = code[0]
        if sec not in SECTIONS or code in ("TOTAL",) or "-U" in code:
            continue
        divs = _divisions(code)
        src = output if sec == "A" else turnover
        vals = [src.get(d) for d in divs]
        if any(v is None for v in vals) or not sum(vals):
            continue
        tj = burned[code] + elec.get(code, 0.0) + heat.get(code, 0.0)
        rev = sum(vals)
        rows.append([code, sec, ";".join(divs), round(tj, 1), round(rev, 1), round(tj / 3.6 / rev, 5), year, SOURCE])
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nace_code", "section", "divisions", "energy_tj", "turnover_meur", "intensity_gwh_per_meur", "year", "source"])
        w.writerows(rows)
    print(f"wrote {len(rows)} activities ({year}) → {OUT}")
    return len(rows)


if __name__ == "__main__":
    build()
