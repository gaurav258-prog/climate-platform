import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, RefreshCw } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader, SectionHead } from '../components/ui'

// Crop calibrations (E162) — every calibration is a recipe fixed before it is fitted (yield series, weather, season,
// driver); the pipeline records every run with its ledger entry. The runs that would change what customers see are
// proposed as one batch and publish only when approved through the one approvals path.

interface BatchRun { run_id: string; commodity: string; origin: string; driver: string; recipe: string; r2_oos: number | null; published_r2_oos: number | null; downside_pass: boolean; upside_pass: boolean; upside_failed: string[] | null; first_run: boolean }
interface Batch { approval_request_id: string; title: string; created_at: string; maker_id: string | null; maker: string | null; review: string | null; summary: { runs: BatchRun[]; downside_passes: number; upside_passes: number; gate_flips: string[] } | null }
interface Recipe {
  spec_id: string; commodity: string; origin: string; yield_region: string; driver: string; weather_kind: string; weather_key: string
  season_months: number[]; season_prev_months: number[]; spei_scale: number; yield_source: string; allow_cycle: boolean; basis: string; protocol: string
  latest_run_at: string | null; latest_status: string | null; outcome: string | null; latest_r2_oos: number | null; latest_downside: boolean | null; latest_upside: boolean | null; latest_upside_failed: string[] | null
  published_run_id: string | null; published_r2_oos: number | null; published_downside: boolean | null; published_upside: boolean | null; published_at: string | null
}
interface Protocol { protocol: string; downside: { gate: string }; upside: { rules: string[]; judged_on: string } }

const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const season = (r: Pick<Recipe, 'season_months' | 'season_prev_months'>) =>
  [...(r.season_prev_months ?? []).map(m => `${MONTH[m - 1]}*`), ...r.season_months.map(m => MONTH[m - 1])].join(' ')
const oos = (v: number | null | undefined) => v == null ? '—' : v.toFixed(3)
const day = (s: string | null) => s ? s.slice(0, 10) : '—'

function Verdict({ ok, held }: { ok: boolean | null | undefined; held?: string }) {
  if (ok == null) return <span className="text-[var(--color-faint)]">—</span>
  return <span className="mono text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5"
    style={{ color: ok ? 'var(--color-good)' : 'var(--color-faint)', borderColor: ok ? 'var(--color-good)' : 'var(--color-line-2)' }}>{ok ? 'publishes' : held ?? 'held'}</span>
}

export default function Calibrations() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['calibrations'], queryFn: () => api.get<{ pending: Batch[]; recipes: Recipe[]; protocol: Protocol }>('/v1/ops/calibrations') })
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<{ user?: { id?: string; user_id?: string } }>('/v1/auth/me') })
  const myId = me.data?.user?.id ?? me.data?.user?.user_id ?? null
  const [busy, setBusy] = useState(false)
  const rerun = async () => {
    setBusy(true)
    try { await api.post('/v1/ops/calibrations/run', {}); toast.success('Re-running every recipe — changed results will be proposed here.') }
    catch (e) { toast.error(apiMessage(e, 'Could not start the run.')) }
    finally { setBusy(false) }
  }
  const d = q.data
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Platform · calibrations" title="Crop calibrations"
        lead="Every calibration is a recipe fixed before it is fitted — its yield series, weather, season and driver. Each run is recorded with its audit-ledger entry; a run that would change what customers see publishes only when approved." />
      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the calibrations.')}</Card>
        : <>
          {d.pending.length === 0
            ? <Card className="p-5 text-[13px] text-[var(--color-mute)]">No calibration batch is awaiting a decision.</Card>
            : d.pending.map(b => <BatchReview key={b.approval_request_id} b={b} mine={!!myId && b.maker_id === myId} onDone={() => qc.invalidateQueries({ queryKey: ['calibrations'] })} />)}

          <Card className="p-5">
            <SectionHead icon={FlaskConical} className="mb-2">The gates ({d.protocol.protocol})</SectionHead>
            <div className="text-[12.5px] text-[var(--color-mute)] max-w-[100ch] space-y-1.5">
              <div><span className="text-[var(--color-ink)]">Downside:</span> {d.protocol.downside.gate}.</div>
              <div><span className="text-[var(--color-ink)]">Upside</span> ({d.protocol.upside.judged_on}):</div>
              <ul className="list-disc pl-5 space-y-0.5">{d.protocol.upside.rules.map(r => <li key={r}>{r}</li>)}</ul>
            </div>
          </Card>

          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
              <SectionHead>Recipes · {d.recipes.length}</SectionHead>
              <Button variant="ghost" onClick={rerun} disabled={busy}><RefreshCw size={13} /> Re-run all</Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full tabular-nums text-[12px]">
                <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left">
                  {['Crop', 'Origin', 'Driver', 'Weather', 'Season', 'Yield series', 'Latest run', 'r²oos', 'Downside', 'Upside'].map(h => <th key={h} className="font-normal px-3 py-2">{h}</th>)}
                </tr></thead>
                <tbody>{d.recipes.map(r => (
                  <tr key={r.spec_id} className="border-t border-[var(--color-line)] align-top" title={r.basis}>
                    <td className="px-3 py-1.5 text-[var(--color-ink)]">{r.commodity}</td>
                    <td className="px-3 mono">{r.origin}{r.yield_region ? ` · ${r.yield_region}` : ''}</td>
                    <td className="px-3">{r.driver.replace('_', ' ')}</td>
                    <td className="px-3 mono text-[11px]">{r.weather_kind === 'box' ? r.weather_key : `crop area · ${r.weather_key}`}</td>
                    <td className="px-3 mono text-[11px]">{season(r)}</td>
                    <td className="px-3 text-[11px] text-[var(--color-mute)]">{r.yield_source}{r.allow_cycle ? ' · cycle removed' : ''}</td>
                    <td className="px-3 mono text-[11px]">{day(r.latest_run_at)} · {r.latest_status ?? '—'}</td>
                    <td className="px-3 mono">{oos(r.published_r2_oos ?? r.latest_r2_oos)}</td>
                    <td className="px-3"><Verdict ok={r.published_run_id ? r.published_downside : r.latest_downside} /></td>
                    <td className="px-3"><Verdict ok={r.published_run_id ? r.published_upside : r.latest_upside}
                      held={(r.latest_downside ?? r.published_downside) ? 'held' : 'not judged'} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
            <div className="px-5 py-2 text-[11px] text-[var(--color-faint)] border-t border-[var(--color-line)]">* a month of the previous calendar year (a season crossing the new year). Hover a row for why its recipe is what it is.</div>
          </Card>
        </>}
    </div>
  )
}

function BatchReview({ b, mine, onDone }: { b: Batch; mine: boolean; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const s = b.summary
  const decide = async (decision: 'approved' | 'returned') => {
    setBusy(true)
    try {
      await api.post(`/v1/approvals/${b.approval_request_id}/decide`, { decision, reason: reason.trim() || undefined })
      toast.success(decision === 'approved' ? 'Approved — the runs are published.' : 'Returned — nothing published.')
      onDone()
    } catch (e) { toast.error(apiMessage(e, 'Could not record the decision.')) }
    finally { setBusy(false) }
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center gap-x-5 gap-y-1 text-[12.5px]">
        <span className="mono text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5" style={{ color: 'var(--color-sky)', borderColor: 'var(--color-sky)' }}>awaiting decision</span>
        <span className="text-[var(--color-ink)]">{b.title}</span>
        <span className="text-[var(--color-mute)]">proposed {day(b.created_at)} by {b.maker ?? 'the platform'}</span>
        {s && <span className="text-[var(--color-mute)]">{s.downside_passes} pass the downside gate · {s.upside_passes} pass the upside rules{s.gate_flips.length ? ` · gate changes: ${s.gate_flips.join(', ')}` : ' · no gate changes'}</span>}
      </div>
      {b.review && <div className="px-5 pt-3 text-[12px] text-[var(--color-mute)]">{b.review}</div>}
      {s && <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full tabular-nums text-[12px]">
          <thead className="sticky top-0 bg-[var(--color-bg-1,var(--color-bg))]"><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left">
            {['Crop', 'Origin', 'Driver', 'Recipe', 'r²oos published → this run', 'Downside', 'Upside', 'Upside held because'].map(h => <th key={h} className="font-normal px-3 py-2">{h}</th>)}
          </tr></thead>
          <tbody>{s.runs.map(r => (
            <tr key={r.run_id} className="border-t border-[var(--color-line)]">
              <td className="px-3 py-1 text-[var(--color-ink)]">{r.commodity}</td><td className="px-3 mono">{r.origin}</td>
              <td className="px-3">{r.driver.replace('_', ' ')}</td><td className="px-3 mono text-[11px]">{r.recipe}</td>
              <td className="px-3 mono">{oos(r.published_r2_oos)} → <span className={r.published_r2_oos != null && r.r2_oos !== r.published_r2_oos ? 'text-[var(--color-warn)]' : ''}>{oos(r.r2_oos)}</span></td>
              <td className="px-3"><Verdict ok={r.downside_pass} /></td>
              <td className="px-3"><Verdict ok={r.upside_pass} held={r.downside_pass ? 'held' : 'not judged'} /></td>
              <td className="px-3 text-[11px] text-[var(--color-mute)]">{r.upside_pass || !r.downside_pass ? '' : (r.upside_failed ?? []).join('; ')}</td>
            </tr>))}</tbody>
        </table>
      </div>}
      <div className="px-5 py-4 border-t border-[var(--color-line)] flex flex-wrap items-end gap-3">
        {mine ? <div className="text-[12px] text-[var(--color-warn)]">You proposed this batch — another person decides it.</div> : <>
          <textarea value={reason} onChange={e => setReason(e.target.value)} placeholder="What you checked (kept with the decision)"
            className="flex-1 min-w-[240px] h-16 rounded-lg border border-[var(--color-line-2)] bg-transparent p-2 text-[12.5px]" />
          <Button onClick={() => decide('approved')} disabled={busy}>Approve — publish</Button>
          <Button variant="ghost" onClick={() => decide('returned')} disabled={busy}>Return</Button>
        </>}
      </div>
    </Card>
  )
}
