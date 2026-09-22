import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, ReferenceLine, Cell } from 'recharts'
import { LayoutGrid, Rows3 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
const eurS = (v: number) => v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`
// ── Peer benchmark — every sector in the profile, every configured metric, every supervised entity ────────
interface BenchEntity { org_id: string; name: string; value: number | null; flag: string; percentile: number | null }
interface BenchMetric { id: string; label: string; unit: string; direction?: string; watch_above?: number; act_above?: number; watch_below?: number
  distribution: { n: number; min?: number; p25?: number; median?: number; p75?: number; max?: number }; entities: BenchEntity[] }
interface BenchResp { scenario: string; horizon: string; profile_id: string
  sectors: Record<string, { label: string; book_noun: string; frameworks: string[]; n_entities: number; metrics: BenchMetric[] }> }
const FLAGC: Record<string, string> = { act: 'var(--color-bad)', watch: 'var(--color-warn)', ok: 'var(--color-good)', na: 'var(--color-faint)' }
const fmtV = (unit: string, v: number | null | undefined) => v == null ? '—' : unit === 'eur' ? eurS(v) : `${v}%`

const eurAxis = (v: number) => eurS(v)

function BenchmarkCard() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const can = (profile?.permissions ?? []).includes('supervisor.benchmark.view')
  const q = useQuery({ queryKey: ['supervisor-benchmark'], enabled: can, queryFn: () => api.get<BenchResp>('/v1/supervisor/benchmark') })
  const [sector, setSector] = useState<string | null>(null)
  const [view, setView] = useState<'table' | 'chart'>('table')
  if (!can) return null
  const d = q.data
  const keys = d ? Object.keys(d.sectors) : []
  const sec = d ? d.sectors[sector && d.sectors[sector] ? sector : keys[0]] : null
  const openEntity = (org?: string) => { if (org) nav(`/supervised/${org}`) }
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-3">
        <div>
          <div className="text-[15px] font-semibold">Peer benchmark</div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">Each entity's own engine figures, side by side. Flags are your profile's supervisory expectations, not a judgement of the entity.{d ? ` Basis ${d.scenario} · ${d.horizon}.` : ''}</div>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {keys.length > 1 && (
            <div className="flex gap-1">{keys.map(k => (
              <button key={k} onClick={() => setSector(k)} className={`px-2.5 py-1 rounded-lg text-[12px] border ${sec === d!.sectors[k] ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{d!.sectors[k].label}</button>))}</div>
          )}
          <div className="flex gap-0.5 p-0.5 rounded-lg border border-[var(--color-line)]">
            {([['table', 'Table', Rows3], ['chart', 'Chart', LayoutGrid]] as const).map(([k, l, Icon]) => (
              <button key={k} onClick={() => setView(k)} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11.5px] transition ${view === k ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-mute)]'}`}>
                <Icon size={12} /> {l}
              </button>))}
          </div>
        </div>
      </div>
      {q.isLoading ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">computing the population benchmark…</div>
        : !sec ? <div className="text-[12.5px] text-[var(--color-faint)]">No sector in your profile has supervised entities yet.</div>
        : sec.n_entities === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No supervised {sec.label.toLowerCase()} in your population.</div>
        : view === 'table' ? (
        <div className="overflow-x-auto">
          <table className="data-table w-full text-[12.5px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="">Metric</th><th className="num">Peer median</th>
              {sec.metrics[0].entities.map(e => <th key={e.org_id} className="num"><Link to={`/supervised/${e.org_id}`} className="hover:text-[var(--color-sky)] hover:underline">{e.name.replace(' (demo)', '')}</Link></th>)}
            </tr></thead>
            <tbody>{sec.metrics.map(m => (
              <tr key={m.id} className="border-t border-[var(--color-line)]">
                <td className="text-[var(--color-ink)]">{m.label}
                  {(m.watch_above != null || m.watch_below != null) && <span className="mono text-[10px] text-[var(--color-faint)] ml-2">{m.watch_above != null ? `watch >${m.watch_above}` : `watch <${m.watch_below}`}{m.act_above != null ? ` · act >${m.act_above}` : ''}</span>}</td>
                <td className="num mono text-[var(--color-mute)]">{fmtV(m.unit, m.distribution.median)}</td>
                {m.entities.map(e => (
                  <td key={e.org_id} className="pr-3 text-right">
                    <Link to={`/supervised/${e.org_id}`} className="mono hover:underline" style={{ color: FLAGC[e.flag] }}
                      title={e.percentile != null ? `${e.percentile}th percentile` : ''}>{fmtV(m.unit, e.value)}</Link>
                  </td>))}
              </tr>))}</tbody>
          </table>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-2">{sec.n_entities} {sec.label.toLowerCase()} · frameworks expected: {sec.frameworks.join(', ')} · colour = flag against your thresholds (green within, amber watch, red act)</div>
        </div>) : (
        <div>
          <div className="text-[11.5px] text-[var(--color-mute)] mb-3">each entity against your profile's expectations — amber watch, red act; the dashed line is the peer median · click a bar to open the entity file</div>
          <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
            {sec.metrics.filter(m => m.direction !== 'neutral').map(m => (
              <div key={m.id}>
                <div className="text-[12px] text-[var(--color-ink)] mb-1">{m.label} <span className="mono text-[10px] text-[var(--color-faint)]">{m.watch_above != null ? `watch >${m.watch_above}` : m.watch_below != null ? `watch <${m.watch_below}` : ''}{m.act_above != null ? ` · act >${m.act_above}` : ''}</span></div>
                <div style={{ height: 40 + 22 * Math.max(1, m.entities.length) }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={m.entities.map(e => ({ name: e.name.replace(' (demo)', ''), value: e.value ?? 0, flag: e.flag, org_id: e.org_id }))} layout="vertical" margin={{ top: 2, right: 16, left: 4, bottom: 0 }} style={{ cursor: 'pointer' }}>
                      <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--color-faint)' }} tickFormatter={(v) => m.unit === 'eur' ? eurAxis(Number(v)) : `${v}%`} />
                      <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 10.5, fill: 'var(--color-mute)' }} />
                      <Tooltip formatter={(v) => [m.unit === 'eur' ? eurAxis(Number(v)) : `${v}%`, m.label]} />
                      {m.distribution.median != null && <ReferenceLine x={m.distribution.median} stroke="var(--color-sky)" strokeDasharray="4 3" />}
                      {m.watch_above != null && <ReferenceLine x={m.watch_above} stroke="#EF9F27" />}
                      {m.act_above != null && <ReferenceLine x={m.act_above} stroke="#E24B4A" />}
                      {m.watch_below != null && <ReferenceLine x={m.watch_below} stroke="#EF9F27" />}
                      <Bar dataKey="value" isAnimationActive={false} onClick={(bar) => openEntity((bar as { org_id?: string; payload?: { org_id?: string } }).org_id ?? (bar as { payload?: { org_id?: string } }).payload?.org_id)}>
                        {m.entities.map((e, i) => <Cell key={i} fill={FLAGC[e.flag]} />)}</Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>))}
          </div>
        </div>)}
    </Card>
  )
}


export default function SupervisorBenchmark() {
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Peer benchmark" title="The population, side by side"
        lead="Each entity's own engine figures on the metrics your profile declares. Flags are your supervisory expectations, not a judgement of the entity." />
      <BenchmarkCard />
    </div>
  )
}
