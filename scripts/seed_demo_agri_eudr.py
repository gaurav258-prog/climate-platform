"""Three demo agri companies get an EUDR set-up so the /eudr page is not empty — DEMO data for fictional companies
(made-up suppliers, plots and shipments; not regulatory, not validated, no real company), through the app's own governed
paths, four eyes where the app asks for them (as tests/integration/test_e2e_eudr_statement.py does):

  intake       a supplier and a customer (eudr_suppliers / eudr_customers), two plots with their geolocation — one
               polygon, one point under four hectares (supply_plots), one shipment placed on the market by the operator
               (eudr_movements) and its plots with production dates (eudr_movement_plots)
  records      the undertaking's EUDR status (POST /v1/eudr/status, a second person approves), the plots read against
               the satellite record (POST /v1/eudr/plots/read — the platform's real forest-loss reading), legality evidence
               per plot, the shipment's risk assessment (full path, Art. 10(2) criteria answered; a second person approves)
  verified     GET /v1/eudr/movements/{id}/statement — its blocking checks are printed (none expected)

No filing is prepared. Idempotent: a shipment already on file is not uploaded again; a status, evidence or assessment
already in place (or waiting for approval) is left as it is.

  venv/bin/python scripts/seed_demo_agri_eudr.py [--base http://localhost:8001]

Local demo only: logs in with the seeded demo credentials (analyst = maker, admin = the second person).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time

import httpx

STATUS_FROM = "2026-12-30"          # Art. 38(2): Arts. 3-13 apply from 30 December 2026
BOOK_DATE = "2026-09-30"


def _poly(lon: float, lat: float, d: float = 0.002) -> str:
    """A closed square ring with six-decimal corners (Art. 2(28)); d degrees a side (~4-5 ha near the equator)."""
    ring = [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]
    return json.dumps({"type": "Polygon", "coordinates": [[[round(x, 6), round(y, 6)] for x, y in ring]]})


COMPANIES = {
    "oranje": {
        "org": "Oranje Foods NV (demo)", "country": "NL", "eori": "NL812345678",
        "address": "[Demo text] Havenstraat 12, 3011 AB Rotterdam, Netherlands",
        "supplier": {"party_name": "Ashanti Demo Cocoa Co-op", "party_ref": "DEMO-ORA-SUP-01", "country": "GH",
                     "address": "[Demo text] PO Box 101, Techiman, Bono East, Ghana", "contact_email": "co-op@ashanti-demo.example"},
        "customer": {"party_name": "Delta Demo Chocolatiers BV", "party_ref": "DEMO-ORA-CUS-01", "country": "NL",
                     "address": "[Demo text] Fabrieksweg 4, 1505 Zaandam, Netherlands", "contact_email": "buying@delta-demo.example"},
        "commodity": "Cocoa", "region": "Bono East", "plot_country": "GH",
        "plots": [("Techiman Demo Farm A", "DEMO-ORA-P-01", -1.931234, 7.582345, None),
                  ("Techiman Demo Farm B", "DEMO-ORA-P-02", -1.902345, 7.601234, "3.20")],
        "movement": {"movement_ref": "DEMO-ORA-M-2027-01", "planned_on": "2027-01-18", "hs_code": "180100",
                     "description": "[Demo text] Cocoa beans, raw, fermented and dried", "net_mass_kg": "24000"},
        "production": ("2026-03-01", "2026-08-31"),
    },
    "douro": {
        "org": "Douro Alimentar (demo)", "country": "PT", "eori": "PT509876543",
        "address": "[Demo text] Rua do Cais 45, 4050-123 Porto, Portugal",
        "supplier": {"party_name": "Serra Verde Demo Cafe Ltda", "party_ref": "DEMO-DOU-SUP-01", "country": "BR",
                     "address": "[Demo text] Rodovia MG-167 km 12, Varginha, MG, Brazil", "contact_email": "export@serraverde-demo.example"},
        "customer": {"party_name": "Ribeira Demo Torrefacao Lda", "party_ref": "DEMO-DOU-CUS-01", "country": "PT",
                     "address": "[Demo text] Avenida da Boavista 900, 4100-112 Porto, Portugal",
                     "contact_email": "compras@ribeira-demo.example"},
        "commodity": "Coffee", "region": "Minas Gerais", "plot_country": "BR",
        "plots": [("Sul de Minas Demo Talhao 1", "DEMO-DOU-P-01", -45.431234, -21.552345, None),
                  ("Sul de Minas Demo Talhao 2", "DEMO-DOU-P-02", -45.402345, -21.571234, "2.80")],
        "movement": {"movement_ref": "DEMO-DOU-M-2027-01", "planned_on": "2027-02-08", "hs_code": "090111",
                     "description": "[Demo text] Green arabica coffee, not roasted, not decaffeinated", "net_mass_kg": "19200"},
        "production": ("2026-05-01", "2026-09-30"),
    },
    "padania": {
        "org": "Padania Alimentari (demo)", "country": "IT", "eori": "IT01234567890",
        "address": "[Demo text] Via Emilia 210, 43126 Parma, Italy",
        "supplier": {"party_name": "Oeste Demo Graos Cooperativa", "party_ref": "DEMO-PAD-SUP-01", "country": "BR",
                     "address": "[Demo text] Avenida Brasil 1500, Cascavel, PR, Brazil", "contact_email": "vendas@oeste-demo.example"},
        "customer": {"party_name": "Po Valley Demo Mangimi Srl", "party_ref": "DEMO-PAD-CUS-01", "country": "IT",
                     "address": "[Demo text] Strada Provinciale 343 n. 8, 26100 Cremona, Italy",
                     "contact_email": "acquisti@povalley-demo.example"},
        "commodity": "Soybean", "region": "Parana", "plot_country": "BR",
        "plots": [("Cascavel Demo Gleba 1", "DEMO-PAD-P-01", -53.451234, -24.952345, None),
                  ("Cascavel Demo Gleba 2", "DEMO-PAD-P-02", -53.422345, -24.971234, "3.60")],
        "movement": {"movement_ref": "DEMO-PAD-M-2027-01", "planned_on": "2027-03-02", "hs_code": "12019000",
                     "description": "[Demo text] Soya beans, whether or not broken, other than seed", "net_mass_kg": "60000"},
        "production": ("2026-01-15", "2026-04-30"),
    },
}
CRITERIA = ("a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n")     # Art. 10(2) (services/eudr/records.py)


def _login(c: httpx.Client, email: str, pw: str) -> dict:
    for _ in range(6):
        r = c.post("/v1/auth/login", json={"email": email, "password": pw})
        if r.status_code != 429:
            r.raise_for_status()
            return {"Authorization": "Bearer " + r.json()["access_token"]}
        time.sleep(30)
    raise SystemExit(f"login {email}: rate-limited")


def _csv(rows: list[dict]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


def _approve(c, checker, rid, why):
    d = c.post(f"/v1/approvals/{rid}/decide", headers=checker, json={"decision": "approved", "reason": why})
    if d.status_code != 200:
        raise SystemExit(f"approve {rid}: {d.status_code} {d.text[:300]}")


def _upload(c, maker, checker, url, rows, label, **form):
    r = c.post(url, headers=maker, files={"file": (f"{label}.csv", _csv(rows), "text/csv")},
               data={"approval_reason": f"demo {label}", **form})
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code == 202 and body.get("state") == "awaiting_approval":
        _approve(c, checker, body["approval_request_id"], f"demo {label} checked")
        return
    if r.status_code != 200 or body.get("state") != "imported":
        raise SystemExit(f"{label}: {r.status_code} {r.text[:500]}")


def _intake(c, maker, checker, k: dict) -> None:
    sup, cus, mv = k["supplier"], k["customer"], k["movement"]
    _upload(c, maker, checker, "/v1/eudr/intake/eudr_suppliers/upload", [sup], "eudr_suppliers")
    _upload(c, maker, checker, "/v1/eudr/intake/eudr_customers/upload", [cus], "eudr_customers")
    plots = []
    for name, ref, lon, lat, area in k["plots"]:
        row = {"plot_name": f"{name} (demo)", "commodity": k["commodity"], "annual_spend_eur": "250000", "external_ref": ref,
               "supplier_ref": sup["party_ref"], "country": k["plot_country"], "region": k["region"], "currency": "EUR",
               "book_date": BOOK_DATE, "latitude": "", "longitude": "", "plot_geojson": "", "plot_area_ha": ""}
        if area is None:
            row["plot_geojson"] = _poly(lon, lat)
        else:
            row.update(latitude=f"{lat:.6f}", longitude=f"{lon:.6f}", plot_area_ha=area)
        plots.append(row)
    _upload(c, maker, checker, "/v1/supply/plots/upload", plots, "supply_plots", currency="EUR", book_date=BOOK_DATE)
    _upload(c, maker, checker, "/v1/eudr/intake/eudr_movements/upload", [{
        **mv, "movement_kind": "placing", "actor_role": "operator", "customs_flow": "true",
        "supplier_ref": sup["party_ref"], "customer_ref": cus["party_ref"]}], "eudr_movements")
    _upload(c, maker, checker, "/v1/eudr/intake/eudr_movement_plots/upload", [
        {"movement_ref": mv["movement_ref"], "plot_ref": ref, "production_from": k["production"][0],
         "production_to": k["production"][1]} for _, ref, *_ in k["plots"]], "eudr_movement_plots")


def _movement(c, maker, ref) -> dict | None:
    r = c.get("/v1/eudr/movements", headers=maker)
    r.raise_for_status()
    return next((m for m in r.json()["movements"] if m["external_ref"] == ref), None)


def _records(c, maker, on) -> dict:
    r = c.get("/v1/eudr/records", headers=maker, params={"on": on})
    r.raise_for_status()
    return r.json()


def _read_plots(c, maker, mine: list[dict], on: str) -> str:
    """The platform's own forest-loss reading of each plot not yet read, or read as not assessable (a job); a point plot is
    read within 100 m of it (~3.1 ha, its stated area); waits up to two minutes for it."""
    was = {p["plot_id"]: (p.get("reading") or {}).get("assessed_at") for p in mine}
    todo = [p["plot_id"] for p in mine if (p.get("reading") or {}).get("outcome") in (None, "not_assessable")]
    if todo:
        r = c.post("/v1/eudr/plots/read", headers=maker, json={"plot_ids": todo, "point_radius_m": 100})
        if r.status_code != 202:
            return f"reading not started ({r.status_code} {r.text[:200]})"
        for _ in range(24):
            time.sleep(5)
            got = {p["plot_id"]: p.get("reading") for p in _records(c, maker, on)["plots"]}
            if all(got.get(pid) and got[pid].get("assessed_at") != was.get(pid) for pid in todo):
                break
    got = {p["plot_id"]: p.get("reading") for p in _records(c, maker, on)["plots"]}
    return ", ".join(f"{p['external_ref']}: {(got.get(p['plot_id']) or {}).get('outcome', 'not read yet')}" for p in mine)


def seed(c: httpx.Client, slug: str, k: dict) -> str:
    maker = _login(c, f"analyst@{slug}.demo", "Demo!analyst1")
    checker = _login(c, f"admin@{slug}.demo", "Demo!admin1")
    mv, on = k["movement"], k["movement"]["planned_on"]

    # ── 1 intake: supplier, customer, plots, the shipment and its plots (skipped once the shipment is on file) ──
    m = _movement(c, maker, mv["movement_ref"])
    if m is None or not m["n_plots"]:
        _intake(c, maker, checker, k)
        m = _movement(c, maker, mv["movement_ref"])
        if m is None:
            raise SystemExit(f"{slug}: the shipment did not land")
    mid = m["movement_id"]

    # ── 2 the undertaking's status for the shipment's date (four eyes) ──
    rec = _records(c, maker, on)
    if rec["status"] is None and not any(p["request_type"] == "eudr.status" for p in rec["pending"]):
        r = c.post("/v1/eudr/status", headers=maker, json={
            "effective_from": STATUS_FROM, "size_class": "large", "country": k["country"], "address": k["address"],
            "eori": k["eori"], "basis": "[Demo text] Large undertaking under Directive 2013/34/EU Art. 3(4) (demo figures)."})
        if r.status_code != 202:
            raise SystemExit(f"{slug} status: {r.status_code} {r.text[:300]}")
        _approve(c, checker, r.json()["approval_request_id"], "demo EUDR status checked")

    # ── 3 the satellite reading of each plot (the platform's real forest-loss reading) ──
    refs = {ref for _, ref, *_ in k["plots"]}
    mine = [p for p in _records(c, maker, on)["plots"] if p["external_ref"] in refs]
    readings = _read_plots(c, maker, mine, on)

    # ── 4 legality evidence per plot (append-only: only where the statement holds none) ──
    st = c.get(f"/v1/eudr/movements/{mid}/statement", headers=maker).json()
    if not st["legality_evidence"]:
        for p in mine:
            r = c.post("/v1/eudr/evidence", headers=maker, json={
                "aspect": "land_use_rights", "document_kind": "Land title (demo)", "plot_id": p["plot_id"],
                "document_ref": f"DEMO-TITLE-{p['external_ref']}", "issued_by": "[Demo text] Land registry (fictional)",
                "valid_from": "2020-01-01", "note": "[Demo text] Illustrative land-use right for a fictional plot."})
            if r.status_code != 201:
                raise SystemExit(f"{slug} evidence: {r.status_code} {r.text[:300]}")

    # ── 5 the shipment's risk assessment, full path (four eyes) ──
    pending = any(p["request_type"] == "eudr.risk" and p["movement_id"] == mid for p in _records(c, maker, on)["pending"])
    if st["risk_assessment"] is None and not pending:
        r = c.post(f"/v1/eudr/movements/{mid}/risk-assessment", headers=maker, json={
            "path": "full", "conclusion": "negligible",
            "criteria": {x: f"[Demo text] Criterion ({x}) assessed for {k['supplier']['party_name']}: no indication of "
                            "risk found (illustrative)." for x in CRITERIA},
            "mitigation": {"a": "[Demo text] Supplier asked for plot maps and land titles (illustrative)."}})
        if r.status_code != 202:
            raise SystemExit(f"{slug} risk assessment: {r.status_code} {r.text[:300]}")
        _approve(c, checker, r.json()["approval_request_id"], "demo risk assessment checked")

    # ── 6 the statement as it stands: what still blocks ──
    st = c.get(f"/v1/eudr/movements/{mid}/statement", headers=maker).json()
    blocking = [f"{f['rule']}: {f['message']}" for f in st["checks"] if not f["passed"] and f["severity"] == "blocking"]
    warnings = [f"{f['rule']}: {f['message']}" for f in st["checks"] if not f["passed"] and f["severity"] == "warning"]
    return (f"{slug}: shipment {mv['movement_ref']} ({mid}), supplier {k['supplier']['party_name']}, "
            f"plots {sorted(refs)}\n  readings: {readings}\n  blocking: {blocking or 'none'}\n  warnings: {warnings or 'none'}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8001")
    a = ap.parse_args()
    if not a.base.startswith(("http://localhost", "http://127.0.0.1")):
        print("demo seeding runs against a local development API only", file=sys.stderr)
        return 2
    with httpx.Client(base_url=a.base, timeout=180) as c:
        for slug, k in COMPANIES.items():
            print(seed(c, slug, k))
    return 0


if __name__ == "__main__":
    sys.exit(main())
