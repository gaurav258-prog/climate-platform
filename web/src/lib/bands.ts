import { bucketLabel } from './hazards'

// One band for a 0–100 hazard score, as the platform defines it (core/types.py _BUCKET_THRESHOLDS: Low below 25,
// Elevated from 25, High from 50, Severe from 75) and names it (lib/hazards BUCKET_LABEL). Every map colours and
// names a score by these bands — never by cut-offs of its own (tests/unit/test_agri_maps_words.py holds them equal
// to the server's).
export const BANDS = [
  { key: 'L', from: 0, hex: '#5fb98c' },
  { key: 'M', from: 25, hex: '#e8b24c' },
  { key: 'H', from: 50, hex: '#e9744a' },
  { key: 'VH', from: 75, hex: '#d23b3b' },
] as const
export type Band = (typeof BANDS)[number]['key']
export const NOT_SCORED_HEX = '#8a94a6'

export const bandOf = (score: number): Band => [...BANDS].reverse().find(b => score >= b.from)?.key ?? 'L'
// plain hex, because leaflet and the SVG overlays write it into attributes (a CSS var() would not resolve there)
export const bandHex = (score: number | null | undefined): string =>
  score == null ? NOT_SCORED_HEX : BANDS.find(b => b.key === bandOf(score))!.hex
export const bandName = (score: number | null | undefined): string => score == null ? 'Not scored yet' : bucketLabel(bandOf(score))

// The bands in words, for a legend or a pop-up: 'Low below 25', 'Elevated from 25', …
export const bandRanges = (): { key: Band; hex: string; label: string }[] =>
  BANDS.map((b, i) => ({ key: b.key, hex: b.hex, label: i === 0 ? `${bucketLabel(b.key)} below ${BANDS[1].from}` : `${bucketLabel(b.key)} from ${b.from}` }))
