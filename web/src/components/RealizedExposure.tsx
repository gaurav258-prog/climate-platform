import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'

// Realized exposure — the real, named climate events that have ALREADY crossed this book (observed, not
// modelled). The retrospective counterpart to the forward scores; every row is a catalogued storm, earthquake
// or observed yield shock matched to the org's own assets.

interface REvent {
  kind: string; name?: string; commodity?: string; country?: string; year: number | null
  severity: string; n_assets?: number; value_exposed_eur?: number; closest_km?: number
  yoy_change_pct?: number; spend_eur?: number
}
interface Realized {
  available: boolean; sector?: string; n_events?: number; n_storms?: number; n_earthquakes?: number
  since_year?: number | null; headline?: string; events?: REvent[]; peak_value_exposed_eur?: number
  spend_exposed_eur?: number; note?: string
}

const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

function tone(e: REvent): string {
  if (e.kind === 'crop_shock') return (e.yoy_change_pct ?? 0) <= -20 ? '#D23B3B' : '#E8853C'
  if (e.kind === 'earthquake') return '#B5731A'
  return '#2F6FB0'
}
function icon(e: REvent): string {
  return e.kind === 'crop_shock' ? '🌾' : e.kind === 'earthquake' ? '⊕' : '🌀'
}

export default function RealizedExposure() {
  const q = useQuery({ queryKey: ['realized-exposure'], queryFn: () => api.get<Realized>('/v1/realized-exposure') })
  const d = q.data
  if (!d || !d.available || !d.events || d.events.length === 0) return null

  return (
    <Card className="p-5" style={{ borderColor: 'var(--color-blued)', background: 'linear-gradient(180deg,#0e2338,var(--color-panel))' }}>
      <div className="flex items-center gap-2 mb-1">
        <History size={16} className="text-[var(--color-sky)]" />
        <span className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-sky)]">Realized exposure · observed history</span>
      </div>
      <h2 className="display text-2xl font-semibold text-[#F4EFE6] leading-tight max-w-2xl">
        {d.headline}
      </h2>
      <p className="text-[12.5px] text-[var(--color-mute)] mt-1.5 max-w-2xl">
        Not a projection — real catalogued events (named storms, dated earthquakes, measured yield failures) matched to your own assets. Climate risk isn't a 2050 problem; here's what has already crossed your book.
      </p>

      <div className="mt-4 divide-y divide-[color-mix(in_oklab,var(--color-sky)_14%,transparent)] border-t border-[color-mix(in_oklab,var(--color-sky)_14%,transparent)]">
        {d.events.slice(0, 8).map((e, i) => (
          <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[12.5px]">
            <span className="text-[13px] w-5 text-center">{icon(e)}</span>
            <span className="font-semibold text-[#F4EFE6] min-w-0">{e.kind === 'crop_shock' ? `${e.commodity} · ${e.country}` : e.name}</span>
            <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ background: `${tone(e)}22`, color: tone(e) }}>{e.severity}</span>
            <span className="mono text-[11px] text-[var(--color-faint)]">{e.year ?? '—'}</span>
            <span className="flex-1 min-w-0" />
            {e.kind === 'crop_shock' ? (
              <span className="mono text-[11px] text-[var(--color-mute)] tabular-nums">{eur(e.spend_eur)} spend exposed</span>
            ) : (
              <span className="mono text-[11px] text-[var(--color-mute)] tabular-nums">{e.n_assets} asset{e.n_assets === 1 ? '' : 's'} · {eur(e.value_exposed_eur)} · {e.closest_km}km</span>
            )}
          </div>
        ))}
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        {d.sector === 'manufacturer'
          ? 'Observed national yield failures (>5% YoY decline) matched to the commodity × origin you source.'
          : `${d.n_storms ?? 0} storms (IBTrACS) + ${d.n_earthquakes ?? 0} earthquakes (USGS) within the felt radius of your assets.`} Observed catalogue events only — nothing projected.
      </div>
    </Card>
  )
}
