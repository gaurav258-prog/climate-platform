import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead } from './ui'
import { DocumentItems, type DocItem } from './SfdrDocumentItems'
import FilingPreflight from './FilingPreflight'

// An insurer's two document reports as they stand now — the ORSA climate change scenario analysis (Directive
// 2009/138/EC Art. 45a) and the pre-emptive recovery plan's nat-cat stress and capital indicators (Directive (EU)
// 2025/1 Art. 5(7)-(8)) — for the whole organisation, one undertaking or the group. Both apply to reports made from
// 30 January 2027: the planned date of the report chooses the rules and is frozen with the filing.

interface Doc {
  report_type: string; title: string; citation: string; period_end: string
  spec: { framework: string; version: string; applies: { from: string } }; items: DocItem[]
}
interface Ent { entity_id: string; name: string; kind: string }
const DOCS = [
  { k: 'insurer_orsa_climate', label: 'ORSA climate (Art. 45a)' },
  { k: 'insurer_recovery_stress', label: 'Recovery plan stress (IRRD Art. 5)' },
] as const

export default function InsurerDocuments() {
  const qc = useQueryClient()
  const nav = useNavigate()
  const [doc, setDoc] = useState<(typeof DOCS)[number]['k']>('insurer_orsa_climate')
  const [entity, setEntity] = useState('')
  const [when, setWhen] = useState('')                    // '' = the platform's default (today, or the day the rules apply)
  const [filing, setFiling] = useState(false)
  const ents = useQuery({ queryKey: ['filing-entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/filings/entities') })
  const key = ['insurer-doc', doc, entity, when]
  const q = useQuery({ queryKey: key, queryFn: () => api.get<Doc>(`/v1/insurance/documents/${doc}?${new URLSearchParams({ ...(entity ? { entity_id: entity } : {}), ...(when ? { disclosure_date: when } : {}) })}`) })
  const d = q.data
  const answer = async (id: string, value: any) => {
    try {
      const r = await api.put<{ refused: { item: string; reason: string }[] }>(`/v1/insurance/documents/${doc}/answers`,
        { answers: { [id]: value }, entity_id: entity || null, disclosure_date: when || null })
      if (r.refused?.length) toast.error(r.refused[0].reason)
      else toast.success('Answer saved')
      qc.invalidateQueries({ queryKey: ['insurer-doc', doc] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the answer.')); throw e }
  }
  const missing = d ? d.items.filter(i => i.status === 'missing').length : 0
  const planned = when || (d ? d.spec.applies.from : '')
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <SectionHead icon={FileText} hint={d ? d.citation : undefined}>Solvency II documents</SectionHead>
          {d && <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">
            {missing ? `${missing} to answer` : 'every item computed or answered'} · period ending {d.period_end} · rules in force on {planned}</div>}
        </div>
        <div className="flex items-center gap-3 shrink-0 flex-wrap">
          <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden">
            {DOCS.map(x => (
              <button key={x.k} onClick={() => setDoc(x.k)} aria-pressed={doc === x.k}
                className={`mono text-[11px] px-2.5 py-1 ${doc === x.k ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{x.label}</button>
            ))}
          </div>
          <select aria-label="Undertaking or group" value={entity} onChange={e => setEntity(e.target.value)}
            className="mono text-[11px] bg-transparent border border-[var(--color-line-2)] rounded px-2 py-1">
            <option value="">Whole organisation</option>
            {(ents.data?.entities ?? []).map(e => <option key={e.entity_id} value={e.entity_id}>{e.kind === 'group' ? `Group — ${e.name}` : e.name}</option>)}
          </select>
          <label className="mono text-[11px] text-[var(--color-mute)] flex items-center gap-1.5">
            {doc === 'insurer_orsa_climate' ? 'concluded on' : 'submitted on'}
            <input type="date" value={when} min={d?.spec.applies.from} onChange={e => setWhen(e.target.value)}
              className="bg-transparent border border-[var(--color-line-2)] rounded px-1.5 py-0.5" />
          </label>
          {d && <button onClick={() => setFiling(true)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">prepare filing</button>}
        </div>
      </div>
      {q.isLoading && <div className="px-5 py-6 text-[12.5px] text-[var(--color-faint)]">running the scenarios…</div>}
      {q.isError && <div className="px-5 py-6 text-[12.5px] text-[var(--color-mute)]">{apiMessage(q.error, 'This document is not available.')}</div>}
      {d && <DocumentItems items={d.items} onAnswer={answer} />}
      {filing && <FilingPreflight framework={doc} entity={entity || undefined} disclosureDate={planned || undefined}
        onClose={() => setFiling(false)} onGenerated={id => { setFiling(false); nav(`/filings?filing=${id}`) }} />}
    </Card>
  )
}
