# GHCN-Daily global station extremes (Africa, Asia, Latin America, Oceania)
- Source: NOAA NCEI Access Data Service https://www.ncei.noaa.gov/access/services/data/v1 (dataset daily-summaries, TMIN/TMAX/PRCP, 1991-01-01..2020-12-31); inventory/station list https://www.ncei.noaa.gov/pub/data/ghcn/daily/ (ghcnd-inventory.txt, ghcnd-stations.txt, in data/ghcn/). Public domain, no credentials.
- Acquired 2026-09-21 by scripts/ingest_ghcn_global.py (4 threads, 0.5 s pause per request). Output: extremes.json.
- Selection: 1 station per 1 degree box, >=20 complete years (>=330 daily values of each element); hash-ordered cap 150 boxes per region; up to 5 candidates per box.
- Counts: africa 0, asia 48, latin_america_caribbean 3, oceania 114 (total 165) from 600 boxes tried.
- Caveats: Africa yields no station meeting the completeness rule (TMIN/TMAX records too gappy); Latin America only 3; Oceania is mostly Australia; Asia mostly a few countries. Cap means not all eligible boxes were tried (Asia 1170 candidate boxes, 150 tried). Stations are mostly airports/synoptic sites, so a coastal/urban siting bias applies.
