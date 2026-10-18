import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, Treemap, XAxis, YAxis } from 'recharts'
import { api } from '../lib/api'
import { Card, PageHeader, StatGrid } from '../components/ui'
import { severityHex } from '../components/SiteMap'
import { SCENARIO_LABEL, hazardLabel, horizonLabel } from '../lib/hazards'
import { balance } from '../lib/money'
import { pressable } from '../lib/pressable'
import { HEADING, InfoButton, MessageLine, messageDetails, type DetailSection, type Message } from '../components/Details'
import MethodGap from '../components/MethodGap'
import { Timeliness, type TimelinessResp } from './supervisorAnalysis/Timeliness'

// The horizontal risk analyst's workbench, to the UI standard (2026-10-16): charts first — where the population's
// exposure sits, how it shifts by scenario, which hazards lead it, how filings and filed shares move — with each
// chart's method one click away in the server's catalogue words.
interface TrendResp { entities: { org_id: string; name: string; latest_period: string | null; latest_share_pct: number | null; previous_period: string | null; previous_share_pct: number | null; change_pp: number | null }[]; note: Message }
interface Region { key: string; name: string; country: string | null; kind: string; value_eur: number; n_sites: number; max_score: number | null; worst_hazard: string | null; entities: string[] }
interface Anchor { scenario: string; horizon: string; hazards: number; hazard_list: string[]; message: Message | null }
interface Resp { scenario: string; horizon: string; n_entities: number; n_assets: number; precision: string; at_risk_level: number | null; gap?: string
  concentration: { total_value_eur: number; unlocated_value_eur: number; n_regions: number; top10_share_pct: number | null; by_region: Region[]
    curve: { rank: number; cum_share_pct: number }[]; by_hazard: { hazard: string; value_eur: number; high_value_eur: number | null; n: number }[] }
  scenario_shift: { scenarios: string[]; horizons: string[]; note: Message
    cells: { scenario: string; horizon: string; value_eur: number | null; high_risk_value_eur: number | null; high_risk_share_pct: number | null; projected_share_of_high_pct: number | null }[] }
  anchor_coverage: { anchors: Anchor[]; hazards_today: number }
  distribution: Record<string, { label: string; n_entities: number; metrics: { id: string; label: string; unit: string; direction?: string; watch_above?: number; act_above?: number; watch_below?: number
    distribution: { n: number; median?: number }; entities: { org_id: string; name: string; value: number | null; flag: string }[] }[] }> }
const SCEN_COLOR: Record<string, string> = { baseline: '#888780', orderly_1_5c: '#1D9E75', disorderly_2c: '#EF9F27', hot_house_3_5c: '#E24B4A' }
const FLAGC: Record<string, string> = { act: '#E24B4A', watch: '#EF9F27', ok: '#639922', na: '#B4B2A9' }
const scen = (s: string) => SCENARIO_LABEL[s] ?? 'Scenario'
const hazard = (h: string) => h === 'unscored' ? 'Not scored' : hazardLabel(h)

const ABOUT = [
  { heading: HEADING.shows, body: 'Your supervised population as one book: where its exposure sits by region and by hazard, how the share at or above your at-risk threshold shifts by scenario and year, how each entity’s filed share moves, whether filings arrive on time, and where each entity sits against your supervision profile’s expectations.' },
  { heading: HEADING.read, body: 'Every chart reads the same scenario and year, chosen above, and your own at-risk threshold, so entities are compared on one definition. Select a region, an entity or a filing to open it.' },
  { heading: HEADING.sources, body: 'The entities’ own portfolios on the platform, located to the point, and the platform’s hazard scores. Filed shares come from the templates on file; timeliness from the entities’ obligations calendars and filing records.' },
  { heading: HEADING.limits, body: 'Exposure without a location is counted in the total and shown apart, never placed on the map. Nothing is estimated where data is missing.' },
]

function downloadCsv(name: string, rows: Record<string, unknown>[]) {
  if (!rows.length) return
  const cols = Object.keys(rows[0])
  const esc = (v: unknown) => { const t = v == null ? '' : String(v); return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t }
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))].join('\n')
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' })); a.download = `${name}.csv`; a.click(); URL.revokeObjectURL(a.href)
}
function CsvBtn({ name, rows }: { name: string; rows: Record<string, unknown>[] }) {
  return <button onClick={() => downloadCsv(name, rows)} className="text-[11.5px] text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download this chart’s data as CSV">CSV ↓</button>
}

// A chart card: its title, the ⓘ with how to read it, and its CSV.
function ChartHead({ title, sections, csv }: { title: string; sections: DetailSection[]; csv?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <div className="text-[14px] font-semibold">{title}</div>
      <InfoButton compact details={{ title, sections }} />
      <span className="ml-auto">{csv}</span>
    </div>
  )
}

function TreeTile(p: { x?: number; y?: number; width?: number; height?: number; name?: string; max_score?: number | null; value?: number; regionKey?: string; onOpen?: (key: string) => void }) {
  const { x = 0, y = 0, width = 0, height = 0, name = '', max_score = null, value = 0, regionKey = '', onOpen } = p
  if (width < 4 || height < 4) return null
  return (
    <g {...pressable(onOpen && (() => onOpen(regionKey)), { label: name })} style={{ cursor: 'pointer' }} data-region={regionKey}>
      <rect x={x} y={y} width={width} height={height} rx={3} fill={severityHex(max_score)} fillOpacity={0.85} stroke="var(--color-bg)" strokeWidth={1.5} />
      {width > 60 && height > 28 && <text x={x + 6} y={y + 16} fontSize={11} fill="#fff" style={{ pointerEvents: 'none' }}>{name.length > width / 6.5 ? name.slice(0, Math.max(3, width / 6.5 - 1)) + '…' : name}</text>}
      {width > 60 && height > 42 && <text x={x + 6} y={y + 30} fontSize={10} fill="#fff" opacity={0.85} style={{ pointerEvents: 'none' }}>{balance(value)}</text>}
    </g>)
}

export default function SupervisorAnalytics() {
  const nav = useNavigate()
  const [scenario, setScenario] = useState('baseline'); const [horizon, setHorizon] = useState('current')
  const q = useQuery({ queryKey: ['sup-analytics', scenario, horizon], queryFn: () => api.get<Resp>(`/v1/supervisor/analytics?scenario=${scenario}&horizon=${horizon}`) })
  const tq = useQuery({ queryKey: ['sup-trend'], queryFn: () => api.get<TrendResp>('/v1/supervisor/trend') })
  const tl = useQuery({ queryKey: ['sup-timeliness'], queryFn: () => api.get<TimelinessResp>('/v1/supervisor/timeliness') })
  const d = q.data
  const anchor = useMemo(() => d?.anchor_coverage.anchors.find(a => a.scenario === scenario && a.horizon === horizon) ?? null, [d, scenario, horizon])
  const tree = useMemo(() => (d?.concentration.by_region ?? []).slice(0, 40).map(r => ({ name: r.name, size: r.value_eur, value: r.value_eur, max_score: r.max_score, regionKey: r.key })), [d])
  const shift = useMemo(() => {
    if (!d) return []
    return d.scenario_shift.horizons.map(h => {
      const row: Record<string, number | string | null> = { horizon: horizonLabel(h) }
      for (const s of d.scenario_shift.scenarios) row[s] = d.scenario_shift.cells.find(x => x.scenario === s && x.horizon === h)?.high_risk_share_pct ?? null
      return row
    })
  }, [d])
  const projected = d?.scenario_shift.cells.find(c => c.scenario === scenario && c.horizon === horizon)?.projected_share_of_high_pct ?? null
  const select = 'ml-2 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none'
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Analytics" title="Your population" lead="Where your population’s exposure sits, and how it shifts by scenario." about={ABOUT} />
      {d?.gap && <MethodGap gap={d.gap} what="At-risk analytics" />}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-[12px] text-[var(--color-mute)]">Scenario
          <select value={scenario} onChange={e => setScenario(e.target.value)} className={select}>
            {Object.entries(SCENARIO_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className="text-[12px] text-[var(--color-mute)]">Year
          <select value={horizon} onChange={e => setHorizon(e.target.value)} className={select}>
            {['current', '2030', '2050', '2100'].map(h => <option key={h} value={h}>{horizonLabel(h)}</option>)}</select></label>
        {d && <span className="text-[12px] text-[var(--color-faint)] tabular-nums">{d.n_entities} entities · {d.n_assets.toLocaleString()} assets · {balance(d.concentration.total_value_eur)}</span>}
        {anchor?.message && <span className="text-[12px] text-[var(--color-warn)]"><MessageLine m={anchor.message} /></span>}
      </div>
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">Computing across the population…</div> : !d ? <div className="text-[13px] text-[var(--color-bad)]">The analytics could not be loaded.</div> : (<>
        <StatGrid cols={4} items={[
          { label: 'Regions with exposure', value: String(d.concentration.n_regions), sub: 'with located exposure' },
          { label: 'Top 10 regions hold', value: d.concentration.top10_share_pct != null ? `${d.concentration.top10_share_pct}%` : '—', sub: 'of located exposure', accent: (d.concentration.top10_share_pct ?? 0) > 50 ? 'var(--color-warn)' : undefined },
          { label: 'Largest region', value: d.concentration.by_region[0] ? balance(d.concentration.by_region[0].value_eur) : '—', sub: d.concentration.by_region[0]?.name ?? '' },
          { label: 'Exposure without a location', value: balance(d.concentration.unlocated_value_eur), sub: 'not on the map' },
        ]} />

        <div className="grid lg:grid-cols-[3fr_2fr] gap-6">
          <Card className="p-5">
            <ChartHead title="Concentration by region" csv={<CsvBtn name="concentration_by_region" rows={d.concentration.by_region.map(r => ({ region: r.key, name: r.name, country: r.country, kind: r.kind, value_eur: r.value_eur, n_sites: r.n_sites, max_score: r.max_score, worst_hazard: r.worst_hazard }))} />}
              sections={[{ heading: HEADING.read, body: 'Each tile is a region; its size is the exposure there, its colour the highest hazard score in the region. The 40 largest regions are shown. Select a tile to open the map on that region.' },
                { heading: HEADING.limits, body: `Regions are NUTS-3 in Europe and map cells elsewhere. Precision: ${d.precision}.` }]} />
            <div style={{ height: 340 }}>
              <ResponsiveContainer width="100%" height="100%">
                <Treemap data={tree} dataKey="size" nameKey="name" content={<TreeTile onOpen={(k) => nav(`/supervisor/map?region=${encodeURIComponent(k)}`)} />} isAnimationActive={false} />
              </ResponsiveContainer>
            </div>
          </Card>
          <Card className="p-5">
            <ChartHead title="Concentration curve" csv={<CsvBtn name="concentration_curve" rows={d.concentration.curve} />}
              sections={[{ heading: HEADING.read, body: 'The share of all located exposure held by the largest regions, adding one region at a time. The steeper the curve, the more concentrated the population. The dashed line marks the ten largest.' }]} />
            <div style={{ height: 340 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={d.concentration.curve} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis dataKey="rank" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} label={{ value: 'regions, largest first', position: 'insideBottom', offset: -2, fontSize: 11, fill: 'var(--color-faint)' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} unit="%" />
                  <Tooltip formatter={(v) => [`${v}%`, 'Share of exposure']} labelFormatter={(l) => `Largest ${l} regions`} />
                  <ReferenceLine x={10} stroke="var(--color-warn)" strokeDasharray="4 3" label={{ value: 'top 10', fontSize: 10, fill: 'var(--color-warn)' }} />
                  <Line type="monotone" dataKey="cum_share_pct" stroke="var(--color-sky)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <Card className="p-5">
            <ChartHead title="Scenario shift" csv={<CsvBtn name="scenario_shift" rows={d.scenario_shift.cells} />}
              sections={[...messageDetails(d.scenario_shift.note).sections, {
                heading: 'Hazards scored', body: d.scenario_shift.scenarios.map(s => `${scen(s)}: ${d.scenario_shift.horizons.map(h => {
                  const a = d.anchor_coverage.anchors.find(x => x.scenario === s && x.horizon === h)
                  return `${horizonLabel(h)} ${a?.hazards ?? 0} of ${d.anchor_coverage.hazards_today}`
                }).join(', ')}`).join('. ') + '.' }]} />
            {d.at_risk_level == null ? <div className="h-[280px] grid place-items-center text-[12.5px] text-[var(--color-faint)]">Needs your at-risk threshold</div> : <div style={{ height: 280 }}>
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={shift} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" />
                  <XAxis dataKey="horizon" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} unit="%" />
                  <Tooltip formatter={(v, n) => [`${v}%`, scen(String(n))]} />
                  <Legend formatter={(v) => scen(String(v))} wrapperStyle={{ fontSize: 11 }} />
                  {d.scenario_shift.scenarios.map(s => <Line key={s} type="monotone" dataKey={s} stroke={SCEN_COLOR[s]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>}
            {projected != null && <Projected share={projected} />}
          </Card>
          <Card className="p-5">
            <ChartHead title="Exposure by leading hazard" csv={<CsvBtn name="exposure_by_hazard" rows={d.concentration.by_hazard} />}
              sections={[{ heading: HEADING.read, body: 'The exposure whose highest-scoring hazard is each one. The red bar is the part at or above your at-risk threshold.' }]} />
            <div style={{ height: 300 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.concentration.by_hazard.slice(0, 10).map(h => ({ ...h, label: hazard(h.hazard) }))} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} tickFormatter={(v) => balance(Number(v))} />
                  <YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 11, fill: 'var(--color-mute)' }} />
                  <Tooltip formatter={(v, n) => [balance(Number(v)), n === 'high_value_eur' ? 'At or above your threshold' : 'Exposure']} />
                  <Bar dataKey="value_eur" fill="#85B7EB" isAnimationActive={false} />
                  <Bar dataKey="high_value_eur" fill="#E24B4A" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <Card className="p-5">
            <ChartHead title="Filed share, latest year against the year before" csv={tq.data && <CsvBtn name="trend" rows={tq.data.entities} />}
              sections={tq.data ? [...messageDetails(tq.data.note).sections, { heading: HEADING.read, body: 'Select an entity’s bar to open its file.' }] : []} />
            {!tq.data ? <div className="text-[12px] text-[var(--color-faint)]">Loading…</div> : tq.data.entities.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">No templates on file yet.</div> : (
              <div style={{ height: Math.max(120, 36 * tq.data.entities.length + 40) }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={tq.data.entities.map(e => ({ name: e.name, previous: e.previous_share_pct, latest: e.latest_share_pct, pl: e.previous_period, ll: e.latest_period, change: e.change_pp, org_id: e.org_id }))} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke="var(--color-line)" strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" domain={[0, 100]} unit="%" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} />
                    <YAxis type="category" dataKey="name" width={150} tick={{ fontSize: 11, fill: 'var(--color-mute)' }} />
                    <Tooltip formatter={(v, n, p) => [`${v ?? '—'}%`, n === 'previous' ? `Year before (${p.payload.pl ?? '—'})` : `Latest (${p.payload.ll ?? '—'})${p.payload.change != null ? ` · ${p.payload.change > 0 ? '+' : ''}${p.payload.change} pts` : ''}`]} />
                    <Legend formatter={(v) => v === 'previous' ? 'Year before' : 'Latest year'} wrapperStyle={{ fontSize: 11 }} />
                    {(['previous', 'latest'] as const).map(k => <Bar key={k} dataKey={k} fill={k === 'previous' ? '#8290a8' : '#38bdf8'} isAnimationActive={false} style={{ cursor: 'pointer' }}
                      onClick={(bar) => { const org = (bar as { payload?: { org_id?: string } }).payload?.org_id; if (org) nav(`/supervised/${org}`) }} />)}
                  </BarChart>
                </ResponsiveContainer>
              </div>)}
          </Card>
          <Timeliness data={tl.data} csv={tl.data && <CsvBtn name="timeliness" rows={tl.data.rows} />} />
        </div>

        {Object.entries(d.distribution).map(([sec, s]) => (
          <Card key={sec} className="p-5">
            <ChartHead title={`Against your expectations · ${s.label}`} csv={<CsvBtn name={`distribution_${sec}`} rows={s.metrics.flatMap(m => m.entities.map(e => ({ metric: m.id, entity: e.name, value: e.value, flag: e.flag })))} />}
              sections={[{ heading: HEADING.read, body: 'Each entity against the expectations your supervision profile sets for its sector: amber when it passes the watch level, red when it passes the act level. The dashed line is the middle entity (median). Select a bar to open the entity’s file.' }]} />
            <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
              {s.metrics.filter(m => m.direction !== 'neutral').map(m => (
                <div key={m.id}>
                  <div className="text-[12px] text-[var(--color-ink)] mb-1">{m.label} <span className="text-[11px] text-[var(--color-faint)]">{m.watch_above != null ? `watch above ${m.watch_above}` : m.watch_below != null ? `watch below ${m.watch_below}` : ''}{m.act_above != null ? ` · act above ${m.act_above}` : ''}</span></div>
                  <div style={{ height: 40 + 22 * Math.max(1, m.entities.length) }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={m.entities.map(e => ({ name: e.name.replace(' (demo)', ''), value: e.value ?? 0, flag: e.flag, org_id: e.org_id }))} layout="vertical" margin={{ top: 2, right: 16, left: 4, bottom: 0 }} style={{ cursor: 'pointer' }}>
                        <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--color-faint)' }} tickFormatter={(v) => m.unit === 'eur' ? balance(Number(v)) : `${v}%`} />
                        <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10.5, fill: 'var(--color-mute)' }} />
                        <Tooltip formatter={(v) => [m.unit === 'eur' ? balance(Number(v)) : `${v}%`, m.label]} />
                        {m.distribution.median != null && <ReferenceLine x={m.distribution.median} stroke="var(--color-sky)" strokeDasharray="4 3" />}
                        {m.watch_above != null && <ReferenceLine x={m.watch_above} stroke="#EF9F27" />}
                        {m.act_above != null && <ReferenceLine x={m.act_above} stroke="#E24B4A" />}
                        {m.watch_below != null && <ReferenceLine x={m.watch_below} stroke="#EF9F27" />}
                        <Bar dataKey="value" isAnimationActive={false} onClick={(bar) => { const org = (bar as { payload?: { org_id?: string } }).payload?.org_id; if (org) nav(`/supervised/${org}`) }}>
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

// How much of the at-risk value at the chosen scenario and year is led by a hazard the climate projections move.
function Projected({ share }: { share: number }) {
  return (
    <div className="mt-3 space-y-1.5">
      <div className="flex h-2.5 gap-[2px] rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={`${share}% led by a projected hazard`}>
        <div style={{ width: `${share}%`, background: 'var(--color-sky)' }} /><div style={{ width: `${100 - share}%`, background: 'var(--color-slate)' }} />
      </div>
      <div className="flex flex-wrap gap-x-4 text-[11.5px] text-[var(--color-mute)] tabular-nums">
        <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--color-sky)]" />{share}% of the value at risk led by flooding, storms or wildfire</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-[var(--color-slate)]" />{Math.round((100 - share) * 10) / 10}% by other hazards</span>
      </div>
    </div>
  )
}
