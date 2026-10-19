import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Building2, ListChecks, PenLine, Scale, History, ChevronRight } from 'lucide-react'
import { api, apiMessage, apiDetail } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead, PageHeader, Button } from '../components/ui'
import ReportTabs from '../components/ReportTabs'
import FilingPreflight from '../components/FilingPreflight'
import EsrsItems, { Materiality } from '../components/esrs/EsrsItems'
import EsrsFigures from '../components/esrs/EsrsFigures'
import EsrsUndertaking from '../components/esrs/EsrsUndertaking'
import EsrsComparatives from '../components/esrs/EsrsComparatives'
import { HEADING, InfoButton, MessageLine, messageDetails } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { Ring, SidePanel, Stack, TONE } from '../components/sfdr/visuals'
import { fmtDate } from '../components/sfdr/words'
import type { Check, Section, Statement } from '../components/esrs/types'

// An undertaking's ESRS sustainability statement (climate change, water and marine resources, biodiversity and
// ecosystems) for the financial year it reports, on the version of the standards that governs that year. In order: who
// reports and whether it must; the checks the filing will run; the figures it states; its materiality assessment; the
// comparatives; then each standard, item by item as the standard prints it, one click away.

interface Ent { entity_id: string; name: string; kind: string }
const SEVERITY = { blocking: 'To resolve', warning: 'To review' } as const

const todo = (s: Section) => s.items.filter(i => i.status === 'missing').length
const counts = (s: Section) => ({
  filled: s.items.filter(i => i.status === 'filled').length, omitted: s.items.filter(i => i.status === 'omitted').length, missing: todo(s),
})

export default function EsrsStatement() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [entity, setEntity] = useState('')
  const [std, setStd] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'todo'>('todo')
  const [filing, setFiling] = useState(false)
  const [passed, setPassed] = useState(false)
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const q = useQuery({ queryKey: ['esrs-statement', entity], queryFn: () =>
    api.get<Statement>(`/v1/esrs/statement${entity ? `?entity_id=${entity}` : ''}`) })
  const d = q.data, doc = d?.document_report
  const answer = async (standard: string, id: string, value: any) => {
    try {
      const r = await api.put<{ refused: { item: string; msg: { label: string } }[] }>('/v1/esrs/answers',
        { standard, answers: { [id]: value }, entity_id: entity || null })
      if (r.refused?.length) toast.error(r.refused[0].msg.label)
      else toast.success(value === null ? 'Cleared' : 'Saved')
      qc.invalidateQueries({ queryKey: ['esrs-statement'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save.')); throw e }
  }
  const checks = d?.checks ?? []
  const open = checks.filter(c => !c.passed)
  const blocking = open.filter(c => c.severity === 'blocking').length
  const sec = doc?.sections.find(s => s.standard === std)
  const all = (doc?.sections ?? []).map(counts).reduce((a, c) => ({ filled: a.filled + c.filled, omitted: a.omitted + c.omitted, missing: a.missing + c.missing }), { filled: 0, omitted: 0, missing: 0 })
  const total = all.filled + all.omitted + all.missing

  return (
    <div className="space-y-5">
      <ReportTabs />
      <PageHeader eyebrow="Report" title="ESRS sustainability statement"
        lead="Climate, water and biodiversity, for one undertaking or group."
        about={[
          { heading: HEADING.shows, body: 'The statement under the European Sustainability Reporting Standards for the financial year you report: who reports, the checks the filing runs, the figures you state, the materiality assessment, the comparatives and each standard item by item.' },
          { heading: HEADING.read, body: 'Every figure says where it comes from: computed by us, stated by you and attested by a second person, or derived from both. Anything not reported is omitted with its reason.' },
          ...(d ? [{ heading: 'Legal basis', body: `${d.spec.act}; Directive (EU) 2022/2464, Article 5(2), on who must report.` }] : []),
        ]}
        actions={<>
          <select aria-label="Undertaking or group" value={entity} onChange={e => setEntity(e.target.value)}
            className="text-[12.5px] bg-transparent border border-[var(--color-line-2)] rounded px-2 py-1.5">
            <option value="">Whole organisation</option>
            {(ents.data?.entities ?? []).map(e => <option key={e.entity_id} value={e.entity_id}>{e.kind === 'group' ? `Group — ${e.name}` : e.name}</option>)}
          </select>
          {d && <Button variant="primary" onClick={() => setFiling(true)}>Prepare filing</Button>}
        </>}>
        {doc && <div className="flex flex-wrap items-center gap-2 mt-2">
          <StatusChip tone="neutral" label={`Year ending ${fmtDate(doc.period_end)}`} />
          <StatusChip tone="neutral" label={`${doc.statement.sites.length} site${doc.statement.sites.length === 1 ? '' : 's'} in scope`} />
          {doc.statement.scope.basis_msg && <span className="inline-flex items-center gap-1"><StatusChip tone="neutral" label={doc.statement.scope.basis_msg.label} /><InfoButton compact details={messageDetails(doc.statement.scope.basis_msg)} /></span>}
          {(doc.statement.scope.gap_msgs ?? []).map((m, i) => <MessageLine key={i} m={m} className="text-[12px] text-[var(--color-warn)]" />)}
        </div>}
      </PageHeader>

      {q.isLoading && <Card className="p-5 text-[12.5px] text-[var(--color-faint)]">Building the statement…</Card>}
      {q.isError && <Card className="p-5"><MessageLine m={{ label: apiMessage(q.error, 'The statement is not available.'), detail: apiDetail(q.error) }} className="text-[12.5px] text-[var(--color-mute)]" /></Card>}

      {d && doc && <>
        {/* where the statement stands */}
        <Card className="p-5 flex flex-wrap items-center gap-6">
          <Ring value={total ? ((all.filled + all.omitted) / total) * 100 : 0} tone={all.missing ? TONE.warn : TONE.good} size={72} />
          <div className="flex-1 min-w-[220px] space-y-2">
            <div className="text-[13px] text-[var(--color-ink)]">Items reported or omitted with a reason</div>
            <Stack parts={[{ n: all.filled, tone: TONE.good, label: 'reported' }, { n: all.omitted, tone: TONE.slate, label: 'omitted' }, { n: all.missing, tone: TONE.warn, label: 'to do' }]} />
          </div>
          <div className="flex flex-col gap-1.5">
            {blocking ? <StatusChip tone="bad" label={`${blocking} check${blocking === 1 ? '' : 's'} to resolve`} /> : <StatusChip tone="good" label="Nothing blocks the filing" />}
            {open.length - blocking > 0 && <StatusChip tone="warn" label={`${open.length - blocking} to review`} />}
          </div>
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={Building2}>Who reports</SectionHead></div>
          <EsrsUndertaking key={entity} periodEnd={doc.period_end} entity={entity} role={doc.role} scope={doc.scope_check} closed={doc.period_closed} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
            <SectionHead icon={ListChecks}>Checks</SectionHead>
            <InfoButton compact details={{ title: 'Checks', sections: [{ heading: HEADING.shows, body: 'The checks the filing runs before it can be sent for approval: scope, completeness, consistency and the period close.' }] }} />
          </div>
          <div className="px-5 py-3 border-b border-[var(--color-line)]">
            <Stack parts={[{ n: checks.length - open.length, tone: TONE.good, label: 'passed' }, { n: open.length - blocking, tone: TONE.warn, label: 'to review' }, { n: blocking, tone: TONE.bad, label: 'to resolve' }]} />
          </div>
          <div className="divide-y divide-[var(--color-line)]">
            {open.map(c => <CheckRow key={c.rule} c={c} />)}
            {checks.length > open.length && (
              <button type="button" onClick={() => setPassed(p => !p)} className="w-full text-left px-5 py-2 text-[12px] text-[var(--color-faint)] hover:text-[var(--color-sky)]">
                {passed ? 'Hide' : 'Show'} {checks.length - open.length} passed</button>)}
            {passed && checks.filter(c => c.passed).map(c => <CheckRow key={c.rule} c={c} />)}
          </div>
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
            <SectionHead icon={PenLine}>Figures you state</SectionHead>
            <InfoButton compact details={{ title: 'Figures you state', sections: [{ heading: HEADING.read, body: 'A second person attests each value under Approvals before the statement uses it.' }] }} />
          </div>
          <EsrsFigures periodEnd={doc.period_end} entity={entity} closed={doc.period_closed} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={Scale}>Material topics</SectionHead></div>
          <Materiality key={entity} sections={doc.sections} onAnswer={answer} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={History}>Comparative information</SectionHead></div>
          <EsrsComparatives key={entity} c={doc.comparatives} v2026={d.spec.version.startsWith('dr_2026')} onAnswer={(id, v) => answer('comparatives', id, v)} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
            <SectionHead icon={FileText}>The statement</SectionHead>
            <InfoButton compact details={{ title: 'The statement', sections: [{ heading: HEADING.read, body: 'Each standard opens item by item, worded as the standard prints it: answer an item, or omit it with its reason.' }] }} />
          </div>
          <div className="grid gap-2.5 p-5 sm:grid-cols-3">
            {doc.sections.map(s => {
              const c = counts(s)
              return (
                <button key={s.standard} type="button" onClick={() => setStd(s.standard)}
                  className="text-left rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 hover:border-[var(--color-sky)] transition space-y-2">
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-[13px] text-[var(--color-ink)]">{s.title}</span>
                    <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />
                  </span>
                  <span className="block">{s.topic?.material === false ? <StatusChip tone="neutral" label="Not material" /> : c.missing ? <StatusChip tone="warn" label={`${c.missing} to do`} /> : <StatusChip tone="good" label="Complete" />}</span>
                  <Stack legend={false} parts={[{ n: c.filled, tone: TONE.good, label: 'reported' }, { n: c.omitted, tone: TONE.slate, label: 'omitted' }, { n: c.missing, tone: TONE.warn, label: 'to do' }]} />
                </button>)
            })}
          </div>
        </Card>

        {sec && (
          <SidePanel title={sec.title} wide onClose={() => setStd(null)}
            about={{ title: sec.title, sections: [{ heading: 'Legal basis', body: `${d.spec.act}, ESRS ${sec.standard}.` }] }}>
            <div className="flex items-center justify-between gap-3 mb-3">
              <span className="text-[12px] text-[var(--color-faint)]">Previous period ending {fmtDate(doc.comparatives.previous_period_end)}</span>
              <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden" role="group" aria-label="Which items">
                {(['todo', 'all'] as const).map(f => (
                  <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                    className={`text-[12px] px-2.5 py-1 ${filter === f ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{f === 'todo' ? 'To do' : 'Every item'}</button>))}
              </div>
            </div>
            <div className="-mx-6"><EsrsItems key={`${entity}-${sec.standard}`} section={sec} phaseIns={d.phase_ins} onAnswer={answer} filter={filter} /></div>
          </SidePanel>)}
      </>}

      {filing && <FilingPreflight framework="esrs_pack" entity={entity || undefined}
        onClose={() => setFiling(false)} onGenerated={id => { setFiling(false); nav(`/filings?filing=${id}`) }} />}
    </div>
  )
}

function CheckRow({ c }: { c: Check }) {
  const tone = c.passed ? 'good' : c.severity === 'blocking' ? 'bad' : 'warn'
  return (
    <div className="px-5 py-2 flex items-center gap-3 text-[12.5px]">
      <StatusChip tone={tone} label={c.passed ? 'Passed' : SEVERITY[c.severity as keyof typeof SEVERITY] ?? 'To review'} />
      {c.msg ? <MessageLine m={c.msg} className="text-[var(--color-mute)]" />
        : <span className="inline-flex items-center gap-1.5 text-[var(--color-mute)]">A check of the statement
          <InfoButton compact details={{ title: 'This check', sections: [{ heading: HEADING.shows, body: c.message }] }} /></span>}
      {c.ref && <InfoButton compact details={{ title: 'Legal basis', sections: [{ heading: 'Legal basis', body: c.ref }] }} />}
    </div>
  )
}
