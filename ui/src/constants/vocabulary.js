/**
 * Canonical vocabulary — UI mirror of core/types.py.
 *
 * This is the JavaScript side of the platform's single source of truth for
 * hazard / scenario / time-horizon terms. It MUST stay in sync with
 * core/types.py (Python). When you change one, change the other.
 *
 * The UI's job is to stop emitting stray dialects (e.g. "Heat_Stress",
 * "1.5C_Paris_Aligned") into uploads and API calls. Run user/CSV input through
 * the normalize* helpers before sending it anywhere downstream.
 */

export const HAZARD_VALUES = [
  'flood', 'heat_acute', 'heat_chronic', 'wildfire', 'drought', 'storm', 'seismic',
]

export const SCENARIO_VALUES = [
  'baseline', 'orderly_1_5c', 'disorderly_2c', 'hot_house_3_5c',
]

export const TIME_HORIZON_VALUES = ['current', '2030', '2050', '2100']

export const RISK_BUCKET_VALUES = ['L', 'M', 'H', 'VH']

// score (0–100) → bucket. One definition, matches core.types.score_to_bucket.
export function scoreToBucket(score) {
  if (score < 0 || score > 100) throw new Error(`risk score out of range [0,100]: ${score}`)
  if (score < 25) return 'L'
  if (score < 50) return 'M'
  if (score < 75) return 'H'
  return 'VH'
}

const key = (raw) =>
  String(raw).trim().toLowerCase()
    .replace(/[\s.-]+/g, '_')
    .replace(/__+/g, '_')

const HAZARD_ALIASES = {
  flood: 'flood', flooding: 'flood', river_flood: 'flood', fluvial: 'flood',
  coastal_flood: 'flood', pluvial: 'flood', urban_flood: 'flood',
  heat: 'heat_acute', heat_acute: 'heat_acute', heat_stress: 'heat_acute',
  heatwave: 'heat_acute', heat_wave: 'heat_acute', extreme_heat: 'heat_acute',
  extreme_heat_waves: 'heat_acute',
  heat_chronic: 'heat_chronic', chronic_heat: 'heat_chronic',
  wildfire: 'wildfire', fire: 'wildfire', bushfire: 'wildfire', forest_fire: 'wildfire',
  drought: 'drought', water_stress: 'drought',
  storm: 'storm', extreme_weather: 'storm', cyclone: 'storm', hurricane: 'storm',
  typhoon: 'storm', hail: 'storm', wind: 'storm',
  seismic: 'seismic', earthquake: 'seismic', quake: 'seismic',
}

const SCENARIO_ALIASES = {
  baseline: 'baseline', current_policies: 'baseline', now: 'baseline',
  orderly_1_5c: 'orderly_1_5c', orderly: 'orderly_1_5c', '1_5c': 'orderly_1_5c',
  '15c': 'orderly_1_5c', paris: 'orderly_1_5c', paris_aligned: 'orderly_1_5c',
  '1_5c_paris_aligned': 'orderly_1_5c', ssp1_2_6: 'orderly_1_5c', ssp126: 'orderly_1_5c',
  net_zero: 'orderly_1_5c', net_zero_2050: 'orderly_1_5c',
  disorderly_2c: 'disorderly_2c', disorderly: 'disorderly_2c', '2c': 'disorderly_2c',
  '2_0c': 'disorderly_2c', '2c_moderate_transition': 'disorderly_2c',
  moderate: 'disorderly_2c', ssp2_4_5: 'disorderly_2c', ssp245: 'disorderly_2c',
  hot_house_3_5c: 'hot_house_3_5c', hot_house: 'hot_house_3_5c', hothouse: 'hot_house_3_5c',
  '3_5c': 'hot_house_3_5c', '4c': 'hot_house_3_5c', '4_0c': 'hot_house_3_5c',
  '4c_business_as_usual': 'hot_house_3_5c', business_as_usual: 'hot_house_3_5c',
  bau: 'hot_house_3_5c', ssp5_8_5: 'hot_house_3_5c', ssp585: 'hot_house_3_5c',
}

const TIME_HORIZON_ALIASES = {
  current: 'current', now: 'current', baseline: 'current', spot: 'current',
  short_term: '2030', short: '2030', near_term: '2030', '2030': '2030',
  medium_term: '2050', medium: '2050', mid_term: '2050', '2050': '2050',
  long_term: '2100', long: '2100', far_term: '2100', '2100': '2100',
}

export function normalizeHazard(raw) {
  const v = HAZARD_ALIASES[key(raw)]
  if (!v) throw new Error(`unknown hazard '${raw}'. Canonical: ${HAZARD_VALUES.join(', ')}`)
  return v
}

export function normalizeScenario(raw) {
  const v = SCENARIO_ALIASES[key(raw)]
  if (!v) throw new Error(`unknown scenario '${raw}'. Canonical: ${SCENARIO_VALUES.join(', ')}`)
  return v
}

export function normalizeTimeHorizon(raw) {
  const v = TIME_HORIZON_ALIASES[key(raw)]
  if (!v) throw new Error(`unknown time horizon '${raw}'. Canonical: ${TIME_HORIZON_VALUES.join(', ')}`)
  return v
}
