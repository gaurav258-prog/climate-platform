"""Transmission: every mandate names a channel the registry defines; adapters never pretend to send."""
from services.supervision.mandates import registry
from services.transmission.adapters import ADAPTERS, ManualAdapter, credentials_status


def test_every_mandate_channel_exists_and_has_an_adapter():
    r = registry()
    for m in r["mandates"]:
        cid = m["deliverable"]["channel_id"]
        assert cid in r["channels"], (m["id"], cid)
        assert r["channels"][cid]["kind"] in ADAPTERS
    assert "tellumen_supervisor" in r["channels"] and r["channels"]["tellumen_supervisor"]["kind"] == "tellumen"


def test_portal_without_credentials_is_awaiting_not_sent(monkeypatch):
    ch = registry()["channels"]["eba_reporting_portal"]
    for k in ("URL", "USER", "PASSWORD"):
        monkeypatch.delenv(f"TELLUMEN_CHANNEL_EBA_REPORTING_PORTAL_{k}", raising=False)
    cs = credentials_status("eba_reporting_portal", ch, None)
    assert not cs["configured"] and set(cs["missing"]) == {"url", "user", "password"}
    monkeypatch.setenv("TELLUMEN_CHANNEL_EBA_REPORTING_PORTAL_URL", "https://portal.example")
    monkeypatch.setenv("TELLUMEN_CHANNEL_EBA_REPORTING_PORTAL_USER", "u")
    monkeypatch.setenv("TELLUMEN_CHANNEL_EBA_REPORTING_PORTAL_PASSWORD", "p")
    assert credentials_status("eba_reporting_portal", ch, None)["configured"]


def test_manual_channel_waits_for_a_receipt():
    res = ManualAdapter().send(None, org_id="o", filing={}, payload=b"x", filename="f.json", fmt="json", channel_id="nca_manual", org_settings=None)
    assert res["status"] == "awaiting_receipt"
