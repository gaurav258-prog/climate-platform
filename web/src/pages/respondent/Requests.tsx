import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileDown, MessagesSquare } from 'lucide-react'
import clsx from 'clsx'
import { api, apiMessage, download } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button, Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { HEADING, InfoButton } from '../../components/Details'
import { day, field } from './common'
import { useRequests, type InDetail } from './data'

// Requests and findings from the supervisor: we reply and report progress, the supervisor closes. The list carries
// status, severity and due date as chips; a request opens in a drawer with its letter, legal basis and thread.

const SEVERITY: Record<string, { label: string; tone: 'bad' | 'warn' | 'neutral' }> = {
  high: { label: 'High', tone: 'bad' }, medium: { label: 'Medium', tone: 'warn' }, low: { label: 'Low', tone: 'neutral' } }
const statusTone = (s: string) => s === 'closed' ? 'good' : s === 'open' ? 'warn' : 'neutral'

export function SupervisorRequestsInbox({ open, onOpen }: { open?: string | null; onOpen?: (id: string | null) => void } = {}) {
  const q = useRequests()
  const [own, setOwn] = useState<string | null>(null)
  const sel = onOpen ? open ?? null : own
  const choose = onOpen ?? setOwn
  const [show, setShow] = useState<'open' | 'closed'>('open')
  if (!q.data || q.data.requests.length === 0) return null
  const d = q.data
  const closed = d.requests.length - d.summary.open
  const rows = d.requests.filter(r => (r.status === 'closed') === (show === 'closed'))
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <SectionHead icon={MessagesSquare} hint="you reply, your supervisor closes">Requests from your supervisor</SectionHead>
        <div className="ml-auto flex rounded-lg border border-[var(--color-line-2)] overflow-hidden text-[12px]">
          {([['open', `Open · ${d.summary.open}`], ['closed', `Closed · ${closed}`]] as const).map(([k, l]) => (
            <button key={k} type="button" onClick={() => setShow(k)} aria-pressed={show === k}
              className={clsx('px-3 py-1', show === k ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{l}</button>))}
        </div>
      </div>
      {rows.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">{show === 'open' ? 'Nothing open.' : 'Nothing closed yet.'}</div> : (
        <div className="divide-y divide-[var(--color-line)]">
          {rows.map(r => (
            <button key={r.request_id} type="button" onClick={() => choose(r.request_id)} className="w-full text-left py-2.5 flex items-center gap-3 flex-wrap text-[12.5px] group">
              <span className="min-w-0 mr-auto">
                <span className="block text-[var(--color-ink)] group-hover:text-[var(--color-sky)]">{r.title}</span>
                <span className="block text-[11.5px] text-[var(--color-faint)]">{r.kind_label}{r.reference ? ` · ${r.reference}` : ''}</span>
              </span>
              {r.severity && SEVERITY[r.severity] && <StatusChip label={`${SEVERITY[r.severity].label} severity`} tone={SEVERITY[r.severity].tone} />}
              <StatusChip label={r.status_label} tone={statusTone(r.status)} />
              <span className="w-32 text-right tabular-nums whitespace-nowrap text-[12px]" style={{ color: r.overdue ? 'var(--color-bad)' : 'var(--color-mute)' }}>{r.due_date ? `Due ${day(r.due_date)}` : '—'}</span>
            </button>
          ))}
        </div>
      )}
      {sel && <RequestDrawer id={sel} canRespond={d.can_respond} onClose={() => choose(null)} />}
    </Card>
  )
}

function RequestDrawer({ id, canRespond, onClose }: { id: string; canRespond: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const det = useQuery({ queryKey: ['my-supervisor-request', id], queryFn: () => api.get<InDetail>(`/v1/me/supervisors/requests/${id}`) })
  const [body, setBody] = useState(''); const [busy, setBusy] = useState(false)
  const refresh = async () => { await qc.invalidateQueries({ queryKey: ['my-supervisor-request', id] }); await qc.invalidateQueries({ queryKey: ['my-supervisor-requests'] }) }
  const post = async (path: string, payload: object, done: string) => {
    setBusy(true)
    try { await api.post(`/v1/me/supervisors/requests/${id}/${path}`, payload); toast.success(done); setBody(''); await refresh() }
    catch (e) { toast.error(apiMessage(e, 'Could not send.')) } finally { setBusy(false) }
  }
  const r = det.data
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
          {r.severity && SEVERITY[r.severity] && <StatusChip label={`${SEVERITY[r.severity].label} severity`} tone={SEVERITY[r.severity].tone} />}
          {r.overdue && <StatusChip value="overdue" />}
          {r.receipt_at && <StatusChip label={`Receipt acknowledged ${day(r.receipt_at)}`} tone="good" />}
        </div>
        <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-[12.5px] mb-4">
          <dt className="text-[var(--color-mute)]">From</dt><dd className="m-0 text-[var(--color-ink)]">{r.regulator}</dd>
          <dt className="text-[var(--color-mute)]">Issued</dt><dd className="m-0 text-[var(--color-ink)]">{day(r.raised_at)}{r.raised_by ? ` · ${r.raised_by}` : ''}</dd>
          <dt className="text-[var(--color-mute)]">Reply due</dt><dd className="m-0" style={{ color: r.overdue ? 'var(--color-bad)' : 'var(--color-ink)' }}>{day(r.due_date)}{r.response_days ? ` · ${r.response_days} days to respond` : ''}</dd>
        </dl>
        <div className="flex flex-wrap items-center gap-3 mb-5 text-[12.5px]">
          {r.has_letter && <Button variant="ghost" onClick={() => download(`/v1/me/supervisors/requests/${r.request_id}/letter.pdf`, `${r.reference ?? 'letter'}.pdf`)}><FileDown size={14} className="inline -mt-0.5 mr-1" />Letter (PDF)</Button>}
          {r.legal_basis && <InfoButton label="Legal basis" details={{ title: 'Legal basis', sections: [
            { heading: HEADING.shows, body: r.legal_basis.act ?? r.legal_basis.ref },
            ...(r.legal_basis.text ? [{ heading: 'What it says', body: <span className="italic">“{r.legal_basis.text}”</span> }] : []),
            ...(r.legal_basis.url ? [{ heading: HEADING.sources, body: <a href={r.legal_basis.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">The act on EUR-Lex ↗</a> }] : []),
          ] }} />}
          {!r.receipt_at && canRespond && <Button variant="ghost" disabled={busy} onClick={() => post('receipt', {}, 'Receipt acknowledged.')}>Acknowledge receipt</Button>}
        </div>
        <div className="text-[12px] text-[var(--color-mute)] mb-2">Thread</div>
        <div className="space-y-2 mb-4">
          {r.messages.map(m => (
            <div key={m.message_id} className={clsx('rounded-lg px-3 py-2 text-[13px]', m.side === 'entity' ? 'bg-[var(--color-panel-2)] ml-8' : 'bg-[var(--color-panel)] mr-8 border border-[var(--color-line)]')}>
              <div className="flex items-center gap-2 flex-wrap text-[11px] text-[var(--color-faint)] mb-0.5">
                <span>{m.side === 'entity' ? 'You' : r.regulator}{m.author ? ` · ${m.author}` : ''} · {day(m.created_at)}</span>
                {m.status_label && <StatusChip label={`Set to ${m.status_label}`} tone="neutral" />}
              </div>
              {m.body && <div className="text-[var(--color-ink)] whitespace-pre-wrap">{m.body}</div>}
            </div>))}
        </div>
        {canRespond ? (r.status !== 'closed' && <>
          <textarea value={body} onChange={e => setBody(e.target.value)} rows={3} placeholder="Reply to your supervisor…" aria-label="Reply" className={clsx(field, 'w-full mb-2')} />
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" onClick={() => post('messages', { body }, 'Reply sent.')} disabled={busy || !body.trim()}>Send</Button>
            {r.can_set.map(s => <Button key={s.key} onClick={() => post('messages', { body: body || null, status_to: s.key }, `Marked ${s.label.toLowerCase()}.`)} disabled={busy}>Mark {s.label.toLowerCase()}</Button>)}
          </div></>) : <div className="text-[12px] text-[var(--color-faint)]">Replying needs the release permission.</div>}
      </>)}
    </Drawer>
  )
}
