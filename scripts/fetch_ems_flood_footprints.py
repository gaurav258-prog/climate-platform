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
Each observed layer must also be the product's own (E172): its file names the activation and AOI it is listed
under and its polygons lie inside that product's outline — the catalogue once listed another activation's layer (a
Bolivian flood) under Storm Boris. Accepted layers and refused ones (with the reason) are recorded in the file, with
the mapped area: the union of the accepted products' own outlines — where EMS looked. Outside it a place was not
observed, so it is neither flooded nor dry.
Usage: PYTHONPATH=. .venv/bin/python scripts/fetch_ems_flood_footprints.py [--refetch "<event name>"]
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
from shapely import wkt
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


def api_observed_layers(act: dict) -> list[dict]:
    """Every delineation product's observedEventA layer, across all AOIs: its JSON URL with the activation, AOI number
    and product outline (WKT) it is listed under — the evidence `layer_refusal` checks it against."""
    out = []
    for aoi in act.get("aois", []):
        for pr in aoi.get("products", []):
            if pr.get("type") != "DEL":
                continue
            for layer in pr.get("layers", []):
                if "observedEventA" in (layer.get("name") or "") and layer.get("json"):
                    out.append({"url": layer["json"], "emsr": pr.get("activationCode") or act.get("code"),
                                "aoi": pr.get("aoiNumber", aoi.get("number")), "extent": pr.get("extent") or aoi.get("extent")})
    return out


INSIDE_MIN = 0.99     # share of a layer's flooded area that must lie inside the product outline it is listed under


def layer_refusal(layer: dict, geoms: list) -> str | None:
    """Why a listed observedEventA layer is not this product's own observation, or None when it is (E172). The EMS
    catalogue can list a layer of another activation under a product (EMSR756 AOI02 listed EMSR765_AOI01's file — a
    flood in Bolivia), so a layer is accepted only when its file names the activation and AOI it is listed under AND
    its polygons lie inside that product's outline."""
    from shapely import wkt
    name = layer["url"].rsplit("/", 1)[-1]
    own = f"{layer['emsr']}_AOI{int(layer['aoi']):02d}_"
    if not name.startswith(own):
        return f"listed under {own.rstrip('_')} but the file is {name}"
    if not layer.get("extent"):
        return f"{name}: the product states no outline to check the polygons against"
    if not geoms:
        return None
    u = unary_union(geoms)
    inside = u.intersection(wkt.loads(layer["extent"]).buffer(0)).area / u.area if u.area else 1.0
    if inside < INSIDE_MIN:
        return f"{name}: only {inside:.1%} of its flooded area lies inside the product outline it is listed under"
    return None


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
    all_obs, used, pdates, layers, refused, mapped = [], {}, [], [], [], []
    for k in range(lo, hi + 1):
        emsr = f"EMSR{k:03d}"
        act = api_activation(emsr)
        if act is not None:                       # API era: verify on metadata, read the observedEventA layer JSONs
            if not api_verify(ev, act):
                continue
            for lay in api_observed_layers(act):
                name = lay["url"].rsplit("/", 1)[-1]
                try:
                    fc = requests.get(lay["url"], headers=HEADERS, timeout=120).json()
                except Exception as e:
                    print(f"    {name}: {e}"); continue
                geoms = [shape(f["geometry"]).buffer(0) for f in fc.get("features", []) if f.get("geometry")]
                why = layer_refusal(lay, geoms)
                if why:
                    refused.append({"emsr": lay["emsr"], "aoi": lay["aoi"], "file": name, "reason": why})
                    print(f"    refused — {why}"); continue
                if geoms:
                    all_obs += geoms; used[emsr] = used.get(emsr, 0) + 1
                    layers.append({"emsr": lay["emsr"], "aoi": lay["aoi"], "file": name})
                    mapped.append(wkt.loads(lay["extent"]).buffer(0))
                    pdates.append(date.fromisoformat(act["eventTime"][:10]))
            print(f"    {emsr} {act['name']} ({act['eventTime'][:10]}): {used.get(emsr, 0)} observed-event layers")
            continue
        for u in product_zips(emsr):
            name = u.rsplit("/", 1)[-1]
            try:
                aoi, obs, pdate = read_package(u)
            except Exception as e:  # one broken package must not kill the scan
                print(f"    {name}: {e}"); continue
            if not (verify(ev, aoi, pdate) and obs):
                continue
            o = unary_union(obs)
            inside = o.intersection(unary_union(aoi)).area / o.area if o.area else 1.0
            if inside < INSIDE_MIN:              # the same rule as the API era: the observation lies in its own AOI
                refused.append({"emsr": emsr, "file": name,
                                "reason": f"only {inside:.1%} of its flooded area lies inside the package's own AOI"})
                continue
            all_obs += obs; used[emsr] = used.get(emsr, 0) + 1; pdates.append(pdate)
            layers.append({"emsr": emsr, "file": name})
            mapped += aoi
    if not all_obs:
        return None
    u = unary_union(all_obs)
    area = unary_union(mapped)
    return {"type": "FeatureCollection", "event": ev["name"], "emsr": "+".join(sorted(used)), "n_aoi_packages": sum(used.values()),
            "product_date": min(pdates).isoformat(), "flooded_km2": round(_km2(u), 1), "mapped_km2": round(_km2(area), 1),
            "source": "Copernicus EMS rapid mapping, delineation product, observedEventA (official flooded area)",
            "layers": layers, "refused": refused,
            # the areas EMS actually mapped (each accepted product's own outline): outside them nothing was observed
            "mapped_area": area.__geo_interface__,
            "features": [{"type": "Feature", "properties": {"emsr": "+".join(sorted(used))}, "geometry": u.__geo_interface__}]}


def _km2(geom) -> float:
    import math
    lat = geom.centroid.y
    return geom.area * (111.32 ** 2) * math.cos(math.radians(lat))


def main(refetch: set[str] = frozenset()) -> int:
    """Fetch every EMS-era event not yet landed; `--refetch "<event name>"` rebuilds the named events only."""
    OUT.mkdir(parents=True, exist_ok=True)
    for ev in EVENTS:
        if refetch and ev["name"] not in refetch:
            continue
        if ev["peak"] < date(2012, 1, 1) or ev["name"] not in GUESS:
            print(f"{ev['name']:30s} pre-EMS / no candidate — skipped"); continue
        out = OUT / f"ems_{slug(ev['name'])}.geojson"
        if out.exists() and ev["name"] not in refetch:
            print(f"{ev['name']:30s} already landed ({out.name})"); continue
        fc = fetch_event(ev)
        if fc is None:
            lo, hi = SPANS.get(ev["name"], (GUESS[ev["name"]] - SPAN, GUESS[ev["name"]] + SPAN))
            print(f"{ev['name']:30s} NOT FOUND in EMSR{lo:03d}..EMSR{hi:03d}"); continue
        out.write_text(json.dumps(fc))
        print(f"{ev['name']:30s} {fc['emsr']}  AOIs {fc['n_aoi_packages']}  product {fc['product_date']}  "
              f"flooded {fc['flooded_km2']} km²  refused {len(fc['refused'])}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main({args[i + 1] for i, a in enumerate(args) if a == "--refetch" and i + 1 < len(args)}))
