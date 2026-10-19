import type { Message } from '../Details'

// The observed record as the server sends it (services/intelligence/realized_exposure.py): catalogued storms and
// earthquakes, or falls in national crop production, matched by distance — facts, never modelled. An event's strength
// is words: its storm class, its magnitude or its fall in production.

export type Kind = 'storm' | 'earthquake' | 'crop_shock'

export interface ObservedAsset { id: string; name: string; value_eur: number; closest_km: number }

export interface ObservedEvent {
  kind: Kind; id?: string; name?: string; year: number | null; date?: string | null
  strength: string; category?: number | null; max_wind_kt?: number | null; magnitude?: number; depth_km?: number | null
  closest_km?: number
  // a book's event: the assets within reach and the value they hold
  n_assets?: number; value_exposed_eur?: number; assets?: ObservedAsset[]
  // a production shock
  commodity?: string; country?: string; yoy_change_pct?: number; spend_eur?: number
}

export interface Source { kind: 'storm' | 'earthquake'; name: string; first: string; last: string; years: number }
export interface Definition { storm_radius_km: number; quake_radius_km: number; min_magnitude: number }
export type { Message }
