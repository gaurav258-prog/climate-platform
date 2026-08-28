# Sovereign boundary overlay (compliance)

The maps use a global basemap (Esri) whose boundaries follow the **de-facto / UN depiction**, which does **not**
match every government's official position. For India specifically, maps shown in India must depict the
**Survey of India** official boundaries (Jammu & Kashmir, Ladakh incl. Aksai Chin, and Arunachal Pradesh as
part of India) — a **legal requirement** (Criminal Law Amendment Act; IT/geospatial rules). Rendering the
wrong official boundary is a legal risk, so we do **not** ship a fabricated one.

## How the overlay works

`RiskMap` (and, when wired, the other maps) call `addOfficialBoundaries()`, which fetches
**`/geo/official_boundaries.geojson`** and, *if present*, draws it as a line layer on top of the base. Until
that file is supplied it is a **graceful no-op** — no incorrect boundary is drawn.

## What to supply (procurement)

Drop an **authoritative** boundary GeoJSON at `web/public/geo/official_boundaries.geojson`:

- **Preferred:** the official India boundary from **Survey of India / Bhuvan (ISRO/NRSC)**
  (bhuvan.nrsc.gov.in) — GoI-authoritative by definition. Confirm the licence permits redistribution in the app.
- Or a **licensed commercial boundaries dataset** whose India depiction is GoI-compliant.

To *fully* mask the base map's de-facto lines near India (not just overlay the correct one), also add a filled
polygon in the same file matching the base ground colour over the disputed segments, drawn beneath the official
line — or, for the strongest guarantee, serve India-extent tiles from Bhuvan.

**Status:** overlay mechanism shipped and dormant; the authoritative GeoJSON is an external procurement item.
