// Plain-language hazard names + severity traffic-light, shared across the app so every screen
// speaks the same language a non-specialist can read.

export const HAZARD_LABEL: Record<string, string> = {
  flood: 'Flooding (rivers & heavy rain)',
  coastal_flood: 'Sea-level rise & coastal flooding',
  storm: 'Storms & high winds',
  wildfire: 'Wildfire',
  drought: 'Drought',
  heat_acute: 'Extreme heat (heatwaves)',
  heat_chronic: 'Rising average heat',
  seismic: 'Earthquake',
  volcanic: 'Volcanic activity',
  pollution: 'Air pollution',
  frost: 'Frost & cold snaps',
  soil_water: 'Soil-water stress',
  heavy_precip: 'Heavy rainfall (extreme downpours)',
  landslide: 'Landslides & slope failure',
  temp_variability: 'Temperature swings (seasonal variability)',
  precip_variability: 'Erratic rainfall (variability)',
  changing_temp: 'Warming trend (projected)',
  changing_precip: 'Shifting rainfall (projected)',
  changing_wind: 'Shifting wind patterns (projected)',
  subsidence: 'Land subsidence (ground sinking)',
  coastal_erosion: 'Coastal erosion (shoreline retreat)',
  permafrost: 'Permafrost thaw',
  soil_erosion: 'Soil erosion',
  saline_intrusion: 'Saltwater intrusion (coastal aquifers)',
  glacial_lake_outburst: 'Glacial-lake outburst flood',
  ocean_acidification: 'Ocean acidification (marine)',
  avalanche: 'Avalanche',
  solifluction: 'Solifluction (periglacial soil creep)',
  soil_degradation: 'Soil degradation',
  severe_convective: 'Severe convective storm (tornado / hail)',
}

export const hazardLabel = (h?: string | null): string =>
  !h ? '—' : (HAZARD_LABEL[h] ?? h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))

// traffic-light by 0–100 severity: red severe / amber high / green moderate
export const sevColor = (s: number): string => (s >= 75 ? '#fb7185' : s >= 50 ? '#f0a860' : '#34d399')
export const sevLabel = (s: number): string => (s >= 75 ? 'Severe' : s >= 50 ? 'High' : 'Moderate')

// risk-bucket codes → plain words (never show VH/H/M/L to a user)
export const BUCKET_LABEL: Record<string, string> = { VH: 'Severe', H: 'High', M: 'Elevated', L: 'Low' }
export const bucketLabel = (b?: string | null): string => !b ? '—' : (BUCKET_LABEL[b] ?? b)

// regulatory-framework codes → the disclosure's readable name (never show bank_tcfd / sfdr_pai to a user)
export const FRAMEWORK_LABEL: Record<string, string> = {
  bank_tcfd: 'TCFD · EU Taxonomy',
  reit_tcfd: 'TCFD · EU Taxonomy',
  sfdr_pai: 'SFDR · Principal Adverse Impacts',
  csrd_e1: 'CSRD · ESRS E1',
  esrs_pack: 'ESRS Climate & Nature',
  insurer_climate: 'Climate / NatCat disclosure',
}
// map a known key; otherwise title-case it (handles free-typed / future framework names gracefully)
export const frameworkLabel = (f?: string | null): string =>
  !f ? '—' : (FRAMEWORK_LABEL[f] ?? f.replace(/[_-]/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))

// generic: turn an internal snake_case / colon code into a readable label (last resort for enums/fields)
export const prettify = (s?: string | null): string =>
  !s ? '—' : s.replace(/[_:]/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b\w/g, c => c.toUpperCase())

// Scenario keys are engine identifiers; users see the NGFS-style names.
export const SCENARIO_LABEL: Record<string, string> = {
  baseline: 'Current policies', orderly_1_5c: 'Orderly 1.5°C', disorderly_2c: 'Disorderly 2°C', hot_house_3_5c: 'Hot house 3.5°C',
}
export const scenarioLabel = (s?: string | null): string => !s ? '—' : (SCENARIO_LABEL[s] ?? prettify(s))
export const horizonLabel = (h?: string | null): string => !h ? '—' : h === 'current' ? 'today' : h

// Filing / task status codes → words.
export const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft', in_review: 'In review', returned: 'Returned', approved: 'Approved', attested: 'Attested', submitted: 'Submitted',
  accepted: 'Accepted', rejected: 'Rejected', superseded: 'Superseded', released: 'Released', no_submission: 'Not submitted',
  in_progress: 'In progress', none: 'Not filed', filed: 'Filed', pending: 'Awaiting approval', active: 'Active', expired: 'Expired',
  terminated: 'Terminated', computing: 'Computing', done: 'Done', failed: 'Failed', not_assessed: 'Not assessed',
}
export const statusLabel = (s?: string | null): string => !s ? '—' : (STATUS_LABEL[s] ?? prettify(s))

// Model identifiers are engine slugs; users see a name and a version.
const MODEL_NAME: [RegExp, string][] = [
  [/^wildfire-climatology/, 'Wildfire hazard climatology'], [/^wildfire-firms/, 'Wildfire fire-weather model'], [/^wildfire/, 'Wildfire model'],
  [/^windstorm/, 'Windstorm gust climatology'], [/^soil-water/, 'Soil-water aridity'], [/^volcanic/, 'Volcanic proximity (GVP)'],
  [/^landslide/, 'Landslide susceptibility (NASA)'], [/^subsidence/, 'Land subsidence susceptibility'], [/^permafrost/, 'Permafrost probability'],
  [/^severe-convective/, 'Severe convective environment'], [/^soil-erosion/, 'Soil erosion (GloSEM)'], [/^soil-degradation/, 'Land degradation (SDG 15.3.1)'],
  [/^solifluction/, 'Solifluction susceptibility'], [/^saline-intrusion/, 'Saline intrusion screen'], [/^glof/, 'Glacial-lake outburst proximity'],
  [/^coastal-erosion/, 'Coastal erosion (JRC)'], [/^ocean-acidification/, 'Ocean acidification'], [/^avalanche/, 'Avalanche terrain screen'],
  [/^frost/, 'Frost climatology'], [/^heavy-precip/, 'Heavy precipitation climatology'], [/^changing-temp/, 'Changing temperature (CMIP6)'],
  [/^changing-precip/, 'Changing precipitation (CMIP6)'], [/^changing-wind/, 'Changing wind (CMIP6)'], [/^temp-variability/, 'Temperature variability'],
  [/^precip-variability/, 'Precipitation variability'], [/^sea-level/, 'Sea-level rise (IPCC AR6)'], [/^pollution/, 'Air quality (WHO guideline)'],
  [/^transition/, 'Transition risk (NGFS)'], [/^flood-multievent/, 'Flood multi-event model'], [/^flood/, 'Flood model'],
  [/^heat-climatology/, 'Heat climatology'], [/^drought/, 'Drought (SPEI)'], [/^storm/, 'Cyclone wind field'], [/^seismic/, 'Seismic (USGS)'],
  [/^fallback_rule_based/, 'Rule-based baseline'], [/^df-/, 'Damage function'],
]
export const modelLabel = (mv?: string | null): string => {
  if (!mv) return '—'
  const hit = MODEL_NAME.find(([re]) => re.test(mv))
  const ver = mv.match(/v(\d+(?:\.\d+)?)/)?.[1]
  return hit ? `${hit[1]}${ver ? ` v${ver}` : ''}` : prettify(mv)
}
