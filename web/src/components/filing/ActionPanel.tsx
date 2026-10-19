import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ShieldCheck, CheckCircle2, PenLine, Send, Stamp, RefreshCw, Trash2, GitCompareArrows, ArrowRight, Footprints } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { Card, Button, SectionHead } from '../ui'
import { HEADING, InfoButton, MessageLine, type Message } from '../Details'
import { StatusChip } from '../StatusChip'

// The next step of a filing, as its status and the reader's permissions allow: refresh or send a draft for approval,
// approve or return it (a second person), attest it (the accountable person, under their own sign-in), record its
// submission and the regulator's acknowledgement, restate a filed report, or withdraw a draft made by mistake.

export interface FilingDetail {
  filing_id: string; framework: string; label: string; period_label: string; status: string
  approval_request_id: string | null; superseded_by?: string | null
  own_flow?: { frozen_by: string | null; accepted_by: string | null; own_page: string } | null   // e.g. EUDR: per shipment
  events: { action: string; detail: Record<string, unknown>; at: string; actor: string | null }[]
}

const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
const Line = ({ children, info }: { children: React.ReactNode; info?: { title: string; body: React.ReactNode } }) => (
  <p className="text-[12.5px] text-[var(--color-mute)] m-0 flex items-center gap-1.5 flex-wrap">{children}
    {info && <InfoButton compact details={{ title: info.title, sections: [{ heading: HEADING.shows, body: info.body }] }} />}</p>)

export function ActionPanel({ f, perms, onDone, blocking, onOpen }: { f: FilingDetail; perms: string[]; onDone: () => void; blocking: number; onOpen: (id: string) => void }) {
  const { profile } = useAuth()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)
  const [reason, setReason] = useState('')
  const [statement, setStatement] = useState('I certify these figures are complete and accurate to the best of my knowledge.')
  const [fn, setFn] = useState('')
  const [subRef, setSubRef] = useState('')
  const [ackRef, setAckRef] = useState('')
  const [withdrawing, setWithdrawing] = useState(false)
  const [wReason, setWReason] = useState('')
  const canReview = perms.includes('approvals.create')
  const canDecide = perms.includes('approvals.decide')
  const canPublish = perms.includes('reports.publish')
  const canAttest = perms.includes('board.attest')   // personal accountability: its own permission, not publish rights
  const draft = f.status === 'draft' || f.status === 'returned'
  const eudr = f.framework === 'eudr_dds'
  const withdrawal = f.status === 'withdrawn' ? [...f.events].reverse().find(e => e.action === 'withdraw') : undefined

  const call = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null)
    try { await fn(); onDone() }
    catch (e) { setErr({ label: apiMessage(e, 'The step could not be completed'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  // approve / return through the approvals service (the approver is never the preparer: enforced on the server)
  const decide = (decision: 'approved' | 'returned') =>
    call(() => api.post(`/v1/approvals/${f.approval_request_id}/decide`, { decision, reason: reason || undefined }))

  return (
    <Card className="p-4 space-y-3">
      <SectionHead icon={Footprints}>Next step</SectionHead>
      {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}

      {draft && canReview && f.own_flow && (
        <Line info={{ title: 'Prepared on its own page', body: `This report is prepared ${f.own_flow.frozen_by}.` }}>
          Prepared on its own page. <Link to={f.own_flow.own_page} className="text-[var(--color-sky)] hover:underline">Open it</Link></Line>)}
      {draft && canReview && !f.own_flow && (
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/refresh`, {}))} disabled={busy}><RefreshCw size={13} /> Refresh data</Button>
          <InfoButton compact details={{ title: 'Refresh data', sections: [{ heading: HEADING.shows, body: 'Freezes this draft again from the book as it is now, so inputs supplied since — energy labels, credit stages, maturities — reach the form.' }] }} />
        </div>)}

      {draft && (canReview
        ? <div className="space-y-2">
            {blocking > 0 && <StatusChip tone="bad" label={`Resolve ${blocking} blocking ${blocking === 1 ? 'check' : 'checks'} first`} />}
            <div><Button onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/submit-for-review`, {}))} disabled={busy || blocking > 0}><Send size={14} /> Send for approval</Button></div>
          </div>
        : <Line>A colleague who prepares filings sends it for approval.</Line>)}

      {f.status === 'in_review' && (canDecide
        ? <div className="space-y-2">
            <Line info={{ title: 'Four-eyes approval', body: 'A second person, never the preparer, approves this filing or returns it to the preparer.' }}>Approve or return this filing.</Line>
            <textarea className={box} rows={2} placeholder="Note to the preparer (optional)" value={reason} onChange={e => setReason(e.target.value)} />
            <div className="flex gap-2">
              <Button onClick={() => decide('approved')} disabled={busy}><ShieldCheck size={14} /> Approve</Button>
              <Button variant="ghost" onClick={() => decide('returned')} disabled={busy}>Return to preparer</Button>
            </div>
          </div>
        : <Line>Waiting for the second approver.</Line>)}

      {f.status === 'approved' && (canAttest
        ? <div className="space-y-2">
            <Line info={{ title: 'Attestation', body: 'The accountable person certifies the frozen figures. Your name is taken from your own sign-in and cannot be edited.' }}>
              Attesting as <span className="text-[var(--color-ink)]">{profile?.user?.name ?? profile?.user?.email}</span></Line>
            <textarea className={box} rows={2} aria-label="Statement you certify" value={statement} onChange={e => setStatement(e.target.value)} />
            {eudr && (
              <label className="block text-[12.5px] text-[var(--color-mute)]">
                <span className="inline-flex items-center gap-1.5">Your function
                  <InfoButton compact details={{ title: 'Your function', sections: [{ heading: HEADING.shows, body: 'It is printed with your name in the signature block of the due diligence statement.' },
                    { heading: 'Legal basis', body: 'Regulation (EU) 2023/1115, Annex II, point 6.' }] }} /></span>
                <input className={`${box} mt-1`} value={fn} onChange={e => setFn(e.target.value)} placeholder="For example Head of Sourcing Compliance" />
              </label>)}
            <Button onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/attest`, { statement, function: fn || undefined }))}
              disabled={busy || !statement || (eudr && !fn.trim())}><Stamp size={14} /> Attest filing</Button>
          </div>
        : <Line>Approved. Awaiting attestation by the accountable person.</Line>)}

      {f.status === 'attested' && (canPublish
        ? <div className="space-y-2">
            <Line info={{ title: 'Recording the submission', body: "Submit the downloaded report through the regulator's own portal, then record its reference here. The platform records the submission; it does not send the report to the regulator itself." }}>
              Record the submission to the regulator.</Line>
            <input className={box} placeholder="Submission reference" value={subRef} onChange={e => setSubRef(e.target.value)} />
            <Button onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/submit`, { submission_ref: subRef || undefined }))} disabled={busy}><PenLine size={14} /> Record submission</Button>
          </div>
        : <Line>Attested. Awaiting submission to the regulator.</Line>)}

      {f.status === 'submitted' && f.own_flow && (
        <Line info={{ title: 'Accepted on its own page', body: `This report is accepted ${f.own_flow.accepted_by}.` }}>
          Accepted on its own page. <Link to={f.own_flow.own_page} className="text-[var(--color-sky)] hover:underline">Open it</Link></Line>)}
      {f.status === 'submitted' && !f.own_flow && (canPublish
        ? <div className="space-y-2">
            <Line>Record the regulator's acknowledgement.</Line>
            <input className={box} placeholder="Acknowledgement reference (optional)" value={ackRef} onChange={e => setAckRef(e.target.value)} />
            <Button onClick={() => call(() => api.post(`/v1/filings/${f.filing_id}/accept`, { ack_ref: ackRef || undefined }))} disabled={busy}><CheckCircle2 size={14} /> Mark accepted</Button>
          </div>
        : <Line>Submitted. Awaiting the regulator's acknowledgement.</Line>)}

      {f.status === 'accepted' && (f.own_flow
        ? <Line>Reference number recorded. <Link to={f.own_flow.own_page} className="text-[var(--color-sky)] hover:underline">Amendments and withdrawal</Link></Line>
        : <StatusChip tone="good" label="Accepted by the regulator · complete" />)}

      {(f.status === 'submitted' || f.status === 'accepted') && canPublish && (
        <div className="pt-3 border-t border-[var(--color-line)] space-y-2">
          <Line info={{ title: 'Restating a filing', body: 'A new version is frozen from the current book and runs the whole lifecycle again; this one is kept, marked superseded.' }}>Correct a filed figure by restating it.</Line>
          <input className={box} placeholder="Reason for the restatement" value={reason} onChange={e => setReason(e.target.value)} />
          <Button variant="ghost" disabled={busy || !reason}
            onClick={() => call(async () => { const r = await api.post<{ filing_id: string }>(`/v1/filings/${f.filing_id}/restate`, { reason }); onDone(); onOpen(r.filing_id) })}>
            <GitCompareArrows size={14} /> Restate filing</Button>
        </div>)}

      {draft && canReview && (
        <div className="pt-3 border-t border-[var(--color-line)] space-y-2">
          {!withdrawing
            ? <button onClick={() => setWithdrawing(true)} className="text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-bad)] hover:underline">Prepared by mistake? Withdraw this draft</button>
            : <>
                <Line info={{ title: 'Withdrawing a draft', body: 'The draft stays on record with its history and frozen data, but is no longer live, so the right one can be prepared for this period and scope. This cannot be undone.' }}>
                  Withdraw this draft.</Line>
                <textarea className={box} rows={2} placeholder="Reason (at least 10 characters)" value={wReason} onChange={e => setWReason(e.target.value)} />
                <div className="flex gap-2">
                  <Button variant="ghost" disabled={busy || wReason.trim().length < 10}
                    onClick={() => call(async () => { await api.post(`/v1/filings/${f.filing_id}/withdraw`, { reason: wReason.trim() }); toast.success('Draft withdrawn') })}>
                    <Trash2 size={14} /> Withdraw draft</Button>
                  <Button variant="ghost" onClick={() => { setWithdrawing(false); setWReason('') }} disabled={busy}>Cancel</Button>
                </div>
              </>}
        </div>)}

      {f.status === 'withdrawn' && (
        <Line info={withdrawal?.detail?.reason ? { title: 'Withdrawn', body: String(withdrawal.detail.reason) } : undefined}>
          Withdrawn{withdrawal?.actor ? ` by ${withdrawal.actor}` : ''}{withdrawal ? ` on ${withdrawal.at.slice(0, 10)}` : ''}; never filed.</Line>)}

      {f.status === 'superseded' && f.superseded_by && (
        <button onClick={() => onOpen(f.superseded_by!)} className="inline-flex items-center gap-1 text-[12.5px] text-[var(--color-sky)] hover:underline">
          Superseded by a restatement · open it <ArrowRight size={12} /></button>)}
    </Card>
  )
}
