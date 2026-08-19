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


# ── Data-lineage graph (self-contained HTML) ────────────────────────────────────────────────────────────────
_FEED_SOURCE = {
    "climate_reanalysis": "Copernicus / ECMWF ERA5", "fire_thermal": "NASA FIRMS", "storms_ocean": "NOAA / IBTrACS",
    "deforestation": "Hansen Global Forest Change", "flood": "JRC GloFAS / ERA5 runoff", "geophysical": "USGS",
    "natura2000": "EEA Natura 2000", "wdpa": "WDPA (IBAT)", "osm_protected": "OpenStreetMap", "kba": "KBA",
    "reference_lei": "GLEIF", "reference_assets": "Asset register", "imagery": "Sentinel-2", "atmosphere": "CAMS",
    "wdoecm": "WD-OECM",
}
_MATURITY_TONE = {"live": "#137a4b", "on_demand": "#1f6fb0", "proxy": "#b5731a", "partial": "#b5731a",
                  "estimated": "#b5731a", "planned": "#8896a8", "untracked": "#8896a8", "overdue": "#c2410c",
                  "fresh": "#137a4b"}


def _pill(text: str, tone: str) -> str:
    return (f"<span style='display:inline-block;padding:1px 7px;border-radius:9px;font-size:10px;"
            f"background:{tone}1a;color:{tone};font-weight:600'>{text}</span>")


def _lineage_html(entity: str, snap: dict, basis: dict, ev: dict) -> str:
    """A self-contained data-lineage graph: authoritative feeds → golden source → engine → frozen snapshot →
    filing. Built entirely from the snapshot's own engine_versions/basis — no external assets, no dependency."""
    maturity = (ev.get("feed_maturity") or {})
    freshness = (ev.get("feed_freshness_at_freeze") or {})
    feed_rows = ""
    for feed in sorted(maturity):
        src = _FEED_SOURCE.get(feed, feed)
        m = maturity.get(feed, "—")
        fr = freshness.get(feed)
        feed_rows += (f"<tr><td>{src}</td><td style='color:#5a6b80'>{feed}</td>"
                      f"<td>{_pill(m, _MATURITY_TONE.get(m, '#5a6b80'))}</td>"
                      f"<td>{_pill(fr, _MATURITY_TONE.get(fr, '#8896a8')) if fr else '—'}</td></tr>")
    verified = "hash verified ✓" if snap.get("hash_verified") else "hash not verified"
    stages = [
        ("Authoritative feeds", "Copernicus/ECMWF · NASA · USGS · NOAA · GLEIF — direct satellite &amp; agency data"),
        ("Golden source (H3)", "Each site/plot geolocated to a ~0.7&nbsp;km² H3 cell; append-only per-cell scores"),
        ("Engine", f"impact {ev.get('impact_version','—')} · fits {', '.join(ev.get('fit_versions') or []) or '—'} · "
                   f"code {ev.get('code_version','—')} · r² floor {ev.get('ranged_floor','—')}"),
        ("Frozen snapshot", f"{snap['report_type']} v{snap['version']} · sha256 {(snap.get('payload_sha256') or '')[:16]}… · {verified}"),
        ("Filing", f"{snap['report_type']} · basis {basis.get('scenario')}/{basis.get('horizon')} · period {basis.get('reporting_period_end')}"),
    ]
    chain = ""
    for i, (name, desc) in enumerate(stages):
        arrow = "<div style='color:#9fb0c4;font-size:20px;align-self:center'>&#8595;</div>" if i else ""
        chain += (arrow + f"<div style='border:1px solid #d5e3f2;border-left:4px solid #2f6fb0;border-radius:9px;"
                  f"padding:11px 15px;background:#f7fafd'><div style='font-weight:700;font-size:13.5px;color:#12314f'>"
                  f"{name}</div><div style='font-size:12px;color:#4a5b70;margin-top:2px'>{desc}</div></div>")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Data lineage — {entity}</title>
<style>body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;color:#12202f;max-width:760px;margin:40px auto;padding:0 26px;line-height:1.5}}
h1{{font-size:23px;margin:0 0 2px}}.sub{{color:#5a6b80;margin:0 0 22px;font-size:14.5px}}
.chain{{display:flex;flex-direction:column;gap:8px;margin:18px 0 30px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}th,td{{padding:6px 9px;border-bottom:1px solid #eef1f6;text-align:left}}
th{{color:#6a7a90;font-weight:600;font-size:10.5px;text-transform:uppercase;letter-spacing:.05em}}
.foot{{color:#8896a8;font-size:11px;margin-top:24px}}</style></head><body>
<h1>Data lineage</h1><p class="sub">{entity} · {snap['report_type']} v{snap['version']} — source to filing</p>
<div class="chain">{chain}</div>
<h3 style="font-size:14px;margin:0 0 4px">Feed provenance &amp; freshness at freeze</h3>
<table><thead><tr><th>Authoritative source</th><th>Feed</th><th>Maturity</th><th>Freshness at freeze</th></tr></thead>
<tbody>{feed_rows or '<tr><td colspan=4 style="color:#8896a8">No feed maturity recorded on this snapshot.</td></tr>'}</tbody></table>
<p class="foot">Every stage is recorded on the frozen snapshot itself (engine_versions); this graph reads that record, it does not re-derive it. Maturity: live &lt; on-demand &lt; proxy/partial/estimated &lt; planned.</p>
</body></html>"""


# ── Minimal dependency-free PDF (single page, Helvetica) ─────────────────────────────────────────────────────
def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _render_cover_pdf(title: str, lines: list[tuple[str, str]]) -> bytes:
    """Render a one-page A4 cover PDF from (text, kind) lines — kind ∈ {title, head, normal, mono}. A tiny,
    correct PDF/1.4 writer (catalog → pages → page → 2 fonts → content stream) so the pack ships a real .pdf
    the assurer can drop into working papers, with no third-party PDF dependency."""
    H = 842
    x, y = 56, H - 64
    style = {"title": ("F2", 18, 26), "head": ("F2", 11, 20), "normal": ("F1", 9.5, 15), "mono": ("F3", 9, 14)}
    parts = ["BT"]
    for line_text, kind in [(title, "title"), *lines]:
        font, size, gap = style.get(kind, style["normal"])
        y -= gap
        parts += [f"/{font} {size} Tf", f"1 0 0 1 {x} {y:.0f} Tm", f"({_pdf_escape(line_text)}) Tj"]
    parts.append("ET")
    content = ("\n".join(parts)).encode("latin-1", "replace")

    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R /F2 5 0 R /F3 6 0 R >> >> /Contents 7 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
    ]
    buf = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n".encode()
    buf += b"0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n".encode()
    buf += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF").encode()
    return buf


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

    # data-lineage graph — the source→filing chain + feed provenance, self-contained HTML
    lineage_blob = _lineage_html(entity, snap, basis, snap.get("engine_versions") or {}).encode("utf-8")
    manifest_files.insert(1, {"file": "lineage.html", "sha256": hashlib.sha256(lineage_blob).hexdigest(), "bytes": len(lineage_blob)})

    # rendered PDF cover — a real one-page .pdf (no print-to-PDF step), dependency-free writer
    _pdf_lines: list[tuple[str, str]] = [
        (f"{entity}  ·  {snap['report_type']} v{snap['version']}", "head"),
        ("", "normal"),
        (f"Reporting basis: scenario {basis.get('scenario')} · horizon {basis.get('horizon')}", "normal"),
        (f"Materiality {basis.get('materiality_threshold')} · period {basis.get('reporting_period_end')}", "normal"),
        (f"Pack generated {generated} (UTC)", "normal"),
        ("", "normal"),
        ("Frozen payload hash (SHA-256):", "head"),
        ((snap.get("payload_sha256") or "—"), "mono"),
        (verified, "normal"),
        ("", "normal"),
        ("Honesty gate", "head"),
        ("A euro is a firm figure only where the hazard->yield/asset chain clears", "normal"),
        ("r2 >= 0.40; otherwise exposure is mapped and the euro withheld. The r2", "normal"),
        ("floor is a fixed constant, not a per-filing setting.", "normal"),
        ("", "normal"),
        ("Contents (each artifact hashed for tamper-evidence):", "head"),
    ] + [(f"- {f['file']}  ({f['bytes']:,} bytes)", "mono") for f in manifest_files]
    cover_pdf_blob = _render_cover_pdf("Assurance evidence pack", _pdf_lines)
    manifest_files.insert(2, {"file": "cover.pdf", "sha256": hashlib.sha256(cover_pdf_blob).hexdigest(), "bytes": len(cover_pdf_blob)})

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
        z.writestr("cover.pdf", cover_pdf_blob)
        z.writestr("cover.html", cover_blob)
        z.writestr("lineage.html", lineage_blob)
        z.writestr("manifest.json", manifest_blob)
        z.writestr("methodology.md", method_blob)
        for name, blob in blobs.items():
            z.writestr(name, blob)
    buf.seek(0)
    fname = f"assurance-pack-{snap['report_type']}-v{snap['version']}.zip"
    return fname, buf.getvalue()
