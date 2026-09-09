import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
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

function BenchmarkCard() {
  const { profile } = useAuth()
  const can = (profile?.permissions ?? []).includes('supervisor.benchmark.view')
  const q = useQuery({ queryKey: ['supervisor-benchmark'], enabled: can, queryFn: () => api.get<BenchResp>('/v1/supervisor/benchmark') })
  const [sector, setSector] = useState<string | null>(null)
  if (!can) return null
  const d = q.data
  const keys = d ? Object.keys(d.sectors) : []
  const sec = d ? d.sectors[sector && d.sectors[sector] ? sector : keys[0]] : null
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-3">
        <div>
          <div className="text-[15px] font-semibold">Peer benchmark</div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">Each entity's own engine figures, side by side. Flags are your profile's supervisory expectations, not a judgement of the entity.{d ? ` Basis ${d.scenario} · ${d.horizon}.` : ''}</div>
        </div>
        {keys.length > 1 && (
          <div className="flex gap-1">{keys.map(k => (
            <button key={k} onClick={() => setSector(k)} className={`px-2.5 py-1 rounded-lg text-[12px] border ${sec === d!.sectors[k] ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{d!.sectors[k].label}</button>))}</div>
        )}
      </div>
      {q.isLoading ? <div className="py-8 text-center text-[var(--color-faint)] text-sm">computing the population benchmark…</div>
        : !sec ? <div className="text-[12.5px] text-[var(--color-faint)]">No sector in your profile has supervised entities yet.</div>
        : sec.n_entities === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No supervised {sec.label.toLowerCase()} in your population.</div>
        : (
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
                {m.entities.map(e => <td key={e.org_id} className="pr-3 text-right mono" style={{ color: FLAGC[e.flag] }} title={e.percentile != null ? `${e.percentile}th percentile` : ''}>{fmtV(m.unit, e.value)}</td>)}
              </tr>))}</tbody>
          </table>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-2">{sec.n_entities} {sec.label.toLowerCase()} · frameworks expected: {sec.frameworks.join(', ')} · colour = flag against your thresholds (green within, amber watch, red act)</div>
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
