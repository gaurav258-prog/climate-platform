"""EUDR → TRACES / EU Information System submission client.

Tier-1 (built earlier) assembles a Due Diligence Statement and the operator keys the reference number
back by hand. This is **Tier-2**: the client that maps our assembled DDS to a TRACES-shaped submission
envelope and files it directly — *once the operator is registered and credentials are configured*.

Honesty about what this can and can't do here:
  - By default it runs in **`prepared`** mode: it builds and completeness-checks the exact envelope it
    *would* submit and returns it, WITHOUT any network call. Nothing is filed. This is fully real and
    useful — the operator reviews precisely what goes out.
  - It flips to **`live`** only when `TRACES_MODE=live` AND `TRACES_BASE_URL` + `TRACES_API_TOKEN` are set
    (which requires the customer to have registered as an EUDR operator and obtained API access). Only then
    does it POST. Missing creds in live mode is an explicit, honest error — not a silent fake success.
  - The envelope field names are **Tellumen's mapping** and must be aligned to the published EUDR IS / TRACES
    DDS schema before real submission. That alignment is data, and it's flagged in every response.

So: the assembling, the completeness gate, the mapping and the submit path are all real; the only things
gated externally are the operator's registration and the official field-name confirmation.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from services.intelligence.eudr_dds import assemble_dds

_MODE = os.getenv("TRACES_MODE", "prepared").lower()          # "prepared" | "live"
_BASE = os.getenv("TRACES_BASE_URL")                           # e.g. https://webgate.ec.europa.eu/tracesnt/... (sandbox)
_TOKEN = os.getenv("TRACES_API_TOKEN")
_ACTIVITY = os.getenv("TRACES_ACTIVITY_TYPE", "TRADE")         # IMPORT | EXPORT | TRADE | DOMESTIC

_MAPPING_NOTE = ("Envelope uses Tellumen's field mapping; align to the published EUDR Information System / "
                 "TRACES DDS schema before live submission. Field alignment is data, not code.")


def _internal_reference(org_id: str, plot_ids: list[str]) -> str:
    """A deterministic internal reference for the statement (stable for the same plot set)."""
    h = hashlib.sha256((org_id + "|" + "|".join(sorted(plot_ids))).encode()).hexdigest()[:12].upper()
    return f"TELLUMEN-{h}"


def build_submission(dds: dict, org_id: str) -> dict:
    """Map an assembled DDS to a TRACES-shaped submission envelope (no side effects)."""
    plot_ids = [p["plot_id"] for it in dds["items"] for p in it["plots"]]
    op = dds["operator"]
    commodities = []
    for it in dds["items"]:
        commodities.append({
            "hsHeading": it.get("hs_code"),
            "descriptionOfGoods": it["commodity"],
            "netWeightKg": it.get("quantity_net_mass_kg"),      # operator supplies at filing
            "countriesOfProduction": it["countries_of_production"],
            "producers": [
                {"country": p["country"], "plotName": p["plot_name"], "areaHa": p["area_ha"],
                 "geometry": p["geolocation"], "deforestationDetermination": p["determination"],
                 "forestSource": p["forest_source"]}
                for p in it["plots"]
            ],
        })
    return {
        "internalReferenceNumber": _internal_reference(org_id, plot_ids),
        "activityType": _ACTIVITY,
        "operator": {"name": op.get("name"), "identifier": op.get("eori"), "identifierType": "EORI",
                     "address": op.get("address"), "country": op.get("country")},
        "commodities": commodities,
        "geoLocationConfidential": False,
        "dueDiligenceStatement": dds["statement"],
        "_mapping_note": _MAPPING_NOTE,
    }


def submission_preview(session: Session, org_id: str) -> dict:
    """The envelope we would file + readiness — no network, safe to call anytime (Tier-1 style review)."""
    dds = assemble_dds(session, org_id)
    envelope = build_submission(dds, org_id) if dds["fileable_plots"] else None
    return {
        "mode": _MODE, "ready": dds["ready"], "reason": dds["reason"],
        "covered_plots": dds["covered_plots"], "fileable_plots": dds["fileable_plots"],
        "blockers": dds["blockers"], "operator_completes": dds["operator_completes"],
        "envelope": envelope,
        "live_configured": bool(_BASE and _TOKEN),
        "note": _MAPPING_NOTE,
    }


def submit_dds(session: Session, org_id: str) -> dict:
    """Prepare (default) or live-submit the DDS. Live requires TRACES_MODE=live + base URL + token."""
    dds = assemble_dds(session, org_id)
    if not dds["ready"]:
        return {"status": "blocked", "reason": dds["reason"], "blockers": dds["blockers"],
                "operator_completes": dds["operator_completes"]}

    envelope = build_submission(dds, org_id)

    # PREPARED: build + validate, no network. The honest default.
    if _MODE != "live":
        return {"status": "prepared", "mode": _MODE,
                "internal_reference": envelope["internalReferenceNumber"],
                "envelope": envelope,
                "note": "Prepared, NOT filed. Set TRACES_MODE=live with base URL + token (needs the "
                        "operator's EUDR registration) to submit. " + _MAPPING_NOTE}

    # LIVE: requires configured credentials (i.e. the customer is registered).
    if not (_BASE and _TOKEN):
        return {"status": "not_configured",
                "reason": "Live mode selected but TRACES_BASE_URL / TRACES_API_TOKEN are not set. The "
                          "operator must register in the EU Information System and provide API credentials."}
    try:
        req = urllib.request.Request(
            _BASE.rstrip("/") + "/dds",
            data=json.dumps(envelope).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {_TOKEN}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
        return {"status": "submitted", "http_status": resp.status,
                "reference": body.get("referenceNumber") or body.get("ddsIdentifier"),
                "verification": body.get("verificationNumber"),
                "internal_reference": envelope["internalReferenceNumber"], "response": body}
    except urllib.error.HTTPError as e:  # noqa: PERF203
        return {"status": "rejected", "http_status": e.code, "error": e.read().decode("utf-8", "replace")[:500],
                "internal_reference": envelope["internalReferenceNumber"]}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "error": str(e), "internal_reference": envelope["internalReferenceNumber"]}
