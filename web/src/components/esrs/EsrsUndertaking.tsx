import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import type { Role, Scope } from './types'

// Who reports and whether it must: the undertaking's CSRD role for the year (a second person approves it), what
// Art. 5(2) of Directive (EU) 2022/2464 as amended says on its stated facts, and closing the reporting period.

const ROLES = [
  { k: 'individual', label: 'Individual statement (Art. 19a)' },
  { k: 'consolidated', label: 'Consolidated statement of a group parent (Art. 29a)' },
  { k: 'exempt_subsidiary', label: 'Exempt subsidiary — in the parent’s consolidated statement' },
  { k: 'voluntary', label: 'Voluntary statement' },
] as const
const input = 'block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]'
const YES: Record<string, { t: string; c: string }> = {
  true: { t: 'required', c: 'var(--color-good)' }, false: { t: 'not required', c: 'var(--color-mute)' },
  null: { t: 'not determinable yet', c: 'var(--color-warn)' },
}

export default function EsrsUndertaking({ periodEnd, entity, role, scope, closed }: {
  periodEnd: string; entity: string; role: Role | null; scope: Scope; closed: boolean
}) {
  const qc = useQueryClient()
  const [edit, setEdit] = useState(false)
  const [r, setR] = useState<string>(role?.role ?? 'individual')
  const [parent, setParent] = useState({ parent_name: '', parent_registered_office: '', parent_report_ref: '' })
  const [basis, setBasis] = useState('')
  const [busy, setBusy] = useState(false)
  const blockers = useQuery({ queryKey: ['close-blockers', periodEnd, entity], enabled: !closed, queryFn: () =>
    api.get<{ blockers: string[] }>(`/v1/periods/close/blockers?period_end=${periodEnd}${entity ? `&entity_id=${entity}` : ''}`) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['esrs-statement'] })
  const stateRole = async () => {
    setBusy(true)
    try {
      await api.post('/v1/periods/role', { period_end: periodEnd, entity_id: entity || null, role: r, basis: basis || null,
        ...(r === 'exempt_subsidiary' ? parent : {}) })
      toast.success('Role submitted — a second person approves it under Approvals'); setEdit(false); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not state the role.')) } finally { setBusy(false) }
  }
  const close = async () => {
    setBusy(true)
    try {
      await api.post('/v1/periods/close', { period_end: periodEnd, entity_id: entity || null })
      toast.success('Close requested — a second person approves it under Approvals'); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not ask to close the period.')) } finally { setBusy(false) }
  }
  const y = YES[String(scope.required)]
  return (
    <div className="grid gap-4 p-5 md:grid-cols-3">
      <div className="space-y-1.5">
        <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">CSRD role</div>
        <div className="text-[13px] text-[var(--color-ink)]">{role ? ROLES.find(x => x.k === role.role)?.label : 'Not stated'}</div>
        {role?.parent_name && <div className="text-[11.5px] text-[var(--color-mute)]">Parent: {role.parent_name} — {role.parent_report_ref}</div>}
        {!edit && <button onClick={() => setEdit(true)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">{role ? 'change' : 'state the role'}</button>}
        {edit && <div className="space-y-2 pt-1">
          <select aria-label="Role" value={r} onChange={e => setR(e.target.value)} className={input}>
            {ROLES.map(x => <option key={x.k} value={x.k}>{x.label}</option>)}</select>
          {r === 'exempt_subsidiary' && (['parent_name', 'parent_registered_office', 'parent_report_ref'] as const).map(k => (
            <input key={k} aria-label={k} value={parent[k]} onChange={e => setParent(p => ({ ...p, [k]: e.target.value }))} className={input}
              placeholder={{ parent_name: 'parent’s name', parent_registered_office: 'parent’s registered office', parent_report_ref: 'weblink to its consolidated report' }[k]} />))}
          <textarea rows={2} value={basis} onChange={e => setBasis(e.target.value)} className={input} placeholder="basis (optional)" />
          <div className="flex gap-3 items-center"><Button variant="primary" onClick={stateRole} disabled={busy}>Submit</Button>
            <button onClick={() => setEdit(false)} className="mono text-[11px] text-[var(--color-mute)] hover:underline">cancel</button></div>
        </div>}
      </div>
      <div className="space-y-1.5">
        <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">Art. 5(2) — is a statement required?</div>
        <div className="text-[13px]" style={{ color: y.c }}>{y.t}{scope.point ? ` · point ${scope.point}` : ''}</div>
        {scope.reason && <div className="text-[11.5px] text-[var(--color-mute)]">{scope.reason}</div>}
        {(scope.conditions ?? []).map(c => (
          <div key={c.fact} className="text-[11px] flex gap-1.5"><span style={{ color: c.met ? 'var(--color-good)' : c.met === false ? 'var(--color-bad)' : 'var(--color-warn)' }}>{c.met ? '✓' : c.met === false ? '✗' : '?'}</span>
            <span className="text-[var(--color-mute)]">{c.detail ?? c.fact}</span></div>))}
        {scope.quote && <details className="text-[11px] text-[var(--color-faint)]"><summary className="cursor-pointer">the text ({scope.ref})</summary><p className="mt-1 italic">{scope.quote}</p></details>}
        {scope.derogation && <div className="text-[11px] text-[var(--color-mute)]">Member State derogation ({scope.derogation.ref}): stated as “{scope.derogation.stated.replace('_', ' ')}” — set it in calculation settings.</div>}
      </div>
      <div className="space-y-1.5">
        <div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)]">Reporting period</div>
        <div className="text-[13px] text-[var(--color-ink)]">{closed ? 'Closed — a change is a restatement' : 'Open'}</div>
        {!closed && <>
          {(blockers.data?.blockers ?? []).map(b => <div key={b} className="text-[11px] text-[var(--color-warn)]">{b}</div>)}
          <Button variant="ghost" onClick={close} disabled={busy || (blockers.data?.blockers.length ?? 1) > 0}>Ask to close</Button>
        </>}
      </div>
    </div>
  )
}
