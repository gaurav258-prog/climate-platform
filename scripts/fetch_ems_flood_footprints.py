"""Copernicus EMS rapid-mapping OBSERVED flood extents — independent flood target.

For each flood event in scripts/build_multievent_flood.EVENTS that falls inside the EMS era (2012→), finds the
matching EMS activation, downloads every AOI's delineation PRODUCT vector package, and unions the
`observedEventA` polygons (the photo-interpreted / SAR-derived flooded area) into
data/flood_val/ems_<slug>.geojson. These are the official European record of what actually flooded — not our
hand-drawn corridor rectangles, and not an input to the ERA5-Land features the flood model scores from.

The EMS portal (mapping.emergency.copernicus.eu) renders its activation list client-side and its activation
pages carry no event title, so an activation id cannot be looked up by name. We therefore scan CANDIDATE ids
around a best guess and VERIFY each by evidence inside the package itself: the areaOfInterestA footprint must
sit inside the event's fetch_area and the product's file date must be within DATE_TOL days of the event peak.
Unverified candidates are discarded; a verified one is recorded with its id, AOIs and product date.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_ems_flood_footprints.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import unary_union

from scripts.build_multievent_flood import EVENTS

PORTAL = "https://mapping.emergency.copernicus.eu/activations/{id}"
OUT = Path("data/flood_val")
DATE_TOL = 45
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TellumenClimatePlatform/1.0)"}
# best-guess EMS activation numbers per event (scanned ±SPAN and verified by AOI geometry + product date)
GUESS = {
    "2013 Danube (Passau)": 44, "2014 Sava (Balkans)": 79, "2016 Seine (Paris)": 168, "2019 Spain DANA": 388,
    "2020 Storm Alex": 467, "2021 Rhine/Ahr": 517, "2023 Emilia-Romagna": 664, "2024 Storm Boris": 773,
    "2024 Valencia DANA": 777,
}
SPAN = 4
# wider scan windows where the guess is weak / the flood produced several activations
SPANS = {"2013 Danube (Passau)": (40, 50), "2014 Sava (Balkans)": (74, 86), "2016 Seine (Paris)": (160, 176),
         "2023 Emilia-Romagna": (660, 668), "2024 Storm Boris": (750, 768), "2024 Valencia DANA": (770, 778)}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


API = "https://mapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={id}"
# the public key the EMS portal's own map viewer ships with (rm-viewer bundle); metadata is public, no login
API_KEY = "ot_11c814fd6e47ddc06b0e.AK9NxXauRvC4YPgrHNBKxg"


def api_activation(emsr: str) -> dict | None:
    """Activation metadata from the portal's dashboard API (activations ≈EMSR660+ only; older ones 403)."""
    r = requests.get(API.format(id=emsr), headers={**HEADERS, "Accept": "application/json", "apikey": API_KEY}, timeout=60)
    if r.status_code != 200:
        return None
    res = r.json().get("results") or []
    return res[0] if res else None


def api_observed_layers(act: dict) -> list[str]:
    """JSON URLs of every delineation product's observedEventA layer, across all AOIs."""
    urls = []
    for aoi in act.get("aois", []):
        for pr in aoi.get("products", []):
            if pr.get("type") != "DEL":
                continue
            for layer in pr.get("layers", []):
                if "observedEventA" in (layer.get("name") or "") and layer.get("json"):
                    urls.append(layer["json"])
    return urls


def api_verify(ev: dict, act: dict) -> bool:
    from datetime import datetime
    if act.get("category") != "Flood":
        return False
    n, w, s, e = ev["fetch_area"]
    m = re.match(r"POINT \(([-\d.]+) ([-\d.]+)\)", act.get("centroid") or "")
    if not m:
        return False
    x, y = float(m.group(1)), float(m.group(2))
    t = datetime.fromisoformat(act["eventTime"][:19]).date()
    return (s <= y <= n) and (w <= x <= e) and abs((t - ev["peak"]).days) <= DATE_TOL


def product_zips(emsr: str) -> list[str]:
    r = requests.get(PORTAL.format(id=emsr), headers=HEADERS, timeout=60)
    if r.status_code != 200:
        return []
    urls = set(re.findall(r'href="(https://[^"]+_vector\.zip)"', r.text))
    # delineation products only: new scheme `_DEL_PRODUCT_`, old scheme `_DELINEATION_{DETAILxx|OVERVIEW}_`;
    # skip reference / grading / monitoring packages (they carry no observedEventA or a later state)
    keep = [u for u in urls if ("_DEL_PRODUCT_" in u or re.search(r"_DELINEATION_(DETAIL\d+|OVERVIEW)_v\d+_vector", u))]
    return sorted(keep)


def read_package(url: str) -> tuple[list, list, date | None]:
    """→ (aoi polygons, observed-event polygons, product file date) from one product vector zip."""
    r = requests.get(url, headers=HEADERS, timeout=300)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    aoi, obs, pdate = [], [], None
    for n in z.namelist():
        if not n.endswith(".json"):
            continue
        if "areaOfInterestA" in n or "observedEventA" in n:
            fc = json.loads(z.read(n))
            geoms = [shape(f["geometry"]).buffer(0) for f in fc.get("features", []) if f.get("geometry")]
            (aoi if "areaOfInterestA" in n else obs).extend(geoms)
            y, m, d = z.getinfo(n).date_time[:3]
            pdate = date(y, m, d)
    return aoi, obs, pdate


def verify(ev: dict, aoi: list, pdate: date | None) -> bool:
    if not aoi or pdate is None:
        return False
    n, w, s, e = ev["fetch_area"]
    c = unary_union(aoi).centroid
    return (s <= c.y <= n) and (w <= c.x <= e) and abs((pdate - ev["peak"]).days) <= DATE_TOL


def fetch_event(ev: dict) -> dict | None:
    """Scan the candidate range; verify EVERY package on its own AOI + date (one activation can span several AOIs,
    and one flood can have several activations — e.g. the June-2013 central-European flood); union all that pass."""
    g = GUESS.get(ev["name"])
    if g is None:
        return None
    lo, hi = SPANS.get(ev["name"], (g - SPAN, g + SPAN))
    all_obs, used, pdates = [], {}, []
    for k in range(lo, hi + 1):
        emsr = f"EMSR{k:03d}"
        act = api_activation(emsr)
        if act is not None:                       # API era: verify on metadata, read the observedEventA layer JSONs
            if not api_verify(ev, act):
                continue
            for u in api_observed_layers(act):
                try:
                    fc = requests.get(u, headers=HEADERS, timeout=120).json()
                except Exception as e:
                    print(f"    {u.rsplit('/', 1)[-1]}: {e}"); continue
                geoms = [shape(f["geometry"]).buffer(0) for f in fc.get("features", []) if f.get("geometry")]
                if geoms:
                    all_obs += geoms; used[emsr] = used.get(emsr, 0) + 1
                    pdates.append(date.fromisoformat(act["eventTime"][:10]))
            print(f"    {emsr} {act['name']} ({act['eventTime'][:10]}): {used.get(emsr, 0)} observed-event layers")
            continue
        for u in product_zips(emsr):
            try:
                aoi, obs, pdate = read_package(u)
            except Exception as e:  # one broken package must not kill the scan
                print(f"    {u.rsplit('/', 1)[-1]}: {e}"); continue
            if verify(ev, aoi, pdate) and obs:
                all_obs += obs; used[emsr] = used.get(emsr, 0) + 1; pdates.append(pdate)
    if not all_obs:
        return None
    u = unary_union(all_obs)
    return {"type": "FeatureCollection", "event": ev["name"], "emsr": "+".join(sorted(used)), "n_aoi_packages": sum(used.values()),
            "product_date": min(pdates).isoformat(), "flooded_km2": round(_km2(u), 1),
            "source": "Copernicus EMS rapid mapping, delineation product, observedEventA (official flooded area)",
            "features": [{"type": "Feature", "properties": {"emsr": "+".join(sorted(used))}, "geometry": u.__geo_interface__}]}


def _km2(geom) -> float:
    import math
    lat = geom.centroid.y
    return geom.area * (111.32 ** 2) * math.cos(math.radians(lat))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for ev in EVENTS:
        if ev["peak"] < date(2012, 1, 1) or ev["name"] not in GUESS:
            print(f"{ev['name']:30s} pre-EMS / no candidate — skipped"); continue
        out = OUT / f"ems_{slug(ev['name'])}.geojson"
        if out.exists():
            print(f"{ev['name']:30s} already landed ({out.name})"); continue
        fc = fetch_event(ev)
        if fc is None:
            lo, hi = SPANS.get(ev["name"], (GUESS[ev["name"]] - SPAN, GUESS[ev["name"]] + SPAN))
            print(f"{ev['name']:30s} NOT FOUND in EMSR{lo:03d}..EMSR{hi:03d}"); continue
        out.write_text(json.dumps(fc))
        print(f"{ev['name']:30s} {fc['emsr']}  AOIs {fc['n_aoi_packages']}  product {fc['product_date']}  "
              f"flooded {fc['flooded_km2']} km²")
    return 0


if __name__ == "__main__":
    sys.exit(main())
