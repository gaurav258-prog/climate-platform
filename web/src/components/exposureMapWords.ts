import { balance } from '../lib/money.ts'
import { hazardLabel } from '../lib/hazards.ts'
import { countryName } from '../lib/codeWords.ts'

// A region of the supervisor's exposure map (services/geo/regions.py aggregate_by_region).
export interface Region { key: string; name: string; country: string | null; kind: 'nuts3' | 'h3'; geometry: GeoJSON.Geometry
  n_sites: number; value_eur: number; max_score: number | null; mean_score: number | null; worst_hazard: string | null; entities: string[] }

// a region in words — its name, its country where the name does not already say it, and what kind of area it is (the
// catalogue's names.region_kind) — then what sits in it. Leaflet sets a tooltip as HTML, so every text from the data
// (a region's or an entity's name) is escaped: an entity named with markup is shown as text, never run in the page.
const REGION_KIND: Record<string, string> = { nuts3: 'Region', h3: 'Grid cell' }
const esc = (t: string) => t.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
export function regionTooltip(r: Region): string {
  const country = countryName(r.country)
  const where = country && !r.name.includes(country) ? `${r.name} · ${country}` : r.name
  const score = r.max_score != null
    ? `worst ${Math.round(r.max_score)}/100${r.worst_hazard ? ` · ${esc(hazardLabel(r.worst_hazard))}` : ''}${r.mean_score != null ? ` · average ${Math.round(r.mean_score)}` : ''}`
    : 'not yet scored'
  return `<b>${esc(where)}</b> · ${REGION_KIND[r.kind] ?? 'Area'}<br/>${r.n_sites} site${r.n_sites === 1 ? '' : 's'} · ${esc(balance(r.value_eur))}<br/>${score}`
    + (r.entities.length ? `<br/><span style="opacity:.7">${r.entities.map(esc).join(' · ')}</span>` : '')
}
