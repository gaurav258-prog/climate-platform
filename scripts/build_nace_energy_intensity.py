"""Build the sector energy-intensity tables used to ESTIMATE a company's energy consumption intensity (SFDR PAI 6) when
neither the company nor a data vendor gives it.

    intensity (GWh per €M revenue) = energy the activity consumed (TJ ÷ 3.6) ÷ its net turnover (€M)

  energy consumed = fuels and other energy products BURNED by the activity (Eurostat PEFA env_ac_pefasu, "emission-
                    relevant use", all energy products — fossil and biomass) + ELECTRICITY and HEAT it used (PEFA "use",
                    P26 + P27). Products transformed rather than burned (crude oil into a refinery) are not consumption
                    and are left out — the boundary ESRS E1-5 draws.
  net turnover    = Eurostat structural business statistics sbs_ovw_act (NETTUR_MEUR); agriculture (not in SBS) uses
                    its output at current prices (nama_10_a64 P1).

One method for every activity: the national figures of every country reporting to Eurostat that publishes ALL the parts
for it (fuel burned, electricity, turnover; heat where published) are summed — Σ energy ÷ Σ turnover — and the countries
used are recorded. No country list is assumed: whoever reports is used. (Eurostat's own European total of electricity
and heat is withheld below section level, which is why it is rebuilt from the national figures.)

  nace_energy_intensity.csv             the European figure per activity (section, division or Eurostat group of
                                        divisions); an activity resting on fewer than MIN_COUNTRIES is marked thin
  nace_energy_intensity_by_country.csv  each country's own figure per activity — so a company is estimated at its own
                                        country's intensity where that country reports it (≥ €1bn of turnover there)

Activities are the high-climate-impact sections of RTS (EU) 2022/1288 (A–H, L) and M as the EET lists it; divisions are
resolved by the platform's NACE reference (services/reference/nace.py). Every input is kept per row.
    python -m scripts.build_nace_energy_intensity
"""
from __future__ import annotations

import csv
from pathlib import Path

import requests

from services.reference import nace
from services.reference.iso_country import EU_TO_ISO  # one alias table

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
REF = Path(__file__).resolve().parent.parent / "data" / "reference"
OUT, OUT_COUNTRY = REF / "nace_energy_intensity.csv", REF / "nace_energy_intensity_by_country.csv"
SECTIONS = "ABCDEFGHLM"
YEARS = (2022, 2021, 2020)
MIN_COUNTRIES = 10                    # a European figure from fewer reporting countries is marked thin
MIN_COUNTRY_TURNOVER_MEUR = 1000.0    # a national figure is kept only for an activity of at least €1bn turnover there
SOURCE = ("Eurostat PEFA env_ac_pefasu (ER_USE of P00 + USE of P26, P27) ÷ Eurostat SBS sbs_ovw_act NETTUR_MEUR "
          "(agriculture: nama_10_a64 P1); national figures summed over the countries publishing every part")


def _by_country(dataset: str, **params) -> dict[tuple[str, str], float]:
    """{(geo, nace_code): value} for every single-country geo Eurostat returns (aggregates like EU27_2020 dropped)."""
    q = "&".join(f"{k}={v}" for k, v in params.items())
    d = requests.get(f"{API}{dataset}?format=JSON&lang=en&{q}", timeout=300).json()
    if "dimension" not in d:
        return {}
    ids, size = d["id"], d["size"]
    cats = {k: list(d["dimension"][k]["category"]["index"]) for k in ids}
    strides = [1] * len(size)
    for i in range(len(size) - 2, -1, -1):
        strides[i] = strides[i + 1] * size[i + 1]
    gi, ni = ids.index("geo"), ids.index("nace_r2")
    out = {}
    for flat, v in d["value"].items():
        n, pos = int(flat), []
        for s in strides:
            pos.append(n // s)
            n %= s
        geo = cats["geo"][pos[gi]]
        if len(geo) == 2:
            out[(EU_TO_ISO.get(geo, geo), cats["nace_r2"][pos[ni]])] = float(v)
    return out


def build() -> int:
    for year in YEARS:
        burn = _by_country("env_ac_pefasu", time=year, unit="TJ", stk_flow="ER_USE", prod_nrg="P00")
        if burn:
            break
    else:
        raise SystemExit("no PEFA data for the recent years")
    elec = _by_country("env_ac_pefasu", time=year, unit="TJ", stk_flow="USE", prod_nrg="P26")
    heat = _by_country("env_ac_pefasu", time=year, unit="TJ", stk_flow="USE", prod_nrg="P27")
    turn = _by_country("sbs_ovw_act", time=year, indic_sbs="NETTUR_MEUR")
    outp = _by_country("nama_10_a64", time=year, unit="CP_MEUR", na_item="P1")
    codes = sorted({c for _, c in burn if c[:1] in SECTIONS and "-U" not in c and c != "TOTAL"})
    geos = sorted({g for g, _ in burn})
    rows, country_rows = [], []
    for code in codes:
        divs = nace.divisions_in(code)
        if not divs:
            continue
        sec, src = code[0], (outp if code[0] == "A" else turn)
        tj = rev = 0.0
        used = []
        for g in geos:
            b, e = burn.get((g, code)), elec.get((g, code))
            # a section's turnover as Eurostat publishes it; a division / group of divisions as the sum of its divisions
            t_g = [src.get((g, code))] if code == sec else [src.get((g, d)) for d in divs]
            if b is None or e is None or any(v is None for v in t_g) or not sum(t_g):
                continue
            tj_g, rev_g = b + e + heat.get((g, code), 0.0), sum(t_g)
            tj, rev = tj + tj_g, rev + rev_g
            used.append(g)
            if rev_g >= MIN_COUNTRY_TURNOVER_MEUR:
                country_rows.append([g, code, sec, ";".join(divs), round(tj_g, 1), round(rev_g, 1), round(tj_g / 3.6 / rev_g, 5), year])
        if used:
            rows.append([code, sec, ";".join(divs), round(tj, 1), round(rev, 1), round(tj / 3.6 / rev, 5), year,
                         len(used), ";".join(used), "yes" if len(used) < MIN_COUNTRIES else "", SOURCE])
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["nace_code", "section", "divisions", "energy_tj", "turnover_meur", "intensity_gwh_per_meur", "year",
                    "n_countries", "countries", "thin", "source"])
        w.writerows(rows)
    with OUT_COUNTRY.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country_iso2", "nace_code", "section", "divisions", "energy_tj", "turnover_meur", "intensity_gwh_per_meur", "year"])
        w.writerows(country_rows)
    print(f"wrote {len(rows)} activities and {len(country_rows)} country × activity figures ({year})")
    return len(rows)


if __name__ == "__main__":
    build()
