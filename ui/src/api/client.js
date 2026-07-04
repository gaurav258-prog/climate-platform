const BASE = '/api'
const TOKEN_KEY = 'ci_token'

// Rehydrate the session token from storage so a page refresh stays logged in.
let _apiKey = (typeof localStorage !== 'undefined' && localStorage.getItem(TOKEN_KEY)) || null

export function setApiKey(key) { _apiKey = key }

export function setAuthToken(token) {
  _apiKey = token
  try { localStorage.setItem(TOKEN_KEY, token) } catch {}
}

export function clearAuthToken() {
  _apiKey = null
  try { localStorage.removeItem(TOKEN_KEY) } catch {}
}

export function hasToken() { return !!_apiKey }

function headers() {
  const h = { 'Content-Type': 'application/json' }
  if (_apiKey) h['Authorization'] = `Bearer ${_apiKey}`
  return h
}

/** Raise an Error whose .status + .body carry the API's error detail. */
async function raise(res, path) {
  let body = null
  try { body = await res.json() } catch {}
  const msg = body?.error?.message || body?.detail || body?.error || `${res.status} ${path}`
  const err = new Error(typeof msg === 'string' ? msg : `${res.status} ${path}`)
  err.status = res.status
  err.body = body
  throw err
}

async function get(path) {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) return raise(res, path)
  return res.json()
}

async function send(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method, headers: headers(), body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) return raise(res, path)
  if (res.status === 204) return null
  return res.json()
}
const post = (path, body) => send('POST', path, body)
const patch = (path, body) => send('PATCH', path, body)

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

/**
 * Live aggregates over the current canonical scores — per hazard: cell count,
 * bucket distribution, score range, model version, data vintage, top cells.
 * Powers the platform overview and the industry modules.
 */
export async function fetchScoresSummary() {
  return get('/v1/scores/summary')
}

// ── Consolidated platform UI (public, read-only) ──────────────────────────

/** H3 risk cells for the live map: { hazard, resolution, count, cells:[{h3_cell, score, bucket}] }. */
export async function fetchGeoScores(hazard, maxCells = 12000) {
  return get(`/v1/platform/geo?hazard=${hazard}&max_cells=${maxCells}`)
}

/** Model registry with honest metrics: { models:[{hazard_type, model_version, algorithm, auc, avg_precision, validation_note, is_active, ...}] }. */
export async function fetchModels() {
  return get('/v1/platform/models')
}

// ── Any-address hazard lookup (public, no auth) ───────────────────────────

/** Score every hazard for an address: { latitude, longitude, display_name, h3_cell, hazards:[...], overall:{...} }. */
export async function lookupScore(address) {
  return get(`/v1/lookup/score?address=${encodeURIComponent(address)}`)
}

/** Poll a pending gridded-hazard job: { hazard:{...}, overall:{...} }. */
export async function pollLookup(lookupId) {
  return get(`/v1/lookup/score/${lookupId}`)
}

/** Daily forecast-verification series for a region: { region, points:[{as_of_date, predicted_count, sigma, observed_count, z_score, ...}] }. */
export async function fetchVerification(region = 'Venezuela M7.5') {
  return get(`/v1/platform/verification?region=${encodeURIComponent(region)}`)
}

/** Recent seismic events from the live feed: { count, events:[{magnitude, depth_km, lat, lon, origin_time, region_name, ...}] }. */
export async function fetchSeismicEvents(days = 14, minMag = 4.5) {
  return get(`/v1/platform/seismic-events?days=${days}&min_mag=${minMag}`)
}

// ── Banking flagship (loan book projected onto the golden source) ─────────────

/** Loan book + per-asset projected risk + rollup: { org_id, rollup, assets:[{asset_id, asset_name, value_eur, headline_score, headline_bucket, hazards:[...], ...}] }. */
export async function fetchPortfolio({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/bank/portfolio?scenario=${scenario}&horizon=${horizon}`)
}

/** Command-center rollup: { org, rollup:{ n_assets, total_value_eur, value_at_risk_eur, pct_value_at_risk, by_bucket, top_assets } }. */
export async function fetchBankSummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/bank/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** One asset: full projection across hazards/scenarios + provenance: { asset, risks:[...] }. */
export async function fetchAsset(assetId) {
  return get(`/v1/bank/asset/${assetId}`)
}

/** TCFD/EU-Taxonomy disclosure pack: { rollup, by_hazard, taxonomy, financed_emissions_tco2e }. */
export async function fetchDisclosure({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/bank/disclosure?scenario=${scenario}&horizon=${horizon}`)
}

// ── Insurance (Loss-curve pricing) ────────────────────────────────────────

/** Property book → loss-curve pricing rollup: { org, rollup:{ n_policies, total_sum_insured_eur,
 * total_expected_annual_loss_eur, total_gross_premium_eur, by_bucket, top_policies } }. */
export async function fetchInsuranceSummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/insurance/summary?scenario=${scenario}&horizon=${horizon}`)
}

// ── Agriculture / supply-chain (COGS-at-risk) ─────────────────────────────

/** Procurement book → COGS-at-risk rollup: { org, rollup, commodities, eudr }. */
export async function fetchSupplySummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/supply/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** Full book: { commodities, products, bom, plots }. */
export async function fetchSupplyPortfolio({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/supply/portfolio?scenario=${scenario}&horizon=${horizon}`)
}

/** One sourcing plot: { plot, risks, note }. */
export async function fetchSupplyPlot(plotId) {
  return get(`/v1/supply/plot/${plotId}`)
}

/** Impact-function backtests (credibility record): { impact_version, events:[...] }. */
export async function fetchSupplyValidation() {
  return get('/v1/supply/validation')
}

/** Ag hazard models + per-commodity calibration status: { hazard_models, commodities, frost_note }. */
export async function fetchSupplyModels() {
  return get('/v1/supply/models')
}

/** Early-warning alerts: { n_alerts, alerts:[...], pending:[...] }. */
export async function fetchSupplySignals({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/supply/signals?scenario=${scenario}&horizon=${horizon}`)
}

/** EUDR overlay + CSRD pack: { rollup, csrd:[...], eudr:{summary, plots} }. */
export async function fetchSupplyDisclosure({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/supply/disclosure?scenario=${scenario}&horizon=${horizon}`)
}

// ── Auth (user login sessions) ────────────────────────────────────────────

/** Log in; stores the JWT and returns { user, org, roles, permissions, entitlements }. */
export async function login(email, password) {
  const data = await post('/v1/auth/login', { email, password })
  setAuthToken(data.access_token)
  return data
}

export async function logout() {
  try { await post('/v1/auth/logout') } catch {}
  clearAuthToken()
}

/** Current profile from the stored token: { user, org, roles, permissions, entitlements }. */
export async function fetchMe() {
  return get('/v1/auth/me')
}

// ── Admin ─────────────────────────────────────────────────────────────────

export const fetchAdminUsers   = () => get('/v1/admin/users')
export const createAdminUser   = (body) => post('/v1/admin/users', body)
export const patchAdminUser    = (id, body) => patch(`/v1/admin/users/${id}`, body)
export const fetchRoles        = () => get('/v1/admin/roles')
export const fetchPermissions  = () => get('/v1/admin/permissions')
export const setRolePermissions = (roleId, codes) =>
  patch(`/v1/admin/roles/${roleId}/permissions`, { permission_codes: codes })
export const fetchAudit = ({ actor, action, limit = 100 } = {}) => {
  const q = new URLSearchParams({ limit })
  if (actor) q.set('actor', actor)
  if (action) q.set('action', action)
  return get(`/v1/admin/audit?${q}`)
}

// ── Approvals (4-eyes) ────────────────────────────────────────────────────

export const fetchApprovals   = (status) => get(`/v1/approvals${status ? `?status=${status}` : ''}`)
export const createApproval   = (body) => post('/v1/approvals', body)
export const decideApproval   = (id, decision, reason) =>
  post(`/v1/approvals/${id}/decide`, { decision, reason })

// ── Service portal ────────────────────────────────────────────────────────

export const fetchServiceRequests = () => get('/v1/portal/requests')
export const createServiceRequest = (body) => post('/v1/portal/requests', body)
export const patchServiceRequest  = (id, status) => patch(`/v1/portal/requests/${id}`, { status })
