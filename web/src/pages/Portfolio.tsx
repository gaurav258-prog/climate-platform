import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, Download } from 'lucide-react'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'

// The financial-sector operating surface behind the Horizon globe. One page, sector-adaptive: the org's
// type (bank / insurer / asset_manager / reit) chooses which real book endpoint to read and how to label
// its rollup — every number is the projected book from the golden source, nothing invented. Agriculture
// keeps its own workspace (Sourcing/Cogs/…); this is the equivalent operating book for the four financials.

interface Hazard { hazard: string; score: number; bucket: string }
interface Valuation { discounted_value_eur: number; is_overridden: boolean }
interface Asset {
  region?: string; lat?: number; lon?: number
  headline_score: number | null; headline_bucket: string | null; headline_hazard: string | null
  hazards: Hazard[]; valuation?: Valuation
  [k: string]: unknown   // id/name/type/value + rollup live under sector-specific keys
}
type Rollup = Record<string, number | unknown>
type PortfolioResp = { scenario: string; horizon: string; rollup: Rollup } & Record<string, unknown>

type Kpi = { label: string; field?: string; num?: string; den?: string; fmt: 'eur' | 'pct' | 'frac'; tone?: string }
interface Cfg {
  prefix: string; listKey: string; noun: string
  idKey: string; nameKey: string; typeKey: string; valueKey: string
  kpis: Kpi[]
}
// The ONLY thing that differs between the four financial books — list key, per-item value key, rollup labels.
const SECTORS: Record<string, Cfg> = {
  bank: {
    prefix: 'bank', listKey: 'assets', noun: 'financed assets',
    idKey: 'asset_id', nameKey: 'asset_name', typeKey: 'asset_type', valueKey: 'value_eur',
    kpis: [
      { label: 'Book value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Value at risk (High+)', field: 'value_at_risk_eur', fmt: 'eur', tone: '#E9744A' },
      { label: '% of book at risk', field: 'pct_value_at_risk', fmt: 'pct' },
      { label: 'scored', num: 'n_scored', den: 'n_assets', fmt: 'frac' },
    ],
  },
  insurer: {
    prefix: 'insurance', listKey: 'policies', noun: 'insured locations',
    idKey: 'policy_id', nameKey: 'policy_name', typeKey: 'policy_type', valueKey: 'sum_insured_eur',
    kpis: [
      { label: 'Sum insured', field: 'total_sum_insured_eur', fmt: 'eur' },
      { label: 'Expected annual loss', field: 'total_expected_annual_loss_eur', fmt: 'eur', tone: '#E9744A' },
      { label: 'Loss ratio', field: 'portfolio_loss_ratio_pct', fmt: 'pct' },
      { label: 'priced', num: 'n_priced', den: 'n_policies', fmt: 'frac' },
    ],
  },
  asset_manager: {
    prefix: 'assetmgmt', listKey: 'holdings', noun: 'holdings',
    idKey: 'holding_id', nameKey: 'holding_name', typeKey: 'sector', valueKey: 'position_value_eur',
    kpis: [
      { label: 'Portfolio value', field: 'total_portfolio_value_eur', fmt: 'eur' },
      { label: 'Climate VaR', field: 'total_climate_var_eur', fmt: 'eur', tone: '#E9744A' },
      { label: 'VaR %', field: 'portfolio_climate_var_pct', fmt: 'pct' },
      { label: 'scored', num: 'n_scored', den: 'n_holdings', fmt: 'frac' },
    ],
  },
  reit: {
    prefix: 'realestate', listKey: 'properties', noun: 'properties',
    idKey: 'property_id', nameKey: 'property_name', typeKey: 'property_type', valueKey: 'property_value_eur',
    kpis: [
      { label: 'Portfolio value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Annual NOI', field: 'total_annual_noi_eur', fmt: 'eur' },
      { label: 'NOI impact', field: 'portfolio_noi_impact_pct', fmt: 'pct', tone: '#E8B24C' },
      { label: 'scored', num: 'n_scored', den: 'n_properties', fmt: 'frac' },
    ],
  },
}

const HORIZONS = ['current', '2030', '2050', '2100'] as const
const SCENARIOS: [string, string][] = [['baseline', 'Today'], ['disorderly_2c', 'Disorderly 2°C']]

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
function col(l: number): [number, number, number] { return l < 28 ? [95, 185, 140] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59] }
const BUCKET: Record<string, string> = { VH: 'severe', H: 'high', M: 'elevated', L: 'low' }

function kpiValue(k: Kpi, r: Rollup | undefined): string {
  if (!r) return '—'
  if (k.fmt === 'frac') return `${(r[k.num!] as number) ?? 0}/${(r[k.den!] as number) ?? 0}`
  const v = r[k.field!] as number | undefined
  if (v == null) return '—'
  return k.fmt === 'pct' ? `${v}%` : eur(v)
}

export default function Portfolio() {
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const cfg = SECTORS[type]
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState<string>('current')
  const [open, setOpen] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['fin-portfolio', cfg?.prefix, scenario, horizon],
    queryFn: () => api.get<PortfolioResp>(`/v1/${cfg!.prefix}/portfolio?scenario=${scenario}&horizon=${horizon}`),
    enabled: !!cfg,
  })

  if (!cfg) return (
    <div className="fadeup"><Eyebrow>Portfolio</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">This workspace has no financial book — the Portfolio view is for bank, insurer, asset-manager and REIT tenants.</Card>
    </div>
  )

  const r = q.data?.rollup
  const items = (q.data?.[cfg.listKey] as Asset[] | undefined) ?? []
  const sorted = [...items].sort((a, b) => (b.headline_score ?? -1) - (a.headline_score ?? -1))

  return (
    <div className="fadeup space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>{profile?.org?.name} · {cfg.noun}</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Portfolio</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">Your {cfg.noun} projected onto the golden source — worst-hazard physical risk and per-asset detail. Every figure is the real projected book; a cell reads “—” where an asset isn’t yet scored.</p>
        </div>
        <div className="flex flex-col gap-2 items-end">
          <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
            {SCENARIOS.map(([k, lbl]) => (
              <button key={k} onClick={() => setScenario(k)} className={`px-3 py-1.5 rounded-md text-[12px] transition ${scenario === k ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>
            ))}
          </div>
          <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
            {HORIZONS.map(h => (
              <button key={h} onClick={() => setHorizon(h)} className={`px-3 py-1.5 rounded-md text-[12px] transition ${horizon === h ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{h === 'current' ? 'Now' : h}</button>
            ))}
          </div>
        </div>
      </div>

      {/* rollup KPIs — sector-labelled */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cfg.kpis.map(k => <Kpi key={k.label} label={k.label} value={kpiValue(k, r)} tone={k.tone} />)}
      </div>

      {/* the book */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
          <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">The book · worst-hazard first</div>
          <button
             className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"
             onClick={() => download(`/v1/${cfg.prefix}/portfolio.xlsx?scenario=${scenario}&horizon=${horizon}`, `${cfg.prefix}-portfolio.xlsx`).catch(() => alert('Could not download the export.'))}>
            <Download size={13} /> Export .xlsx
          </button>
        </div>
        {q.isLoading ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">loading the book…</div>
          : sorted.length === 0 ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">No {cfg.noun} located yet.</div>
          : (
          <div className="divide-y divide-[var(--color-line)]">
            {sorted.map((a) => {
              const id = String(a[cfg.idKey] ?? '')
              const name = String(a[cfg.nameKey] ?? '—')
              const atype = a[cfg.typeKey] ? String(a[cfg.typeKey]) : null
              const value = a[cfg.valueKey] as number | null
              const sc = a.headline_score
              const [rr, gg, bb] = col(sc ?? 0)
              const bk = a.headline_bucket ? BUCKET[a.headline_bucket] : null
              const isOpen = open === id
              return (
                <div key={id}>
                  <button onClick={() => setOpen(isOpen ? null : id)} className="w-full text-left px-5 py-3 flex items-center gap-4 hover:bg-[var(--color-bg-2)] transition">
                    <ChevronRight size={15} className={`shrink-0 text-[var(--color-faint)] transition-transform ${isOpen ? 'rotate-90' : ''}`} />
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] text-[var(--color-ink)] truncate">{name}</div>
                      <div className="mono text-[11px] text-[var(--color-faint)] truncate">{[a.region, atype?.replace(/_/g, ' ')].filter(Boolean).join(' · ') || '—'}</div>
                    </div>
                    <div className="mono text-[13px] text-[var(--color-mute)] tabular-nums shrink-0 w-24 text-right">{eur(value)}</div>
                    <div className="shrink-0 w-28 text-right">
                      {sc == null ? <span className="mono text-[12px] text-[var(--color-faint)]">—</span>
                        : <span className="inline-flex items-center gap-1.5 mono text-[12px]" style={{ color: `rgb(${rr},${gg},${bb})` }}>
                            <span className="w-1.5 h-1.5 rounded-full" style={{ background: `rgb(${rr},${gg},${bb})` }} />
                            {Math.round(sc)}/100{bk ? ` · ${bk}` : ''}
                          </span>}
                    </div>
                  </button>
                  {isOpen && (
                    <div className="px-5 pb-4 pt-1 bg-[var(--color-bg-2)]">
                      <div className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-2">Worst hazard: {a.headline_hazard ?? '—'} · scenario {scenario} · {horizon}</div>
                      <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5">
                        {(a.hazards ?? []).length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No hazard scores under this scenario/horizon yet.</div>}
                        {(a.hazards ?? []).map(h => { const [hr, hg, hb] = col(h.score); return (
                          <div key={h.hazard} className="flex items-center justify-between gap-3 text-[12.5px] border-b border-[var(--color-line)] py-1">
                            <span className="text-[var(--color-mute)] capitalize">{h.hazard.replace(/_/g, ' ')}</span>
                            <span className="mono tabular-nums" style={{ color: `rgb(${hr},${hg},${hb})` }}>{Math.round(h.score)}/100 · {BUCKET[h.bucket] ?? h.bucket}</span>
                          </div>) })}
                      </div>
                      {a.valuation && (
                        <div className="mono text-[11.5px] text-[var(--color-faint)] mt-3">
                          risk-adjusted value {eur(a.valuation.discounted_value_eur)}{a.valuation.is_overridden ? ' · analyst override on file' : ''}
                          {a.lat != null && a.lon != null ? ` · ${Math.abs(a.lat).toFixed(1)}°${a.lat >= 0 ? 'N' : 'S'}, ${Math.abs(a.lon).toFixed(1)}°${a.lon >= 0 ? 'E' : 'W'}` : ''}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>
      {q.isError && <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the book — reload, or sign in again.</div>}
    </div>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="display text-[26px] leading-none" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="mono text-[10.5px] tracking-[0.14em] uppercase text-[var(--color-faint)] mt-2">{label}</div>
    </Card>
  )
}
