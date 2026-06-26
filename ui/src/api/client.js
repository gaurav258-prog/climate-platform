const BASE = '/api'

let _apiKey = null

export function setApiKey(key) { _apiKey = key }

function headers() {
  const h = { 'Content-Type': 'application/json' }
  if (_apiKey) h['Authorization'] = `Bearer ${_apiKey}`
  return h
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json()
}

export async function fetchPortfolioScores(hazardType, limit = 5000) {
  return get(`/v1/scores/portfolio?hazard_type=${hazardType}&limit=${limit}`)
}

export async function fetchAlerts() {
  return get('/v1/scores/portfolio/alerts')
}

export async function fetchCellHistory(h3Cell, hazardType) {
  return get(`/v1/scores/cell/${h3Cell}/history?hazard_type=${hazardType}`)
}

/**
 * Current canonical score(s) for one H3 cell. This is the projection entry
 * point the bank report flow uses: an asset's physical risk comes from here,
 * not from an uploaded CSV column. Returns the platform's ScoreListResponse
 * { total, scores: [{ hazard_type, risk_score, risk_bucket, model_version,
 * scored_at, ... }] }.
 */
export async function fetchCellScores(h3Cell, { scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/scores/cell/${h3Cell}?scenario=${scenario}&horizon=${horizon}`)
}

export async function fetchCompoundEvents() {
  return get('/v1/scores/compound')
}
