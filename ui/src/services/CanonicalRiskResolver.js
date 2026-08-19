/**
 * Canonical Risk Resolver — the UI side of reconciliation #1.
 *
 * The bank product used to take an asset's physical risk straight from the
 * uploaded CSV column (Physical_Risk_Score_0_100). That number was whatever the
 * bank typed in — not the platform's golden source. This resolver replaces it:
 * for each asset it computes the H3 cell from lat/lng and fetches the canonical
 * score from the platform (`/v1/scores/cell/{h3}`), so what the report shows is
 * the same score the engine produces.
 *
 * Provenance is explicit and never faked. Each asset ends up with one of:
 *   'canonical'           — a real platform score was found (use it)
 *   'no_canonical_score'  — platform reachable, but this cell isn't scored yet
 *   'platform_unreachable'— could not reach the platform at all
 *   'no_coordinates'      — asset has no lat/lng, so it can't be matched
 * We NEVER silently substitute the uploaded CSV number for a canonical score.
 */

import { latLngToCell } from 'h3-js'
import { fetchCellScores } from '../api/client'
import { normalizeHazard, normalizeScenario, scoreToBucket } from '../constants/vocabulary'

const H3_RESOLUTION = 8 // must match core/config.py H3_RESOLUTION

/**
 * Resolve canonical physical risk for a list of parsed assets.
 * @param assets   array from CSVParser (need latitude/longitude)
 * @param options  { scenario, horizon, hazardType }
 * @returns { assets: enriched[], summary: {...} }
 */
export async function resolveCanonicalRisk(assets, options = {}) {
  const scenario = normalizeScenario(options.scenario || 'baseline')
  const horizon = options.horizon || 'current'
  const hazardFilter = options.hazardType ? normalizeHazard(options.hazardType) : null

  const enriched = []
  const summary = {
    total: assets.length,
    canonical: 0,
    noCanonicalScore: 0,
    platformUnreachable: 0,
    noCoordinates: 0,
    scenario,
    horizon,
  }

  for (const asset of assets) {
    const lat = Number(asset.latitude)
    const lng = Number(asset.longitude)

    if (!Number.isFinite(lat) || !Number.isFinite(lng) || (lat === 0 && lng === 0)) {
      summary.noCoordinates++
      enriched.push({ ...asset, h3Cell: null, canonicalRisk: null, riskSource: 'no_coordinates' })
      continue
    }

    const h3Cell = latLngToCell(lat, lng, H3_RESOLUTION)

    let resp
    try {
      resp = await fetchCellScores(h3Cell, { scenario, horizon })
    } catch (err) {
      summary.platformUnreachable++
      enriched.push({ ...asset, h3Cell, canonicalRisk: null, riskSource: 'platform_unreachable', error: String(err) })
      continue
    }

    const scores = (resp && resp.scores) || []
    const match = hazardFilter
      ? scores.find(s => normalizeHazard(s.hazard_type) === hazardFilter)
      : highestScore(scores)

    if (!match) {
      summary.noCanonicalScore++
      enriched.push({ ...asset, h3Cell, canonicalRisk: null, riskSource: 'no_canonical_score' })
      continue
    }

    const score = Number(match.risk_score)
    summary.canonical++
    enriched.push({
      ...asset,
      h3Cell,
      canonicalRisk: {
        hazardType: normalizeHazard(match.hazard_type),
        riskScore: score,
        riskBucket: match.risk_bucket || scoreToBucket(score),
        modelVersion: match.model_version,
        scoredAt: match.scored_at,
        scenario,
        horizon,
      },
      riskSource: 'canonical',
    })
  }

  return { assets: enriched, summary }
}

/** Pick the highest-scoring hazard for a cell (the binding physical risk). */
function highestScore(scores) {
  if (!scores || scores.length === 0) return null
  return scores.reduce((hi, s) =>
    (Number(s.risk_score) > Number(hi.risk_score) ? s : hi), scores[0])
}

/**
 * The physical risk a report should use for an asset: the canonical score when
 * present, otherwise null with the reason. Callers must surface the reason —
 * they must not fall back to the uploaded number and call it canonical.
 */
export function effectivePhysicalRisk(enrichedAsset) {
  if (enrichedAsset.riskSource === 'canonical') {
    return { value: enrichedAsset.canonicalRisk.riskScore, source: 'canonical' }
  }
  return { value: null, source: enrichedAsset.riskSource }
}
