import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, DatabaseZap, RefreshCw, ShieldCheck } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, type Message } from '../components/Details'
import { ChangeBar, Legend, ReleaseReview, STATUS, Stepper, day, num, type Release } from './ReferenceReleaseReview'

// Reference data releases, to the UI standard (2026-10-16): a reviewed publisher's new file is staged with its
// difference against what the platform holds and is applied only when approved — by two people, or proposed by the
// platform and approved by one, as the Approvers rule states. The main screen is the sources, the rule and the
// releases as bars and steps; each release opens in a side panel, every explanation in a pop-up.

type Detail = Message['detail']
interface Feed { source: string; name: string; about: Detail; cadence_days: number; last_refresh: string | null; last_status: string | null; status: string; awaiting_review: { release_id: string; status: string } | null; attribution: string }
interface Policy { action_key: string; label: string; detail: Detail; human_approvers: number; updated_at?: string | null; updated_by?: string | null }

const ABOUT = [
  { heading: HEADING.shows, body: 'Each new file from a reviewed publisher — FAO, Eurostat, the US Department of Agriculture and Statistics Canada — with what it would change in the platform’s crop data, before it is applied.' },
  { heading: HEADING.read, body: 'A release moves through three steps: received; proposed by an operator who reviewed it; approved and applied by a second person. Where the rule states one approver, the platform proposes and one person approves. Open a release to see its changes by crop, the largest revisions and the rows set aside.' },
  { heading: HEADING.sources, body: 'The publishers’ own files, fetched from their official sites. Each source’s coverage and schedule is behind its ⓘ.' },
  { heading: HEADING.limits, body: 'Nothing here changes customers’ figures until a release is approved; a release that is not applied changes nothing. Calibrations listed for a re-check are never changed here.' },
]

// Where a source's last check stands.
function standing(f: Feed): { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' } {
  if (f.awaiting_review) return f.awaiting_review.status === 'proposed' ? { label: 'Awaiting approval', tone: 'warn' } : { label: 'To review', tone: 'warn' }
  if (f.last_status === 'failed' || f.status === 'failed') return { label: 'Last check failed', tone: 'bad' }
  if (f.status === 'overdue') return { label: 'Check overdue', tone: 'warn' }
  if (f.status === 'untracked') return { label: 'Not checked yet', tone: 'neutral' }
  return { label: 'Up to date', tone: 'good' }
}

export default function ReferenceReleases() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['reference-releases'], queryFn: () => api.get<{ feeds: Feed[]; releases: Release[] }>('/v1/ops/reference-releases') })
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<{ user?: { id?: string; user_id?: string } }>('/v1/auth/me') })
  const myId = me.data?.user?.id ?? me.data?.user?.user_id ?? null
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const refresh = () => qc.invalidateQueries({ queryKey: ['reference-releases'] })
  const check = async (f: Feed) => {
    setBusy(f.source)
    try {
      const r = await api.post<{ status: string; awaiting_review: unknown }>(`/v1/ops/reference-releases/check?source=${f.source}`, {})
      if (r.status === 'failed') toast.error(`The check of ${f.name} failed. Try again later.`)
      else toast.success(r.awaiting_review ? `A new ${f.name} release is ready to review.` : `Nothing new from ${f.name}.`)
    } catch (e) { toast.error(apiMessage(e, `Could not check ${f.name}.`)) }
    finally { setBusy(null); refresh() }
  }
  const d = q.data
  const count = (s: Release['status']) => d?.releases.filter(r => r.status === s).length ?? 0
  const current = d?.releases.find(r => r.release_id === open) ?? null
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Platform · reference data" title="Reference data releases" lead="New publisher files, reviewed and approved before they are used." about={ABOUT} />
      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">Loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the releases.')}</Card>
        : <>
          <StatGrid cols={4} items={[
            { label: 'To review', value: count('staged'), accent: count('staged') ? 'var(--color-warn)' : undefined },
            { label: 'Awaiting approval', value: count('proposed'), accent: count('proposed') ? 'var(--color-warn)' : undefined },
            { label: 'Applied', value: count('landed') },
            { label: 'Sources', value: d.feeds.length, sub: 'checked monthly' },
          ]} />

          <Card className="p-5">
            <SectionHead icon={DatabaseZap} className="mb-3">Sources</SectionHead>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {d.feeds.map(f => {
                const st = standing(f)
                return (
                  <div key={f.source} className="rounded-lg border border-[var(--color-line-2)] p-3 flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[13px] font-medium text-[var(--color-ink)] leading-snug">{f.name}
                        <InfoButton compact className="ml-1.5" details={{ title: f.name, sections: [
                          { heading: HEADING.shows, body: f.about?.what }, { heading: 'How it is checked', body: f.about?.why },
                          { heading: HEADING.sources, body: f.attribution },
                        ].filter(s => s.body) }} /></span>
                      <StatusChip label={st.label} tone={st.tone} />
                    </div>
                    <div className="flex items-center justify-between gap-2 mt-auto">
                      <span className="text-[11.5px] text-[var(--color-faint)]">Checked {day(f.last_refresh)}</span>
                      <button type="button" onClick={() => check(f)} disabled={busy !== null || !!f.awaiting_review}
                        className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)] disabled:opacity-40 disabled:cursor-not-allowed">
                        <RefreshCw size={12} className={busy === f.source ? 'animate-spin' : ''} /> Check now</button>
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>

          <ApproverRule />

          <Card className="p-0 overflow-hidden">
            <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-2">
              <SectionHead>Releases</SectionHead>
              <Legend kinds={['added', 'revised', 'recomputed']} />
            </div>
            {d.releases.length === 0 ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No release received yet.</div>
              : <div className="divide-y divide-[var(--color-line)]">
                  {d.releases.map(r => {
                    const changes = r.summary.added + r.summary.revised + r.summary.recomputed
                    return (
                      <button key={r.release_id} type="button" onClick={() => setOpen(r.release_id)}
                        className="w-full text-left px-5 py-3 grid grid-cols-[minmax(0,1fr)_auto] md:grid-cols-[8.5rem_minmax(0,1.4fr)_minmax(0,1fr)_4.5rem_1rem] items-center gap-x-4 gap-y-2 hover:bg-[var(--color-bg-2)]">
                        <span className="order-2 md:order-none justify-self-end md:justify-self-start"><StatusChip label={STATUS[r.status].label} tone={STATUS[r.status].tone} /></span>
                        <span className="min-w-0"><span className="block text-[13px] text-[var(--color-ink)] truncate">{r.source_name}</span>
                          <span className="block text-[11.5px] text-[var(--color-faint)]">Received {day(r.fetched_at)}</span></span>
                        <span className="col-span-2 md:col-span-1 order-3 md:order-none flex items-center gap-2 min-w-0">
                          <span className="flex-1 min-w-0"><ChangeBar s={r.summary} /></span>
                          <span className="text-[11.5px] tabular-nums text-[var(--color-mute)] w-20 text-right shrink-0">{changes ? num(changes) : 'No changes'}</span>
                        </span>
                        <span className="hidden md:block"><Stepper r={r} compact /></span>
                        <ChevronRight size={15} className="hidden md:block text-[var(--color-faint)]" />
                      </button>
                    )
                  })}
                </div>}
          </Card>
          {current && <ReleaseReview r={current} myId={myId} attribution={d.feeds.find(f => f.source === current.source_key)?.attribution}
            onClose={() => setOpen(null)} onDone={refresh} />}
        </>}
    </div>
  )
}

// Who must approve a platform change: two people (one proposes, another approves), or one person approving what the
// platform proposes — stated when the organisation has a single approver.
function ApproverRule() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['platform-policy'], queryFn: () => api.get<{ policies: Policy[] }>('/v1/ops/reference-releases/policy') })
  const [edit, setEdit] = useState<string | null>(null)
  const [n, setN] = useState(2)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async (key: string) => {
    setBusy(true)
    try {
      await api.put('/v1/ops/reference-releases/policy', { action_key: key, human_approvers: n, reason: reason.trim() })
      toast.success('Approval rule saved.'); setEdit(null); setReason('')
      qc.invalidateQueries({ queryKey: ['platform-policy'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the rule.')) }
    finally { setBusy(false) }
  }
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  return (
    <Card className="p-5">
      <div className="flex items-center gap-1.5 mb-3">
        <SectionHead icon={ShieldCheck}>Approvers</SectionHead>
        <InfoButton compact details={{ title: 'Approvers', sections: [
          { heading: HEADING.shows, body: 'Who must approve before a change reaches customers.' },
          { heading: HEADING.read, body: 'Two people: one proposes, another approves. One person: the platform proposes, with its counts as the review note, and one person approves. Either way, nobody approves their own proposal.' },
        ] }} />
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {(q.data?.policies ?? []).map(p => (
          <div key={p.action_key} className="py-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12.5px]">
            <span className="text-[var(--color-ink)] min-w-[15rem] inline-flex items-center gap-1">{p.label}
              <InfoButton compact details={{ title: p.label, sections: [{ heading: HEADING.shows, body: p.detail?.what }] }} /></span>
            <StatusChip label={p.human_approvers === 1 ? 'One person' : 'Two people'} tone="neutral" />
            {p.updated_by && <span className="text-[11.5px] text-[var(--color-faint)]">Set {day(p.updated_at)} by {p.updated_by}</span>}
            {edit !== p.action_key
              ? <Button variant="ghost" className="ml-auto" onClick={() => { setEdit(p.action_key); setN(p.human_approvers) }}>Change</Button>
              : <div className="flex flex-wrap items-center gap-2 w-full">
                  <select value={n} onChange={e => setN(Number(e.target.value))} aria-label="Approvers" className={field}>
                    <option value={2}>Two people</option><option value={1}>One person</option></select>
                  <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why — kept in the audit record" aria-label="Why"
                    className={`${field} flex-1 min-w-[16rem]`} />
                  <Button disabled={busy || reason.trim().length < 10} onClick={() => save(p.action_key)}>Save</Button>
                  <Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button>
                </div>}
          </div>
        ))}
      </div>
    </Card>
  )
}
