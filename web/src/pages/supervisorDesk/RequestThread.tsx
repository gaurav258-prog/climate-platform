import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileDown } from 'lucide-react'
import clsx from 'clsx'
import { api, apiMessage, download } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { HEADING, InfoButton } from '../../components/Details'
import { FULL } from '../supervisorAnalysis/checks'
import type { Req } from '../SupervisorRequests'
import { Facts, day, field } from './common'

// One request or finding in a side drawer: its chips, the letter and its legal basis (one click away), the thread both
// sides read, and the supervisor's reply and status steps. The entity-side twin is pages/respondent/Requests.tsx.
interface Msg { message_id: string; side: 'supervisor' | 'entity'; body: string | null; status_label: string | null; created_at: string; author: string | null }
interface Detail extends Req {
  messages: Msg[]; can_set: { key: string; label: string }[]
  legal_basis?: { ref: string; act?: string; url?: string | null; text?: string | null } | null; response_days?: number | null
  signatory?: string | null; has_letter?: boolean; receipt_at?: string | null; receipt_by?: string | null
}
export const SEV_TONE: Record<string, 'bad' | 'warn' | 'neutral'> = { high: 'bad', medium: 'warn', low: 'neutral' }
export const statusTone = (s: string) => s === 'closed' ? 'good' : s === 'open' ? 'warn' : 'neutral'

export function RequestDrawer({ id, onChange, onClose }: { id: string; onChange: () => Promise<unknown>; onClose: () => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['supervisor-request', id], queryFn: () => api.get<Detail>(`/v1/supervisor/requests/${id}`) })
  const [body, setBody] = useState(''); const [busy, setBusy] = useState(false)
  const r = q.data
  const send = async (status?: { key: string; label: string }) => {
    setBusy(true)
    try {
      await api.post(`/v1/supervisor/requests/${id}/messages`, { body: body || null, status_to: status?.key ?? null })
      setBody(''); toast.success(status ? `Set to ${status.label.toLowerCase()}.` : 'Sent to the entity.')
      await qc.invalidateQueries({ queryKey: ['supervisor-request', id] }); await onChange()
    } catch (e) { toast.error(apiMessage(e, 'Could not update the thread.')) } finally { setBusy(false) }
  }
  const verb = (s: { key: string; label: string }) => s.key === 'closed' ? 'Close' : s.key === 'open' ? 'Reopen' : `Set ${s.label.toLowerCase()}`
  return (
    <Drawer label={r?.title ?? 'Request'} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <div className="text-[12px] text-[var(--color-mute)]">{r ? `${r.kind_label}${r.reference ? ` · ${r.reference}` : ''}` : 'Loading…'}</div>
          <div className="text-[16px] font-semibold text-[var(--color-ink)] leading-snug">{r?.title}</div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      {r && (<>
        <div className="flex flex-wrap gap-2 mb-4">
          <StatusChip label={r.status_label} tone={statusTone(r.status)} />
          {r.severity_label && <StatusChip label={`${r.severity_label} severity`} tone={SEV_TONE[r.severity ?? ''] ?? 'neutral'} />}
          {r.overdue && <StatusChip value="overdue" />}
          {r.source?.label && <StatusChip label={r.source.label} tone="neutral" />}
          {r.receipt_at ? <StatusChip label={`Receipt acknowledged ${day(r.receipt_at)}`} tone="good" /> : <StatusChip label="Receipt not yet acknowledged" tone="neutral" />}
        </div>
        <div className="mb-4">
          <Facts rows={[['Entity', r.entity], ['Issued', `${day(r.raised_at)}${r.raised_by ? ` · ${r.raised_by}` : ''}`],
            ['Reply due', <span style={{ color: r.overdue ? 'var(--color-bad)' : undefined }}>{day(r.due_date)}{r.response_days ? ` · ${r.response_days} days to respond` : ''}</span>],
            ['Signed by', r.signatory ?? '—'], ...(r.receipt_by ? [['Acknowledged by', r.receipt_by] as [string, string]] : [])]} />
        </div>
        <div className="flex flex-wrap items-center gap-3 mb-5 text-[12.5px]">
          {r.has_letter && <Button variant="ghost" onClick={() => download(`/v1/supervisor/requests/${r.request_id}/letter.pdf`, `${r.reference ?? 'letter'}.pdf`)}><FileDown size={14} />Letter (PDF)</Button>}
          {r.legal_basis && <InfoButton label="Legal basis" details={{ title: 'Legal basis', sections: [
            { heading: HEADING.shows, body: r.legal_basis.act ?? r.legal_basis.ref },
            ...(r.legal_basis.text ? [{ heading: 'What it says', body: <span className="italic">“{r.legal_basis.text}”</span> }] : []),
            ...(r.legal_basis.url ? [{ heading: HEADING.sources, body: <a href={r.legal_basis.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">The act on EUR-Lex ↗</a> }] : []),
          ] }} />}
          {r.source?.type === 'lens_cell' && <Link to={`/supervised/${r.supervised_org_id}/lens`} className="text-[var(--color-sky)] hover:underline">
            {FULL}: {r.source.geography_label} · {r.source.sector_label} →</Link>}
        </div>
        <div className="text-[12px] text-[var(--color-mute)] mb-2">Thread</div>
        <div className="space-y-2 mb-4">
          {r.messages.map(m => (
            <div key={m.message_id} className={clsx('rounded-lg px-3 py-2 text-[13px]', m.side === 'entity' ? 'bg-[var(--color-panel-2)] ml-8' : 'bg-[var(--color-panel)] mr-8 border border-[var(--color-line)]')}>
              <div className="flex items-center gap-2 flex-wrap text-[11px] text-[var(--color-faint)] mb-0.5">
                <span>{m.side === 'entity' ? r.entity : 'You'}{m.author ? ` · ${m.author}` : ''} · {day(m.created_at)}</span>
                {m.status_label && <StatusChip label={`Set to ${m.status_label}`} tone="neutral" />}
              </div>
              {m.body && <div className="text-[var(--color-ink)] whitespace-pre-wrap">{m.body}</div>}
            </div>))}
        </div>
        <textarea value={body} onChange={e => setBody(e.target.value)} rows={3} placeholder="Write to the entity…" aria-label="Message to the entity" className={clsx(field, 'w-full mb-2')} />
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={() => send()} disabled={busy || !body.trim()}>Send</Button>
          {r.can_set.map(s => <Button key={s.key} onClick={() => send(s)} disabled={busy}>{verb(s)}</Button>)}
        </div>
      </>)}
    </Drawer>
  )
}
