"""Write the published tropical-cyclone damage family of Eberenz, Lüthi & Bresch (2021), 'Regional tropical cyclone
impact functions for globally consistent risk assessments', Nat. Hazards Earth Syst. Sci. 21, 393–415,
doi:10.5194/nhess-21-393-2021 (CC BY 4.0) — data/reference/vulnerability/eberenz_2021_tdr.json and _rmsf.json (E171).

Transcribed from the paper: Eq. (1) (Emanuel 2011), f = vn³ / (1 + vn³), vn = max(V − Vthresh, 0) / (Vhalf − Vthresh),
Vthresh = 25.7 m/s; Vhalf per calibration region from Table A2 (page 410), column (c) TDR-optimised and column (b)
RMSF-optimised; the countries of each region from Table A1 (page 409). V is the '1 min sustained wind speed' (page 395).
The curves are aggregate: a share of total asset value, for every building use.

Usage: PYTHONPATH=. venv/bin/python -m scripts.build_eberenz_family <path to the paper's PDF>"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V_THRESH = 25.7
# Table A2, page 410: Vhalf (m/s) — (b) RMSF optimized, (c) TDR optimized
TABLE_A2 = {"NA1": (59.6, 66.3), "NA2": (86.0, 89.2), "NI": (58.7, 70.8), "OC": (49.7, 64.1), "SI": (46.8, 52.4),
            "WP1": (56.7, 66.4), "WP2": (84.7, 188.4), "WP3": (80.2, 112.8), "WP4": (135.6, 190.5)}
# Table A1, page 409: the countries of each calibration region, as the paper names them
TABLE_A1 = {
    "NA1": "Anguilla; Antigua and Barbuda; Argentina; Aruba; Bahamas; Barbados; Belize; Bermuda; Plurinational State of "
           "Bolivia; Cabo Verde; Cayman Islands; Chile; Colombia; Costa Rica; Cuba; Dominica; Dominican Republic; Ecuador; "
           "El Salvador; Falkland Islands (Malvinas); French Guiana; Grenada; Guadeloupe; Guatemala; Guyana; Haiti; "
           "Honduras; Jamaica; Martinique; Mexico; Montserrat; Nicaragua; Panama; Paraguay; Peru; Puerto Rico; Saint "
           "Helena, Ascension and Tristan da Cunha; Saint Kitts and Nevis; Saint Lucia; Saint Vincent and the Grenadines; "
           "Sint Maarten (Dutch part); Suriname; Trinidad and Tobago; Turks and Caicos Islands; Uruguay; Bolivarian "
           "Republic of Venezuela; British Virgin Islands; US Virgin Islands",
    "NA2": "Canada; United States of America",
    "NI": "Afghanistan; Armenia; Azerbaijan; Bahrain; Bangladesh; Bhutan; Djibouti; Eritrea; Ethiopia; Georgia; India; "
          "Islamic Republic of Iran; Iraq; Israel; Jordan; Kazakhstan; Kuwait; Kyrgyzstan; Lebanon; Maldives; Mongolia; "
          "Myanmar; Nepal; Oman; Pakistan; Qatar; Saudi Arabia; Somalia; Sri Lanka; Syrian Arab Republic; Tajikistan; "
          "Turkmenistan; Uganda; United Arab Emirates; Uzbekistan; Yemen",
    "OC": "American Samoa; Australia; Cook Islands; Fiji; French Polynesia; Guam; Kiribati; Marshall Islands; Federated "
          "States of Micronesia; Nauru; New Caledonia; New Zealand; Niue; Norfolk Island; northern Mariana Islands; Palau; "
          "Papua New Guinea; Pitcairn; Samoa; Solomon Islands; Timor-Leste; Tokelau; Tonga; Tuvalu; Vanuatu; Wallis and "
          "Futuna",
    "SI": "Comoros; Democratic Republic of the Congo; Eswatini; Madagascar; Malawi; Mali; Mauritius; Mozambique; South "
          "Africa; United Republic of Tanzania; Zimbabwe",
    "WP1": "Cambodia; Indonesia; Lao People's Democratic Republic; Malaysia; Thailand; Viet Nam",
    "WP2": "Philippines",
    "WP3": "Mainland China",
    "WP4": "Hong Kong; Japan; Republic of Korea; Macao; Taiwan"}
REGION_NAMES = {"NA1": "Caribbean and Mexico", "NA2": "USA and Canada", "NI": "North Indian", "OC": "Oceania",
                "SI": "South Indian", "WP1": "South East Asia", "WP2": "Philippines", "WP3": "China Mainland",
                "WP4": "North West Pacific"}
ALIASES = {"Plurinational State of Bolivia": "BO", "Bolivarian Republic of Venezuela": "VE", "Islamic Republic of Iran": "IR",
           "Republic of Korea": "KR", "Lao People's Democratic Republic": "LA", "Viet Nam": "VN",
           "United Republic of Tanzania": "TZ", "Federated States of Micronesia": "FM", "Syrian Arab Republic": "SY",
           "Democratic Republic of the Congo": "CD", "Cabo Verde": "CV", "Falkland Islands (Malvinas)": "FK",
           "Saint Helena, Ascension and Tristan da Cunha": "SH", "Sint Maarten (Dutch part)": "SX",
           "Turks and Caicos Islands": "TC", "US Virgin Islands": "VI", "British Virgin Islands": "VG",
           "northern Mariana Islands": "MP", "Hong Kong": "HK", "Macao": "MO", "Mainland China": "CN",
           "United States of America": "US", "Saint Kitts and Nevis": "KN", "Saint Lucia": "LC",
           "Saint Vincent and the Grenadines": "VC", "Antigua and Barbuda": "AG", "Wallis and Futuna": "WF",
           "Timor-Leste": "TL", "Myanmar": "MM", "Eswatini": "SZ", "Pitcairn": "PN", "Trinidad and Tobago": "TT"}


def _iso2(names: list[str]) -> dict[str, str]:
    from sqlalchemy import text

    from core.db.session import get_session
    with get_session() as s:
        ref = {r[1].strip().lower(): r[0].strip() for r in s.execute(text("SELECT iso2, name_en FROM ref_countries"))}
    out, missing = {}, []
    for n in names:
        code = ALIASES.get(n) or ref.get(n.lower())
        (out.__setitem__(n, code) if code else missing.append(n))
    if missing:
        raise SystemExit(f"names not matched to an ISO code: {missing}")
    return out


def emanuel(v: float, v_half: float) -> float:
    vn = max(v - V_THRESH, 0.0) / (v_half - V_THRESH)
    return vn ** 3 / (1 + vn ** 3)


def main(pdf: str) -> None:
    src = Path(pdf)
    held = ROOT / "data" / "datasets" / "sources" / "eberenz_2021_nhess-21-393.pdf"
    held.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, held)
    sha = hashlib.sha256(held.read_bytes()).hexdigest()
    names = {r: [n.strip() for n in TABLE_A1[r].split(";")] for r in TABLE_A1}
    codes = _iso2(sorted({n for ns in names.values() for n in ns}))
    for variant, col, label in (("tdr", 1, "(c) TDR optimized"), ("rmsf", 0, "(b) RMSF optimized")):
        curves = []
        for r, (rmsf, tdr) in TABLE_A2.items():
            vh = (rmsf, tdr)[col]
            pts = [[float(v), round(emanuel(v, vh), 6)] for v in range(0, 121)]
            curves.append({"key": f"eberenz_2021_{variant}:all:{r}", "occupancy": "*", "region": REGION_NAMES[r],
                           "countries": sorted({codes[n] for n in names[r]}), "points": pts,
                           "form": {"equation": "Emanuel (2011), Eberenz et al. (2021) Eq. (1)", "v_thresh": V_THRESH,
                                    "v_half": vh},
                           "quote": {"table": f"Table A2, Vhalf {label}, region {r}; Table A1 for its countries",
                                     "page": "410 (Table A2), 409 (Table A1)"}})
        doc = {"family": f"eberenz_2021_{variant}", "kind": "published", "peril": "storm",
               "metric": "max_sustained_wind_1min", "unit": "m/s", "damage_basis": "asset_value",
               "metric_basis": "Eberenz et al. (2021): the hazard is the '1 min sustained wind speed' at 10 m (page 395)",
               "source": {"authors": "Eberenz, S., Lüthi, S. and Bresch, D. N.", "year": 2021,
                          "title": "Regional tropical cyclone impact functions for globally consistent risk assessments",
                          "publisher": "Natural Hazards and Earth System Sciences 21, 393–415",
                          "url": "https://doi.org/10.5194/nhess-21-393-2021", "file": str(held.relative_to(ROOT)),
                          "sha256": sha},
               "licence": "CC BY 4.0 (Copernicus Publications)", "beyond_last": "hold", "curves": curves}
        out = ROOT / "data" / "reference" / "vulnerability" / f"eberenz_2021_{variant}.json"
        out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(out.name, len(curves), "regions")


if __name__ == "__main__":
    main(sys.argv[1])
