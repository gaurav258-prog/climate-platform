import { useMemo, useState } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ReferenceDot,
} from 'recharts'
import { ArrowUpRight, ArrowDownRight, Minus, LineChart as LineIcon, Table2, Download, X } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

// Analytics — the forward-looking read: how the book's climate exposure moves across the two parameters
// (scenario × horizon). The centrepiece is the scenario TRAJECTORY (value-at-risk over Now→2100, one line
// per warming pathway); below it, per-hazard small-multiples show what drives the change. Every figure is the
// projected book from the golden source — nothing invented; a table view carries the exact numbers.

interface HazardBlock { exposed_value_eur: number }
interface TaxBlock { value_eur: number }
interface Disc { by_hazard: Record<string, HazardBlock>; taxonomy: Record<string, TaxBlock>; financed_emissions_tco2e?: { scope1: number; scope2: number; scope3: number } }

const PREFIX: Record<string, string> = { bank: 'bank', asset_manager: 'assetmgmt', reit: 'realestate' }
// scenario severity ramp (cool→hot), colours validated for both themes (dataviz skill) via CSS tokens
const SCEN = [
  { key: 'baseline', label: 'Today', color: 'var(--scn-baseline)' },
  { key: 'orderly_1_5c', label: 'Orderly 1.5°C', color: 'var(--scn-orderly)' },
  { key: 'disorderly_2c', label: 'Disorderly 2°C', color: 'var(--scn-disorderly)' },
  { key: 'hot_house_3_5c', label: 'Hot-house 3.5°C', color: 'var(--scn-hot)' },
] as const
const HZ: [string, string][] = [['current', 'Now'], ['2030', '2030'], ['2050', '2050'], ['2100', '2100']]

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(0)}m` : `€${Math.round(n / 1e3)}k`
const tco2e = (n?: number | null) => n == null ? '—' : Math.round(n).toLocaleString('en-GB')
const totExposed = (d?: Disc) => d ? Object.values(d.by_hazard).reduce((s, v) => s + (v.exposed_value_eur || 0), 0) : null
const sumEm = (d?: Disc) => d?.financed_emissions_tco2e ? d.financed_emissions_tco2e.scope1 + d.financed_emissions_tco2e.scope2 + d.financed_emissions_tco2e.scope3 : null

export default function Analytics() {
  const { profile } = useAuth()
  const prefix = PREFIX[profile?.org?.type ?? '']
  const canDrill = profile?.org?.type === 'bank'   // only the loan book returns the per-asset array to drill into
  // the two parameters the user drives — a live "what-if": scenario × horizon. They recompute the headline
  // figures and mark the point on the trajectory. `sel` is the scenario key; `hz` is the horizon index.
  const [sel, setSel] = useState('hot_house_3_5c')
  const [hz, setHz] = useState(3)   // 0..3 → Now / 2030 / 2050 / 2100
  const [asTable, setAsTable] = useState(false)
  const [drill, setDrill] = useState<string | null>(null)   // hazard key for the drill-down drawer

  // the full 4×4 grid, one query per (scenario, horizon) — SLIM (aggregates only; the per-asset array is
  // fetched on demand for drill-down), cached individually
  const specs = useMemo(() => SCEN.flatMap(s => HZ.map(([h]) => ({ s: s.key, h }))), [])
  const results = useQueries({
    queries: specs.map(({ s, h }) => ({
      queryKey: ['analytics-grid', prefix, s, h],
      enabled: !!prefix,
      staleTime: 5 * 60 * 1000,
      queryFn: () => api.get<Disc>(`/v1/${prefix}/disclosure?scenario=${s}&horizon=${h}&slim=1`),
    })),
  })
  const at = (scen: string, hIdx: number): Disc | undefined => results[specs.findIndex(x => x.s === scen && x.h === HZ[hIdx][0])]?.data
  const loading = results.some(r => r.isLoading)

  if (!prefix) return (
    <div className="fadeup"><Eyebrow>Analytics</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">Forward-looking exposure analytics are available for the loan / holdings / property book. This workspace has no such book here.</Card>
    </div>
  )

  // Value at risk is the ONLY genuinely scenario/horizon-projected metric — it moves with the warming
  // pathway. Taxonomy-eligibility and financed emissions are point-in-time BOOK facts (a classification and a
  // PCAF footprint) that the physical projection doesn't touch, so they're shown as current-book KPIs, not
  // scenario trajectories. `hasEm` gates the emissions KPI (asset managers / insurers carry no such block).
  const hasEm = SCEN.some((s, si) => HZ.some((_, hi) => sumEm(results[si * 4 + hi]?.data) != null))

  // trajectory rows for the hero line chart: value exposed at High+, one column per scenario
  const traj = HZ.map(([, lbl], hi) => {
    const row: Record<string, number | string | null> = { hz: lbl }
    SCEN.forEach(s => { row[s.key] = totExposed(at(s.key, hi)) })
    return row
  })

  // headline: value at risk for the SELECTED pathway/horizon (delta vs the same pathway Now) + its sparkline;
  // taxonomy & emissions are the current book facts.
  const scen = SCEN.find(s => s.key === sel) ?? SCEN[3]
  const sparkVar = HZ.map(([, l], hi) => ({ hz: l, v: totExposed(at(sel, hi)) ?? 0 }))
  const now = sparkVar[0].v, end = sparkVar[hz].v
  const taxBook = at('baseline', 0)?.taxonomy?.eligible?.value_eur ?? null   // point-in-time book fact
  const emBook = sumEm(at('baseline', 0))                                    // point-in-time book fact
  const hzLabel = HZ[hz][1]
  const heroY = totExposed(at(sel, hz))   // the marker point on the hero (selected pathway/horizon)
  // tighten the hero y-axis to the data band (padded) so the divergence is legible
  const vals = traj.flatMap(r => SCEN.map(s => r[s.key]).filter(v => typeof v === 'number')) as number[]
  const yDomain: [number, number] = vals.length ? [Math.min(...vals) * 0.94, Math.max(...vals) * 1.04] : [0, 1]

  // hazard facets for the selected scenario: top hazards by exposure at the selected horizon
  const hazards = useMemo(() => {
    const bh = at(sel, hz)?.by_hazard ?? at(sel, 0)?.by_hazard ?? {}
    return Object.entries(bh).filter(([, v]) => (v?.exposed_value_eur ?? 0) > 0)
      .sort((a, b) => b[1].exposed_value_eur - a[1].exposed_value_eur).slice(0, 6).map(([k]) => k)
  }, [results, sel, hz])
  const hazTraj = (hazKey: string) => HZ.map(([, lbl], hi) => ({ hz: lbl, v: at(sel, hi)?.by_hazard?.[hazKey]?.exposed_value_eur ?? 0 }))

  return (
    <div className="fadeup space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>{profile?.org?.name} · analytics</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Forward-looking analytics</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">How the book’s climate exposure moves as the world warms — value at risk along each scenario pathway, and the hazards driving it.</p>
        </div>
        <button onClick={() => setAsTable(t => !t)} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:border-[var(--color-sky)] transition">
          {asTable ? <><LineIcon size={13} /> Charts</> : <><Table2 size={13} /> Table</>}
        </button>
      </div>

      {/* what-if — the two parameters the user drives; everything below recomputes live */}
      <Card className="px-5 py-4">
        <div className="grid md:grid-cols-2 gap-x-8 gap-y-3">
          <div>
            <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Warming pathway</div>
            <div className="flex flex-wrap gap-1.5">
              {SCEN.map(s => (
                <button key={s.key} onClick={() => setSel(s.key)}
                  className={`px-2.5 py-1.5 rounded-lg text-[12px] inline-flex items-center gap-1.5 border transition ${sel === s.key ? 'border-transparent text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}
                  style={sel === s.key ? { background: `color-mix(in oklab, ${s.color} 16%, transparent)` } : undefined}>
                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />{s.label}
                </button>
              ))}
            </div>
          </div>
          <div>
            <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Horizon</div>
            <div className="flex gap-1.5">
              {HZ.map(([, l], i) => (
                <button key={l} onClick={() => setHz(i)}
                  className={`flex-1 px-2.5 py-1.5 rounded-lg text-[12px] border transition ${hz === i ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{l}</button>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* headline KPIs — value at risk is the forward number (recomputed for the selected pathway × horizon,
          delta vs the same pathway Now, with its trajectory sparkline). Taxonomy-eligible and financed
          emissions are point-in-time BOOK facts — they don't move with the warming pathway, so no delta/spark. */}
      <div className={`grid gap-3 ${hasEm ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
        <Kpi label="Value at risk" sub={`${scen.label} · ${hzLabel}`} value={eur(end)} base={now} end={end} spark={sparkVar} mark={hz} tone={scen.color} worseUp loading={loading} />
        <Kpi label="Taxonomy-eligible" sub="book · point-in-time" value={eur(taxBook)} tone="var(--scn-baseline)" loading={loading} />
        {hasEm && <Kpi label="Financed emissions" sub="book · point-in-time · tCO₂e" value={tco2e(emBook)} tone="var(--scn-baseline)" loading={loading} />}
      </div>

      {asTable ? <TrajTable at={at} /> : (
        <>
          {/* hero — scenario trajectories for the selected metric */}
          <Card className="p-0 overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-[var(--color-line)]">
              <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Value exposed at High+ · by warming pathway</span>
              <div className="flex items-center gap-3">
                <div className="flex flex-wrap gap-x-3 gap-y-1">
                  {SCEN.map(s => (
                    <button key={s.key} onClick={() => setSel(s.key)} title="Focus this pathway"
                      className="inline-flex items-center gap-1.5 text-[11px] transition" style={{ color: sel === s.key ? 'var(--color-ink)' : 'var(--color-mute)', opacity: sel === s.key ? 1 : 0.6 }}>
                      <span className="w-3 rounded-full" style={{ height: sel === s.key ? 4 : 3, background: s.color }} />{s.label}
                    </button>
                  ))}
                </div>
                <button onClick={() => exportCsv(traj)} title="Download the projection as CSV" className="text-[var(--color-faint)] hover:text-[var(--color-sky)] shrink-0"><Download size={14} /></button>
              </div>
            </div>
            <div className="px-4 py-6" style={{ height: 380 }}>
              {loading ? <Skeleton /> : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={traj} margin={{ top: 8, right: 20, bottom: 4, left: 8 }}>
                    <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 5" vertical={false} />
                    <XAxis dataKey="hz" tick={{ fill: 'var(--color-faint)', fontSize: 11.5 }} axisLine={{ stroke: 'var(--color-line)' }} tickLine={false} dy={8} padding={{ left: 12, right: 12 }} />
                    <YAxis domain={yDomain} tickFormatter={eur} tick={{ fill: 'var(--color-faint)', fontSize: 11 }} axisLine={false} tickLine={false} width={58} />
                    <Tooltip content={(p) => <HeroTip {...p} fmt={eur} />} cursor={{ stroke: 'var(--color-line-2)', strokeWidth: 1, strokeDasharray: '3 3' }} />
                    {/* the selected horizon, marked live */}
                    <ReferenceLine x={hzLabel} stroke="var(--color-line-2)" strokeDasharray="4 4" />
                    {SCEN.map(s => {
                      const on = s.key === sel
                      return (
                        <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color}
                          strokeWidth={on ? 3 : 1.75} strokeOpacity={on ? 1 : 0.32}
                          dot={on ? { r: 3, fill: s.color, strokeWidth: 0 } : false} activeDot={{ r: 5, stroke: 'var(--color-bg-2)', strokeWidth: 2 }}
                          isAnimationActive={false} connectNulls />
                      )
                    })}
                    {typeof heroY === 'number' && <ReferenceDot x={hzLabel} y={heroY} r={6} fill={scen.color} stroke="var(--color-bg-2)" strokeWidth={2.5} isFront />}
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
            <div className="px-5 py-2.5 border-t border-[var(--color-line)] mono text-[9.5px] text-[var(--color-faint)] leading-relaxed">
              Parametric warming shift applied to the climate-physical hazard scores at each horizon; excludes non-climate drivers (policy, fuel, labour). <span className="text-[var(--color-mute)]">Today / Now</span> equals the current-basis figures a filing freezes.
            </div>
          </Card>

          {/* hazard facets — single-hue small-multiples for the selected pathway */}
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
              <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">What drives it · hazard trajectory</span>
              <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: scen.color }} />{scen.label}</span>
            </div>
            {loading ? <Card className="p-10"><Skeleton /></Card> : (
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {hazards.map(h => {
                  const d = hazTraj(h); const a = d[0].v, b = d[hz].v
                  return (
                    <Card key={h} className={`p-3 ${canDrill ? 'cursor-pointer hover:border-[var(--color-sky)] transition' : ''}`} onClick={canDrill ? () => setDrill(h) : undefined}>
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <div className="text-[12.5px] text-[var(--color-ink)] leading-snug capitalize">{hazardLabel(h)}{canDrill && <span className="text-[var(--color-faint)] group-hover:text-[var(--color-sky)]"> →</span>}</div>
                        <Delta base={a} cmp={b} />
                      </div>
                      <div className="mono text-[17px] tabular-nums text-[var(--color-ink)] mb-1">{eur(b)}<span className="text-[10.5px] text-[var(--color-faint)] ml-1.5">at {hzLabel}</span></div>
                      <div style={{ height: 56 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={d} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
                            <defs>
                              <linearGradient id={`g-${h}`} x1="0" y1="0" x2="0" y2="1">
                                <stop offset="0%" stopColor="var(--chart-seq)" stopOpacity={0.35} />
                                <stop offset="100%" stopColor="var(--chart-seq)" stopOpacity={0.02} />
                              </linearGradient>
                            </defs>
                            <Tooltip content={<FacetTip />} cursor={{ stroke: 'var(--color-line-2)' }} />
                            <Area type="monotone" dataKey="v" stroke="var(--chart-seq)" strokeWidth={2} fill={`url(#g-${h})`} isAnimationActive={false} dot={false} activeDot={{ r: 3.5, stroke: 'var(--color-bg-2)', strokeWidth: 1.5 }} />
                            <ReferenceLine x={hzLabel} stroke="var(--color-line-2)" strokeDasharray="3 3" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="flex justify-between mono text-[9px] text-[var(--color-faint)] mt-0.5"><span>Now {eur(a)}</span><span>{hzLabel}</span></div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}

      {drill && canDrill && <DrillDrawer prefix={prefix} hazard={drill} scenario={sel} horizonKey={HZ[hz][0]}
        scenarioLabel={scen.label} horizonLabel={hzLabel} onClose={() => setDrill(null)} />}
    </div>
  )
}

interface DrillAsset { asset_id: string; asset_name: string; value_eur: number | null; country: string | null; region: string | null; hazards: { hazard: string; score: number | null; bucket: string | null }[] }
const BUCKET: Record<string, { label: string; color: string }> = {
  VH: { label: 'Severe', color: 'var(--color-bad)' }, H: { label: 'High', color: 'var(--scn-disorderly)' },
  M: { label: 'Elevated', color: 'var(--scn-orderly)' }, L: { label: 'Low', color: 'var(--color-faint)' },
}

// drill-down — the exposures driving one hazard at the selected pathway/horizon. Fetches the FULL disclosure
// (with the per-asset array) on demand, filters to assets exposed to this hazard at High+, ranks by value.
function DrillDrawer({ prefix, hazard, scenario, horizonKey, scenarioLabel, horizonLabel, onClose }:
  { prefix: string; hazard: string; scenario: string; horizonKey: string; scenarioLabel: string; horizonLabel: string; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['analytics-drill', prefix, scenario, horizonKey],
    queryFn: () => api.get<{ assets: DrillAsset[] }>(`/v1/${prefix}/disclosure?scenario=${scenario}&horizon=${horizonKey}`),
  })
  const rows = (q.data?.assets ?? [])
    .map(a => ({ a, hz: a.hazards?.find(x => x.hazard === hazard) }))
    .filter(x => x.hz && (x.hz.bucket === 'H' || x.hz.bucket === 'VH'))
    .sort((x, y) => (y.a.value_eur ?? 0) - (x.a.value_eur ?? 0))
    .slice(0, 20)
  const total = rows.reduce((s, x) => s + (x.a.value_eur ?? 0), 0)
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)]" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-center justify-between">
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Exposures driving this hazard</div>
            <div className="text-[15px] font-semibold capitalize mt-0.5">{hazardLabel(hazard)}</div>
            <div className="mono text-[10px] text-[var(--color-faint)]">{scenarioLabel} · {horizonLabel}</div>
          </div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>
        {q.isLoading ? <div className="p-8 text-[13px] text-[var(--color-faint)]">reading the book…</div>
          : rows.length === 0 ? <div className="p-8 text-[13px] text-[var(--color-faint)]">No exposures at High+ for this hazard under the selected pathway.</div>
          : (
            <div className="p-5">
              <div className="mono text-[11px] text-[var(--color-mute)] mb-3">{rows.length} exposure{rows.length === 1 ? '' : 's'} at High+ · {eur(total)} exposed</div>
              <div className="space-y-1.5">
                {rows.map(({ a, hz }) => (
                  <div key={a.asset_id} className="flex items-center gap-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <div className="text-[12.5px] text-[var(--color-ink)] truncate">{a.asset_name}</div>
                      <div className="mono text-[10px] text-[var(--color-faint)]">{[a.region, a.country].filter(Boolean).join(', ') || '—'}</div>
                    </div>
                    <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0" style={{ color: BUCKET[hz!.bucket ?? 'L']?.color, background: `color-mix(in oklab, ${BUCKET[hz!.bucket ?? 'L']?.color} 15%, transparent)` }}>{BUCKET[hz!.bucket ?? 'L']?.label ?? hz!.bucket}{hz!.score != null ? ` ${Math.round(hz!.score)}` : ''}</span>
                    <span className="mono text-[12px] tabular-nums text-[var(--color-ink)] w-20 text-right shrink-0">{eur(a.value_eur)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
      </div>
    </div>
  )
}

function HeroTip({ active, payload, label, fmt = eur }: { active?: boolean; payload?: { dataKey: string; value: number; color: string }[]; label?: string; fmt?: (n?: number | null) => string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] shadow-xl px-3 py-2">
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">{label}</div>
      {[...payload].sort((a, b) => b.value - a.value).map(p => {
        const s = SCEN.find(x => x.key === p.dataKey)
        return (
          <div key={p.dataKey} className="flex items-center gap-2 text-[12px]">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
            <span className="text-[var(--color-mute)] flex-1">{s?.label ?? p.dataKey}</span>
            <span className="mono tabular-nums text-[var(--color-ink)]">{fmt(p.value)}</span>
          </div>
        )
      })}
    </div>
  )
}

// download the value-at-risk scenario × horizon grid as CSV
function exportCsv(traj: Record<string, number | string | null>[]) {
  const head = ['Horizon', ...SCEN.map(s => s.label)]
  const rows = traj.map(r => [r.hz, ...SCEN.map(s => { const v = r[s.key]; return typeof v === 'number' ? Math.round(v) : '' })])
  const csv = [head, ...rows].map(r => r.join(',')).join('\n')
  const blob = new Blob([`# Value exposed at High+ (EUR) — projected scenario x horizon\n${csv}\n`], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'analytics-value-at-risk.csv'; a.click()
  URL.revokeObjectURL(url)
}

function FacetTip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] shadow-xl px-2.5 py-1.5 text-[11.5px]">
      <span className="mono text-[var(--color-faint)]">{label}</span> <span className="mono tabular-nums text-[var(--color-ink)] ml-1.5">{eur(payload[0].value)}</span>
    </div>
  )
}

function Skeleton() {
  return <div className="w-full h-full rounded-lg animate-pulse" style={{ background: 'color-mix(in oklab, var(--color-line) 40%, transparent)' }} />
}

// direction-aware delta chip (more exposure = adverse = red by default)
function Delta({ base, cmp, worseUp = true }: { base?: number | null; cmp?: number | null; worseUp?: boolean }) {
  if (base == null || cmp == null) return null
  const d = cmp - base, pct = base ? (d / base) * 100 : null
  const tone = d === 0 ? 'var(--color-mute)' : (d > 0) === worseUp ? 'var(--color-bad)' : 'var(--color-good)'
  const Icon = d > 0 ? ArrowUpRight : d < 0 ? ArrowDownRight : Minus
  return (
    <span className="inline-flex items-center gap-0.5 mono text-[11px] tabular-nums shrink-0" style={{ color: tone }}>
      <Icon size={12} />{d === 0 ? '—' : `${d > 0 ? '+' : '−'}${Math.abs(pct ?? 0).toFixed(0)}%`}
    </span>
  )
}

function Kpi({ label, sub, value, base, end, spark, mark, tone, worseUp = false, loading }:
  { label: string; sub: string; value: string; base?: number | null; end?: number | null; spark?: { hz: string; v: number }[]; mark?: number; tone: string; worseUp?: boolean; loading?: boolean }) {
  const gid = `kg-${label.replace(/\W/g, '')}`
  return (
    <Card className="px-5 py-4">
      <div className="text-[13px] text-[var(--color-ink)] font-medium">{label}</div>
      <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-1">{sub}</div>
      <div className="flex items-end justify-between gap-2 mt-3">
        <div className="display text-[30px] leading-none tabular-nums">{loading ? '—' : value}</div>
        <div className="mb-0.5"><Delta base={base} cmp={end} worseUp={worseUp} /></div>
      </div>
      {spark && (
        <div style={{ height: 40 }} className="mt-3 -mx-1">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={spark} margin={{ top: 3, right: 2, bottom: 0, left: 2 }}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={tone} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={tone} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Tooltip content={<FacetTip />} cursor={{ stroke: 'var(--color-line-2)' }} />
              <Area type="monotone" dataKey="v" stroke={tone} strokeWidth={1.75} fill={`url(#${gid})`} isAnimationActive={false} dot={false} activeDot={{ r: 3, stroke: 'var(--color-bg-2)', strokeWidth: 1.5 }} />
              {mark != null && spark[mark] && <ReferenceDot x={spark[mark].hz} y={spark[mark].v} r={3.5} fill={tone} stroke="var(--color-bg-2)" strokeWidth={1.5} isFront />}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

// accessible table view of the same trajectory grid (dataviz: a table view always exists)
function TrajTable({ at }: { at: (scen: string, hIdx: number) => Disc | undefined }) {
  return (
    <Card className="p-0 overflow-x-auto">
      <table className="w-full text-[12.5px]">
        <thead>
          <tr className="text-left border-b border-[var(--color-line)]">
            <th className="px-4 py-2.5 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium">Pathway · value at High+</th>
            {HZ.map(([, l]) => <th key={l} className="px-4 py-2.5 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium text-right">{l}</th>)}
          </tr>
        </thead>
        <tbody>
          {SCEN.map(s => (
            <tr key={s.key} className="border-b border-[var(--color-line)]">
              <td className="px-4 py-2.5 text-[var(--color-ink)]"><span className="inline-flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full" style={{ background: s.color }} />{s.label}</span></td>
              {HZ.map((_, hi) => <td key={hi} className="px-4 py-2.5 text-right mono tabular-nums text-[var(--color-mute)]">{eur(totExposed(at(s.key, hi)))}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
