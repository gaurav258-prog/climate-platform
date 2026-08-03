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
}

export const hazardLabel = (h?: string | null): string =>
  !h ? '—' : (HAZARD_LABEL[h] ?? h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()))

// traffic-light by 0–100 severity: red severe / amber high / green moderate
export const sevColor = (s: number): string => (s >= 75 ? '#fb7185' : s >= 50 ? '#f0a860' : '#34d399')
export const sevLabel = (s: number): string => (s >= 75 ? 'Severe' : s >= 50 ? 'High' : 'Moderate')
