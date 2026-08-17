import { useMemo, useState } from 'react'
import { useQueries, useQueryClient } from '@tanstack/react-query'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell } from 'recharts'
import { Save, Trash2, Share2, Download, BarChart3, Plus, Star, Info } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead } from './ui'
import { hazardLabel } from '../lib/hazards'

// Custom views — bounded self-service analytics. A user picks scope × measure × scenario × horizon × group-by
// and gets a chart/table, then saves it as a named, shareable view. CRITICAL: a view stores only PARAMETERS —
// every number is recomputed here from the same golden-source disclosure the rest of Analytics reads, so a
// custom cut is always defensible and always EXPLORATORY (never a filed figure). Nothing is invented, no user
// formulas, no arbitrary joins — just aggregations of the authoritative per-asset book.

const SCEN = [
  { key: 'baseline', label: 'Today' }, { key: 'orderly_1_5c', label: 'Orderly 1.5°C' },
  { key: 'disorderly_2c', label: 'Disorderly 2°C' }, { key: 'hot_house_3_5c', label: 'Hot-house 3.5°C' },
] as const
// The golden source MODELS risk at four snapshot horizons. Any other year is an interpolation between the two
// bracketing anchors — the exact treatment the hero trajectory uses — and is always labelled as such so an
// interpolated €-figure is never mistaken for a modelled one.
const ANCHORS = [
  { key: 'current', year: 2025, label: 'Now' }, { key: '2030', year: 2030, label: '2030' },
  { key: '2050', year: 2050, label: '2050' }, { key: '2100', year: 2100, label: '2100' },
] as const
// per-sector book shape — the disclosure returns the per-asset array under a different key/field per vertical
const BOOK: Record<string, { key: string; name: string; value: string; sector: string; sectorLabel: string }> = {
  bank:       { key: 'assets',     name: 'asset_name',    value: 'value_eur',          sector: 'sector',        sectorLabel: 'Sector' },
  assetmgmt:  { key: 'holdings',   name: 'holding_name',  value: 'position_value_eur', sector: 'sector',        sectorLabel: 'Sector' },
  realestate: { key: 'properties', name: 'property_name', value: 'property_value_eur', sector: 'property_type', sectorLabel: 'Type' },
}
const BUCKET: Record<string, { label: string; color: string }> = {
  VH: { label: 'Severe', color: 'var(--color-bad)' }, H: { label: 'High', color: 'var(--scn-disorderly)' },
  M: { label: 'Elevated', color: 'var(--scn-orderly)' }, L: { label: 'Low', color: 'var(--color-faint)' },
}
const MEASURES = [{ k: 'value', label: '€ exposed' }, { k: 'pct', label: '% of book' }, { k: 'count', label: '# exposures' }] as const
const THRESHOLDS = [{ k: 'highplus', label: 'High +', set: ['H', 'VH'] }, { k: 'severe', label: 'Severe only', set: ['VH'] }] as const

const eur = (n: number) => n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

interface Hz { hazard: string; bucket: string | null; score: number | null }
interface Item { name: string; value: number; sector: string; region: string; country: string; hazards: Hz[]; bucket: string | null }
interface ViewConfig { groupBy: string; measure: string; scenario: string; horizon: number; threshold: string; chart: string; scope: { dim: string; val: string } | null }
interface SavedView { view_id: string; name: string; config: ViewConfig; is_shared: boolean; is_pinned: boolean; is_owner: boolean }
interface Grp { value: number; count: number; color?: string }

const DEFAULT: ViewConfig = { groupBy: 'hazard', measure: 'value', scenario: 'disorderly_2c', horizon: 2050, threshold: 'highplus', chart: 'bar', scope: null }

export default function AnalyticsViews({ prefix, orgName }: { prefix: string; orgName?: string }) {
  const bk = BOOK[prefix] ?? BOOK.bank
  const qc = useQueryClient()
  const [cfg, setCfg] = useState<ViewConfig>(DEFAULT)
  const [name, setName] = useState('')
  const set = <K extends keyof ViewConfig>(k: K, v: ViewConfig[K]) => setCfg(c => ({ ...c, [k]: v }))

  const groupBys = [
    { k: 'hazard', label: 'Hazard' }, { k: 'sector', label: bk.sectorLabel },
    { k: 'region', label: 'Region' }, { k: 'country', label: 'Country' }, { k: 'severity', label: 'Severity band' },
  ]

  // The authoritative book at the requested year — the SAME endpoint the drill-down uses. The ENGINE does
  // the horizon work: a non-anchor year is blended per-asset between the bracketing modelled nodes ALONG the
  // scenario's warming curve (GWL-weighted, not calendar-linear) and re-bucketed server-side, so every cut
  // here is consistent with the rest of the platform and defensible. `interpolated` is true off the anchors.
  const interpolated = !ANCHORS.some(a => a.year === cfg.horizon)
  const q = useQueries({ queries: [{
    queryKey: ['analytics-book', prefix, cfg.scenario, cfg.horizon],
    queryFn: () => api.get<Record<string, unknown>>(`/v1/${prefix}/disclosure?scenario=${cfg.scenario}&horizon=${cfg.horizon}`),
    staleTime: 5 * 60 * 1000,
  }] })[0]
  const loading = q.isLoading
  const items = useMemo(() => {
    const raw = (q.data?.[bk.key] as Record<string, unknown>[] | undefined) ?? []
    return raw.map(a => ({
      name: (a[bk.name] as string) ?? '—', value: (a[bk.value] as number) ?? 0,
      sector: (a[bk.sector] as string) ?? '—', region: (a.region as string) ?? '—', country: (a.country as string) ?? '—',
      hazards: Array.isArray(a.hazards) ? (a.hazards as Hz[]) : [], bucket: (a.headline_bucket as string) ?? null,
    })) as Item[]
  }, [q.data, bk])

  const dimVal = (i: Item, dim: string) => dim === 'sector' ? i.sector : dim === 'region' ? i.region : dim === 'country' ? i.country : '—'
  const scopeValues = useMemo(() => {
    if (!cfg.scope?.dim) return []
    return [...new Set(items.map(i => dimVal(i, cfg.scope!.dim)).filter(v => v && v !== '—'))].sort()
  }, [items, cfg.scope?.dim])

  // ── the computation: aggregate the authoritative book into the chosen groups ────────────────────────────
  const aggregate = (items: Item[]): { groups: Map<string, Grp>; total: number } => {
    const thr = new Set<string>(THRESHOLDS.find(t => t.k === cfg.threshold)!.set)
    let pool = items
    if (cfg.scope?.dim && cfg.scope.val) pool = items.filter(i => dimVal(i, cfg.scope!.dim) === cfg.scope!.val)
    const g = new Map<string, Grp>()
    if (cfg.groupBy === 'hazard') {
      for (const it of pool) for (const h of it.hazards) if (h.bucket && thr.has(h.bucket)) {
        const e = g.get(h.hazard) ?? { value: 0, count: 0 }; e.value += it.value; e.count += 1; g.set(h.hazard, e)
      }
    } else {
      for (const it of pool) {
        const atRisk = (it.bucket && thr.has(it.bucket)) || it.hazards.some(h => h.bucket && thr.has(h.bucket))
        if (!atRisk) continue
        const key = cfg.groupBy === 'severity' ? (it.bucket ?? '—') : dimVal(it, cfg.groupBy)
        const e = g.get(key) ?? { value: 0, count: 0 }; e.value += it.value; e.count += 1
        if (cfg.groupBy === 'severity') e.color = BUCKET[key]?.color
        g.set(key, e)
      }
    }
    return { groups: g, total: items.reduce((s, i) => s + (i.value || 0), 0) }
  }

  const result = useMemo(() => {
    const { groups, total } = aggregate(items)
    return [...groups.entries()].map(([k, v]) => ({
      key: k, label: cfg.groupBy === 'hazard' ? hazardLabel(k) : cfg.groupBy === 'severity' ? (BUCKET[k]?.label ?? k) : k,
      raw: cfg.measure === 'count' ? v.count : cfg.measure === 'pct' ? (total ? v.value / total * 100 : 0) : v.value,
      color: v.color,
    })).sort((a, b) => b.raw - a.raw)
  }, [items, cfg])

  const shown = result.slice(0, 12)
  const hidden = result.length - shown.length
  const totalMeasure = result.reduce((s, r) => s + r.raw, 0)
  const fmt = (n: number) => cfg.measure === 'count' ? Math.round(n).toLocaleString('en-GB') : cfg.measure === 'pct' ? `${n.toFixed(1)}%` : eur(n)
  const measureLabel = MEASURES.find(m => m.k === cfg.measure)!.label
  const scen = SCEN.find(s => s.key === cfg.scenario)!

  // ── saved views (own + shared in the org) ───────────────────────────────────────────────────────────────
  const views = useQueries({ queries: [{ queryKey: ['analytics-views'], queryFn: () => api.get<{ views: SavedView[] }>('/v1/analytics/views') }] })[0]
  const refetchViews = () => qc.invalidateQueries({ queryKey: ['analytics-views'] })
  const saveView = async () => {
    const nm = name.trim(); if (!nm) return
    try { await api.post('/v1/analytics/views', { name: nm, config: cfg }); setName(''); refetchViews(); toast.success(`Saved “${nm}”.`) }
    catch { toast.error('Could not save the view.') }
  }
  const patchView = async (v: SavedView, body: Partial<Pick<SavedView, 'is_shared' | 'is_pinned'>>) => {
    try { await api.patch(`/v1/analytics/views/${v.view_id}`, body); refetchViews() } catch { toast.error('Could not update the view.') }
  }
  const delView = async (v: SavedView) => {
    try { await api.del(`/v1/analytics/views/${v.view_id}`); refetchViews(); toast.success('View deleted.') } catch { toast.error('Could not delete the view.') }
  }
  const loadView = (v: SavedView) => {
    const c: ViewConfig = { ...DEFAULT, ...v.config }
    if (typeof (c.horizon as unknown) === 'string') { const a = ANCHORS.find(x => x.key === (c.horizon as unknown as string)); c.horizon = a ? a.year : 2050 }
    setCfg(c); toast.info(`Loaded “${v.name}”.`)
  }
  const savedViews = views.data?.views ?? []

  const exportCsv = () => {
    const head = `${groupBys.find(g => g.k === cfg.groupBy)!.label},${measureLabel}\n`
    const body = result.map(r => `"${r.label}",${cfg.measure === 'value' ? Math.round(r.raw) : cfg.measure === 'pct' ? r.raw.toFixed(2) : Math.round(r.raw)}`).join('\n')
    const basis = `# ${orgName ?? ''} · custom view · ${scen.label} · ${cfg.horizon}${interpolated ? ' (INTERPOLATED — not a modelled horizon)' : ''} · ${measureLabel} by ${cfg.groupBy} · EXPLORATORY (not a filed figure)\n`
    const url = URL.createObjectURL(new Blob([basis + head + body], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'tellumen-custom-view.csv'; a.click(); URL.revokeObjectURL(url)
  }

  const Seg = <T extends string>({ value, opts, onChange }: { value: T; opts: { k: T; label: string }[]; onChange: (v: T) => void }) => (
    <div className="inline-flex rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-0.5">
      {opts.map(o => (
        <button key={o.k} onClick={() => onChange(o.k)}
          className={`mono text-[11px] px-2.5 py-1 rounded-md transition ${value === o.k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{o.label}</button>
      ))}
    </div>
  )
  const Select = ({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) => (
    <select value={value} onChange={e => onChange(e.target.value)}
      className="mono text-[11px] rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-2.5 py-1.5 text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]">{children}</select>
  )

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <SectionHead icon={BarChart3} hint="build your own cut of the book">Custom views</SectionHead>
        <span className="inline-flex items-center gap-1.5 mono text-[9.5px] uppercase tracking-wide px-2 py-1 rounded-full" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 14%, transparent)' }}>
          <Info size={11} /> Exploratory · not a filed figure
        </span>
      </div>
      <p className="text-[12.5px] text-[var(--color-mute)] mb-4 max-w-2xl">Slice the same golden-source book any way you need — every figure is recomputed live, never invented. Save a cut as a named view and share it with your team.</p>

      {savedViews.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {savedViews.map(v => (
            <div key={v.view_id} className="group inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line)] bg-[var(--color-bg-2)] pl-3 pr-1.5 py-1 hover:border-[var(--color-sky)] transition">
              <button onClick={() => loadView(v)} className="mono text-[11.5px] text-[var(--color-ink)] flex items-center gap-1.5">
                {v.is_pinned && <Star size={11} className="text-[var(--color-warn)]" fill="var(--color-warn)" />}
                {v.name}
                {v.is_shared && !v.is_owner && <span className="mono text-[9px] text-[var(--color-faint)]">· shared</span>}
              </button>
              {v.is_owner && (
                <span className="flex items-center gap-0.5">
                  <button onClick={() => patchView(v, { is_pinned: !v.is_pinned })} title={v.is_pinned ? 'Unpin' : 'Pin'} className="p-1 rounded text-[var(--color-faint)] hover:text-[var(--color-warn)]"><Star size={11} /></button>
                  <button onClick={() => patchView(v, { is_shared: !v.is_shared })} title={v.is_shared ? 'Shared with org — click to make private' : 'Share with org'} className={`p-1 rounded hover:text-[var(--color-sky)] ${v.is_shared ? 'text-[var(--color-sky)]' : 'text-[var(--color-faint)]'}`}><Share2 size={11} /></button>
                  <button onClick={() => delView(v)} title="Delete" className="p-1 rounded text-[var(--color-faint)] hover:text-[var(--color-bad)]"><Trash2 size={11} /></button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* builder controls */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 mb-4">
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Group by</span>
          <Select value={cfg.groupBy} onChange={v => set('groupBy', v)}>{groupBys.map(g => <option key={g.k} value={g.k}>{g.label}</option>)}</Select></label>
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Measure</span>
          <Seg value={cfg.measure} opts={MEASURES.map(m => ({ k: m.k, label: m.label }))} onChange={v => set('measure', v)} /></label>
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Pathway</span>
          <Select value={cfg.scenario} onChange={v => set('scenario', v)}>{SCEN.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}</Select></label>
        {/* horizon: any year 2025–2100; the four modelled anchors are quick-picks, everything else is interpolated */}
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Horizon</span>
          <input type="number" min={2025} max={2100} step={1} value={cfg.horizon}
            onChange={e => set('horizon', Math.max(2025, Math.min(2100, parseInt(e.target.value) || 2050)))}
            className="mono text-[11px] w-[62px] rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-2 py-1.5 text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]" />
          <div className="flex gap-0.5">
            {ANCHORS.map(a => (
              <button key={a.key} onClick={() => set('horizon', a.year)}
                className={`mono text-[10px] px-1.5 py-1 rounded transition ${cfg.horizon === a.year ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>{a.label}</button>
            ))}
          </div>
        </label>
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Threshold</span>
          <Seg value={cfg.threshold} opts={THRESHOLDS.map(t => ({ k: t.k, label: t.label }))} onChange={v => set('threshold', v)} /></label>
        <label className="flex items-center gap-2"><span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Scope</span>
          <Select value={cfg.scope?.dim ?? ''} onChange={v => set('scope', v ? { dim: v, val: '' } : null)}>
            <option value="">Whole book</option><option value="sector">By {bk.sectorLabel.toLowerCase()}</option><option value="region">By region</option><option value="country">By country</option>
          </Select>
          {cfg.scope?.dim && (
            <Select value={cfg.scope.val} onChange={v => set('scope', { dim: cfg.scope!.dim, val: v })}>
              <option value="">Choose…</option>{scopeValues.map(v => <option key={v} value={v}>{v}</option>)}
            </Select>
          )}
        </label>
      </div>

      {/* headline + interpolation badge + chart/table toggle + export */}
      <div className="flex items-end justify-between flex-wrap gap-3 mb-2">
        <div>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] flex items-center gap-2 flex-wrap">
            {measureLabel} · {scen.label} · {cfg.horizon}{cfg.scope?.val ? ` · ${cfg.scope.val}` : ''}
            {interpolated && <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded normal-case" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 14%, transparent)' }}><Info size={10} /> interpolated — not a modelled horizon</span>}
          </div>
          <div className="display text-[26px] leading-none tabular-nums text-[var(--color-ink)]">{loading ? '—' : fmt(totalMeasure)}</div>
        </div>
        <div className="flex items-center gap-2">
          <Seg value={cfg.chart} opts={[{ k: 'bar', label: 'Chart' }, { k: 'table', label: 'Table' }]} onChange={v => set('chart', v)} />
          <button onClick={exportCsv} title="Download this view as CSV" className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Download size={13} /> CSV</button>
        </div>
      </div>

      {loading ? <div className="h-[260px] grid place-items-center text-[13px] text-[var(--color-faint)]">reading the book…</div>
        : result.length === 0 ? <div className="h-[200px] grid place-items-center text-[13px] text-[var(--color-faint)]">No exposures match this cut. Try a hotter pathway, later horizon, or the High+ threshold.</div>
        : cfg.chart === 'bar' ? (
          <div style={{ height: Math.max(180, shown.length * 34 + 30) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={shown} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 8 }}>
                <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 5" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--color-faint)' }} tickFormatter={(n: number) => fmt(n)} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 11, fill: 'var(--color-mute)' }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: 'color-mix(in oklab, var(--color-sky) 8%, transparent)' }}
                  content={({ active, payload }: any) =>
                    active && payload?.length ? <div className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 shadow-lg"><div className="text-[12px] text-[var(--color-ink)]">{payload[0].payload.label}</div><div className="mono text-[12px] tabular-nums text-[var(--color-sky)]">{fmt(payload[0].payload.raw)}</div></div> : null} />
                <Bar dataKey="raw" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {shown.map((r, i) => <Cell key={i} fill={r.color ?? 'var(--chart-seq)'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="border-b border-[var(--color-line)]">
                <th className="text-left mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] py-2">{groupBys.find(g => g.k === cfg.groupBy)!.label}</th>
                <th className="text-right mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] py-2">{measureLabel}</th>
              </tr></thead>
              <tbody>{result.map(r => (
                <tr key={r.key} className="border-b border-[var(--color-line)]">
                  <td className="py-2 text-[var(--color-ink)] flex items-center gap-2">{r.color && <span className="w-2 h-2 rounded-full" style={{ background: r.color }} />}{r.label}</td>
                  <td className="py-2 text-right mono tabular-nums text-[var(--color-mute)]">{fmt(r.raw)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      {hidden > 0 && cfg.chart === 'bar' && <div className="mono text-[10.5px] text-[var(--color-faint)] mt-2">+{hidden} more group{hidden === 1 ? '' : 's'} — switch to Table or export CSV for the full list.</div>}

      <div className="mt-4 pt-4 border-t border-[var(--color-line)] flex items-center gap-2 flex-wrap">
        <Save size={14} className="text-[var(--color-faint)]" />
        <input value={name} onChange={e => setName(e.target.value)} onKeyDown={e => e.key === 'Enter' && saveView()}
          placeholder="Name this view — e.g. Drought € by sector, 2050…" maxLength={120}
          className="flex-1 min-w-[220px] bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <button onClick={saveView} disabled={!name.trim()}
          className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 mono text-[12px] font-medium bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:bg-[var(--color-blue)] transition disabled:opacity-50"><Plus size={13} /> Save view</button>
      </div>
    </Card>
  )
}
