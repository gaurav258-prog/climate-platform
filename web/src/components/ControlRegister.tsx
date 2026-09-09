import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, StatGrid } from '../components/ui'

// The reporting control register — every automated reporting check named as a control, with its owner, review
// date, last outcome and pass rate over the window. Tested daily by the sweep and on demand here.
interface Last { outcome: 'pass' | 'fail' | 'not_applicable'; n_items: number; n_failed: number; detail: Record<string, unknown>[]; at: string }
interface Control { id: string; label: string; category: string; category_label: string; type: string; frequency: string; objective: string; rules: string[]; evidence: string; anchor: string
  last: Last | null; pass_rate_pct: number | null; n_tests: number; last_fail: string | null; owner: string | null; owner_user_id: string | null; review_by: string | null; review_overdue: boolean; owner_note: string | null }
interface Resp { register_version: string; categories: Record<string, string>; controls: Control[]; window_days: number; last_run: { at: string; trigger: string; n_pass: number; n_fail: number; n_na: number } | null
  summary: { controls: number; pass: number; fail: number; not_applicable: number; untested: number; unowned: number; reviews_overdue: number }; can_manage: boolean }
const OUT: Record<string, { label: string; color: string }> = { pass: { label: 'Pass', color: 'var(--color-good)' }, fail: { label: 'Fail', color: 'var(--color-bad)' }, not_applicable: { label: 'n/a', color: 'var(--color-faint)' } }
const dt = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'
const inp = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] outline-none focus:border-[var(--color-sky)]'

export default function ControlRegister() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['controls'], queryFn: () => api.get<Resp>('/v1/controls') })
  const pq = useQuery({ queryKey: ['controls-people'], queryFn: () => api.get<{ people: { user_id: string; full_name: string }[] }>('/v1/controls/people') })
  const [busy, setBusy] = useState(false); const [open, setOpen] = useState<string | null>(null); const [cat, setCat] = useState('')
  const d = q.data
  const test = async () => {
    setBusy(true)
    try { const r = await api.post<{ pass: number; fail: number; not_applicable: number }>('/v1/controls/test'); toast.success(`Tested: ${r.pass} pass, ${r.fail} fail, ${r.not_applicable} not applicable.`); await qc.invalidateQueries({ queryKey: ['controls'] }) }
    catch (e) { toast.error((e as Error).message || 'Could not test the controls.') } finally { setBusy(false) }
  }
  const setOwner = async (c: Control, patch: { owner_user_id?: string | null; review_by?: string | null; note?: string | null }) => {
    try { await api.put(`/v1/controls/${c.id}/owner`, { owner_user_id: c.owner_user_id, review_by: c.review_by, note: c.owner_note, ...patch }); await qc.invalidateQueries({ queryKey: ['controls'] }) }
    catch (e) { toast.error((e as Error).message || 'Could not save.') }
  }
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading the register…</Card>
  if (!d) return <div className="text-[12.5px] text-[var(--color-bad)]">The control register is not available for this organisation.</div>
  const s = d.summary
  const rows = d.controls.filter(c => !cat || c.category === cat)
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="max-w-[760px]">
            <div className="text-[13px] font-medium text-[var(--color-ink)]">Reporting control register <span className="mono text-[10.5px] text-[var(--color-faint)]">v{d.register_version}</span></div>
            <div className="text-[12px] text-[var(--color-mute)] mt-1">Every automated check the platform runs over your regulatory reporting, named as a control: its objective, how often it runs, the evidence it leaves and the regulatory expectation it answers. Controls are tested daily and on demand; every test is recorded, so operating effectiveness has a history an auditor can read. Assign an owner and a review date to each.</div>
            <div className="mono text-[10.5px] text-[var(--color-faint)] mt-2">{d.last_run ? `last tested ${dt(d.last_run.at)} UTC · ${d.last_run.trigger}` : 'never tested'} · pass rate over {d.window_days} days</div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" onClick={() => download('/v1/controls/register.csv', 'reporting-control-register.csv')}>Export register (CSV)</Button>
            {d.can_manage && <Button onClick={test} disabled={busy}>{busy ? 'Testing…' : 'Test all controls now'}</Button>}
          </div>
        </div>
      </Card>
      <StatGrid cols={4} items={[
        { label: 'Controls passing', value: `${s.pass} / ${s.controls - s.not_applicable}`, sub: `${s.not_applicable} not applicable · ${s.untested} untested`, accent: s.fail ? 'var(--color-warn)' : 'var(--color-good)' },
        { label: 'Failing', value: String(s.fail), sub: 'controls with at least one failed item', accent: s.fail ? 'var(--color-bad)' : undefined },
        { label: 'Without an owner', value: String(s.unowned), sub: 'assign below', accent: s.unowned ? 'var(--color-warn)' : undefined },
        { label: 'Reviews overdue', value: String(s.reviews_overdue), sub: 'review date passed', accent: s.reviews_overdue ? 'var(--color-bad)' : undefined },
      ]} />
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <button onClick={() => setCat('')} className={`px-2.5 py-1 rounded-full text-[11.5px] border ${!cat ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>All</button>
          {Object.entries(d.categories).map(([k, v]) => <button key={k} onClick={() => setCat(k)} className={`px-2.5 py-1 rounded-full text-[11.5px] border ${cat === k ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{v}</button>)}
        </div>
        <div className="overflow-x-auto"><table className="data-table text-[12px]">
          <thead><tr><th>Control</th><th>Category</th><th>Type</th><th>Last outcome</th><th className="num">Items</th><th className="num">Pass rate</th><th>Owner</th><th>Review by</th><th></th></tr></thead>
          <tbody>{rows.map(c => (<>
            <tr key={c.id}>
              <td><span className="mono text-[10.5px] text-[var(--color-faint)]">{c.id}</span> <span className="text-[var(--color-ink)]">{c.label}</span></td>
              <td>{c.category_label}</td><td>{c.type}</td>
              <td>{c.last ? <span className="font-medium" style={{ color: OUT[c.last.outcome].color }}>{OUT[c.last.outcome].label}</span> : <span className="text-[var(--color-faint)]">untested</span>}<span className="mono text-[10px] text-[var(--color-faint)] ml-1">{c.last ? dt(c.last.at) : ''}</span></td>
              <td className="num mono">{c.last ? `${c.last.n_failed}/${c.last.n_items}` : '—'}</td>
              <td className="num mono">{c.pass_rate_pct != null ? `${c.pass_rate_pct}%` : '—'}<span className="text-[var(--color-faint)] text-[10px]"> ({c.n_tests})</span></td>
              <td>{d.can_manage ? <select value={c.owner_user_id ?? ''} onChange={e => setOwner(c, { owner_user_id: e.target.value || null })} className={inp}><option value="">— unowned —</option>{(pq.data?.people ?? []).map(p => <option key={p.user_id} value={p.user_id}>{p.full_name}</option>)}</select> : (c.owner ?? '—')}</td>
              <td>{d.can_manage ? <input type="date" value={c.review_by ?? ''} onChange={e => setOwner(c, { review_by: e.target.value || null })} className={inp} style={{ color: c.review_overdue ? 'var(--color-bad)' : undefined }} /> : (c.review_by ?? '—')}</td>
              <td><button onClick={() => setOpen(open === c.id ? null : c.id)} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">{open === c.id ? 'Hide' : 'Detail'}</button></td>
            </tr>
            {open === c.id && <tr key={c.id + '-d'}><td colSpan={9} className="bg-[var(--color-panel-2)]">
              <div className="grid grid-cols-[130px_1fr] gap-y-1 text-[12px] py-1">
                <span className="text-[var(--color-faint)]">Objective</span><span className="text-[var(--color-ink)]">{c.objective}</span>
                <span className="text-[var(--color-faint)]">Frequency</span><span>{c.frequency}</span>
                <span className="text-[var(--color-faint)]">Made of</span><span className="mono text-[11px]">{c.rules.join(' · ')}</span>
                <span className="text-[var(--color-faint)]">Evidence</span><span>{c.evidence}</span>
                <span className="text-[var(--color-faint)]">Answers</span><span>{c.anchor}</span>
                {c.last_fail && <><span className="text-[var(--color-faint)]">Last failure</span><span className="mono text-[11px]">{dt(c.last_fail)}</span></>}
                {c.last && c.last.detail.length > 0 && <><span className="text-[var(--color-faint)]">Latest detail</span>
                  <ul className="m-0 pl-4 space-y-0.5">{c.last.detail.slice(0, 8).map((x, i) => <li key={i} className="text-[var(--color-mute)]">{Object.entries(x).filter(([k]) => k !== 'filing_id').map(([k, v]) => `${k}: ${String(v)}`).join(' · ')}</li>)}</ul></>}
              </div></td></tr>}
          </>))}</tbody>
        </table></div>
      </Card>
    </div>
  )
}
