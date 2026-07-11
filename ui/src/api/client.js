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

/** Downloads a server-generated file (e.g. .xlsx) that needs the auth header —
 * a plain <a href> can't set Authorization, so fetch as a blob and trigger the
 * download in JS instead. */
export async function downloadFile(path, filename) {
  const res = await fetch(`${BASE}${path}`, { headers: headers() })
  if (!res.ok) return raise(res, path)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
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

/** Multipart file upload — no Content-Type header (browser sets the boundary). */
async function postFile(path, file) {
  const form = new FormData()
  form.append('file', file)
  const h = {}
  if (_apiKey) h['Authorization'] = `Bearer ${_apiKey}`
  const res = await fetch(`${BASE}${path}`, { method: 'POST', headers: h, body: form })
  if (!res.ok) return raise(res, path)
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

/** One asset: full projection + lending decision: { asset, risks:[...], valuation, valuation_audit:[...] }. */
export async function fetchAsset(assetId) {
  return get(`/v1/bank/asset/${assetId}`)
}

/** Override the recommended valuation discount for an asset (requires pricing.approve). */
export async function overrideValuation(assetId, discountPct, reason) {
  return post(`/v1/bank/asset/${assetId}/valuation-override`, { discount_pct: discountPct, reason })
}

/** Clear an override, reverting to the recommended discount (requires pricing.approve). */
export async function clearValuationOverride(assetId) {
  return send('DELETE', `/v1/bank/asset/${assetId}/valuation-override`)
}

/** TCFD/EU-Taxonomy disclosure pack: { rollup, assets, by_hazard, taxonomy, financed_emissions_tco2e }. */
export async function fetchDisclosure({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/bank/disclosure?scenario=${scenario}&horizon=${horizon}`)
}

/** Snapshot the current disclosure for one reporting period and queue it for checker release
 * (requires reports.publish). Returns { id, approval_request_id, status: 'draft' }. */
export async function createSubmission(body) {
  return post('/v1/bank/submissions', body)
}

/** Prior submissions for this org, newest period first (requires reports.view). */
export async function fetchSubmissions() {
  return get('/v1/bank/submissions')
}

/** One submission incl. its frozen snapshot (requires reports.view). */
export async function fetchSubmission(id) {
  return get(`/v1/bank/submissions/${id}`)
}

/** Quarter-over-quarter deltas across released submissions: { periods, deltas, cumulative?, status }.
 * status is 'insufficient_history' until at least 2 releases exist. */
export async function fetchSubmissionsTrend() {
  return get('/v1/bank/submissions/trend')
}

/** Bulk-upload a CSV of assets into your own org's loan book. Requires login (writes are
 * always tenant-scoped to the uploader). Returns { n_uploaded, n_cells, n_sync_scored, n_gridded_dispatched }. */
export async function uploadBankAssets(file) {
  return postFile('/v1/bank/assets/upload', file)
}

// ── Insurance (Loss-curve pricing) ────────────────────────────────────────

/** Property book → loss-curve pricing rollup: { org, rollup:{ n_policies, total_sum_insured_eur,
 * total_expected_annual_loss_eur, total_gross_premium_eur, by_bucket, top_policies } }. */
export async function fetchInsuranceSummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/insurance/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** Full property book: { rollup, policies:[...] }. */
export async function fetchInsurancePortfolio({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/insurance/portfolio?scenario=${scenario}&horizon=${horizon}`)
}

/** Bulk-upload a CSV of policies into your own org's property book. */
export async function uploadInsurancePolicies(file) {
  return postFile('/v1/insurance/policies/upload', file)
}

/** Parametric trigger monitoring: { org, rollup:{n_configured, n_triggered_now,
 * total_payout_if_triggered_eur}, triggered_now:[...], configured:[...] }. */
export async function fetchInsuranceTriggers({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/insurance/triggers?scenario=${scenario}&horizon=${horizon}`)
}

/** Set/update a policy's parametric trigger band (requires pricing.approve). */
export async function setTriggerConfig(policyId, hazardType, attachmentScore, exhaustionScore) {
  return post(`/v1/insurance/policies/${policyId}/trigger-config`,
    { hazard_type: hazardType, attachment_score: attachmentScore, exhaustion_score: exhaustionScore })
}

/** One policy — full projection + pricing + trigger + provenance: { policy, risks, audit }. */
export async function fetchInsurancePolicy(policyId) {
  return get(`/v1/insurance/policy/${policyId}`)
}

// ── Real estate (Portfolio & NOI impact) ──────────────────────────────────

/** Property book → portfolio + NOI-impact rollup: { org, rollup:{ n_properties,
 * total_value_eur, total_annual_noi_eur, total_discounted_value_eur,
 * total_expected_insurance_premium_eur, portfolio_noi_impact_pct, by_bucket, top_properties } }. */
export async function fetchRealEstateSummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/realestate/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** Full property book: { rollup, properties:[...] }. */
export async function fetchRealEstatePortfolio({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/realestate/portfolio?scenario=${scenario}&horizon=${horizon}`)
}

/** Physical-risk exposure + EU Taxonomy status: { rollup, by_hazard, taxonomy }. */
export async function fetchRealEstateDisclosure({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/realestate/disclosure?scenario=${scenario}&horizon=${horizon}`)
}

/** Bulk-upload a CSV of properties into your own org's portfolio. */
export async function uploadRealEstateProperties(file) {
  return postFile('/v1/realestate/properties/upload', file)
}

/** One property: full projection + valuation decision: { property, risks:[...], valuation, noi_impact, valuation_audit:[...] }. */
export async function fetchRealEstateProperty(propertyId) {
  return get(`/v1/realestate/property/${propertyId}`)
}

/** Override the recommended valuation discount for a property (requires pricing.approve). */
export async function overrideRealEstateValuation(propertyId, discountPct, reason) {
  return post(`/v1/realestate/property/${propertyId}/valuation-override`, { discount_pct: discountPct, reason })
}

/** Clear an override, reverting to the recommended discount (requires pricing.approve). */
export async function clearRealEstateValuationOverride(propertyId) {
  return send('DELETE', `/v1/realestate/property/${propertyId}/valuation-override`)
}

// ── Asset management (Portfolio climate VaR & screening) ──────────────────

/** Holdings book → portfolio climate VaR rollup: { org, rollup:{ n_holdings, n_flagged,
 * total_portfolio_value_eur, total_climate_var_eur, portfolio_climate_var_pct, by_bucket, top_holdings } }. */
export async function fetchAssetMgmtSummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/assetmgmt/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** Full holdings book: { rollup, holdings:[...] }. */
export async function fetchAssetMgmtPortfolio({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/assetmgmt/portfolio?scenario=${scenario}&horizon=${horizon}`)
}

/** Physical-risk exposure + EU Taxonomy status: { rollup, by_hazard, taxonomy }. */
export async function fetchAssetMgmtDisclosure({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/assetmgmt/disclosure?scenario=${scenario}&horizon=${horizon}`)
}

/** Bulk-upload a CSV of holdings into your own org's portfolio. */
export async function uploadAssetMgmtHoldings(file) {
  return postFile('/v1/assetmgmt/holdings/upload', file)
}

/** One holding: full projection + valuation decision: { holding, risks:[...], climate_var, valuation_audit:[...] }. */
export async function fetchAssetMgmtHolding(holdingId) {
  return get(`/v1/assetmgmt/holding/${holdingId}`)
}

// ── Securities portfolio (funds → issuers → footprints; physical + transition + SFDR PAI) ──

/** Org's funds with headline physical/transition/WACI: { funds:[{fund_id, name, physical_score, transition_score, waci, ...}] }. */
export async function fetchFunds({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/funds?scenario=${scenario}&horizon=${horizon}`)
}

/** One fund's climate report: { fund, physical, transition, pai } value-weighted. */
export async function fetchFund(fundId, { scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/funds/${fundId}?scenario=${scenario}&horizon=${horizon}`)
}

/** A fund's positions, each with issuer physical + transition risk. */
export async function fetchFundPositions(fundId, { scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/funds/${fundId}/positions?scenario=${scenario}&horizon=${horizon}`)
}

/** One issuer — full facility footprint + per-facility raw scores + transition + emissions. */
export async function fetchIssuer(issuerId, { scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/issuers/${issuerId}?scenario=${scenario}&horizon=${horizon}`)
}

/** Onboard holdings by ISIN into a fund. body: { as_of_date?, holdings:[{isin, market_value_eur, weight_pct?, asset_class?, currency?}] }.
 *  Returns an honest coverage report: matched/unmatched, footprint seeding, sector gaps. */
export async function onboardHoldings(fundId, body) {
  return post(`/v1/funds/${fundId}/holdings`, body)
}

/** Override the recommended climate-VaR discount for a holding (requires pricing.approve). */
export async function overrideAssetMgmtValuation(holdingId, discountPct, reason) {
  return post(`/v1/assetmgmt/holding/${holdingId}/valuation-override`, { discount_pct: discountPct, reason })
}

/** Clear an override, reverting to the recommended discount (requires pricing.approve). */
export async function clearAssetMgmtValuationOverride(holdingId) {
  return send('DELETE', `/v1/assetmgmt/holding/${holdingId}/valuation-override`)
}

// ── Agriculture / supply-chain (COGS-at-risk) ─────────────────────────────

/** Procurement book → COGS-at-risk rollup: { org, rollup, commodities, eudr }. */
export async function fetchSupplySummary({ scenario = 'baseline', horizon = 'current' } = {}) {
  return get(`/v1/supply/summary?scenario=${scenario}&horizon=${horizon}`)
}

/** Bulk-upload a CSV of sourcing plots into your own org's procurement book. */
export async function uploadSupplyPlots(file) {
  return postFile('/v1/supply/plots/upload', file)
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

export const overrideCommodityCogs = (commodityId, overrideCogsAtRiskP50Eur, reason) =>
  post(`/v1/supply/commodity/${commodityId}/override`, { override_cogs_at_risk_p50_eur: overrideCogsAtRiskP50Eur, reason })
export const clearCommodityCogsOverride = (commodityId) =>
  send('DELETE', `/v1/supply/commodity/${commodityId}/override`)

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

// ── Calc settings (per-org calculation-method triggers) ──────────────────
export const fetchCalcSettings = () => get('/v1/calc-settings')
export const updateCalcSettings = (body) => patch('/v1/calc-settings', body)

// ── Approvals (4-eyes) ────────────────────────────────────────────────────

export const fetchApprovals   = (status) => get(`/v1/approvals${status ? `?status=${status}` : ''}`)
export const createApproval   = (body) => post('/v1/approvals', body)
export const decideApproval   = (id, decision, reason) =>
  post(`/v1/approvals/${id}/decide`, { decision, reason })

// ── Service portal ────────────────────────────────────────────────────────

export const fetchServiceRequests = () => get('/v1/portal/requests')
export const createServiceRequest = (body) => post('/v1/portal/requests', body)
export const patchServiceRequest  = (id, status) => patch(`/v1/portal/requests/${id}`, { status })
