"""A FAOSTAT crop-production file is landed only after review (E148).

  stage     the scheduled fetch (or an operator) hands in the publisher's file: it is read, compared with what the
            store holds for the same source, and kept as a release — the rows that would be added, revised (the
            publisher's production or area changed) or recomputed (only our derived yield / year-on-year changed),
            each with the value held before; the store is not touched. A file already recorded (same sha-256)
            is not staged twice; one open release per source at a time.
  propose   a platform operator who has reviewed the difference asks for it to land (an approval request in the
            platform organisation, 'reference.release_land')
  decide    a second operator approves (four eyes — the approvals path refuses the maker) → the rows are written to
            crop_yield_observations; or rejects / returns it → nothing is written, the release is closed

Facts the review shows (summary): rows added and revised per commodity, years newly reported, the largest revisions,
rows the store holds that the file no longer reports (kept, never deleted), and the crop calibrations whose window
holds a changed year — 'may be affected': a calibration records its years, not its source series, so it is listed for
a refit check, never changed here.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.reference import faostat_crops as F

REQUEST_TYPE = "reference.release_land"
_FIELDS = ("production_tonnes", "area_harvested_ha", "yield_tonnes_ha", "yoy_change_pct")
_PUBLISHED = ("production_tonnes", "area_harvested_ha")      # the publisher's figures; yield and year-on-year are ours
_TOP = 10


class ReleaseError(ValueError):
    """The step cannot be taken as asked (wrong status, no reason, a release still open)."""


class ReleaseNotFound(ReleaseError):
    pass


def _held(session: Session, src: str) -> dict:
    rows = session.execute(text(f"""
        SELECT commodity, country, season_year, {", ".join(f"CAST({c} AS FLOAT) AS {c}" for c in _FIELDS)}
        FROM crop_yield_observations WHERE source = :s"""), {"s": src}).mappings()
    return {(r["commodity"], r["country"], r["season_year"]): {c: r[c] for c in _FIELDS} for r in rows}


def _differs(a, b) -> bool:
    return (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-6 * max(1.0, abs(b)))


def _affected_fits(session: Session, changed: dict[tuple[str, str], set[int]]) -> list[dict]:
    from ml.features.crop_cycle import TREND_K
    out = []
    for f in session.execute(text("""
            SELECT c.name AS commodity, f.origin, f.hazard_driver, f.baseline_from, f.baseline_to
            FROM sc_commodity_fit f JOIN sc_commodities c ON c.commodity_id = f.commodity_id
            ORDER BY c.name, f.origin""")).mappings():
        years = changed.get((f["commodity"], f["origin"]), set())
        lo, hi = (f["baseline_from"] or -9999) - TREND_K, (f["baseline_to"] or 9999) + TREND_K
        hit = sorted(y for y in years if lo <= y <= hi)
        if hit:
            out.append({**dict(f), "changed_years": hit})
    return out


def stage(session: Session, data: bytes, *, last_modified: str | None = None, etag: str | None = None) -> dict:
    src = F.source()
    sha = hashlib.sha256(data).hexdigest()
    countries = F.iso_by_m49(session)
    rdr = F.reader(countries)
    seen = session.execute(text("""SELECT release_id::text, status FROM crop_yield_releases
                                   WHERE source = :s AND file_sha256 = :h AND reader = :r"""),
                           {"s": src, "h": sha, "r": rdr}).mappings().first()
    if seen:
        return {"staged": False, "release_id": seen["release_id"], "status": seen["status"],
                "reason": "this publisher file is already recorded under the current reading rules"}
    open_ = session.execute(text("SELECT release_id::text FROM crop_yield_releases WHERE source = :s AND status IN ('staged', 'proposed')"),
                            {"s": src}).scalar()
    if open_:
        raise ReleaseError(f"release {open_} is still open for review — land or reject it before staging another")
    rows = F.parse(data, countries)
    held = _held(session, src)
    added, revised, recomputed, by_commodity, changed = [], [], [], {}, {}
    for r in rows:
        key = (r["commodity"], r["country"], r["season_year"])
        before = held.get(key)
        if before is None:
            added.append(r)
            kind = "added"
        elif any(_differs(r[c], before[c]) for c in _PUBLISHED):
            revised.append({**r, "held_before": before})
            kind = "revised"
        elif any(_differs(r[c], before[c]) for c in _FIELDS):
            recomputed.append({**r, "held_before": before})
            kind = "recomputed"
        else:
            continue
        b = by_commodity.setdefault(r["commodity"], {"added": 0, "revised": 0, "recomputed": 0, "years_new": set()})
        b[kind] += 1
        if kind != "recomputed":                     # a calibration's inputs change only with the publisher's figures
            changed.setdefault((r["commodity"], r["country"]), set()).add(r["season_year"])
    latest_held = {}
    for (c, _geo, y) in held:
        latest_held[c] = max(latest_held.get(c, 0), y)
    for r in added:
        if r["season_year"] > latest_held.get(r["commodity"], 0):
            by_commodity[r["commodity"]]["years_new"].add(r["season_year"])
    in_file = {(r["commodity"], r["country"], r["season_year"]) for r in rows}
    biggest = sorted((r for r in revised if r["production_tonnes"] is not None and r["held_before"]["production_tonnes"]),
                     key=lambda r: -abs(r["production_tonnes"] / r["held_before"]["production_tonnes"] - 1))[:_TOP]
    summary = {
        "rows_in_file": len(rows), "added": len(added), "revised": len(revised), "recomputed": len(recomputed),
        "unchanged": len(rows) - len(added) - len(revised) - len(recomputed),
        "held_not_in_file": len(set(held) - in_file),
        "by_commodity": {c: {**v, "years_new": sorted(v["years_new"])} for c, v in sorted(by_commodity.items())},
        "largest_revisions": [{"commodity": r["commodity"], "country": r["country"], "year": r["season_year"],
                               "production_before": r["held_before"]["production_tonnes"],
                               "production_now": r["production_tonnes"],
                               "change_pct": round(100 * (r["production_tonnes"] / r["held_before"]["production_tonnes"] - 1), 2)}
                              for r in biggest],
        "calibrations_may_be_affected": _affected_fits(session, changed),
    }
    rid = session.execute(text("""
        INSERT INTO crop_yield_releases (source, file_sha256, file_bytes, origin_url, last_modified, etag, summary, reader)
        VALUES (:s, :h, :n, :u, :lm, :et, CAST(:sum AS jsonb), :rdr) RETURNING release_id::text"""),
        {"s": src, "h": sha, "n": len(data), "u": F.url(), "lm": last_modified, "et": etag,
         "sum": json.dumps(summary), "rdr": rdr}).scalar()
    for kind, rs in (("added", added), ("revised", revised), ("recomputed", recomputed)):
        for r in rs:
            session.execute(text("""
                INSERT INTO crop_yield_release_rows (release_id, commodity, country, season_year, change, production_tonnes,
                       area_harvested_ha, yield_tonnes_ha, yoy_change_pct, note, held_before)
                VALUES (CAST(:rid AS uuid), :commodity, :country, :season_year, :k, :production_tonnes, :area_harvested_ha,
                        :yield_tonnes_ha, :yoy_change_pct, :note, CAST(:hb AS jsonb))"""),
                {**r, "rid": rid, "k": kind, "hb": json.dumps(r["held_before"]) if kind != "added" else None})
    out = {"staged": True, "release_id": rid, "status": "staged", "summary": summary}
    from services.governance.platform_policy import PLATFORM_ORG, SYSTEM_USER, human_approvers
    if human_approvers(session, REQUEST_TYPE) == 1:           # one approver stated: the platform proposes (E150)
        p = propose(session, PLATFORM_ORG, rid, SYSTEM_USER,
                    f"Staged by the platform: {summary['added']} added, {summary['revised']} revised by the publisher, "
                    f"{summary['recomputed']} recomputed, {summary['held_not_in_file']} held but not in the file; "
                    f"{len(summary['calibrations_may_be_affected'])} calibrations may be affected.")
        out.update(status="proposed", approval_request_id=p["approval_request_id"])
    return out


def pending(session: Session) -> dict | None:
    """The open release of the source (staged or proposed), if any — what the feed monitor shows as awaiting review."""
    r = session.execute(text("""SELECT release_id::text, status, fetched_at FROM crop_yield_releases
                                WHERE source = :s AND status IN ('staged', 'proposed')"""), {"s": F.source()}).mappings().first()
    return dict(r) if r else None


def releases(session: Session, limit: int = 20) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT c.release_id::text, c.source, c.file_sha256, c.reader, c.file_bytes, c.origin_url, c.last_modified, c.etag,
               c.fetched_at, c.summary, c.status, c.approval_request_id::text, c.decided_at, c.decision_reason, c.landed_at,
               a.maker_user_id::text AS proposed_by_id, m.email AS proposed_by, a.payload->>'review' AS review,
               a.created_at AS proposed_at, d.email AS decided_by
        FROM crop_yield_releases c
        LEFT JOIN approval_requests a ON a.request_id = c.approval_request_id
        LEFT JOIN users m ON m.user_id = a.maker_user_id
        LEFT JOIN users d ON d.user_id = c.decided_by
        ORDER BY c.seq DESC LIMIT :n"""), {"n": limit}).mappings()]


CHANGES = ("revised", "added", "recomputed")


def release_rows(session: Session, release_id: str, change: str | None = None, limit: int = 500) -> list[dict]:
    if change is not None and change not in CHANGES:
        raise ReleaseError(f"change must be one of {', '.join(CHANGES)}")
    return [dict(r) for r in session.execute(text(f"""
        SELECT commodity, country, season_year, change, {", ".join(f"CAST({c} AS FLOAT) AS {c}" for c in _FIELDS)}, held_before
        FROM crop_yield_release_rows WHERE release_id = CAST(:r AS uuid) AND (CAST(:k AS varchar) IS NULL OR change = :k)
        ORDER BY CASE change WHEN 'revised' THEN 0 WHEN 'added' THEN 1 ELSE 2 END, commodity, country, season_year
        LIMIT :n"""), {"r": release_id, "k": change, "n": limit}).mappings()]


def _release(session: Session, release_id: str) -> dict:
    r = session.execute(text("SELECT release_id::text, status, source FROM crop_yield_releases WHERE release_id = CAST(:r AS uuid)"),
                        {"r": release_id}).mappings().first()
    if not r:
        raise ReleaseNotFound("release not found")
    return dict(r)


def propose(session: Session, platform_org_id: str, release_id: str, maker_user_id: str, reason: str) -> dict:
    """The reviewer asks for the release to land: an approval request a second operator decides. Where the platform
    states ONE human approver (E150), the platform's system account is the maker — the operator's note is kept as the
    review — and one operator decides."""
    from services.governance.platform_policy import SYSTEM_USER, human_approvers
    if human_approvers(session, REQUEST_TYPE) == 1:
        maker_user_id = SYSTEM_USER
    rel = _release(session, release_id)
    if rel["status"] != "staged":
        raise ReleaseError(f"only a staged release can be proposed (this one is {rel['status']})")
    why = (reason or "").strip()
    if len(why) < 10:
        raise ReleaseError("say what was reviewed (at least 10 characters) — it is kept with the release")
    rid = session.execute(text("""
        INSERT INTO approval_requests (org_id, request_type, title, payload, maker_user_id)
        VALUES (CAST(:o AS uuid), :t, :title, CAST(:p AS jsonb), CAST(:m AS uuid)) RETURNING request_id::text"""),
        {"o": platform_org_id, "t": REQUEST_TYPE, "title": f"Land the {rel['source']} release",
         "p": json.dumps({"release_id": release_id, "review": why}), "m": maker_user_id}).scalar()
    session.execute(text("""UPDATE crop_yield_releases SET status = 'proposed', approval_request_id = CAST(:a AS uuid)
                            WHERE release_id = CAST(:r AS uuid)"""), {"a": rid, "r": release_id})
    return {"release_id": release_id, "status": "proposed", "approval_request_id": rid}


def reject(session: Session, release_id: str, actor_user_id: str, reason: str) -> dict:
    """A staged release closed without landing (e.g. the file is damaged); a proposed one is closed by its decision."""
    rel = _release(session, release_id)
    if rel["status"] != "staged":
        raise ReleaseError(f"only a staged release is rejected here (this one is {rel['status']}; decide its approval request)")
    why = (reason or "").strip()
    if len(why) < 10:
        raise ReleaseError("say why the release is rejected (at least 10 characters)")
    _close(session, release_id, "rejected", actor_user_id, why)
    return {"release_id": release_id, "status": "rejected"}


def _close(session: Session, release_id: str, status: str, actor: str, reason: str | None) -> None:
    session.execute(text("""UPDATE crop_yield_releases SET status = CAST(:s AS varchar), decided_by = CAST(:u AS uuid),
                            decided_at = now(), decision_reason = :w,
                            landed_at = CASE WHEN CAST(:s AS varchar) = 'landed' THEN now() END
                            WHERE release_id = CAST(:r AS uuid)"""), {"s": status, "u": actor, "w": reason, "r": release_id})


def apply_decision(session: Session, payload: dict, decision: str, checker_user_id: str, reason: str | None) -> dict:
    """The approvals path's handler: approved → the rows land; rejected / returned → nothing lands, the release closes."""
    release_id = (payload or {}).get("release_id")
    rel = _release(session, release_id)
    if rel["status"] != "proposed":
        raise ReleaseError(f"the release is {rel['status']}, not awaiting a decision")
    if decision != "approved":
        _close(session, release_id, "rejected", checker_user_id, reason or f"{decision} by the second reviewer")
        return {"release_id": release_id, "status": "rejected", "landed_rows": 0}
    n = session.execute(text("""
        INSERT INTO crop_yield_observations (commodity, country, season_year, production_tonnes, area_harvested_ha,
               yield_tonnes_ha, yoy_change_pct, source, note)
        SELECT commodity, country, season_year, production_tonnes, area_harvested_ha, yield_tonnes_ha, yoy_change_pct,
               :src, note
        FROM crop_yield_release_rows WHERE release_id = CAST(:r AS uuid)
        ON CONFLICT (commodity, country, season_year, source) DO UPDATE SET
            production_tonnes = EXCLUDED.production_tonnes, area_harvested_ha = EXCLUDED.area_harvested_ha,
            yield_tonnes_ha = EXCLUDED.yield_tonnes_ha, yoy_change_pct = EXCLUDED.yoy_change_pct,
            note = EXCLUDED.note, ingested_at = now()"""), {"src": rel["source"], "r": release_id}).rowcount
    _close(session, release_id, "landed", checker_user_id, reason)
    return {"release_id": release_id, "status": "landed", "landed_rows": n}


def _last_check(session: Session) -> dict:
    """The publisher's validators as last observed — the latest recorded check, else the latest release's."""
    r = session.execute(text("""SELECT last_modified, etag FROM crop_release_checks WHERE source = :s
                                ORDER BY check_id DESC LIMIT 1"""), {"s": F.source()}).mappings().first()
    if r is None:
        r = session.execute(text("""SELECT last_modified, etag FROM crop_yield_releases WHERE source = :s
                                    ORDER BY seq DESC LIMIT 1"""), {"s": F.source()}).mappings().first()
    return dict(r) if r else {}


def _record_check(session: Session, probe: dict, downloaded: bool, sha: str | None, outcome: str) -> None:
    session.execute(text("""
        INSERT INTO crop_release_checks (source, last_modified, etag, changed, downloaded, file_sha256, outcome)
        VALUES (:s, :lm, :et, :ch, :dl, :h, :o)"""),
        {"s": F.source(), "lm": probe.get("last_modified"), "et": probe.get("etag"), "ch": bool(probe.get("changed")),
         "dl": downloaded, "h": sha, "o": outcome[:500]})


def refresh(session: Session) -> dict:
    """The scheduled refresh (feed 'crop_production_faostat'): ask FAOSTAT whether its file changed since the last
    recorded check (HEAD — E152); only then download and stage it for review. Every check is recorded with what the
    publisher answered. Nothing lands without the review."""
    waiting = pending(session)
    if waiting:
        return {"staged": False, "release_id": waiting["release_id"],
                "reason": f"a release is awaiting review ({waiting['status']}) — fetched again after it is decided"}
    last = _last_check(session)
    probe = F.published(last.get("last_modified"), last.get("etag"))
    if not probe["changed"]:
        _record_check(session, probe, False, None, "unchanged since the last check")
        session.commit()
        return {"staged": False, "reason": "FAOSTAT has not published a new file"}
    data = F.download()
    out = stage(session, data, last_modified=probe["last_modified"], etag=probe["etag"])
    _record_check(session, probe, True, hashlib.sha256(data).hexdigest(),
                  f"staged release {out['release_id']}" if out["staged"] else out["reason"])
    session.commit()
    return out
