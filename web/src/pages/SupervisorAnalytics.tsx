import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, Treemap, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { Card, PageHeader, StatGrid } from '../components/ui'
import { severityHex } from '../components/SiteMap'
import { SCENARIO_LABEL } from '../lib/hazards'

// The horizontal risk analyst's workbench. Every chart is an engine figure under one basis; precision is
// labelled; projections say which part of the high-risk value actually moves with the scenario.
interface Region { key: string; name: string; country: string | null; kind: string; value_eur: number; n_sites: number; max_score: number | null; worst_hazard: string | null; entities: string[] }
interface Resp { scenario: string; horizon: string; profile_id: string; n_entities: number; n_assets: number; precision: string
  concentration: { total_value_eur: number; unlocated_value_eur: number; n_regions: number; top10_share_pct: number | null; by_region: Region[]
    curve: { rank: number; cum_share_pct: number }[]; by_hazard: { hazard: string; value_eur: number; high_value_eur: number; n: number }[] }
  scenario_shift: { scenarios: string[]; horizons: string[]; note: string
    cells: { scenario: string; horizon: string; value_eur: number; high_risk_value_eur: number; high_risk_share_pct: number | null; projected_share_of_high_pct: number | null }[] }
  distribution: Record<string, { label: string; n_entities: number; metrics: { id: string; label: string; unit: string; direction?: string; watch_above?: number; act_above?: number; watch_below?: number
    distribution: { n: number; median?: number }; entities: { org_id: string; name: string; value: number | null; flag: string }[] }[] }> }
const eur = (v: number) => v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`
const SCEN_LABEL = SCENARIO_LABEL
const SCEN_COLOR: Record<string, string> = { baseline: '#888780', orderly_1_5c: '#1D9E75', disorderly_2c: '#EF9F27', hot_house_3_5c: '#E24B4A' }
const FLAGC: Record<string, string> = { act: '#E24B4A', watch: '#EF9F27', ok: '#639922', na: '#B4B2A9' }

function downloadCsv(name: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => { const t = v == null ? '' : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t }
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n')
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `${name}.csv`; a.click(); URL.revokeObjectURL(a.href)
}
function CsvBtn({ name, rows }: { name: string; rows: Record<string, unknown>[] }) {
  return <button onClick={() => downloadCsv(name, rows)} className="mono text-[10.5px] text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download this chart's data as CSV">CSV ↓</button>
}

function TreeTile(p: { x?: number; y?: number; width?: number; height?: number; name?: string; max_score?: number | null; value?: number; key?: string; regionKey?: string; onOpen?: (key: string) => void }) {
  const { x = 0, y = 0, width = 0, height = 0, name = '', max_score = null, value = 0, regionKey = '', onOpen } = p
  if (width < 4 || height < 4) return null
  return (
    <g onClick={() => onOpen?.(regionKey)} style={{ cursor: 'pointer' }} data-region={regionKey}>
      <rect x={x} y={y} width={width} height={height} rx={3} fill={severityHex(max_score)} fillOpacity={0.85} stroke="var(--color-bg)" strokeWidth={1.5} />
      {width > 60 && height > 28 && <text x={x + 6} y={y + 16} fontSize={11} fill="#fff" style={{ pointerEvents: 'none' }}>{name.length > width / 6.5 ? name.slice(0, Math.max(3, width / 6.5 - 1)) + '…' : name}</text>}
      {width > 60 && height > 42 && <text x={x + 6} y={y + 30} fontSize={10} fill="#fff" opacity={0.85} style={{ pointerEvents: 'none' }}>{eur(value)}</text>}
    </g>)
}

export default function SupervisorAnalytics() {
  const nav = useNavigate()
  const [scenario, setScenario] = useState('baseline'); const [horizon, setHorizon] = useState('current')
  const q = useQuery({ queryKey: ['sup-analytics', scenario, horizon], queryFn: () => api.get<Resp>(`/v1/supervisor/analytics?scenario=${scenario}&horizon=${horizon}`) })
  const d = q.data
  const tree = useMemo(() => (d?.concentration.by_region ?? []).slice(0, 40).map(r => ({ name: r.name, size: r.value_eur, value: r.value_eur, max_score: r.max_score, regionKey: r.key })), [d])
  const shift = useMemo(() => {
    if (!d) return []
    return d.scenario_shift.horizons.map(h => {
      const row: Record<string, number | string | null> = { horizon: h === 'current' ? 'today' : h }
      for (const s of d.scenario_shift.scenarios) { const c = d.scenario_shift.cells.find(x => x.scenario === s && x.horizon === h); row[s] = c?.high_risk_share_pct ?? null; row[s + '_proj'] = c?.projected_share_of_high_pct ?? null }
      return row
    })
  }, [d])
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow={`Analytics${d ? ` · ${d.precision}` : ''}`} title="The population, analysed"
        lead="Concentration, scenario shift and the distribution of your metrics across entities — engine figures under one basis, precision labelled, projections with the part that actually moves." />
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-[12px] text-[var(--color-mute)]">Scenario
          <select value={scenario} onChange={e => setScenario(e.target.value)} className="ml-2 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none">
            {Object.entries(SCEN_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-[12px] text-[var(--color-mute)]">Horizon
          <select value={horizon} onChange={e => setHorizon(e.target.value)} className="ml-2 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none">
            {['current', '2030', '2050', '2100'].map(h => <option key={h} value={h}>{h === 'current' ? 'today' : h}</option>)}</select></label>
        {d && <span className="mono text-[11px] text-[var(--color-faint)]">{d.n_entities} entities · {d.n_assets.toLocaleString()} assets · {eur(d.concentration.total_value_eur)}</span>}
      </div>
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">computing across the population…</div> : !d ? <div className="text-[13px] text-[var(--color-bad)]">Could not load analytics.</div> : (<>
        <StatGrid cols={4} items={[
          { label: 'Regions with exposure', value: String(d.concentration.n_regions), sub: 'NUTS-3 · hexagons outside EU' },
          { label: 'Top-10 regions hold', value: d.concentration.top10_share_pct != null ? `${d.concentration.top10_share_pct}%` : '—', sub: 'of located exposure', accent: (d.concentration.top10_share_pct ?? 0) > 50 ? 'var(--color-warn)' : undefined },
          { label: 'Largest region', value: d.concentration.by_region[0] ? eur(d.concentration.by_region[0].value_eur) : '—', sub: d.concentration.by_region[0]?.name ?? '' },
          { label: 'Unlocated exposure', value: eur(d.concentration.unlocated_value_eur), sub: 'no coordinates — not on the map' },
        ]} />

        <div className="grid lg:grid-cols-[3fr_2fr] gap-6">
          <Card className="p-5">
            <div className="flex items-baseline justify-between"><div className="text-[14px] font-semibold mb-1">Concentration by region</div><CsvBtn name="concentration_by_region" rows={d.concentration.by_region.map(r => ({ region: r.key, name: r.name, country: r.country, kind: r.kind, value_eur: r.value_eur, n_sites: r.n_sites, max_score: r.max_score, worst_hazard: r.worst_hazard }))} /></div>
            <div className="text-[11.5px] text-[var(--color-mute)] mb-2">tile = exposure, colour = worst headline score in the region · click a tile to open the map on that region</div>
            <div style={{ height: 340 }}>
              <ResponsiveContainer width="100%" height="100%">
                <Treemap data={tree} dataKey="size" nameKey="name" content={<TreeTile onOpen={(k) => nav(`/supervisor/map?region=${encodeURIComponent(k)}`)} />} isAnimationActive={false} />
              </ResponsiveContainer>
            </div>
          </Card>
          <Card className="p-5">
            <div className="flex items-baseline justify-between"><div className="text-[14px] font-semibold mb-1">Concentration curve</div><CsvBtn name="concentration_curve" rows={d.concentration.curve} /></div>
            <div className="text-[11.5px] text-[var(--color-mute)] mb-2">cumulative share of exposure by region rank — the steeper, the more concentrated</div>
            <div style={{ height: 340 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={d.concentration.curve} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis dataKey="rank" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} label={{ value: 'regions, by size', position: 'insideBottom', offset: -2, fontSize: 11, fill: 'var(--color-faint)' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} unit="%" />
                  <Tooltip formatter={(v) => [`${v}%`, 'cumulative share']} labelFormatter={(l) => `top ${l} regions`} />
                  <ReferenceLine x={10} stroke="var(--color-warn)" strokeDasharray="4 3" label={{ value: 'top 10', fontSize: 10, fill: 'var(--color-warn)' }} />
                  <Line type="monotone" dataKey="cum_share_pct" stroke="var(--color-sky)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <Card className="p-5">
            <div className="flex items-baseline justify-between"><div className="text-[14px] font-semibold mb-1">Scenario shift · share of exposure at high risk</div><CsvBtn name="scenario_shift" rows={d.scenario_shift.cells} /></div>
            <div className="text-[11.5px] text-[var(--color-mute)] mb-2">{d.scenario_shift.note}</div>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={shift} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis dataKey="horizon" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} unit="%" />
                  <Tooltip formatter={(v, n) => [`${v}%`, SCEN_LABEL[String(n)] ?? String(n)]} />
                  <Legend formatter={(v) => SCEN_LABEL[v] ?? v} wrapperStyle={{ fontSize: 11 }} />
                  {d.scenario_shift.scenarios.map(s => <Line key={s} type="monotone" dataKey={s} stroke={SCEN_COLOR[s]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">of the high-risk value under {SCEN_LABEL[scenario]} · {horizon === 'current' ? 'today' : horizon}: {d.scenario_shift.cells.find(c => c.scenario === scenario && c.horizon === horizon)?.projected_share_of_high_pct ?? '—'}% is headlined by a CMIP6-projected hazard (flood / storm / wildfire); the rest by climatology channels with their own anchors</div>
          </Card>
          <Card className="p-5">
            <div className="flex items-baseline justify-between"><div className="text-[14px] font-semibold mb-1">Exposure by headline hazard</div><CsvBtn name="exposure_by_hazard" rows={d.concentration.by_hazard} /></div>
            <div className="text-[11.5px] text-[var(--color-mute)] mb-2">value whose biggest threat is each hazard · darker = at high risk</div>
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.concentration.by_hazard.slice(0, 10).map(h => ({ ...h, label: h.hazard.replace(/_/g, ' ') }))} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} tickFormatter={(v) => eur(Number(v))} />
                  <YAxis type="category" dataKey="label" width={130} tick={{ fontSize: 11, fill: 'var(--color-mute)' }} />
                  <Tooltip formatter={(v, n) => [eur(Number(v)), n === 'high_value_eur' ? 'at high risk' : 'exposure']} />
                  <Bar dataKey="value_eur" fill="#85B7EB" isAnimationActive={false} />
                  <Bar dataKey="high_value_eur" fill="#E24B4A" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        {Object.entries(d.distribution).map(([sec, s]) => (
          <Card key={sec} className="p-5">
            <div className="flex items-baseline justify-between"><div className="text-[14px] font-semibold mb-1">Distribution · {s.label}</div><CsvBtn name={`distribution_${sec}`} rows={s.metrics.flatMap(m => m.entities.map(e => ({ metric: m.id, entity: e.name, value: e.value, flag: e.flag })))} /></div>
            <div className="text-[11.5px] text-[var(--color-mute)] mb-3">each entity against your profile's expectations — amber watch, red act; the dashed line is the peer median · click a bar to open the entity file</div>
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
              {s.metrics.filter(m => m.direction !== 'neutral').map(m => (
                <div key={m.id}>
                  <div className="text-[12px] text-[var(--color-ink)] mb-1">{m.label} <span className="mono text-[10px] text-[var(--color-faint)]">{m.watch_above != null ? `watch >${m.watch_above}` : m.watch_below != null ? `watch <${m.watch_below}` : ''}{m.act_above != null ? ` · act >${m.act_above}` : ''}</span></div>
                  <div style={{ height: 40 + 22 * Math.max(1, m.entities.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={m.entities.map(e => ({ name: e.name.replace(' (demo)', ''), value: e.value ?? 0, flag: e.flag, org_id: e.org_id }))} layout="vertical" margin={{ top: 2, right: 16, left: 4, bottom: 0 }} style={{ cursor: 'pointer' }}>
                        <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--color-faint)' }} tickFormatter={(v) => m.unit === 'eur' ? eur(Number(v)) : `${v}%`} />
                        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10.5, fill: 'var(--color-mute)' }} />
                        <Tooltip formatter={(v) => [m.unit === 'eur' ? eur(Number(v)) : `${v}%`, m.label]} />
                        {m.distribution.median != null && <ReferenceLine x={m.distribution.median} stroke="var(--color-sky)" strokeDasharray="4 3" />}
                        {m.watch_above != null && <ReferenceLine x={m.watch_above} stroke="#EF9F27" />}
                        {m.act_above != null && <ReferenceLine x={m.act_above} stroke="#E24B4A" />}
                        {m.watch_below != null && <ReferenceLine x={m.watch_below} stroke="#EF9F27" />}
                        <Bar dataKey="value" isAnimationActive={false} onClick={(bar) => { const org = (bar as { org_id?: string; payload?: { org_id?: string } }).org_id ?? (bar as { payload?: { org_id?: string } }).payload?.org_id; if (org) nav(`/supervised/${org}`) }}>
                          {m.entities.map((e, i) => <Cell key={i} fill={FLAGC[e.flag]} className="dist-bar" />)}</Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>))}
            </div>
          </Card>))}
      </>)}
    </div>
  )
}
