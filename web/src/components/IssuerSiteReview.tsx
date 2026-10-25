import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Factory, X } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead, StatGrid } from './ui'
import { StatusChip } from './StatusChip'
import { HEADING, InfoButton } from './Details'

// Issuers' real sites from public registers (2026-10-23): Climate TRACE states each site's owner by its LEI, so its sites
// are tied directly; the EEA's industrial register names the parent company only by name, so each such site is proposed
// here and used only after an operator confirms it. A register states no site's share of the company's value.

type Status = 'pending' | 'confirmed' | 'rejected'
interface Source { source: string; match_basis: string; sites: number; issuers: number }
interface Candidate {
  candidate_id: string; issuer_name: string; issuer_lei: string; name: string | null; country: string | null; owner_named: string
  matched_lei: string; matched_name: string; relation: 'issuer' | 'consolidated_entity'; register_vintage: string
  status: Status; decided_by: string | null; decided_at: string | null; note: string | null
  site_facts: { activity?: string | null; city?: string | null }
}
interface Summary { sources: Source[]; counts: Partial<Record<Status, number>>; candidates: Candidate[] }

const REGISTER: Record<string, string> = { climate_trace: 'Climate TRACE', eea_ied: 'EEA industrial register' }
const TABS: { key: Status; label: string }[] = [{ key: 'pending', label: 'To decide' }, { key: 'confirmed', label: 'Confirmed' }, { key: 'rejected', label: 'Rejected' }]
const relation = (c: Candidate) => c.relation === 'issuer' ? `${c.issuer_name} itself` : `a company ${c.issuer_name} consolidates`

export default function IssuerSiteReview() {
  const qc = useQueryClient()
  const [tab, setTab] = useState<Status>('pending')
  const q = useQuery({ queryKey: ['issuer-sites', tab], queryFn: () => api.get<Summary>(`/v1/ops/issuer-sites?status=${tab}`) })
  const [busy, setBusy] = useState<string | null>(null)
  const [notes, setNotes] = useState<Record<string, string>>({})
  const decide = async (c: Candidate, confirm: boolean) => {
    setBusy(c.candidate_id)
    try {
      await api.post(`/v1/ops/issuer-sites/candidates/${c.candidate_id}/decide`, { confirm, note: notes[c.candidate_id]?.trim() || null })
      toast.success(confirm ? `Site added to ${c.issuer_name}.` : 'Proposal rejected.')
      qc.invalidateQueries({ queryKey: ['issuer-sites'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not record the decision.')) }
    finally { setBusy(null) }
  }
  const d = q.data
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1 text-[12px] outline-none focus:border-[var(--color-sky)]'
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-1.5">
        <SectionHead icon={Factory}>Companies’ sites from public registers</SectionHead>
        <InfoButton compact details={{ title: 'Companies’ sites from public registers', sections: [
          { heading: HEADING.shows, body: 'Plants, mines and other facilities of the companies customers’ funds hold, located from public registers with their owners.' },
          { heading: HEADING.read, body: 'Climate TRACE names each site’s owner by its legal entity identifier, so its sites are added directly. The EEA register names the owner only by name: a site is proposed when that name is a registered name of the company or of a company it consolidates, and is added only when you confirm it.' },
          { heading: HEADING.limits, body: 'No register states a site’s share of the company’s value, so these sites are located and assessed, but not weighted into the company’s loss until that share is provided.' },
        ] }} />
      </div>
      {!d ? <div className="text-[12.5px] text-[var(--color-faint)]">{q.isLoading ? 'Loading…' : apiMessage(q.error, 'Could not load the sites.')}</div> : <>
        <StatGrid cols={4} items={[
          ...d.sources.map(s => ({ label: REGISTER[s.source] ?? 'Register', value: s.sites.toLocaleString(), sub: `${s.issuers} ${s.issuers === 1 ? "company" : "companies"}` })),
          { label: 'To decide', value: (d.counts.pending ?? 0).toLocaleString(), accent: d.counts.pending ? 'var(--color-warn)' : undefined, sub: 'EEA register names' },
        ]} />
        <div className="flex gap-2">
          {TABS.map(t => (
            <button key={t.key} type="button" onClick={() => setTab(t.key)}
              className={`px-2.5 py-1 text-[11.5px] rounded-full border ${tab === t.key ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>
              {t.label}{d.counts[t.key] ? ` · ${d.counts[t.key]}` : ''}</button>
          ))}
        </div>
        {d.candidates.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">Nothing here.</div> : (
          <div className="divide-y divide-[var(--color-line)]">
            {d.candidates.map(c => (
              <div key={c.candidate_id} className="py-3 space-y-1.5 text-[12.5px]">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="text-[var(--color-ink)]">{c.name ?? 'Facility'}</span>
                  <span className="text-[11.5px] text-[var(--color-faint)]">{[c.site_facts.city, c.country].filter(Boolean).join(' · ')}</span>
                </div>
                <div className="grid gap-x-4 gap-y-0.5 sm:grid-cols-2">
                  <div><span className="text-[var(--color-mute)]">Register names the owner </span><span className="text-[var(--color-ink)]">{c.owner_named}</span></div>
                  <div><span className="text-[var(--color-mute)]">Registered name </span><span className="text-[var(--color-ink)]">{c.matched_name}</span>
                    <span className="text-[var(--color-faint)]"> — {relation(c)}</span></div>
                </div>
                {tab === 'pending' ? (
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <input value={notes[c.candidate_id] ?? ''} onChange={e => setNotes({ ...notes, [c.candidate_id]: e.target.value })}
                      placeholder="Note (optional)" aria-label="Note" className={`${field} w-48`} />
                    <Button disabled={busy !== null} onClick={() => decide(c, true)}><Check size={13} className="inline -mt-0.5 mr-1" />Confirm</Button>
                    <Button variant="ghost" disabled={busy !== null} onClick={() => decide(c, false)}><X size={13} className="inline -mt-0.5 mr-1" />Reject</Button>
                  </div>
                ) : (
                  <div className="flex items-center justify-end gap-2">
                    <StatusChip label={c.status === 'confirmed' ? 'Confirmed' : 'Rejected'} tone={c.status === 'confirmed' ? 'good' : 'neutral'} />
                    <span className="text-[11px] text-[var(--color-faint)]">{c.decided_by}</span>
                    {c.note && <InfoButton compact details={{ title: 'Decision note', sections: [{ heading: HEADING.shows, body: c.note }] }} />}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </>}
    </Card>
  )
}
