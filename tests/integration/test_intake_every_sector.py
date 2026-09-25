"""The same customer-file journey, run for EVERY sector template from the field catalogue — so a sector cannot quietly
fall behind. Each file is written in a 'customer layout' (our field names swapped for aliases customers use, extra
columns, different order). Runs at the service level as each sector's own admin, inside a transaction that is rolled
back; stored test files are removed afterwards.
"""
from __future__ import annotations

import os
import uuid

import pandas as pd
import pytest
from sqlalchemy import text

from core.db.session import get_session
from services.ingest.upload_validation import enrich_specs
from services.intake import mapping, pipeline, profiling, storage
from services.intake.catalog import TEMPLATES

pytestmark = pytest.mark.integration

_VOCAB_FIELD = {"bank_assets": ("minimum_safeguards_status", "Non-Compliant"), "insurance_policies": ("construction_type", "ISO 2"),
                "realestate_properties": ("epc_rating", "b"), "assetmgmt_holdings": ("minimum_safeguards_status", "compliant"),
                "supply_plots": ("irrigation_status", "rain fed")}


def _org_and_admin(s, org_type):
    return s.execute(text("""SELECT o.org_id::text, u.user_id::text FROM organizations o JOIN users u ON u.org_id = o.org_id
                             WHERE o.type = :t AND u.role = 'admin' ORDER BY o.name LIMIT 1"""), {"t": org_type}).one()


def _customer_file(key: str, tag: str, n: int = 4, value_bump: float = 0.0) -> pd.DataFrame:
    """A book in the customer's own layout: every required field under an alias (or its label), plus a value-list
    field in the customer's spelling, the customer's own ID, and a column we do not use."""
    tpl = TEMPLATES[key]
    specs = [s for s in enrich_specs(tpl.specs(pd.DataFrame())) if s.get("required") or s["name"] == "external_ref"]
    if key == "insurance_policies":
        specs.append(next(s for s in enrich_specs(tpl.specs(pd.DataFrame())) if s["name"] == "sum_insured_eur"))
    rows = []
    for i in range(n):
        r = {}
        for s in specs:
            col = (s.get("aliases") or [s["label"]])[0] if s["name"] not in ("latitude", "longitude") else {"latitude": "Lat", "longitude": "Lng"}[s["name"]]
            if s["name"] == "external_ref":
                v = f"{tag}-{i}"
            elif s["name"] == "latitude":
                v = 48.0 + i / 50
            elif s["name"] == "longitude":
                v = 2.0 + i / 50
            elif s.get("field_kind") == "name":
                v = f"TEST-EVERY-{tag}-{i}"
            elif s.get("kind") == "money":
                v = float(s["example"]) * (1 + (value_bump if i == 0 else 0))
            else:
                v = s["example"]
            r[col] = v
        vf, vv = _VOCAB_FIELD[key]
        r["Their " + vf] = vv
        r["Internal notes"] = "not used"
        rows.append(r)
    return pd.DataFrame(rows)


def _csv(df):
    return df.to_csv(index=False).encode()


@pytest.fixture()
def session_rolled_back():
    shas = []
    real_put = storage.put

    def tracking_put(raw):
        out = real_put(raw)
        shas.append(out[0])
        return out
    storage.put = tracking_put
    import services.tasks.jobs as jobs
    real_submit = jobs.submit
    jobs.submit = lambda *a, **k: {"job": "stubbed-in-test"}
    with get_session() as s:
        try:
            yield s
        finally:
            s.rollback()
            storage.put, jobs.submit = real_put, real_submit
    for sha in set(shas):
        with get_session() as s:
            if not s.execute(text("SELECT 1 FROM intake_files WHERE sha256 = :h"), {"h": sha}).first():
                try:
                    os.remove(storage._path_for(sha))
                except OSError:
                    pass


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_customer_layout_is_proposed_confirmed_then_reused_automatically(key, session_rolled_back):
    s, tpl, tag = session_rolled_back, TEMPLATES[key], uuid.uuid4().hex[:8]
    org_id, user_id = _org_and_admin(s, tpl.org_type)
    df = _customer_file(key, tag)

    # 1. the file is not in our layout: the answer carries a proposal for every required field
    with pytest.raises(pipeline.IntakeError) as e:
        pipeline.preview(s, org_id, key, _csv(df), f"{tag}.csv")
    body = e.value.body
    assert body["error"] == "missing_columns"
    proposal = profiling.column_map(body["suggestion"])
    required = [x["name"] for x in tpl.specs(pd.DataFrame()) if x.get("required")]
    assert set(required) <= set(proposal), f"{key}: no proposal for {set(required) - set(proposal)}"
    vf, _ = _VOCAB_FIELD[key]
    cmap = {**proposal, vf: "Their " + vf}

    # 2. the customer confirms it (saved with the layout), and the file imports through it — value spelling matched
    prof = mapping.save(s, org_id, key, f"Every-sector {tag}", cmap, {}, user_id, enrich_specs(tpl.specs(pd.DataFrame())),
                        source_columns=list(df.columns))
    out = pipeline.submit(s, org_id, key, _csv(df), f"{tag}-1.csv", user_id=user_id, mapping_profile_id=prof["profile_id"])
    assert out["state"] == "imported", out.get("controls", {}).get("gate")
    assert out["controls"]["matching"]["new"] == 4 and out["controls"]["values"][vf]["n_unknown"] == 0
    assert out["mapping"]["auto"] is False

    # 3. next month's file, same layout, no mapping chosen: used automatically; one value changed → one update
    df2 = _customer_file(key, tag, value_bump=0.1)
    out2 = pipeline.submit(s, org_id, key, _csv(df2), f"{tag}-2.csv", user_id=user_id)
    assert out2["state"] == "imported", out2.get("controls", {}).get("gate")
    assert out2["mapping"]["auto"] is True and out2["mapping"]["profile_id"] == prof["profile_id"]
    m = out2["controls"]["matching"]
    assert (m["new"], m["update"], m["unchanged"]) == (0, 1, 3)


@pytest.mark.parametrize("key", sorted(TEMPLATES))
def test_unrecognised_values_are_reported_never_silently_blanked(key, session_rolled_back):
    s, tpl, tag = session_rolled_back, TEMPLATES[key], uuid.uuid4().hex[:8]
    org_id, _ = _org_and_admin(s, tpl.org_type)
    df = _customer_file(key, tag)
    vf, _ = _VOCAB_FIELD[key]
    df.loc[0, "Their " + vf] = "Something else"
    cmap = {**profiling.column_map(profiling.suggest(s, df, enrich_specs(tpl.specs(df)))), vf: "Their " + vf}
    prof = {"profile_id": "p", "name": "t", "version": 1, "column_map": cmap, "transforms": {}}
    canon, _ = mapping.apply(s, df, prof)
    ctl = pipeline._run_controls(s, org_id, tpl, uuid.uuid4().hex, canon, None)
    v = ctl["controls"]["values"][vf]
    assert v["n_unknown"] == 1 and v["unknown"] == {"Something else": 1}
    assert ctl["controls"]["gate"]["status"] == "needs_signoff"
    assert any(r.startswith("Values:") and "Something else" in r for r in ctl["controls"]["gate"]["reasons"])


def test_our_own_template_workbook_uploads_as_is():
    """The downloadable template marks required columns 'name *'; a filled-in template must be read as-is."""
    df = pipeline._parse(b"asset_name *,latitude *, region\nA,1,x\n", "csv", "upload")
    assert list(df.columns) == ["asset_name", "latitude", "region"]
