# Horizon front-door + financial-surface — workflow & audit review

Scope: everything introduced in the 2026-08-02 sessions on `feature/asset-manager-reference-data`
(commits `09afc41`…`3f90b57`). For each function this checks four axes: a **real workflow** behind it
(no dead buttons, no fabricated numbers), **audit-trail** coverage of state changes, **persistence**
(migrated + reversible), and **saved** (committed + pushed). Verdict: **clean** — every state-changing
action is audited, every UI control maps to a real endpoint, all migrations are reversible and at a single
head, and the tree is committed + pushed.

## 1. Persistence / git
- Working tree clean; all commits pushed to `origin/feature/asset-manager-reference-data`.
- Single Alembic head: `approval_assignee_202608`; DB `current` == head.
- All four session migrations carry `revision` + `down_revision` + `downgrade`:
  `climbaseline_latlon_202608`, `reporting_entities_202608`, `approval_returned_202608`, `approval_assignee_202608`.

## 2. Audit trail (access_audit_log) — every runtime state change is recorded
| Action | Endpoint | Audit action | Gate |
|---|---|---|---|
| Submit for approval | `POST /v1/approvals` | `approval.create` | `approvals.create` |
| Approve / reject / send-back | `POST /v1/approvals/{id}/decide` | `approval.decide` | `approvals.decide`, maker≠checker (4-eyes) |
| Assign to an approver | `POST /v1/approvals/{id}/assign` | `approval.assign` | maker or `approvals.decide`; assignee must hold `approvals.decide` |
| Set parametric trigger | `POST /v1/insurance/policies/{id}/trigger-config` | `policy.trigger_config.set` | `pricing.approve`, org-scoped |
| On-demand hazard scoring | `GET /v1/me/hexes` (ring warm) | writes `canonical_scores` (append-only WORM trigger; provenance in `shap_factors`) | — |

Verified live: audit rows land for `approval.assign` (3), `approval.decide` (15), `policy.trigger_config.set` (4), `approval.create` (9).
Read-only surfaces (Portfolio, Compliance, `/v1/me/globe`, `/v1/me/tasks`, `/deciders`) correctly write nothing.

## 3. Real workflow behind every UI control (no dead buttons)
- **Portfolio** (`/portfolio`): sector-dispatched read of the real `/v1/{bank|insurance|assetmgmt|realestate}/portfolio`; scenario/horizon toggles refetch; row-expand renders provenance already in the response; Export .xlsx → the sector's real `.xlsx`. `—` where unscored — no fabricated euros.
- **Compliance** (`/compliance`): bank/AM/REIT read `/disclosure` (by-hazard, EU-Taxonomy eligibility, financed emissions); insurer reads `/triggers`; bank .xlsx real. Taxonomy caveat stated (eligibility, not aligned %).
- **Approvals**: Approve/Send-back/Reject → `/decide`; Assign → `/assign`; assignee list → `/deciders`. `returned` applies no change.
- **Horizon**: "play to 2030/2050/2100" animates the real projection years client-side; enter-operations → `/portfolio` (financial) or `/home` (agri); granular grid → `/v1/me/hexes` (real scored ring).
- **Login**: role (admin/approver/analyst) × sector → real credential login.

## 4. Governance invariants intact
- 4-eyes: `decide` blocks the maker (422); assignment ≠ deciding (routing only); a `returned` request applies no mutation; approved `supply.*`/`config.*`/`submission.release` take the same apply path as a direct edit.
- Every demo tenant now has an approver (`approver@{meridian|iberia|nordkap|stellar|terra}.demo`), so 4-eyes is exercisable in every sector.

## 5. Build & tests
- `tsc --noEmit` and `npm run build` pass.
- `pytest`: **356 passed, 4 failed**. The 4 failures (`test_ranged_band` ×2, `test_validation_claim_is_not_circular`, `test_feed_staleness_gate`) are pre-existing, **data-state** failures — they assert on calibration fits (e.g. olive-drought r²=0.51) not seeded in this dev DB, and live entirely outside the four backend files this session touched (`approvals.py`, `tasks.py`, `on_demand.py`, the two migrations). Not regressions.

## Honest notes
- Demo data for triggers / reporting-entities / approver users was populated by **seed scripts** (direct DB writes). Seeds are not user actions, so they are intentionally un-audited; the corresponding **runtime** endpoints are all audited (table above).
- Gridded-hazard on-demand scoring for arbitrary H3 cells (drought/flood) still requires the async Celery worker; the fetch-free hazards (seismic/heat/storm) score in-request. Disclosed, not faked.
