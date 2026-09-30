import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Building2, ListChecks, PenLine, Scale } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead, PageHeader, Button } from '../components/ui'
import ReportTabs from '../components/ReportTabs'
import FilingPreflight from '../components/FilingPreflight'
import EsrsItems, { Materiality } from '../components/esrs/EsrsItems'
import EsrsFigures from '../components/esrs/EsrsFigures'
import EsrsUndertaking from '../components/esrs/EsrsUndertaking'
import type { Statement } from '../components/esrs/types'

// An undertaking's ESRS sustainability statement (E1 climate change, E3 water and marine resources, E4 biodiversity
// and ecosystems) for the financial year the organisation reports, on the ESRS version that governs that year. Built in
// order: who reports and must it (role, Art. 5(2)); the figures it states; its materiality assessment; then each
// standard item by item. The checks below are the ones the filing runs; the filing itself is frozen from here.

interface Ent { entity_id: string; name: string; kind: string }
const SEV: Record<string, string> = { blocking: 'var(--color-bad)', warning: 'var(--color-warn)', info: 'var(--color-good)' }

export default function EsrsStatement() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [entity, setEntity] = useState('')
  const [std, setStd] = useState('E1')
  const [filter, setFilter] = useState<'all' | 'todo'>('todo')
  const [filing, setFiling] = useState(false)
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const q = useQuery({ queryKey: ['esrs-statement', entity], queryFn: () =>
    api.get<Statement>(`/v1/esrs/statement${entity ? `?entity_id=${entity}` : ''}`) })
  const d = q.data, doc = d?.document_report
  const answer = async (standard: string, id: string, value: any) => {
    try {
      const r = await api.put<{ refused: { item: string; reason: string }[] }>('/v1/esrs/answers',
        { standard, answers: { [id]: value }, entity_id: entity || null })
      if (r.refused?.length) toast.error(r.refused[0].reason)
      else toast.success(value === null ? 'Cleared' : 'Saved')
      qc.invalidateQueries({ queryKey: ['esrs-statement'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save.')); throw e }
  }
  const blocking = (d?.checks ?? []).filter(c => !c.passed && c.severity === 'blocking').length
  const sec = doc?.sections.find(s => s.standard === std)
  const todo = (s: typeof sec) => s ? s.items.filter(i => i.status === 'missing').length : 0
  return (
    <div className="space-y-5">
      <ReportTabs />
      <PageHeader eyebrow="Report" title="ESRS sustainability statement"
        lead="E1, E3 and E4 for one undertaking or group, on the ESRS version that governs the financial year. Every figure says where it comes from; anything not reported is omitted with its reason."
        actions={<>
          <select aria-label="Undertaking or group" value={entity} onChange={e => setEntity(e.target.value)}
            className="text-[12.5px] bg-transparent border border-[var(--color-line-2)] rounded px-2 py-1.5">
            <option value="">Whole organisation</option>
            {(ents.data?.entities ?? []).map(e => <option key={e.entity_id} value={e.entity_id}>{e.kind === 'group' ? `Group — ${e.name}` : e.name}</option>)}
          </select>
          {d && <Button variant="primary" onClick={() => setFiling(true)}>Prepare filing</Button>}
        </>}>
        {d && doc && <div className="mono text-[11px] text-[var(--color-faint)] mt-2">
          {d.spec.act} · financial year ending {doc.period_end} · {doc.statement.sites.length} site(s) in scope — {doc.statement.scope.basis}</div>}
      </PageHeader>

      {q.isLoading && <Card className="p-5 text-[12.5px] text-[var(--color-faint)]">Building the statement…</Card>}
      {q.isError && <Card className="p-5 text-[12.5px] text-[var(--color-mute)]">{apiMessage(q.error, 'The statement is not available.')}</Card>}

      {d && doc && <>
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={Building2} hint="Directive (EU) 2022/2464 Art. 5(2) as amended">Who reports</SectionHead></div>
          <EsrsUndertaking key={entity} periodEnd={doc.period_end} entity={entity} role={doc.role} scope={doc.scope_check} closed={doc.period_closed} />
          {doc.statement.scope.gaps.length > 0 && <div className="px-5 pb-4 text-[11.5px] text-[var(--color-warn)]">{doc.statement.scope.gaps.join(' · ')}</div>}
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={ListChecks} hint={blocking ? `${blocking} to resolve before filing` : 'nothing blocks the filing'}>Checks</SectionHead></div>
          <div className="divide-y divide-[var(--color-line)]">
            {d.checks.filter(c => !c.passed || c.severity === 'info').map(c => (
              <div key={c.rule} className="px-5 py-2 flex gap-3 text-[12px]">
                <span className="mono text-[10px] w-16 shrink-0 pt-0.5" style={{ color: c.passed ? SEV.info : SEV[c.severity] }}>{c.passed ? 'ok' : c.severity}</span>
                <span className="text-[var(--color-mute)] min-w-0 break-words">{c.message}{c.ref ? <span className="text-[var(--color-faint)]"> — {c.ref}</span> : null}</span>
              </div>))}
          </div>
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={PenLine} hint="attested by a second person before the statement uses them">Figures you state</SectionHead></div>
          <EsrsFigures periodEnd={doc.period_end} entity={entity} closed={doc.period_closed} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)]"><SectionHead icon={Scale} hint="the undertaking's materiality assessment">Material topics</SectionHead></div>
          <Materiality key={entity} sections={doc.sections} onAnswer={answer} />
        </Card>

        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3 flex-wrap">
            <SectionHead icon={FileText} hint={`previous period ${doc.previous.period_end}`}>The statement</SectionHead>
            <div className="flex items-center gap-3">
              <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden">
                {doc.sections.map(s => (
                  <button key={s.standard} onClick={() => setStd(s.standard)} aria-pressed={std === s.standard}
                    className={`mono text-[11px] px-2.5 py-1 ${std === s.standard ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>
                    {s.standard}{todo(s) ? ` · ${todo(s)}` : ''}</button>))}
              </div>
              <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden">
                {(['todo', 'all'] as const).map(f => (
                  <button key={f} onClick={() => setFilter(f)} aria-pressed={filter === f}
                    className={`mono text-[11px] px-2.5 py-1 ${filter === f ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{f === 'todo' ? 'to do' : 'every item'}</button>))}
              </div>
            </div>
          </div>
          {sec && <EsrsItems key={`${entity}-${std}`} section={sec} phaseIns={d.phase_ins} onAnswer={answer} filter={filter} />}
        </Card>
      </>}

      {filing && <FilingPreflight framework="esrs_pack" entity={entity || undefined}
        onClose={() => setFiling(false)} onGenerated={id => { setFiling(false); nav(`/filings?filing=${id}`) }} />}
    </div>
  )
}
