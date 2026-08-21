import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { History, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'
import AssetDrawer, { type DrawerCfg } from './AssetDrawer'

// Realized exposure — the real, named climate events that have ALREADY crossed this book (observed, not
// modelled). The retrospective counterpart to the forward scores; every row is a catalogued storm, earthquake
// or observed yield shock matched to the org's own assets. Each located event expands to the individual assets
// it crossed, and each of those drills into the full asset/policy drawer — the same drawer Portfolio opens.

interface REAsset { id: string; name: string; value_eur: number; closest_km: number }
interface REvent {
  kind: string; name?: string; commodity?: string; country?: string; year: number | null
  severity: string; n_assets?: number; value_exposed_eur?: number; closest_km?: number
  yoy_change_pct?: number; spend_eur?: number; assets?: REAsset[]
}
interface Realized {
  available: boolean; sector?: string; n_events?: number; n_storms?: number; n_earthquakes?: number
  since_year?: number | null; headline?: string; events?: REvent[]; peak_value_exposed_eur?: number
  spend_exposed_eur?: number; note?: string
}

// org type -> the per-asset detail drawer config (same drawers Portfolio uses). Agri drills at commodity level.
const SECTOR_CFG: Record<string, DrawerCfg> = {
  bank: { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  insurer: { prefix: 'insurance', itemKey: 'policy', nameKey: 'policy_name', valueKey: 'sum_insured_eur', typeKey: 'policy_type', auditKey: 'audit', overrideMode: 'trigger' },
  reit: { prefix: 'realestate', itemKey: 'property', nameKey: 'property_name', valueKey: 'property_value_eur', typeKey: 'property_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  asset_manager: { prefix: 'assetmgmt', itemKey: 'holding', nameKey: 'holding_name', valueKey: 'position_value_eur', typeKey: 'sector', valuationKey: 'climate_var', auditKey: 'valuation_audit', overrideMode: 'valuation' },
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
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  const [drawerId, setDrawerId] = useState<string | null>(null)
  if (!d || !d.available || !d.events || d.events.length === 0) return null
  const cfg = d.sector ? SECTOR_CFG[d.sector] : undefined

  return (
    <>
    {/* the card is permanently dark, so force its subtree into dark-token context — otherwise the theme's
        muted/faint text tokens resolve to dark values in light mode and read dark-on-dark (unreadable). */}
    <div data-theme="dark">
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
        {d.events.slice(0, 8).map((e, i) => {
          const drillable = e.kind !== 'crop_shock' && !!e.assets?.length
          const open = openIdx === i
          return (
            <div key={i}>
              <div onClick={() => drillable && setOpenIdx(open ? null : i)}
                className={`flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[12.5px] ${drillable ? 'cursor-pointer' : ''}`}>
                {drillable
                  ? <ChevronRight size={13} className={`text-[var(--color-sky)] transition-transform ${open ? 'rotate-90' : ''}`} />
                  : <span className="w-[13px]" />}
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
              {open && e.assets && (
                <div className="pl-11 pb-2 space-y-0.5">
                  {e.assets.map(a => (
                    <div key={a.id} onClick={() => cfg && setDrawerId(a.id)}
                      className={`flex items-center gap-2 text-[11.5px] py-0.5 ${cfg ? 'cursor-pointer hover:text-[var(--color-sky)]' : ''}`}>
                      <span className="text-[var(--color-mute)] hover:text-[var(--color-sky)] min-w-0 truncate">{a.name}</span>
                      <span className="flex-1" />
                      <span className="mono text-[10.5px] text-[var(--color-faint)] tabular-nums">{eur(a.value_eur)} · {a.closest_km}km</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        {d.sector === 'manufacturer'
          ? 'Observed national yield failures (>5% YoY decline) matched to the commodity × origin you source.'
          : `${d.n_storms ?? 0} storms (IBTrACS) + ${d.n_earthquakes ?? 0} earthquakes (USGS) within the felt radius of your assets.`} Observed catalogue events only — nothing projected. {cfg && d.sector !== 'manufacturer' && <span className="text-[var(--color-sky)]">Expand an event to see the assets it crossed.</span>}
      </div>
    </Card>
    </div>
    {/* drawer stays outside the forced-dark wrapper so it follows the app theme */}
    {drawerId && cfg && <AssetDrawer cfg={cfg} id={drawerId} onClose={() => setDrawerId(null)} onChanged={() => q.refetch()} />}
    </>
  )
}
