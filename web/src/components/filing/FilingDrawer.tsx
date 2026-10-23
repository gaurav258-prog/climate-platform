import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ShieldCheck, AlertTriangle, Clock, Send, Download, RadioTower, ChevronLeft, ArrowRight, Flame, ListChecks, Check, Scale } from 'lucide-react'
import { api, ApiError, apiDetail, apiMessage, download } from '../../lib/api'
import { toast } from '../../lib/toast'
import { frameworkLabel, horizonLabel, scenarioLabel } from '../../lib/hazards'
import { useAuth } from '../../lib/auth'
import { Card, Button, SectionHead } from '../ui'
import { HEADING, InfoButton, MessageLine, type Message, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { CloseButton } from '../Dialog'
import { Drawer } from '../Drawer'
import FilingRun, { type EngineRun } from '../FilingRun'
import FilingRetention from '../FilingRetention'
import FilingLineage from '../FilingLineage'
import FilingVariance from '../FilingVariance'
import FilingForm from '../FilingForm'
import RegulatoryLineage from '../RegulatoryLineage'
import { AssuranceShareDialog } from '../GrcFollowups'
import { ScopeChip } from './ScopeChip'
import { Checklist, type Validation } from './Checklist'
import { ActionPanel, type FilingDetail } from './ActionPanel'
import { BASIS_FIELD, CASE_STAGE, EVENT, FACTS_VIEW, RULES_IN_FORCE, STAGES, STATUS_TONE, fmtDate, version } from './words'

// One filing, full window: where it stands in its lifecycle, what is left before it can be submitted, the frozen
// report behind it (fingerprinted, with its downloads), the final form, how it moved, the law it rests on, the checklist,
// the next step, the regulator case and its history.

interface CaseLink { case_id: string; regulator: string; reference: string | null; stage: string; n_messages: number }
interface Detail extends FilingDetail {
  regulator?: string; basis?: string; events: { from: string | null; to: string; action: string; detail: Record<string, unknown>; at: string; actor: string | null }[]
  export_formats?: string[]; disclosure_date?: string | null; due_date?: string | null; due_rule?: string | null
  fx_revisions?: { currency: string; basis: string; as_of: string; change: string }[]
  run?: EngineRun | null; snapshot_version: number | null; created_at: string; scope?: string; filing_role?: string | null
  entity_name?: string | null; fund_name?: string | null
  snapshot?: { version: number; reporting_basis: Record<string, unknown>; payload_sha256: string; hash_verified: boolean; created_at: string }
}

export default function FilingDrawer({ filingId, onClose, onChanged, onOpen }: { filingId: string; onClose: () => void; onChanged: () => void; onOpen: (id: string) => void }) {
  const [share, setShare] = useState<{ id: string; label: string } | null>(null)
  const { profile } = useAuth()
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['filing', filingId], queryFn: () => api.get<Detail>(`/v1/filings/${filingId}`) })
  const val = useQuery({ queryKey: ['filing-validation', filingId], queryFn: () => api.get<Validation>(`/v1/filings/${filingId}/validation`) })
  const f = q.data
  // a lifecycle action can re-freeze the filing (refresh, restate): its form and supplied values are re-read too
  const reload = () => { q.refetch(); val.refetch(); for (const k of [['filings'], ['obligations'], ['filing-form', filingId], ['provided']]) qc.invalidateQueries({ queryKey: k }); onChanged() }
  const about: DetailSection[] = f ? [
    ...(f.basis ? [{ heading: 'Legal basis', body: f.basis }] : []),
    ...(f.regulator ? [{ heading: 'Regulator', body: f.regulator }] : []),
    ...(f.due_rule ? [{ heading: 'Deadline', body: f.due_rule }] : []),
  ] : []

  return (
    <Drawer placement="full" label={f ? `Filing · ${f.label}` : 'Filing'} onClose={onClose} className="w-full max-w-6xl mx-auto min-h-full pb-16">
      <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-3 border-b border-[var(--color-line)] bg-[var(--color-bg)]/95 backdrop-blur">
        <button onClick={onClose} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-ink)]"><ChevronLeft size={15} /> Back to reports</button>
        <CloseButton onClick={onClose} />
      </div>
      {q.isError ? <div className="p-8"><MessageLine m={{ label: apiMessage(q.error, 'This filing is not available'), detail: apiDetail(q.error) }} className="text-[13px] text-[var(--color-mute)]" /></div>
        : !f ? <div className="p-8 text-[13px] text-[var(--color-faint)]">Loading…</div> : (
        <div className="p-6 space-y-6">
          <div>
            <div className="flex items-center gap-3 mb-1.5 flex-wrap">
              <h2 className="display text-xl font-semibold m-0">{f.label}</h2>
              <StatusChip value={f.status} tone={STATUS_TONE[f.status]} />
              <ScopeChip role={f.filing_role} scope={f.scope} name={f.fund_name ?? f.entity_name} />
              {about.length > 0 && <InfoButton compact details={{ title: f.label, sections: about }} />}
            </div>
            <div className="flex items-center gap-2 flex-wrap text-[12.5px] text-[var(--color-mute)]">
              <span>{[f.period_label, f.regulator, f.scope === 'organisation' ? 'Whole organisation' : null].filter(Boolean).join(' · ')}</span>
              {f.disclosure_date && <StatusChip tone="neutral" label={`Made on ${fmtDate(f.disclosure_date)}`} />}
              {f.due_date && <StatusChip tone="neutral" label={`Due ${fmtDate(f.due_date)}`} />}
            </div>
          </div>

          <StageRail status={f.status} />
          <SubmitReadiness filingId={filingId} status={f.status} blocking={val.data?.blocking ?? 0} />

          {f.snapshot && <FrozenReport f={f} onShare={() => setShare({ id: f.filing_id, label: `${frameworkLabel(f.framework)} · ${f.period_label}` })} />}
          {f.snapshot && <FilingRetention filingId={f.filing_id} />}
          {f.run ? <FilingRun run={f.run} filingId={f.filing_id} />
            : f.snapshot && <div className="px-1 text-[12.5px] text-[var(--color-faint)] flex items-center gap-1.5">Frozen before calculation runs were recorded
                <InfoButton compact details={{ title: 'No calculation run on record', sections: [
                  { heading: HEADING.shows, body: 'This report was frozen before the platform recorded the calculation run behind each filing, so there is no fingerprint to compare newer data with.' },
                  { heading: 'What you can do', body: 'Refresh it while it is a draft, or restate it once filed, to pin it to a recorded run.' }] }} /></div>}

          <FilingForm filingId={filingId} />
          <FilingVariance filingId={filingId} />

          {f.snapshot && <div className="space-y-2">
            <SectionHead icon={Scale} hint="the act, its specification, the templates" className="px-1">From the law to this filing</SectionHead>
            <RegulatoryLineage filingId={filingId} />
          </div>}
          <FilingLineage filingId={filingId} />

          {val.data && <Checklist v={val.data} />}
          <ActionPanel f={f} perms={profile?.permissions ?? []} onDone={reload} blocking={val.data?.blocking ?? 0} onOpen={onOpen} />
          <FilingTransmission f={f} />
          <History events={f.events} />
        </div>
      )}
      {share && <AssuranceShareDialog filingId={share.id} label={share.label} onClose={() => setShare(null)} />}
    </Drawer>
  )
}

// The frozen report: its version, whether it still matches its fingerprint, the basis it was frozen on, and downloads.
function FrozenReport({ f, onShare }: { f: Detail; onShare: () => void }) {
  const s = f.snapshot!
  const value = (k: string, v: unknown): string => {
    const t = String(v ?? '—')
    if (k === 'scenario') return scenarioLabel(t)
    if (k === 'horizon') return horizonLabel(t)
    if (k === 'regulation_status') return RULES_IN_FORCE[t] ?? t
    if (k === 'view') return FACTS_VIEW[t] ?? t
    if (k === 'reporting_period_end') return v ? fmtDate(t) : '—'
    return t
  }
  const field = (k: string) => k === 'reporting_period_end' && 'shipment' in s.reporting_basis ? 'Shipment date'
    : k === 'reporting_period_end' && 'declaration' in s.reporting_basis ? 'Declaration date' : BASIS_FIELD[k] ?? 'Other setting'
  const rows = Object.entries(s.reporting_basis).filter(([, v]) => v != null && v !== '')
  const fx = f.fx_revisions ?? []
  const btn = 'inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition'
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={ShieldCheck}>Frozen report</SectionHead>
        <StatusChip tone="neutral" label={version(s.version)} />
        <StatusChip tone={s.hash_verified ? 'good' : 'bad'} label={s.hash_verified ? 'Matches its fingerprint' : 'Does not match its fingerprint'} />
        <InfoButton compact details={{ title: 'Fingerprint', sections: [
          { heading: HEADING.shows, body: 'When a report is frozen the platform takes a fingerprint of its exact content. Every download and the assurance pack are made from these frozen figures, and the fingerprint shows they have not changed since.' },
          { heading: 'Fingerprint', body: <span className="mono text-[11.5px] break-all">{s.payload_sha256}</span> },
          { heading: 'Frozen', body: new Date(s.created_at).toLocaleString('en-GB') }] }} />
      </div>
      <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5 text-[12.5px]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-b border-[var(--color-line)] pb-1">
            <span className="text-[var(--color-mute)]">{field(k)}</span>
            <span className="text-[var(--color-ink)] text-right" style={k === 'regulation_status' && v !== 'current' ? { color: 'var(--color-warn)' } : undefined}>{value(k, v)}</span>
          </div>))}
      </div>
      {fx.length > 0 && (
        <div className="rounded-lg px-3 py-2 text-[12.5px] flex items-center gap-1.5" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 10%, transparent)' }}>
          <AlertTriangle size={13} /> {fx.length} exchange {fx.length === 1 ? 'rate' : 'rates'} changed since freezing
          <InfoButton compact details={{ title: 'Exchange rates changed since freezing', sections: [
            { heading: HEADING.shows, body: <ul className="space-y-0.5">{fx.map((r, i) => <li key={i}>{`${r.currency} · ${r.as_of}: ${r.change}`}</li>)}</ul> },
            { heading: 'What you can do', body: 'Its money figures may need restating. Restate the filing once it is filed, or refresh it while it is a draft.' }] }} />
        </div>)}
      {(f.export_formats?.length ?? 0) > 0 && (
        <div className="pt-3 border-t border-[var(--color-line)] flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-[var(--color-faint)] mr-1">Download</span>
          {f.export_formats!.map(fmt => (
            <button key={fmt} className={btn} onClick={() => download(`/v1/filings/${f.filing_id}/export?format=${fmt}`,
              SERVER_NAMED.has(fmt) ? undefined : `${f.framework}-${f.period_label}-v${s.version}.${fmt}`)
              .catch(e => toast.error(apiMessage(e, 'Could not download the export.')))}><Download size={12} /> {FORMAT_LABEL[fmt] ?? fmt.toUpperCase()}</button>))}
          <button className={btn} onClick={() => download(`/v1/filings/${f.filing_id}/assurance-pack`, `assurance-${f.framework}-${f.period_label}.zip`)
            .catch(e => toast.error(apiMessage(e, 'Could not download the assurance pack.')))}><ShieldCheck size={12} /> Assurance pack</button>
          <button className={btn} onClick={onShare}><Send size={12} /> Share with auditor</button>
          <InfoButton compact details={{ title: 'Downloads', sections: [
            { heading: HEADING.shows, body: 'Each file is rendered from the frozen report, so it matches the fingerprint above.' },
            ...(f.export_formats!.includes('xbrlcsv') ? [{ heading: 'xBRL-CSV', body: "The file the EBA's Pillar 3 data hub takes: every template figure on the EBA's own datapoint. Its name is the EBA's naming; keep it as downloaded." }] : []),
            { heading: 'Assurance pack', body: 'The evidence behind this filing for an auditor: the method, the validation record, the four-eyes approvals, where each figure came from, and a list of every file with its fingerprint.' },
            { heading: 'Share with auditor', body: 'Sends the auditor a link to the assurance pack. The link expires, counts downloads, can be revoked, and every access is logged.' }] }} />
        </div>)}
    </Card>
  )
}

// formats whose label is not the format code, and whose file name is part of the format (kept as the server sends it)
const FORMAT_LABEL: Record<string, string> = { xbrlcsv: 'xBRL-CSV' }
const SERVER_NAMED = new Set(['xbrlcsv'])

function StageRail({ status }: { status: string }) {
  if (status === 'rejected' || status === 'superseded' || status === 'withdrawn')
    return <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-mute)]">This filing is no longer live <StatusChip value={status} tone={STATUS_TONE[status]} /></div>
  const idx = STAGES.indexOf(status as typeof STAGES[number])
  const tone = (i: number) => i < idx ? 'var(--color-sky)' : i === idx ? 'var(--color-sky)' : 'var(--color-panel-2)'
  return (
    <div className="flex items-center" role="list" aria-label="Lifecycle">
      {STAGES.map((s, i) => {
        const done = i < idx, cur = i === idx
        return (
          <div key={s} role="listitem" className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1.5">
              <span className="relative flex items-center justify-center">
                {cur && <span className="absolute inline-flex h-6 w-6 rounded-full animate-ping" style={{ background: 'var(--color-sky)', opacity: 0.35 }} />}
                <span className="w-6 h-6 rounded-full flex items-center justify-center text-[10.5px] relative z-10"
                  style={{ background: tone(i), color: i <= idx ? 'var(--color-on-accent)' : 'var(--color-faint)' }}>
                  {done ? <Check size={12} strokeWidth={3} /> : i + 1}
                </span>
              </span>
              <span className="text-[10.5px] whitespace-nowrap" style={{ color: i <= idx ? 'var(--color-ink)' : 'var(--color-faint)' }}>{STAGE_WORD[s]}</span>
            </div>
            {i < STAGES.length - 1 && <div className="flex-1 h-0.5 mx-1 mb-4 rounded" style={{ background: i < idx ? 'var(--color-sky)' : 'var(--color-panel-2)' }} />}
          </div>)
      })}
    </div>
  )
}
const STAGE_WORD: Record<string, string> = { draft: 'Draft', in_review: 'In review', approved: 'Approved', attested: 'Attested', submitted: 'Submitted', accepted: 'Accepted' }

// What is left before this filing can be submitted, each one click away (pre-filtered to this filing where supported).
function SubmitReadiness({ filingId, status, blocking }: { filingId: string; status: string; blocking: number }) {
  if (['submitted', 'accepted', 'superseded', 'withdrawn'].includes(status)) return null
  const chip = (tone: string) => `inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[12px] transition hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] ${tone}`
  const neutral = 'border-[var(--color-line-2)] text-[var(--color-mute)]'
  return (
    <Card className="p-3">
      <div className="flex items-center flex-wrap gap-2">
        <span className="text-[12px] text-[var(--color-faint)] mr-1">To submit</span>
        <Link to={`/exceptions?filing=${filingId}`} className={chip(blocking > 0 ? 'border-[var(--color-warn)] text-[var(--color-warn)]' : 'border-[var(--color-line-2)] text-[var(--color-good)]')}>
          <AlertTriangle size={12} /> {blocking > 0 ? `${blocking} blocking ${blocking === 1 ? 'check' : 'checks'} to clear` : 'No blocking checks'} <ArrowRight size={12} />
        </Link>
        <Link to="/approvals" className={chip(status === 'in_review' ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : neutral)}>
          <ListChecks size={12} /> {status === 'in_review' ? 'Awaiting the second approver' : 'Four-eyes approval'} <ArrowRight size={12} />
        </Link>
        <Link to={`/tasks?filing=${filingId}`} className={chip(neutral)}><Flame size={12} /> Team tasks <ArrowRight size={12} /></Link>
      </div>
    </Card>
  )
}

// The regulator case for this filing (Transmission): open it, or start one once the filing is far enough to transmit.
function FilingTransmission({ f }: { f: Detail }) {
  const { profile } = useAuth()
  const nav = useNavigate()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)
  const canOpen = (profile?.permissions ?? []).includes('reports.publish') && ['attested', 'submitted', 'accepted'].includes(f.status)
  const q = useQuery({ queryKey: ['filing-case', f.filing_id], queryFn: () => api.get<{ case: CaseLink | null }>(`/v1/transmission/cases/for-filing/${f.filing_id}`) })
  const c = q.data?.case
  if (!c && !canOpen) return null
  const openCase = async () => {
    setBusy(true); setErr(null)
    try {
      const nc = await api.post<{ case_id: string }>('/v1/transmission/cases', { regulator: f.regulator || 'Regulator', filing_id: f.filing_id })
      qc.invalidateQueries({ queryKey: ['transmission-cases'] })
      nav(`/transmission?case=${nc.case_id}`)
    } catch (e) { setErr({ label: e instanceof ApiError ? apiMessage(e, 'Could not open the case') : 'Could not open the case', detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  return (
    <Card className="p-4 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={RadioTower}>Regulator case</SectionHead>
        {c && <StatusChip tone="neutral" label={CASE_STAGE[c.stage] ?? 'Open'} />}
      </div>
      {c ? <button onClick={() => nav(`/transmission?case=${c.case_id}`)} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline">
            Open the case with {c.regulator}{c.n_messages ? ` · ${c.n_messages} ${c.n_messages === 1 ? 'message' : 'messages'}` : ''} <ArrowRight size={12} /></button>
        : <div className="flex items-center gap-2 flex-wrap">
            <Button variant="ghost" onClick={openCase} disabled={busy}><RadioTower size={13} /> Open a regulator case</Button>
            <InfoButton compact details={{ title: 'Regulator case', sections: [{ heading: HEADING.shows, body: "A case tracks this filing's submission and the regulator's questions and answers, in Transmission." }] }} />
          </div>}
      {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}
    </Card>
  )
}

// The lifecycle as it happened: each step, who and when; what they recorded one click away.
function History({ events }: { events: Detail['events'] }) {
  return (
    <div>
      <SectionHead icon={Clock} className="mb-3">History</SectionHead>
      <ol className="relative border-l border-[var(--color-line-2)] ml-2 space-y-3.5">
        {events.map((e, i) => {
          const d = e.detail ?? {}
          const said: DetailSection[] = [
            ...(typeof d.reason === 'string' && d.reason ? [{ heading: 'Reason', body: d.reason }] : []),
            ...(typeof d.statement === 'string' ? [{ heading: 'Statement', body: `${String(d.attestor_name ?? '')}${d.function ? `, ${String(d.function)}` : ''}: “${d.statement}”` }] : []),
            ...(typeof d.submission_ref === 'string' && d.submission_ref ? [{ heading: 'Submission reference', body: d.submission_ref }] : []),
            ...(typeof d.ack_ref === 'string' && d.ack_ref ? [{ heading: 'Acknowledgement reference', body: d.ack_ref }] : []),
          ]
          return (
            <li key={i} className="pl-4 relative">
              <span className="absolute -left-[5px] top-1.5 h-2.5 w-2.5 rounded-full" style={{ background: e.to === 'withdrawn' || e.to === 'rejected' ? 'var(--color-bad)' : 'var(--color-sky)' }} />
              <div className="flex items-center gap-2 flex-wrap text-[13px] text-[var(--color-ink)]">
                {EVENT[e.action] ?? 'Updated'} <StatusChip value={e.to} tone={STATUS_TONE[e.to]} />
                {said.length > 0 && <InfoButton compact details={{ title: EVENT[e.action] ?? 'What was recorded', sections: said }} />}
              </div>
              <div className="text-[11.5px] text-[var(--color-faint)] mt-0.5">{e.actor ?? 'The platform'} · {new Date(e.at).toLocaleString('en-GB')}</div>
            </li>)
        })}
      </ol>
    </div>
  )
}
