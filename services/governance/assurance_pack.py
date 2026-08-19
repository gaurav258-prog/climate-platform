"""Assurance evidence pack — one auditor-ready bundle, keyed to an immutable report snapshot.

CSRD requires limited (moving to reasonable) assurance. An assurer asks two things of every number:
*how was it produced* and *who could have changed it*. We already hold every primitive that answers
those — this just assembles them, indexed and hashed, around one frozen filing. No new data: the
methodology, the backtest record, the audit trail, the 4-eyes approvals, the provenance and the frozen
figures all already exist. The pack is a ZIP so it travels as a single evidence file.

Honesty carries through: the bundle ships the validation record *including* the retired price-claim and
the r² floor, and the frozen figures *including* the euro deliberately withheld where the chain isn't
validated. We hand the assurer the limits, not a laundered story.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.report_snapshots import get_snapshot

_METHODOLOGY = """# Methodology & basis of preparation

## What this pack is
An evidence bundle for the ESRS/CSRD disclosures frozen in snapshot **{report_type} v{version}** of
**{entity}**, reporting period ending **{period_end}** on basis **{scenario}/{horizon}**, materiality
threshold **{materiality}**. Generated {generated} (UTC).

## How the figures are produced
1. Each own site and each sourcing plot is geolocated and mapped to an H3 cell.
2. Per-cell physical-hazard scores are derived from satellite & agency data — Copernicus/ECMWF (EU) and
   NASA/USGS (US). Deforestation determinations use global forest-change satellite data vs the EUDR
   31-Dec-2020 cutoff.
3. Hazard is translated into euros at risk **only** through impact functions that have been back-tested
   against real historic shocks and clear the **r² >= 0.40** skill floor (a fixed honesty constant, not a
   configurable setting). Where that chain is not validated, exposure is mapped and the euro is **withheld**.

## Controls over the numbers (who could change them)
- Material edits and all deletes of sites/plots require **4-eyes approval** (maker != checker, DB-enforced).
- Every change is written to an immutable **access audit log** (actor, action, target, timestamp).
- The filed figures are **frozen as an immutable, versioned snapshot**; a correction is a new version.

## What is NOT in scope here
GHG accounting (Scope 1/2/3), pollution, circular economy, social and governance are produced by the
entity's other tools and combined into the wider CSRD statement. See the disclosed out-of-scope list.

## Contents of this pack
{contents}
"""


def build_assurance_pack(session: Session, org_id: str, snapshot_id: str) -> tuple[str, bytes] | None:
    """Return (filename, zip_bytes) for the assurance pack around a snapshot, or None if not found."""
    snap = get_snapshot(session, org_id, snapshot_id)
    if not snap:
        return None
    basis = snap["reporting_basis"]
    payload = snap["payload"]
    entity = (payload.get("entity") or {}).get("name") or "Reporting entity"
    generated = datetime.now(timezone.utc).isoformat()

    # 1. the frozen filing itself
    report = {"snapshot_id": snap["snapshot_id"], "report_type": snap["report_type"], "version": snap["version"],
              "reporting_basis": basis, "created_at": snap["created_at"], "created_by": snap["created_by"],
              "note": snap["note"], "payload": payload}

    # 2. validation / backtest record — the credibility spine (kept honest: retired price claim + r² note)
    val = [dict(r) for r in session.execute(text("""
        SELECT event, commodity, origin, hazard, passed,
               CAST(model_prod_shock_pct AS FLOAT) model_prod_shock_pct,
               CAST(observed_prod_shock_pct AS FLOAT) observed_prod_shock_pct,
               price_claim_retired, skill_note, source, impact_version, run_at
        FROM sc_model_validation ORDER BY event, origin
    """)).mappings().all()]
    for r in val:
        r["run_at"] = r["run_at"].isoformat() if r.get("run_at") else None

    # 3. audit trail for this entity
    audit = [dict(r) for r in session.execute(text("""
        SELECT a.created_at, a.action, a.target_type, a.target_id, u.full_name actor, a.detail
        FROM access_audit_log a LEFT JOIN users u ON u.user_id = a.actor_user_id
        WHERE a.org_id = :o ORDER BY a.created_at DESC LIMIT 1000
    """), {"o": org_id}).mappings().all()]
    for r in audit:
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None

    # 4. 4-eyes approvals — control evidence
    appr = [dict(r) for r in session.execute(text("""
        SELECT ar.request_type, ar.title, ar.status, ar.reason,
               mk.full_name maker, ck.full_name checker, ar.created_at, ar.decided_at
        FROM approval_requests ar
        LEFT JOIN users mk ON mk.user_id = ar.maker_user_id
        LEFT JOIN users ck ON ck.user_id = ar.checker_user_id
        WHERE ar.org_id = :o ORDER BY ar.created_at DESC LIMIT 500
    """), {"o": org_id}).mappings().all()]
    for r in appr:
        r["created_at"] = r["created_at"].isoformat() if r.get("created_at") else None
        r["decided_at"] = r["decided_at"].isoformat() if r.get("decided_at") else None

    provenance = payload.get("provenance", {})

    files = {
        "report.json": report,
        "validation_record.json": {"note": "Back-tested impact functions. A crop×origin publishes a euro "
                                    "only where it clears r²>=0.40; the price-claim column records a claim we "
                                    "retired (a supply shock explains ~r²=0.02 of contemporaneous price).",
                                    "records": val},
        "audit_trail.json": {"entries": len(audit), "records": audit},
        "approvals_4eyes.json": {"entries": len(appr), "records": appr},
        "provenance.json": provenance,
    }

    # hash each artifact for the manifest (tamper-evidence)
    blobs = {name: json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode("utf-8")
             for name, obj in files.items()}
    contents_lines = []
    manifest_files = []
    for name, blob in blobs.items():
        h = hashlib.sha256(blob).hexdigest()
        manifest_files.append({"file": name, "sha256": h, "bytes": len(blob)})
        contents_lines.append(f"- `{name}` — sha256 `{h[:16]}…`")

    methodology = _METHODOLOGY.format(
        report_type=snap["report_type"], version=snap["version"], entity=entity,
        period_end=basis.get("reporting_period_end"), scenario=basis.get("scenario"),
        horizon=basis.get("horizon"), materiality=basis.get("materiality_threshold"),
        generated=generated, contents="\n".join(contents_lines))
    method_blob = methodology.encode("utf-8")
    manifest_files.insert(0, {"file": "methodology.md", "sha256": hashlib.sha256(method_blob).hexdigest(), "bytes": len(method_blob)})

    # printable cover — a one-page summary an assurer can open/print to PDF (self-contained, no dependency)
    verified = "hash verified ✓" if snap.get("hash_verified") else "hash not verified"
    _rows = "".join(f"<tr><td>{f['file']}</td><td><code>{f['sha256'][:24]}…</code></td>"
                    f"<td style='text-align:right'>{f['bytes']:,}</td></tr>" for f in manifest_files)
    cover_html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Assurance evidence pack — {entity}</title>
<style>body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#12202f;max-width:760px;margin:40px auto;padding:0 26px;line-height:1.55}}
h1{{font-size:25px;margin:0 0 2px;letter-spacing:-.01em}}.sub{{color:#5a6b80;margin:0 0 22px;font-size:15px}}
.meta{{display:grid;grid-template-columns:180px 1fr;gap:7px 16px;font-size:13.5px;margin:18px 0;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;padding:16px 0}}
.meta b{{color:#33465e;font-weight:600}}
.gate{{background:#f2f7fc;border:1px solid #d5e3f2;border-radius:9px;padding:13px 15px;font-size:12.5px;color:#20344b;margin-top:6px}}
h3{{margin:26px 0 4px;font-size:14px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}}
th,td{{padding:7px 9px;border-bottom:1px solid #eef1f6;text-align:left}}
th{{color:#6a7a90;font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em}}
code{{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:#33465e}}
.foot{{color:#8896a8;font-size:11px;margin-top:26px}}</style></head><body>
<h1>Assurance evidence pack</h1>
<p class="sub">{entity} · {snap['report_type']} v{snap['version']}</p>
<div class="meta">
  <b>Reporting entity</b><span>{entity}</span>
  <b>Filing</b><span>{snap['report_type']} · version {snap['version']}</span>
  <b>Reporting basis</b><span>scenario {basis.get('scenario')} · horizon {basis.get('horizon')} · materiality {basis.get('materiality_threshold')} · period {basis.get('reporting_period_end')}</span>
  <b>Frozen payload hash</b><span><code>{snap.get('payload_sha256')}</code> · {verified}</span>
  <b>Pack generated</b><span>{generated}</span>
</div>
<div class="gate"><b>Honesty gate.</b> A euro is a firm figure only where the hazard→yield/asset chain clears r²&nbsp;≥&nbsp;0.40; otherwise the exposure is mapped and the euro withheld. The r² floor is a fixed constant, not a per-filing setting.</div>
<h3>Contents — every artifact hashed for tamper-evidence</h3>
<table><thead><tr><th>File</th><th>SHA-256</th><th style="text-align:right">Bytes</th></tr></thead><tbody>{_rows}</tbody></table>
<p class="foot">Tellumen assurance evidence pack. This cover summarises the bundle; every figure traces to the frozen snapshot and the artifacts above. Open in a browser and print to PDF for your working papers.</p>
</body></html>"""
    cover_blob = cover_html.encode("utf-8")
    manifest_files.insert(0, {"file": "cover.html", "sha256": hashlib.sha256(cover_blob).hexdigest(), "bytes": len(cover_blob)})

    manifest = {
        "pack": "Tellumen assurance evidence pack",
        "entity": entity, "org_id": org_id,
        "snapshot": {"id": snap["snapshot_id"], "report_type": snap["report_type"], "version": snap["version"],
                     "payload_sha256": snap.get("payload_sha256"),
                     "hash_verified": snap.get("hash_verified"),
                     "engine_versions": snap.get("engine_versions")},
        "reporting_basis": basis, "generated_at": generated,
        "honesty_gate": "A euro is a firm figure only where the hazard→yield/asset chain clears r²>=0.40; "
                        "otherwise exposure is mapped and the euro withheld. The r² floor is a fixed constant.",
        "files": manifest_files,
    }
    manifest_blob = json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("cover.html", cover_blob)
        z.writestr("manifest.json", manifest_blob)
        z.writestr("methodology.md", method_blob)
        for name, blob in blobs.items():
            z.writestr(name, blob)
    buf.seek(0)
    fname = f"assurance-pack-{snap['report_type']}-v{snap['version']}.zip"
    return fname, buf.getvalue()
