import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../Details'
import { StatusChip } from '../StatusChip'
import { SidePanel } from '../sfdr/visuals'
import { ROLE } from './words'
import type { Role, Scope } from './types'

// Who reports and whether it must: the undertaking's reporting role for the year (a second person approves it), whether
// the Directive requires a statement on its stated facts, and closing the reporting period.

const input = 'block w-full mt-1 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1.5 text-[12.5px]'
const REQUIRED: Record<string, { label: string; tone: 'good' | 'warn' | 'neutral' }> = {
  true: { label: 'Required', tone: 'good' }, false: { label: 'Not required', tone: 'neutral' }, null: { label: 'Not known yet', tone: 'warn' },
}
const PARENT = { parent_name: 'Parent’s name', parent_registered_office: 'Parent’s registered office', parent_report_ref: 'Link to its consolidated report' } as const

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
    api.get<{ messages: Message[] }>(`/v1/periods/close/blockers?period_end=${periodEnd}${entity ? `&entity_id=${entity}` : ''}`) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['esrs-statement'] })
  const stateRole = async () => {
    setBusy(true)
    try {
      await api.post('/v1/periods/role', { period_end: periodEnd, entity_id: entity || null, role: r, basis: basis || null,
        ...(r === 'exempt_subsidiary' ? parent : {}) })
      toast.success('Role sent — a second person approves it under Approvals'); setEdit(false); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not state the role.')) } finally { setBusy(false) }
  }
  const close = async () => {
    setBusy(true)
    try {
      await api.post('/v1/periods/close', { period_end: periodEnd, entity_id: entity || null })
      toast.success('Close requested — a second person approves it under Approvals'); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not ask to close the period.')) } finally { setBusy(false) }
  }
  const req = REQUIRED[String(scope.required)]
  const blocks = blockers.data?.messages ?? []
  const tile = 'rounded-lg border border-[var(--color-line)] p-3.5 space-y-2'
  const head = 'text-[12px] text-[var(--color-faint)]'

  return (
    <div className="grid gap-3 p-5 md:grid-cols-3">
      <div className={tile}>
        <div className={head}>Reporting role</div>
        <div className="flex flex-wrap items-center gap-2">
          {role ? <StatusChip tone="neutral" label={ROLE[role.role] ?? 'Stated'} /> : <StatusChip tone="warn" label="Not stated" />}
          {role?.parent_name && <InfoButton compact details={{ title: 'Included in', sections: [{ heading: 'Parent', body: role.parent_name }, { heading: 'Consolidated report', body: role.parent_report_ref ?? '—' }] }} />}
        </div>
        <Button variant="ghost" onClick={() => setEdit(true)}>{role ? 'Change' : 'State the role'}</Button>
      </div>

      <div className={tile}>
        <div className="flex items-center gap-1.5">
          <span className={head}>Is a statement required?</span>
          {scope.quote && <InfoButton compact details={{ title: 'What the Directive says', sections: [{ heading: 'The text', body: <span className="italic">{scope.quote}</span> }, { heading: 'Legal basis', body: scope.ref ?? '—' }] }} />}
        </div>
        <div className="flex items-center gap-1.5">
          <StatusChip tone={req.tone} label={scope.msg?.label ?? req.label} />
          {scope.msg && <InfoButton compact details={messageDetails(scope.msg)} />}
        </div>
        <div className="space-y-1">
          {(scope.conditions ?? []).map(c => (
            <div key={c.fact} className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)]">
              {c.met ? <CheckCircle2 size={13} className="text-[var(--color-good)] shrink-0" /> : c.met === false ? <XCircle size={13} className="text-[var(--color-bad)] shrink-0" /> : <HelpCircle size={13} className="text-[var(--color-warn)] shrink-0" />}
              {c.msg ? <MessageLine m={c.msg} /> : <span>{c.label}</span>}
            </div>))}
        </div>
        {scope.derogation && <div className="flex items-center gap-1.5"><StatusChip tone="neutral" label="Member State choice" />
          <InfoButton compact details={{ title: 'Member State choice', sections: [{ heading: 'The text', body: <span className="italic">{scope.derogation.quote}</span> }, { heading: 'Legal basis', body: scope.derogation.ref }, { heading: 'What you can do', body: 'Set whether your Member State applied it in calculation settings.' }] }} /></div>}
      </div>

      <div className={tile}>
        <div className={head}>Reporting period</div>
        {closed ? <StatusChip tone="good" label="Closed" /> : <StatusChip tone="neutral" label="Open" />}
        {closed
          ? <InfoButton label="What this means" details={{ title: 'A closed period', sections: [{ heading: HEADING.read, body: 'Its year-end values are final; a change now is a restatement, approved by a second person.' }] }} />
          : <>
            {blocks.map((b, i) => <MessageLine key={i} m={b} className="text-[12px] text-[var(--color-warn)]" />)}
            <Button variant="ghost" onClick={close} disabled={busy || !blockers.data || blocks.length > 0}>Ask to close</Button>
          </>}
      </div>

      {edit && (
        <SidePanel title="Reporting role" onClose={() => setEdit(false)}
          about={{ title: 'Reporting role', sections: [{ heading: HEADING.read, body: 'The role for this financial year decides which point of the Directive applies. A second person approves it.' },
            { heading: 'Legal basis', body: 'Directive 2013/34/EU: Article 19a (individual statement), Article 29a (consolidated statement), Articles 19a(9) and 29a(8) (exempt subsidiary).' }] }}>
          <div className="space-y-3">
            <label className="block text-[12.5px] text-[var(--color-mute)]">Role
              <select aria-label="Role" value={r} onChange={e => setR(e.target.value)} className={input}>
                {Object.entries(ROLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
            {r === 'exempt_subsidiary' && (Object.keys(PARENT) as (keyof typeof PARENT)[]).map(k => (
              <label key={k} className="block text-[12.5px] text-[var(--color-mute)]">{PARENT[k]}
                <input aria-label={PARENT[k]} value={parent[k]} onChange={e => setParent(p => ({ ...p, [k]: e.target.value }))} className={input} /></label>))}
            <label className="block text-[12.5px] text-[var(--color-mute)]">Basis (optional)
              <textarea rows={2} value={basis} onChange={e => setBasis(e.target.value)} className={input} /></label>
            <div className="flex gap-2"><Button variant="primary" onClick={stateRole} disabled={busy}>Send for approval</Button>
              <Button variant="ghost" onClick={() => setEdit(false)}>Cancel</Button></div>
          </div>
        </SidePanel>)}
    </div>
  )
}
