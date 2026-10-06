"""E170: GDAL is reached only through the isolated reader — a native crash reading a raster never takes the API or a
worker down. Before this, the flood and subsidence scorers (run inside the public lookup request), the EUDR forest
reader and the crop-map weight build opened rasters in-process.

Every module under api/, services/ and ml/ that imports rasterio is either the isolated reader itself or named here
with why it is safe; scripts/ run offline and are not checked."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    "services/geo/raster_sampler.py": "the isolated reader: rasterio runs only in its child process",
    "services/calibration/crop_area_weights.py": "rasterio is used only in _build, which runs in a process of its own",
    "services/ingestion/adapters/seismic_hazard.py": "called only by scripts/load_eshm20_pga.py, offline",
}
OFFLINE_DIRS = ("services/validation/validators/",)   # run only by scripts/run_validation.py, never the API or worker
_IMPORT = re.compile(r"^\s*(import rasterio|from rasterio\b)", re.M)


def _importers() -> set[str]:
    out = set()
    for top in ("api", "services", "ml", "core"):
        for f in (ROOT / top).rglob("*.py"):
            rel = f.relative_to(ROOT).as_posix()
            if _IMPORT.search(f.read_text(encoding="utf-8", errors="ignore")):
                out.add(rel)
    return out


def test_only_the_isolated_reader_and_named_offline_code_import_rasterio():
    stray = sorted(f for f in _importers() if f not in ALLOWED and not f.startswith(OFFLINE_DIRS))
    assert stray == [], f"these modules open rasters in-process — read through services.geo.raster_sampler: {stray}"


def test_the_named_exceptions_still_hold():
    found = _importers()
    for f in ALLOWED:
        assert (ROOT / f).exists(), f"{f} is allowed but no longer exists — remove it from ALLOWED"
    # crop_area_weights: its two GDAL readers are called only from _build, the function its isolated process runs
    src = (ROOT / "services/calibration/crop_area_weights.py").read_text()
    build = src[src.index("def _build("):]
    for fn in ("_map_array(", "_countries("):
        calls = [m.start() for m in re.finditer(re.escape(fn), src) if not src[max(0, m.start() - 4):m.start()].endswith("def ")]
        assert calls and all(c >= src.index("def _build(") for c in calls), f"{fn} is called outside _build"
        assert fn in build
    for f in ("services/intelligence/forest.py", "ml/scoring/flood_jrc.py", "ml/scoring/subsidence_egms.py"):
        assert f not in found, f"{f} reads rasters in-process again"
