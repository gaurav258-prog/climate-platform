import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, Lock, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, SectionHead } from './ui'
import { HEADING, InfoButton, type DetailSection, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { fmtDate } from './filing/words'
import { Said, errMessage } from './intake/parts'

// CRCS record retention — how long this filed report must be kept and under which law, as a timeline: each rule's
// period from where it starts to when it ends, your own policy, today and the date to keep it until. The law's text,
// its article and the sentence that sets the period sit one click away; a legal hold stops archiving, and lifting it
// needs a second person (services/governance/record_retention.py).

interface Rule { key: string; years: number; runs_from: string; runs_from_label: string | null; from: string; until: string; act: string; article: string; url: string; quote: string; covers: string | null; coverage: 'named' | 'indirect'; note: string | null; scope: 'eu' | 'national' }
interface Retention {
  document: string; document_label: string; country: string | null; country_name: string | null; rules: Rule[]; legal_until: string | null
  policy_years: number; policy_from: string | null; policy_until: string | null; keep_until: string | null; provisional: boolean; gaps: Message[]; may_be_archived: boolean
  legal_hold: { on: boolean; reason: string | null; since: string | null }
}

const t = (s: string) => new Date(s).getTime()

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
    } catch (e) { toast.error(errMessage(e, 'Could not change the legal hold').label) } finally { setBusy(false) }
  }
  const bars = [
    ...r.rules.map(x => ({ key: x.key, from: x.from, until: x.until, label: `${x.years} years · ${x.scope === 'national' ? `${r.country_name ?? 'national'} law` : 'EU law'}`,
      tone: x.coverage === 'indirect' ? 'var(--color-warn)' : 'var(--color-sky)', details: ruleDetails(x) })),
    ...(r.policy_years > 0 && r.policy_from && r.policy_until ? [{ key: 'policy', from: r.policy_from, until: r.policy_until, label: `${r.policy_years} years · your policy`,
      tone: 'var(--color-slate)', details: [{ heading: HEADING.shows, body: `Your organisation keeps every filed report at least ${r.policy_years} years (Settings). It can lengthen a legal period, never shorten it.` }] }] : []),
  ]
  const today = new Date().toISOString().slice(0, 10)
  const lo = Math.min(...bars.map(b => t(b.from)), t(today))
  const hi = Math.max(...bars.map(b => t(b.until)), t(today))
  const pos = (d: string) => `${(100 * (t(d) - lo)) / Math.max(1, hi - lo)}%`

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={Archive}>Record retention</SectionHead>
        <InfoButton compact details={{ title: 'Record retention', sections: [
          { heading: HEADING.shows, body: 'How long this filed report must be kept, and under which law: each rule that applies, with when its period starts and ends, and your own policy.' },
          { heading: HEADING.read, body: 'Keep it until the latest of these dates. A period that starts on publication is provisional until the filing is submitted. Select a rule for the law, the article and the sentence that sets the period.' },
          { heading: HEADING.limits, body: 'Frozen filings are never deleted. “May be archived” means it may leave the active register. A legal hold keeps it whatever the dates say.' }] }} />
        <span className="ml-auto inline-flex items-center gap-1.5 flex-wrap">
          <StatusChip tone="neutral" label={r.document_label} />
          {r.legal_hold.on ? <StatusChip tone="warn" label="On legal hold" /> : r.may_be_archived && <StatusChip tone="good" label="May be archived" />}
        </span>
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-[12.5px] text-[var(--color-mute)]">Keep until</span>
        <span className="display text-[22px] tabular-nums text-[var(--color-ink)]">{r.keep_until ? fmtDate(r.keep_until) : '—'}</span>
        {r.provisional && <span className="inline-flex items-center gap-1"><StatusChip tone="warn" label="Provisional" />
          <InfoButton compact details={{ title: 'Provisional', sections: [{ heading: HEADING.shows, body: 'A period here starts when the report is published. Until it is submitted, it is counted from when it was frozen.' }] }} /></span>}
      </div>

      {bars.length > 0 && (
        <div className="space-y-1.5">
          <div className="relative">
            {bars.map(b => (
              <div key={b.key} className="flex items-center gap-2 py-0.5">
                <span className="w-40 shrink-0 min-w-0 text-[11.5px] text-[var(--color-mute)] flex items-center gap-1">
                  <span className="truncate">{b.label}</span><InfoButton compact details={{ title: b.label, sections: b.details }} /></span>
                <div className="relative flex-1 h-3 rounded-full bg-[var(--color-line)]">
                  <div className="absolute inset-y-0 rounded-full" title={`${fmtDate(b.from)} to ${fmtDate(b.until)}`}
                    style={{ left: pos(b.from), width: `calc(${pos(b.until)} - ${pos(b.from)})`, background: b.tone, opacity: 0.8 }} />
                  <div className="absolute -inset-y-1 w-px bg-[var(--color-ink)]" style={{ left: pos(today) }} title="Today" />
                </div>
              </div>))}
          </div>
          <div className="flex justify-between pl-[10.5rem] text-[11px] text-[var(--color-faint)] tabular-nums">
            <span>{fmtDate(new Date(lo).toISOString())}</span>
            <span className="inline-flex items-center gap-1"><span className="w-px h-3 bg-[var(--color-ink)]" />Today</span>
            <span>{fmtDate(new Date(hi).toISOString())}</span>
          </div>
        </div>)}

      {r.gaps.length > 0 && <div className="space-y-1">{r.gaps.map((g, i) => <div key={i} className="text-[12.5px]"><Said m={g} tone="warn" /></div>)}</div>}

      {r.legal_hold.on && (
        <div className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)]"><Lock size={12} style={{ color: 'var(--color-warn)' }} />
          Held since {r.legal_hold.since ? fmtDate(r.legal_hold.since) : '—'}
          <InfoButton compact details={{ title: 'Why it is held', sections: [{ heading: HEADING.shows, body: r.legal_hold.reason ?? '—' }] }} /></div>)}
      {canAct && (
        <div>
          {!open
            ? <button onClick={() => setOpen(true)} className="text-[12px] text-[var(--color-sky)] hover:underline">{r.legal_hold.on ? 'Ask to lift the hold' : 'Put on legal hold'}</button>
            : (
              <div className="flex flex-wrap items-center gap-2">
                <input autoFocus value={reason} onChange={e => setReason(e.target.value)} aria-label="Reason"
                  placeholder={r.legal_hold.on ? 'Why the hold can end' : 'Why it must be held (a dispute, an investigation)'}
                  className="flex-1 min-w-[220px] rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" />
                <button disabled={busy || !reason.trim()} onClick={() => act(r.legal_hold.on)} className="rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1 text-[12px] disabled:opacity-50">{r.legal_hold.on ? 'Send for approval' : 'Set hold'}</button>
                <button onClick={() => setOpen(false)} className="text-[12px] text-[var(--color-mute)]">Cancel</button>
              </div>)}
        </div>)}
    </Card>
  )
}

// One rule's pop-up: when it runs from, what it covers, and the law itself — act, article, the sentence, the link.
function ruleDetails(x: Rule): DetailSection[] {
  return [
    { heading: HEADING.shows, body: `${x.years} years from ${x.runs_from_label ?? 'its start'}: ${fmtDate(x.from)} to ${fmtDate(x.until)}.` },
    ...(x.covers ? [{ heading: 'What it covers', body: x.covers }] : []),
    ...(x.coverage === 'indirect' ? [{ heading: 'How it applies', body: `It covers this report through general wording${x.note ? `: ${x.note}` : '.'}` }]
      : x.note ? [{ heading: 'Note', body: x.note }] : []),
    { heading: 'The law', body: <span>{x.act}, {x.article}. <a href={x.url} target="_blank" rel="noopener noreferrer" className="underline inline-flex items-center gap-0.5">Read the text <ExternalLink size={11} /></a></span> },
    { heading: 'What it says', body: <i>“{x.quote}”</i> },
  ]
}
