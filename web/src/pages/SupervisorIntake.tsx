import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Check, ChevronLeft, Database, FileSpreadsheet, FolderOpen, Orbit, Play, Telescope } from 'lucide-react'
import { ApiError, api, apiDetail, apiMessage } from '../lib/api'
import { scenarioLabel } from '../lib/hazards'
import { balance } from '../lib/money'
import { toast } from '../lib/toast'
import { Button, Card, PageHeader, SectionHead } from '../components/ui'
import { Dialog } from '../components/Dialog'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine, type Message } from '../components/Details'
import { FileCheck } from './supervisorIntake/FileCheck'
import { yearLabel } from './supervisorIntake/periods'
import { Gauge, SplitBar } from './supervisorIntake/visuals'
import type { Spec, Status, Submission } from './supervisorIntake/types'

// The supervisor's intake for one supervised entity (Tier 2), to the UI standard (2026-10-16): the main screen is three
// visuals — the template on file, how much of the supervisor's own granular data is placed on the map, how far the
// scenario projections are — and a grid of what is on file per year. Uploading shows a valid-versus-problems bar;
// matching columns, the stated basis, the rows with problems and the location rule open one click away.

const ABOUT = [
  { heading: HEADING.shows, body: 'The two files you hold about this entity for each financial year: the template it submitted, and your own granular data on its exposures. Each file is checked against the fields your supervision profile sets for its sector, and nothing is saved until you choose to save it.' },
  { heading: HEADING.read, body: 'Location coverage is the share of your granular data’s value placed on the map. Scenario projections count the locations that have values under every scenario and year; the independent lens needs them complete to tell a difference in the entity’s stated basis from a difference in scoring.' },
  { heading: HEADING.sources, body: 'The template, uploaded by your authority or submitted by the entity through its portal. Your granular data, such as a loan-level extract, located by the region code, postcode or coordinates it carries.' },
  { heading: HEADING.limits, body: 'Rows without a usable location are counted and reported, never placed at a country’s centre. Each import of granular data replaces the previous one for this entity. Your granular data is yours alone: the entity never sees it.' },
]
const CHANNEL: Record<string, string> = { supervisor_upload: 'Uploaded by your authority', entity_portal: 'Submitted by the entity', api: 'Received through a connection' }
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
const back = 'inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline'
const lens = 'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition border border-[var(--color-line-2)] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]'

export default function SupervisorIntake() {
  const { orgId = '' } = useParams()
  const [watching, setWatching] = useState(0)        // while scores and projections are computed after an import or a run
  const q = useQuery({
    queryKey: ['sup-intake', orgId], retry: false,
    queryFn: () => api.get<Status>(`/v1/supervisor/intake/${orgId}`),
    refetchInterval: watching ? 10000 : false,
  })
  const d = q.data
  useEffect(() => {
    if (watching && (d?.shadow_book.projection.complete || Date.now() - watching > 300000)) setWatching(0)
  }, [d, watching])
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">Loading…</div>
  if (!d) return <Unavailable orgId={orgId} profile={errorCode(q.error) === 'supervision.intake.no_spec'}
    m={{ label: apiMessage(q.error, 'Intake is not available for this entity'), detail: apiDetail(q.error) }} />
  const templates = d.submissions.filter(s => s.framework === d.intake.submission.framework)
  const imports = d.submissions.filter(s => s.framework === 'granular')
  const onFile = [...new Set(d.submissions.map(s => s.period_label))]
  const watch = () => setWatching(Date.now())
  return (
    <div className="fadeup space-y-6">
      <Link to={`/supervised/${orgId}`} className={back}><ChevronLeft size={13} /> Entity file</Link>
      <PageHeader eyebrow="Intake" title={d.entity_name ?? 'Supervised entity'} lead="The template this entity submitted, and your own granular data." about={ABOUT}
        actions={<Link to={`/supervised/${orgId}/lens`} className={lens}><Telescope size={14} />Independent lens</Link>} />
      <div className="grid gap-4 lg:grid-cols-3">
        <TemplateCard spec={d.intake} latest={[...templates].sort((a, b) => b.period_label.localeCompare(a.period_label))[0]}>
          <FileCheck orgId={orgId} kind="submission" spec={d.intake} onFile={onFile} onSaved={() => {}} />
        </TemplateCard>
        <GranularCard d={d}>
          <FileCheck orgId={orgId} kind="granular" spec={d.intake} onFile={onFile} onSaved={watch} />
        </GranularCard>
        <ProjectionCard orgId={orgId} d={d} running={!!watching} onRun={watch} />
      </div>
      {d.submissions.length > 0 && <OnFile spec={d.intake} templates={templates} imports={imports} />}
    </div>
  )
}

// A refused intake (core/errors.py): the catalogue's words with their explanation, and the one place to go next.
const errorCode = (e: unknown) => e instanceof ApiError ? (e.body as { error?: { error?: string } } | null)?.error?.error : undefined

function Unavailable({ orgId, m, profile }: { orgId: string; m: Message; profile: boolean }) {
  return (
    <div className="fadeup space-y-4">
      <Link to={`/supervised/${orgId}`} className={back}><ChevronLeft size={13} /> Entity file</Link>
      <Card className="p-6 space-y-3">
        <div className="text-[15px] font-semibold text-[var(--color-ink)]"><MessageLine m={m} /></div>
        <Link to={profile ? '/admin' : '/supervised'} className="inline-block text-[12.5px] text-[var(--color-sky)] hover:underline">
          {profile ? 'Open Settings' : 'Open Population'}
        </Link>
      </Card>
    </div>
  )
}

function CardHead({ icon, title, sections }: { icon: typeof Database; title: string; sections: { heading: string; body: string }[] }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <SectionHead icon={icon}>{title}</SectionHead>
      <InfoButton compact details={{ title, sections }} />
    </div>
  )
}

const Empty = ({ children }: { children: string }) => <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">{children}</div>

function TemplateCard({ spec, latest, children }: { spec: Spec; latest?: Submission; children: React.ReactNode }) {
  const b = latest?.basis ?? {}
  return (
    <Card className="p-5 flex flex-col gap-4">
      <CardHead icon={FileSpreadsheet} title="Submitted template" sections={[
        { heading: HEADING.shows, body: `${spec.submission.label}: the cells as the entity filed them.` },
        { heading: HEADING.read, body: 'The latest template on file, with the scenario and year the entity states in its narrative. The independent lens compares it cell by cell with the same template rebuilt from your granular data.' },
        { heading: HEADING.sources, body: 'Uploaded by your authority, or submitted by the entity through its portal.' },
      ]} />
      {latest ? (
        <div className="flex items-end gap-4">
          <div>
            <div className="display text-[34px] leading-none tabular-nums text-[var(--color-ink)]">{latest.n_cells.toLocaleString()}</div>
            <div className="text-[11.5px] text-[var(--color-mute)] mt-1.5">template cells</div>
          </div>
          <div className="flex flex-col items-start gap-1.5 min-w-0">
            <StatusChip tone="good" label={`On file · ${latest.period_label}`} />
            {(b.scenario || b.horizon) && <StatusChip tone="neutral" label={[b.scenario && scenarioLabel(b.scenario), b.horizon && yearLabel(b.horizon)].filter(Boolean).join(' · ')} />}
          </div>
        </div>
      ) : <Empty>No template on file</Empty>}
      {children}
    </Card>
  )
}

function GranularCard({ d, children }: { d: Status; children: React.ReactNode }) {
  const sb = d.shadow_book, g = d.intake.granular
  const pct = sb.coverage_value_pct
  return (
    <Card className="p-5 flex flex-col gap-4">
      <CardHead icon={Database} title="Your granular data" sections={[
        { heading: HEADING.shows, body: `${g.label}: your own data on the entity’s exposures, row by row. The ring is the share of its value placed on the map.` },
        { heading: HEADING.read, body: g.location_rule },
        { heading: HEADING.limits, body: `Precision: ${g.precision_label}. Each import replaces the previous one. The entity never sees this data.` },
      ]} />
      {sb.n_rows ? (
        <div className="flex items-center gap-4">
          <Gauge share={pct == null ? null : pct / 100} center={pct == null ? '—' : `${Math.round(pct)}%`} caption="of value located"
            color="var(--color-sky)" label={`${pct ?? 0}% of the value has a location`} />
          <div className="min-w-0 flex-1 space-y-2.5">
            <div className="text-[12.5px] text-[var(--color-mute)] tabular-nums">
              <span className="display text-[22px] text-[var(--color-ink)] mr-1.5">{sb.n_rows.toLocaleString()}</span>rows · {balance(sb.value_eur)}
            </div>
            <SplitBar label="Rows by location" parts={[
              { label: `${sb.n_located.toLocaleString()} located`, value: sb.n_located, color: 'var(--color-sky)' },
              { label: `${(sb.n_rows - sb.n_located).toLocaleString()} not located`, value: sb.n_rows - sb.n_located, color: 'var(--color-faint)' },
            ]} />
          </div>
        </div>
      ) : <Empty>No granular data yet</Empty>}
      {children}
    </Card>
  )
}

function ProjectionCard({ orgId, d, running, onRun }: { orgId: string; d: Status; running: boolean; onRun: () => void }) {
  const p = d.shadow_book.projection
  const done = p.cells_complete ?? 0
  const [busy, setBusy] = useState(false)
  const run = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ message: Message }>(`/v1/supervisor/intake/${orgId}/projections/run`, {})
      toast.success(r.message.label); onRun()
    } catch (e) { toast.error(apiMessage(e, 'The projections could not be started')) } finally { setBusy(false) }
  }
  return (
    <Card className="p-5 flex flex-col gap-4">
      <CardHead icon={Orbit} title="Scenario projections" sections={[
        { heading: HEADING.shows, body: `How many locations in your granular data have values under every scenario and year the platform projects (${p.anchors_total} combinations).` },
        { heading: HEADING.read, body: 'The independent lens needs them complete to tell a difference in the entity’s stated basis from a difference in scoring. They are computed after each import of granular data, and you can start them again here.' },
        { heading: HEADING.limits, body: 'A hazard that does not change with the climate scenario keeps the same value under every scenario.' },
      ]} />
      {p.cells ? (
        <div className="flex items-center gap-4">
          <Gauge share={done / p.cells} center={`${done}/${p.cells}`} caption="locations complete"
            color={p.complete ? 'var(--color-good)' : 'var(--color-warn)'} label={`${done} of ${p.cells} locations have every scenario`} />
          <div className="flex flex-col items-start gap-2">
            <StatusChip tone={p.complete ? 'good' : 'warn'} label={p.complete ? 'Complete' : running ? 'Computing' : 'Incomplete'} />
            {!p.complete && <Button onClick={run} disabled={busy || running}><Play size={14} />{busy ? 'Starting…' : 'Run projections'}</Button>}
          </div>
        </div>
      ) : <Empty>Import granular data first</Empty>}
    </Card>
  )
}

// What is on file, per financial year: a filled square where a file was received. The template is kept per year;
// granular data is one book, so only its latest import is in use.
function OnFile({ spec, templates, imports }: { spec: Spec; templates: Submission[]; imports: Submission[] }) {
  const [open, setOpen] = useState<{ s: Submission; granular: boolean } | null>(null)
  const periods = [...new Set([...templates, ...imports].map(s => s.period_label))].sort().reverse()
  const inUse = imports[0]
  const rows = [
    { name: 'Submitted template', granular: false, list: templates },
    { name: 'Your granular data', granular: true, list: imports },
  ]
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-4">
        <SectionHead icon={FolderOpen}>On file</SectionHead>
        <InfoButton compact details={{ title: 'On file', sections: [
          { heading: HEADING.read, body: 'A filled square is a file received for that financial year; open it for the file, who sent it and when. Your granular data is one book: its latest import is in use and earlier ones are replaced.' },
        ] }} />
      </div>
      <div className="overflow-x-auto">
        <table className="text-[12.5px]">
          <thead><tr>
            <th />
            {periods.map(p => <th key={p} className="px-2 pb-2 font-medium text-[var(--color-mute)] tabular-nums">{p}</th>)}
          </tr></thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.name}>
                <td className="pr-4 py-1.5 text-[var(--color-ink)] whitespace-nowrap">{r.name}</td>
                {periods.map(p => {
                  const s = r.list.find(x => x.period_label === p)
                  const current = !r.granular || s === inUse
                  return (
                    <td key={p} className="px-2 py-1.5 text-center">
                      {s ? (
                        <button type="button" onClick={() => setOpen({ s, granular: r.granular })} aria-label={`${r.name} ${p}`}
                          title={`${r.name} · ${p} · ${current ? 'received' : 'replaced'} ${day(s.created_at)}`}
                          className="w-8 h-8 rounded-md inline-grid place-items-center transition hover:ring-2 hover:ring-[var(--color-sky)]"
                          style={{ background: `color-mix(in oklab, ${current ? 'var(--color-good)' : 'var(--color-slate)'} 22%, transparent)`, color: current ? 'var(--color-good)' : 'var(--color-slate)' }}>
                          <Check size={15} />
                        </button>
                      ) : <span className="w-8 h-8 rounded-md inline-block border border-dashed border-[var(--color-line-2)]" aria-hidden="true" />}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && <Received spec={spec} s={open.s} granular={open.granular} inUse={open.s === inUse} onClose={() => setOpen(null)} />}
    </Card>
  )
}

function Received({ spec, s, granular, inUse, onClose }: { spec: Spec; s: Submission; granular: boolean; inUse: boolean; onClose: () => void }) {
  const b = s.basis ?? {}
  const fact = (label: string, value: React.ReactNode) => value == null || value === '' ? null : (
    <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]">
      <span className="text-[var(--color-mute)]">{label}</span><span className="text-right text-[var(--color-ink)] break-all">{value}</span>
    </div>)
  return (
    <Dialog title={`${granular ? 'Your granular data' : 'Submitted template'} · ${s.period_label}`} onClose={onClose} className="max-w-lg">
      <div className="text-[12px] text-[var(--color-mute)] mb-3">{granular ? spec.granular.label : spec.submission.label}</div>
      {granular && fact('Status', <StatusChip tone={inUse ? 'good' : 'neutral'} label={inUse ? 'In use' : 'Replaced'} />)}
      {fact('Received', new Date(s.created_at).toLocaleString())}
      {fact('From', CHANNEL[s.channel ?? ''] ?? 'Uploaded')}
      {fact('By', s.submitted_by)}
      {fact('File', s.source_file)}
      {!granular && fact('Template cells', s.n_cells.toLocaleString())}
      {!granular && fact('Stated scenario', b.scenario ? scenarioLabel(b.scenario) : 'Not stated')}
      {!granular && fact('Stated year', b.horizon ? yearLabel(b.horizon) : 'Not stated')}
      {!granular && fact('At-risk level', b.at_risk_level != null ? String(b.at_risk_level) : null)}
      {!granular && fact('Method note', b.method_note)}
    </Dialog>
  )
}
