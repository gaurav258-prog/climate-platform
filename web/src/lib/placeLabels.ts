// Self-contained English place labels for the globe.
// Inline GeoJSON (no external tile source) so names always render — on the globe and flat —
// and are English by construction. Continents render large/uppercase, countries smaller.
// Centroids are approximate label anchors, not borders.

type Row = [name: string, lon: number, lat: number]

const CONTINENTS: Row[] = [
  ['Africa', 21, 4], ['Europe', 15, 52], ['Asia', 90, 45], ['North America', -100, 45],
  ['South America', -60, -15], ['Oceania', 140, -25], ['Antarctica', 20, -80],
]

const COUNTRIES: Row[] = [
  // Europe
  ['Spain', -3.7, 40.3], ['Portugal', -8, 39.6], ['France', 2.4, 47], ['Italy', 12.5, 42.8],
  ['Germany', 10.4, 51.2], ['United Kingdom', -1.5, 52.8], ['Greece', 22, 39], ['Poland', 19.4, 52],
  ['Ukraine', 31, 49], ['Romania', 25, 46], ['Netherlands', 5.6, 52.2], ['Turkey', 35, 39],
  // Africa
  ['Morocco', -6.5, 31.8], ['Algeria', 2.6, 28], ['Tunisia', 9.5, 34], ['Egypt', 30, 27],
  ["Côte d'Ivoire", -5.5, 7.6], ['Ghana', -1.2, 7.9], ['Nigeria', 8, 9.6], ['Ethiopia', 39.6, 8.6],
  ['Kenya', 37.9, 0.2], ['Tanzania', 34.8, -6.4], ['South Africa', 24, -29], ['Cameroon', 12.4, 5.7],
  ['Uganda', 32.3, 1.4], ['Senegal', -14.5, 14.5],
  // Asia / Middle East
  ['India', 79, 22], ['China', 104, 35], ['Indonesia', 118, -2.5], ['Vietnam', 106, 16],
  ['Iran', 53, 32.4], ['Saudi Arabia', 45, 24], ['Pakistan', 69, 30], ['Kazakhstan', 67, 48],
  ['Japan', 138, 37], ['Thailand', 101, 15], ['Philippines', 122, 12],
  // Americas
  ['United States', -98, 39], ['Canada', -106, 56], ['Mexico', -102, 23], ['Brazil', -51, -10],
  ['Argentina', -64, -35], ['Colombia', -73, 4], ['Peru', -75, -9.5], ['Chile', -71, -33],
  ['Ecuador', -78.5, -1.5],
  // Oceania
  ['Australia', 134, -25], ['New Zealand', 172, -42],
]

const feat = (kind: 'continent' | 'country', [name, lon, lat]: Row) => ({
  type: 'Feature' as const,
  geometry: { type: 'Point' as const, coordinates: [lon, lat] },
  properties: { name, kind },
})

export const PLACE_LABELS = {
  type: 'FeatureCollection' as const,
  features: [
    ...CONTINENTS.map(r => feat('continent', r)),
    ...COUNTRIES.map(r => feat('country', r)),
  ],
}
