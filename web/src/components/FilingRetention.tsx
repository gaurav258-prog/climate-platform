import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Lock, ExternalLink } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card } from './ui'

// CRCS record retention — how long this filed report must be kept, under which law, and a legal hold that stops it
// being archived. The periods come from cited reference data; lifting a hold needs a second person.

interface Rule { key: string; years: number; runs_from: string; from: string; until: string; act: string; article: string; url: string; quote: string; covers: string | null; coverage: 'named' | 'indirect'; note: string | null }
interface Retention {
  document: string; country: string | null; rules: Rule[]; legal_until: string | null; policy_years: number; policy_until: string | null
  keep_until: string | null; provisional: boolean; gaps: string[]; may_be_archived: boolean
  legal_hold: { on: boolean; reason: string | null; since: string | null }
}
const DOC: Record<string, string> = { management_report: 'part of the management report', pillar3: 'a Pillar 3 disclosure',
  sfcr: 'a Solvency and Financial Condition Report', eudr_dds: 'an EUDR due-diligence record', website_disclosure: 'a website disclosure', unknown: 'not mapped' }
const FROM: Record<string, string> = { end_of_calendar_year_prepared: 'from the end of the year it was prepared', end_of_period_year: 'from the end of the reporting year', publication: 'from publication', period_end: 'from the period end' }
function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }

export default function FilingRetention({ filingId }: { filingId: string }) {
  const { profile } = useAuth()
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['retention', filingId], queryFn: () => api.get<Retention>(`/v1/filings/${filingId}/retention`) })
  const [reason, setReason] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const r = q.data
  if (!r) return null
  const act = async (lift: boolean) => {
    setBusy(true)
    try {
      await api.post(`/v1/filings/${filingId}/legal-hold${lift ? '/lift' : ''}`, { reason })
      toast.success(lift ? 'Sent to a second person to lift the hold.' : 'Legal hold set — this filing cannot be archived.')
      setOpen(false); setReason(''); qc.invalidateQueries({ queryKey: ['retention', filingId] })
    } catch (e) { toast.error(msg(e, 'Could not change the legal hold.')) } finally { setBusy(false) }
  }
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] flex items-center gap-1.5"><Archive size={12} /> Record retention</div>
        {r.legal_hold.on
          ? <span className="inline-flex items-center gap-1 mono text-[10.5px]" style={{ color: 'var(--color-warn)' }}><Lock size={12} /> on legal hold</span>
          : r.may_be_archived && <span className="mono text-[10.5px] text-[var(--color-mute)]">may now be archived</span>}
      </div>
      <div className="text-[13px] text-[var(--color-ink)]">
        Keep until <b className="mono">{r.keep_until ?? '—'}</b>{r.provisional && <span className="text-[var(--color-faint)]"> (provisional — counted from submission, once submitted)</span>}
        <span className="text-[var(--color-mute)]"> · this filing is {DOC[r.document] ?? r.document}{r.country ? ` · ${r.country} law` : ''}</span>
      </div>
      <ul className="mt-2 space-y-1.5">
        {r.rules.map(x => (
          <li key={x.key} className="text-[12px] text-[var(--color-mute)]">
            <span className="text-[var(--color-ink)]">{x.years} years</span> {FROM[x.runs_from] ?? x.runs_from} ({x.from} → {x.until}) —{' '}
            <a href={x.url} target="_blank" rel="noopener noreferrer" className="underline inline-flex items-center gap-0.5">{x.act} {x.article} <ExternalLink size={10} /></a>
            <div className="text-[11px] text-[var(--color-faint)] italic">“{x.quote}”</div>
            {x.coverage === 'indirect' && <div className="text-[11px]" style={{ color: 'var(--color-warn)' }}>Covers this report through general wording{x.note ? ` — ${x.note}` : ''}</div>}
            {x.coverage === 'named' && x.note && <div className="text-[11px] text-[var(--color-faint)]">{x.note}</div>}
          </li>))}
        {r.policy_years > 0 && <li className="text-[12px] text-[var(--color-mute)]"><span className="text-[var(--color-ink)]">{r.policy_years} years</span> — your own policy (Settings), until {r.policy_until}</li>}
        {r.gaps.map((g, i) => <li key={i} className="text-[11.5px]" style={{ color: 'var(--color-warn)' }}>{g}</li>)}
      </ul>
      {r.legal_hold.on && <div className="mt-2 text-[12px] text-[var(--color-mute)]">Held since {r.legal_hold.since?.slice(0, 10)}: “{r.legal_hold.reason}”</div>}
      {canAct && (
        <div className="mt-3">
          {!open
            ? <button onClick={() => setOpen(true)} className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-sky)] hover:underline">{r.legal_hold.on ? 'Ask to lift the hold' : 'Put on legal hold'}</button>
            : (
              <div className="flex flex-wrap items-center gap-2">
                <input autoFocus value={reason} onChange={e => setReason(e.target.value)} aria-label="Reason"
                  placeholder={r.legal_hold.on ? 'Why the hold can end' : 'Why the record must be held (a dispute, an investigation)'}
                  className="flex-1 min-w-[220px] rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" />
                <button disabled={busy || !reason.trim()} onClick={() => act(r.legal_hold.on)} className="rounded-lg bg-[var(--color-sky)] text-white px-3 py-1 text-[12px] disabled:opacity-50">{r.legal_hold.on ? 'Send for approval' : 'Set hold'}</button>
                <button onClick={() => setOpen(false)} className="text-[12px] text-[var(--color-mute)]">Cancel</button>
              </div>)}
        </div>)}
    </Card>
  )
}
