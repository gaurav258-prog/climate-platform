import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, RefreshCw } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader, SectionHead } from '../components/ui'
import { HEADING, InfoButton, type Details } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { hazardLabel } from '../lib/hazards'
import { countryName } from '../lib/countries'

// Crop calibrations (E162) — every calibration is a recipe fixed before it is fitted (yield series, weather, season,
// driver); the pipeline records every run with its ledger entry. The runs that would change what customers see are
// proposed as one batch and publish only when approved through the one approvals path.

interface BatchRun { run_id: string; commodity: string; origin: string; driver: string; recipe: string; r2_oos: number | null; published_r2_oos: number | null; downside_pass: boolean; upside_pass: boolean; upside_failed: string[] | null; first_run: boolean }
interface Withdrawn { commodity: string; origin: string; driver: string; reason: string | null }
// A batch as it stands (E168): the runs still awaiting the decision, and those withdrawn since it was proposed.
interface Batch { approval_request_id: string; title: string; proposed_runs: number; created_at: string; maker_id: string | null; maker: string | null; review: string | null; summary: { runs: BatchRun[]; downside_passes: number; upside_passes: number; gate_flips: string[] } | null; withdrawn: Withdrawn[] }
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
// where a recipe reads its weather: a named area (equal weights) or the crop's own growing area
const WEATHER: Record<string, string> = { box: 'Named area', crop_area: "Crop's growing area" }
const weather = (kind: string) => WEATHER[kind] ?? 'Another area'
const origin = (code: string, region?: string) => `${countryName(code)}${region ? ` · ${region}` : ''}`

// A recipe's own record, one click away: why it is what it is.
const recipeDetails = (r: Recipe): Details => ({
  title: `${r.commodity} · ${countryName(r.origin)}`, sections: [{ heading: 'Why this recipe', body: r.basis }],
})
// The tests every calibration is judged by (the protocol the server states), one click away.
const gatesDetails = (pr: Protocol): Details => ({
  title: 'The tests a calibration must pass',
  sections: [
    { heading: 'Loss range', body: pr.downside.gate },
    { heading: 'Gain range', body: <>Judged on {pr.upside.judged_on}.<ul className="list-disc pl-5 mt-1 space-y-0.5">{pr.upside.rules.map(r => <li key={r}>{r}</li>)}</ul></> },
  ],
})

function Verdict({ ok, held }: { ok: boolean | null | undefined; held?: string }) {
  if (ok == null) return <span className="text-[var(--color-faint)]">—</span>
  return <span className="text-[10.5px] font-medium border rounded px-1.5 py-0.5 whitespace-nowrap"
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
        lead="Recipes fixed before they are fitted; changes publish on approval."
        about={[
          { heading: HEADING.shows, body: 'Every calibration is a recipe fixed before it is fitted — its yield series, weather, season and driver. Each run is recorded with its audit-ledger entry.' },
          { heading: HEADING.read, body: 'A run that would change what customers see is proposed in a batch and publishes only when a second person approves it.' },
        ]} />
      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the calibrations.')}</Card>
        : <>
          {d.pending.length === 0
            ? <Card className="p-5 text-[13px] text-[var(--color-mute)]">No calibration batch is awaiting a decision.</Card>
            : d.pending.map(b => <BatchReview key={b.approval_request_id} b={b} mine={!!myId && b.maker_id === myId} onDone={() => qc.invalidateQueries({ queryKey: ['calibrations'] })} />)}

          <Card className="p-5 flex flex-wrap items-center gap-3">
            <SectionHead icon={FlaskConical}>The tests a calibration must pass</SectionHead>
            <InfoButton details={gatesDetails(d.protocol)} label="Read the tests" />
          </Card>

          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
              <SectionHead>Recipes · {d.recipes.length}</SectionHead>
              <Button variant="ghost" onClick={rerun} disabled={busy}><RefreshCw size={13} /> Re-run all</Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full tabular-nums text-[12px]">
                <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
                  {['Crop', 'Origin', 'Driver', 'Weather', 'Season', 'Yield series', 'Latest run', 'Out-of-sample fit (r²)', 'Loss range', 'Gain range'].map(h => <th key={h} className="font-medium px-3 py-2">{h}</th>)}
                </tr></thead>
                <tbody>{d.recipes.map(r => (
                  <tr key={r.spec_id} className="border-t border-[var(--color-line)] align-top tabular-nums">
                    <td className="px-3 py-1.5 text-[var(--color-ink)] whitespace-nowrap">{r.commodity} <InfoButton compact details={recipeDetails(r)} /></td>
                    <td className="px-3">{origin(r.origin, r.yield_region)}</td>
                    <td className="px-3">{hazardLabel(r.driver)}</td>
                    <td className="px-3 text-[11.5px]">{weather(r.weather_kind)}</td>
                    <td className="px-3 text-[11.5px]">{season(r)}</td>
                    <td className="px-3 text-[11px] text-[var(--color-mute)]">{r.yield_source}{r.allow_cycle ? ' · cycle removed' : ''}</td>
                    <td className="px-3 text-[11.5px] whitespace-nowrap">{day(r.latest_run_at)} {r.latest_status && <StatusChip value={r.latest_status} />}</td>
                    <td className="px-3">{oos(r.published_r2_oos ?? r.latest_r2_oos)}</td>
                    <td className="px-3"><Verdict ok={r.published_run_id ? r.published_downside : r.latest_downside} /></td>
                    <td className="px-3"><Verdict ok={r.published_run_id ? r.published_upside : r.latest_upside}
                      held={(r.latest_downside ?? r.published_downside) ? 'held' : 'not judged'} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
            <div className="px-5 py-2 text-[11px] text-[var(--color-faint)] border-t border-[var(--color-line)]">* a month of the previous calendar year</div>
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
        <StatusChip value="pending" label="Awaiting decision" />
        <span className="text-[var(--color-ink)] inline-flex items-center gap-1">{b.title}
          {b.review && <InfoButton compact details={{ title: b.title, sections: [{ heading: 'Why it was proposed', body: b.review }] }} />}</span>
        <span className="text-[var(--color-mute)]">proposed {day(b.created_at)} by {b.maker ?? 'the platform'}</span>
        {s && <span className="text-[var(--color-mute)] inline-flex items-center gap-1">{s.downside_passes} pass the loss test · {s.upside_passes} pass the gain rules · {s.gate_flips.length ? `${s.gate_flips.length} change a test's result` : 'no test result changes'}
          {s.gate_flips.length > 0 && <InfoButton compact details={{ title: "Runs that change a test's result", sections: [{ heading: 'Crop, origin and driver', body: s.gate_flips.join(' · ') }] }} />}</span>}
      </div>
      {b.withdrawn.length > 0 && <details className="px-5 pt-2 text-[12px] text-[var(--color-mute)]">
        <summary className="cursor-pointer">
          {b.proposed_runs - b.withdrawn.length} of the {b.proposed_runs} runs proposed await this decision · {b.withdrawn.length} withdrawn since, never published — show why
        </summary>
        <div className="mt-2 max-h-48 overflow-y-auto">
          <table className="w-full text-[11.5px]"><tbody>{b.withdrawn.map(w => (
            <tr key={`${w.commodity}-${w.origin}-${w.driver}`} className="border-t border-[var(--color-line)] align-top">
              <td className="py-1 pr-3 text-[var(--color-ink)] whitespace-nowrap">{w.commodity}</td><td className="pr-3">{countryName(w.origin)}</td>
              <td className="pr-3">{hazardLabel(w.driver)}</td>
              <td>{w.reason && <InfoButton compact details={{ title: `${w.commodity} · ${countryName(w.origin)}`, sections: [{ heading: 'Why it was withdrawn', body: w.reason }] }} />}</td>
            </tr>))}</tbody></table>
        </div>
      </details>}
      {s && <div className="overflow-x-auto max-h-96 overflow-y-auto">
        <table className="w-full tabular-nums text-[12px]">
          <thead className="sticky top-0 bg-[var(--color-bg-1,var(--color-bg))]"><tr className="text-[var(--color-faint)] text-[11px] text-left">
            {['Crop', 'Origin', 'Driver', 'Weather', 'Out-of-sample fit: published → this run', 'Loss range', 'Gain range'].map(h => <th key={h} className="font-medium px-3 py-2">{h}</th>)}
          </tr></thead>
          <tbody>{s.runs.map(r => (
            <tr key={r.run_id} className="border-t border-[var(--color-line)] tabular-nums">
              <td className="px-3 py-1 text-[var(--color-ink)]">{r.commodity}</td><td className="px-3">{countryName(r.origin)}</td>
              <td className="px-3">{hazardLabel(r.driver)}</td><td className="px-3 text-[11.5px]">{weather(r.recipe)}</td>
              <td className="px-3">{oos(r.published_r2_oos)} → <span className={r.published_r2_oos != null && r.r2_oos !== r.published_r2_oos ? 'text-[var(--color-warn)]' : ''}>{oos(r.r2_oos)}</span></td>
              <td className="px-3"><Verdict ok={r.downside_pass} /></td>
              <td className="px-3 whitespace-nowrap"><Verdict ok={r.upside_pass} held={r.downside_pass ? 'held' : 'not judged'} />
                {!r.upside_pass && r.downside_pass && (r.upside_failed ?? []).length > 0 &&
                  <InfoButton compact className="ml-1" details={{ title: `${r.commodity} · ${countryName(r.origin)}`, sections: [{ heading: 'Gain range held because', body: (r.upside_failed ?? []).join('; ') }] }} />}</td>
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
