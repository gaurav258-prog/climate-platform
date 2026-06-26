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

export async function fetchCompoundEvents() {
  return get('/v1/scores/compound')
}
