import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ChevronDown, Satellite, ArrowDownRight, ArrowUpRight, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import { Card, Lens } from './ui'
import { hazardLabel, sevColor } from '../lib/hazards'
import { HBar } from './Charts'
import LineageGraph from './LineageGraph'

// Bidirectional data lineage inside the filing drawer: click a reported figure to trace it down to the
// satellite/agency feed (asset → H3 cell → golden-source row → source feed), and from any cell back up to
// every holding & filing that reuses it. Nothing invented — a missing golden row shows as "—".

interface HazEntry { hazard: string; exposed_value_eur: number | null; n_exposed: number; max_score: number }
interface Source { key: string; name: string; maturity: string | null; status: string | null }
interface Granular { risk_score: number | null; model_version: string | null; data_vintage: string | null; scored_at: string | null; fingerprint: string | null; ci_lower: number | null; ci_upper: number | null; score_lane: string | null }
interface Contributor { asset_id: string; asset_name: string; value_eur: number | null; h3_cell: string; country: string | null; filed: { score: number | null; bucket: string | null; model_version: string | null }; granular: Granular | null; drift: boolean }
interface Lineage { supported: boolean; framework: string; message?: string; hazard: string; basis: { scenario: string; horizon: string }; cell: { exposed_value_eur: number | null; n_exposed: number; max_score: number }; contributors: Contributor[]; sources: Source[]; drift_count: number }
interface UsedBy { vertical: string; framework: string | null; filing: { filing_id: string; status: string } | null; n: number; value_eur: number; entities: { entity_id: string; name: string; value_eur: number | null }[] }
interface Upstream { h3_cell: string; hazards_scored_here: string[]; used_by: UsedBy[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const feedDot = (s: string | null) => s === 'fresh' || s === 'live' ? '#34d399' : s === 'overdue' || s === 'failed' ? '#fb7185' : s === 'due_soon' ? '#e8b24c' : '#64748b'

export default function FilingLineage({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['lineage-haz', filingId], queryFn: () => api.get<{ hazards: HazEntry[] }>(`/v1/filings/${filingId}/lineage/hazards`) })
  const [open, setOpen] = useState<string | null>(null)
  const hazards = q.data?.hazards ?? []
  if (!hazards.length) return null

  const charted = hazards.filter(h => (h.exposed_value_eur ?? 0) > 0).slice(0, 8)

  return (
    <div className="space-y-4">
      {charted.length > 0 && (
        <div>
          <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Exposure by hazard · value at High+</div>
          <Card className="p-4">
            <HBar data={charted.map(h => ({ label: hazardLabel(h.hazard), value: h.exposed_value_eur ?? 0, color: sevColor(h.max_score) }))} format={eur} />
          </Card>
        </div>
      )}
      <div>
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Reported figures · trace to source</div>
        <Lens kind="insight" />
      </div>
      <Card className="p-0 overflow-hidden">
        {hazards.map(h => (
          <div key={h.hazard} className="border-b border-[var(--color-line)] last:border-0">
            <button onClick={() => setOpen(open === h.hazard ? null : h.hazard)}
              className="w-full px-4 py-2.5 flex items-center gap-3 hover:bg-[var(--color-panel)] transition text-left">
              {open === h.hazard ? <ChevronDown size={14} className="text-[var(--color-faint)]" /> : <ChevronRight size={14} className="text-[var(--color-faint)]" />}
              <span className="flex-1 text-[13px] text-[var(--color-ink)]">{hazardLabel(h.hazard)}</span>
              <span className="mono text-[11px] text-[var(--color-faint)]">{h.n_exposed} assets</span>
              <span className="mono text-[12.5px] tabular-nums text-[var(--color-mute)] w-20 text-right">{eur(h.exposed_value_eur)}</span>
            </button>
            {open === h.hazard && <HazardTrace filingId={filingId} hazard={h.hazard} />}
          </div>
        ))}
      </Card>
      </div>
    </div>
  )
}

function HazardTrace({ filingId, hazard }: { filingId: string; hazard: string }) {
  const q = useQuery({ queryKey: ['lineage', filingId, hazard], queryFn: () => api.get<Lineage>(`/v1/filings/${filingId}/lineage?hazard=${hazard}`) })
  const [graph, setGraph] = useState(false)
  const d = q.data
  if (q.isLoading) return <div className="px-4 py-3 text-[12px] text-[var(--color-faint)]">tracing…</div>
  if (!d) return <div className="px-4 py-3 text-[12px] text-[var(--color-bad)]">could not trace this cell</div>
  if (!d.supported) return <div className="px-4 py-3 text-[12px] text-[var(--color-mute)]">{d.message}</div>

  return (
    <div className="px-4 py-3 bg-[var(--color-panel)] space-y-3">
      <div className="flex justify-end">
        <div className="inline-flex rounded-lg border border-[var(--color-line-2)] overflow-hidden text-[10.5px] mono">
          <button onClick={() => setGraph(false)} className={`px-2 py-0.5 ${!graph ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}`}>list</button>
          <button onClick={() => setGraph(true)} className={`px-2 py-0.5 ${graph ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}`}>graph</button>
        </div>
      </div>
      {graph && (
        <LineageGraph hazardLabel={hazardLabel(d.hazard)} exposed={d.cell.exposed_value_eur}
          contributors={d.contributors} sources={d.sources} />
      )}
      {/* source feeds */}
      <div className="flex items-center gap-2 flex-wrap">
        <Satellite size={13} className="text-[var(--color-sky)]" />
        <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Source</span>
        {d.sources.length === 0 && <span className="text-[11px] text-[var(--color-faint)]">not mapped</span>}
        {d.sources.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-[11px] rounded-full border border-[var(--color-line-2)] px-2 py-0.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: feedDot(s.status) }} />{s.name}
          </span>
        ))}
      </div>
      {d.drift_count > 0 && (
        <div className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-warn)]">
          <AlertTriangle size={12} /> {d.drift_count} asset{d.drift_count === 1 ? '' : 's'} scored with a model version newer than the filed one.
        </div>
      )}

      {/* contributors: asset → cell → golden-source row */}
      <div className="space-y-2">
        <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] flex items-center gap-1">
          <ArrowDownRight size={12} /> Contributing assets ({d.contributors.length})
        </div>
        {d.contributors.map(c => <ContributorRow key={c.asset_id} c={c} />)}
      </div>
    </div>
  )
}

function ContributorRow({ c }: { c: Contributor }) {
  const [rev, setRev] = useState(false)
  const g = c.granular
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-2.5">
      <div className="flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] text-[var(--color-ink)] truncate">{c.asset_name}{c.country ? <span className="text-[var(--color-faint)]"> · {c.country}</span> : null}</div>
          <button onClick={() => setRev(r => !r)} className="mono text-[10px] text-[var(--color-sky)] hover:underline inline-flex items-center gap-1">
            <ArrowUpRight size={11} /> cell {c.h3_cell.slice(0, 10)}… · who else uses it
          </button>
        </div>
        <div className="mono text-[12px] tabular-nums text-[var(--color-mute)]">{eur(c.value_eur)}</div>
      </div>
      {/* golden-source row */}
      <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] border-t border-[var(--color-line)] pt-2">
        <Kv k="filed score" v={c.filed.score != null ? `${c.filed.score} (${c.filed.bucket})` : '—'} />
        <Kv k="golden source" v={g?.risk_score != null ? String(g.risk_score) : '—'} tone={c.drift ? 'warn' : undefined} />
        <Kv k="model" v={g?.model_version ?? '—'} mono />
        <Kv k="data vintage" v={g?.data_vintage ? g.data_vintage.slice(0, 10) : '—'} />
        {g?.fingerprint && <Kv k="fingerprint" v={g.fingerprint + '…'} mono />}
        {g?.ci_lower != null && <Kv k="band" v={`${g.ci_lower}–${g.ci_upper}`} />}
      </div>
      {rev && <ReverseTrace h3={c.h3_cell} />}
    </div>
  )
}

function ReverseTrace({ h3 }: { h3: string }) {
  const q = useQuery({ queryKey: ['upstream', h3], queryFn: () => api.get<Upstream>(`/v1/lineage/cell/${h3}`) })
  const d = q.data
  if (q.isLoading) return <div className="mt-2 text-[11px] text-[var(--color-faint)]">tracing reuse…</div>
  if (!d) return null
  return (
    <div className="mt-2 rounded-lg bg-[var(--color-panel-2)] p-2.5 space-y-2">
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">This granular cell also feeds</div>
      <div className="mono text-[10.5px] text-[var(--color-faint)]">{d.hazards_scored_here.length} hazards scored here: {d.hazards_scored_here.map(hazardLabel).join(', ')}</div>
      {d.used_by.map((u, i) => (
        <div key={i} className="text-[11.5px]">
          <span className="text-[var(--color-ink)] capitalize">{u.vertical}</span>
          <span className="text-[var(--color-mute)]"> · {u.n} holding{u.n === 1 ? '' : 's'} · {eur(u.value_eur)}</span>
          {u.filing && <span className="mono text-[10px] text-[var(--color-sky)]"> → {u.framework} filing ({u.filing.status})</span>}
        </div>
      ))}
    </div>
  )
}

function Kv({ k, v, mono, tone }: { k: string; v: string; mono?: boolean; tone?: 'warn' }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-[var(--color-faint)]">{k}</span>
      <span className={`${mono ? 'mono ' : ''}text-right truncate`} style={{ color: tone === 'warn' ? 'var(--color-warn)' : 'var(--color-ink)' }}>{v}</span>
    </div>
  )
}
