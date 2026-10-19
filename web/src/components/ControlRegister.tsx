import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead, StatGrid } from '../components/ui'
import { HEADING, InfoButton, messageDetails, type Message } from './Details'
import { Drawer } from './Drawer'
import { CloseButton } from './Dialog'
import { StatusChip } from './StatusChip'
import { CONTROL_TRIGGER, CONTROL_TYPE } from '../lib/codeWords'
import { frameworkLabel } from '../lib/hazards'

// The reporting control register — every automated reporting check named as a control, with its owner, review
// date, last outcome and pass rate over the window. Tested daily by the sweep and on demand here.
// a test's item: its stored fields and its catalogue message (services/governance/controls.py named)
type Item = Record<string, unknown> & { msg?: Message }
interface Last { outcome: 'pass' | 'fail' | 'not_applicable'; n_items: number; n_failed: number; detail: Item[]; at: string }
interface Control { id: string; label: string; category: string; category_label: string; type: string; frequency: string; objective: string; rules: string[]; evidence: string; anchor: string
  last: Last | null; pass_rate_pct: number | null; n_tests: number; last_fail: string | null; owner: string | null; owner_user_id: string | null; review_by: string | null; review_overdue: boolean; owner_note: string | null }
interface Resp { register_version: string; categories: Record<string, string>; controls: Control[]; window_days: number; last_run: { at: string; trigger: string; n_pass: number; n_fail: number; n_na: number } | null
  summary: { controls: number; pass: number; fail: number; not_applicable: number; untested: number; unowned: number; reviews_overdue: number }; can_manage: boolean }
// a test's outcome as a status chip
const OUT: Record<string, { label: string; tone: 'good' | 'bad' | 'neutral' }> = { pass: { label: 'Passed', tone: 'good' }, fail: { label: 'Failed', tone: 'bad' }, not_applicable: { label: 'Not applicable', tone: 'neutral' } }
const dt = (s: string | null | undefined) => s ? new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
const ABOUT = (version: string) => [
  { heading: HEADING.shows, body: 'Every automated check the platform runs over your regulatory reporting, named as a control: its objective, how often it runs, the evidence it leaves and the regulatory expectation it answers.' },
  { heading: HEADING.read, body: 'Controls are tested daily and on request, and every test is recorded, so how well each control operates has a history an auditor can read. Give each control an owner and a review date.' },
  { heading: HEADING.sources, body: `The platform's register of reporting controls, as of ${new Date(version).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}.` },
]
const inp = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[12px] outline-none focus:border-[var(--color-sky)]'

export default function ControlRegister() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['controls'], queryFn: () => api.get<Resp>('/v1/controls') })
  const pq = useQuery({ queryKey: ['controls-people'], queryFn: () => api.get<{ people: { user_id: string; full_name: string }[] }>('/v1/controls/people') })
  const [busy, setBusy] = useState(false); const [open, setOpen] = useState<Control | null>(null); const [cat, setCat] = useState('')
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
            <SectionHead className="gap-1.5">Reporting control register <InfoButton compact details={{ title: 'Reporting control register', sections: ABOUT(d.register_version) }} /></SectionHead>
            <div className="text-[12px] text-[var(--color-mute)] mt-1.5">{d.last_run ? `Last tested ${dt(d.last_run.at)}, ${CONTROL_TRIGGER[d.last_run.trigger] ?? 'on request'}` : 'Not tested yet'} · pass rate over {d.window_days} days</div>
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
          <tbody>{rows.map(c => (
            <tr key={c.id}>
              <td className="text-[var(--color-ink)]">{c.label}</td>
              <td>{c.category_label}</td><td>{CONTROL_TYPE[c.type] ?? 'Control'}</td>
              <td>{c.last ? <StatusChip tone={OUT[c.last.outcome].tone} label={OUT[c.last.outcome].label} /> : <StatusChip tone="neutral" label="Not tested yet" />}</td>
              <td className="num mono">{c.last ? `${c.last.n_failed}/${c.last.n_items}` : '—'}</td>
              <td className="num mono">{c.pass_rate_pct != null ? `${c.pass_rate_pct}%` : '—'}<span className="text-[var(--color-faint)] text-[10px]"> ({c.n_tests})</span></td>
              <td>{d.can_manage ? <select value={c.owner_user_id ?? ''} onChange={e => setOwner(c, { owner_user_id: e.target.value || null })} className={inp}><option value="">— unowned —</option>{(pq.data?.people ?? []).map(p => <option key={p.user_id} value={p.user_id}>{p.full_name}</option>)}</select> : (c.owner ?? '—')}</td>
              <td>{d.can_manage ? <input type="date" value={c.review_by ?? ''} onChange={e => setOwner(c, { review_by: e.target.value || null })} className={inp} style={{ color: c.review_overdue ? 'var(--color-bad)' : undefined }} /> : (c.review_by ?? '—')}</td>
              <td><button onClick={() => setOpen(c)} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">Detail</button></td>
            </tr>
          ))}</tbody>
        </table></div>
      </Card>
      {open && <ControlDrawer c={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// the filing an item belongs to, in words ('—' marks an item that belongs to no filing)
const where = (x: Item) => [typeof x.framework === 'string' && x.framework !== '—' ? frameworkLabel(x.framework) : null,
  typeof x.period === 'string' && x.period !== '—' ? x.period : null].filter(Boolean).join(' · ')

// One control, one click away: what it is for, how it is tested, and what its latest test found — each item in words.
function ControlDrawer({ c, onClose }: { c: Control; onClose: () => void }) {
  const items = c.last?.detail ?? []
  const fact = (label: string, value: React.ReactNode) => (
    <div><h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1">{label}</h4><div className="text-[13px] leading-relaxed text-[var(--color-ink)]">{value}</div></div>)
  return (
    <Drawer label={c.label} onClose={onClose} className="w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)]">
      <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-[var(--color-faint)]">{c.category_label} · control {c.id}</div>
          <div className="text-[15px] font-semibold mt-0.5">{c.label}</div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="p-5 space-y-4">
        {fact('Latest test', c.last
          ? <div className="space-y-2">
              <div className="flex items-center gap-2"><StatusChip tone={OUT[c.last.outcome].tone} label={OUT[c.last.outcome].label} /><span className="text-[12px] text-[var(--color-mute)]">{dt(c.last.at)} · {c.last.n_failed} of {c.last.n_items} not passed</span></div>
              {items.length > 0 && <ul className="m-0 p-0 list-none space-y-1 text-[12.5px] text-[var(--color-mute)]">{items.slice(0, 12).map((x, i) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span>{where(x) ? `${where(x)}: ` : ''}{x.msg?.label ?? 'One item did not pass'}</span>
                  {x.msg && <InfoButton compact className="mt-0.5" details={messageDetails(x.msg)} />}
                </li>))}</ul>}
              {items.length > 12 && <div className="text-[11.5px] text-[var(--color-faint)]">and {items.length - 12} more</div>}
            </div>
          : 'Not tested yet.')}
        {c.last_fail && fact('Last failure', dt(c.last_fail))}
        {fact('Objective', c.objective)}
        {fact('How often it runs', c.frequency[0].toUpperCase() + c.frequency.slice(1))}
        {fact('Evidence it leaves', c.evidence[0].toUpperCase() + c.evidence.slice(1))}
        {fact('Regulatory expectation it answers', c.anchor)}
        {fact('Checks it is made of', `${c.rules.length} automated check${c.rules.length === 1 ? '' : 's'}`)}
      </div>
    </Drawer>
  )
}
