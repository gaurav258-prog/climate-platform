"""Observed flood damage for testing damage curves (E171): OpenFEMA NFIP Redacted Claims v3 (data/loss_val/nfip,
data/loss_val/MANIFEST.md), prepared once into data/datasets/nfip_curves/claims.parquet with every row set aside
counted by reason.

Field meanings as FEMA's data dictionary states them (https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3):
  waterDepth             "Depth of flood water in inches. Note: there are instances where measurements were provided
                         in feet." — the unit of a given row cannot be told from the row, so it is kept as published and
                         the ambiguity is tested in the calculation, never resolved by a guess here
  buildingDamageAmount   "The actual cash value amount of damage to a main property in whole dollars."
  buildingPropertyValue  "The actual cash value of the main building prior to any flooding event in whole dollars as
                         estimated by an adjuster." — so damage_ratio = damage / value is a share on one basis
  floodWaterDuration     "Number of hours flood water remained in the insured building"
  latitude / longitude   "to 1 decimal place … lessened to ensure individual privacy" (about 11 km): a claim cannot be
                         placed on a 90 m depth map, so curves are tested on the claim's own recorded depth
FEMA: "This dataset is not intended to be an official federal report"; quoting results to customers waits on counsel
(docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md #8)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from services.loss import registry

SRC = registry.ROOT / "data" / "loss_val" / "nfip" / "NfipClaimsV3.parquet"
OUT = registry.ROOT / "data" / "datasets" / "nfip_curves" / "claims.parquet"
COLUMNS = ["id", "dateOfLoss", "floodEvent", "eventDesignationNumber", "state", "latitude", "longitude", "occupancyType",
           "numberOfFloorsInTheInsuredBuilding", "elevatedBuildingIndicator", "basementEnclosureCrawlspaceType",
           "causeOfDamage", "waterDepth", "exteriorWaterDepth", "interiorWaterDepth", "floodWaterDuration",
           "buildingDamageAmount", "buildingPropertyValue"]


def prepare() -> dict:
    """Write the prepared claims and return {rows_in, kept, set_aside: {reason: n}, file, sha256}."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    t = pq.read_table(SRC, columns=COLUMNS)
    rows_in = t.num_rows
    reasons = {
        "no recorded water depth": pc.is_null(t["waterDepth"]),
        "no building value (actual cash value missing or not above zero)":
            pc.fill_null(pc.less_equal(t["buildingPropertyValue"], 0), True),
        "no building damage amount": pc.is_null(t["buildingDamageAmount"]),
        "negative building damage amount": pc.fill_null(pc.less(t["buildingDamageAmount"], 0), False),
    }
    set_aside, drop = {}, None
    for why, mask in reasons.items():
        new = mask if drop is None else pc.and_(mask, pc.invert(drop))
        set_aside[why] = int(pc.sum(pc.cast(new, pa.int64())).as_py() or 0)
        drop = mask if drop is None else pc.or_(drop, mask)
    kept = t.filter(pc.invert(drop))
    ratio = pc.divide(pc.cast(kept["buildingDamageAmount"], pa.float64()), pc.cast(kept["buildingPropertyValue"], pa.float64()))
    over = pc.greater(ratio, 1.0)
    set_aside["damage above the building's value (ratio over 1)"] = int(pc.sum(pc.cast(over, pa.int64())).as_py() or 0)
    keep = pc.invert(over)
    kept = kept.filter(keep).append_column("damage_ratio", ratio.filter(keep))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".part.parquet")
    pq.write_table(kept, tmp)
    tmp.replace(OUT)
    out = {"rows_in": rows_in, "kept": kept.num_rows, "set_aside": set_aside, "file": str(OUT.relative_to(registry.ROOT)),
           "bytes": OUT.stat().st_size, "sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
           "source": str(SRC.relative_to(registry.ROOT)),
           "source_sha256": hashlib.sha256(SRC.read_bytes()).hexdigest()}
    assert out["kept"] + sum(set_aside.values()) == rows_in, "every claim is either kept or set aside with a reason"
    from scripts.fetch_supply_datasets import record as record_entry
    record_entry("nfip_curve_claims", {"source": "OpenFEMA NFIP Redacted Claims v3, prepared by services.loss.claims",
                                       "url": "https://www.fema.gov/openfema-data-page/nfip-redacted-claims-v3",
                                       "terms": "This dataset is not intended to be an official federal report (FEMA)",
                                       **out})
    return out


def manifest() -> dict:
    return json.loads((registry.ROOT / "data" / "reference" / "supply_datasets.json").read_text()).get("nfip_curve_claims", {})


def held() -> bool:
    return Path(OUT).exists()
