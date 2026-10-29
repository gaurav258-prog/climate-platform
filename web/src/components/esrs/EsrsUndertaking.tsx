import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, XCircle, HelpCircle } from 'lucide-react'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../Details'
import { StatusChip } from '../StatusChip'
import ReportingRoleForm from './ReportingRoleForm'
import { ROLE } from './words'
import type { Role, Scope } from './types'

// Who reports and whether it must: the undertaking's reporting role for the year (a second person approves it), whether
// the Directive requires a statement on its stated facts, and closing the reporting period.

const REQUIRED: Record<string, { label: string; tone: 'good' | 'warn' | 'neutral' }> = {
  true: { label: 'Required', tone: 'good' }, false: { label: 'Not required', tone: 'neutral' }, null: { label: 'Not known yet', tone: 'warn' },
}

export default function EsrsUndertaking({ periodEnd, entity, role, scope, closed }: {
  periodEnd: string; entity: string; role: Role | null; scope: Scope; closed: boolean
}) {
  const qc = useQueryClient()
  const [edit, setEdit] = useState(false)
  const [busy, setBusy] = useState(false)
  const blockers = useQuery({ queryKey: ['close-blockers', periodEnd, entity], enabled: !closed, queryFn: () =>
    api.get<{ messages: Message[] }>(`/v1/periods/close/blockers?period_end=${periodEnd}${entity ? `&entity_id=${entity}` : ''}`) })
  const refresh = () => qc.invalidateQueries({ queryKey: ['esrs-statement'] })
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

      {edit && <ReportingRoleForm periodEnd={periodEnd} entity={entity} initial={role?.role} onClose={() => setEdit(false)}
        onSent={() => { setEdit(false); refresh() }} />}
    </div>
  )
}
