import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText } from 'lucide-react'
import { api, apiMessage, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead } from './ui'
import { DocumentItems, type DocItem } from './SfdrDocumentItems'
import FilingPreflight from './FilingPreflight'

// A fund's SFDR pre-contractual (Annex II / III) and periodic (Annex IV / V) templates as they stand now — every item
// of the governing version, the manager answering what the platform cannot know. Filing freezes one of them through
// the ordinary lifecycle (Reports & filings).

interface Doc {
  document: string; template: string; title: string; citation: string; spec_version: string; period_end: string | null
  items: DocItem[]; missing: string[]; unmapped: Record<string, any>
  interpretations: { reading: string; declared_by: string }[]
}
const DOCS = [{ k: 'precontractual', label: 'Pre-contractual' }, { k: 'periodic', label: 'Periodic' }] as const

export default function SfdrDocument({ fundId, fundName }: { fundId: string; fundName: string }) {
  const qc = useQueryClient()
  const [doc, setDoc] = useState<'precontractual' | 'periodic'>('precontractual')
  const [filing, setFiling] = useState(false)
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['sfdr-doc', fundId, doc], queryFn: () => api.get<Doc>(`/v1/funds/${fundId}/sfdr-documents/${doc}`) })
  const d = q.data
  const answer = async (id: string, value: any) => {
    try {
      const r = await api.put<{ refused: { item: string; reason: string }[] }>(`/v1/funds/${fundId}/sfdr-documents/${doc}/answers`, { answers: { [id]: value } })
      if (r.refused?.length) toast.error(r.refused[0].reason)
      else toast.success('Answer saved')
      qc.invalidateQueries({ queryKey: ['sfdr-doc', fundId, doc] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the answer.')); throw e }
  }
  const nFill = d ? d.items.filter(i => i.source !== 'fixed').length : 0
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <SectionHead icon={FileText} hint={d ? `${d.template} · ${d.citation}` : undefined}>SFDR product disclosures</SectionHead>
          {d && <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">
            {d.missing.length ? `${d.missing.length} to answer` : 'every item answered'} · {nFill} items to fill
            {d.period_end ? ` · reference period ending ${d.period_end}` : ''}</div>}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden">
            {DOCS.map(x => (
              <button key={x.k} onClick={() => setDoc(x.k)} aria-pressed={doc === x.k}
                className={`mono text-[11px] px-2.5 py-1 ${doc === x.k ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{x.label}</button>
            ))}
          </div>
          {d && <button onClick={() => download(`/v1/funds/${fundId}/sfdr-documents/${doc}/annex.html`, `SFDR_${doc}_${fundName.replace(/\W+/g, '_')}.html`).catch(() => toast.error('Could not download.'))}
            className="mono text-[11px] text-[var(--color-sky)] hover:underline">download annex (draft)</button>}
          {d && <button onClick={() => setFiling(true)} className="mono text-[11px] text-[var(--color-sky)] hover:underline">prepare filing</button>}
        </div>
      </div>
      {q.isLoading && <div className="px-5 py-6 text-[12.5px] text-[var(--color-faint)]">reading the template…</div>}
      {q.isError && <div className="px-5 py-6 text-[12.5px] text-[var(--color-mute)]">{apiMessage(q.error, 'This template does not apply to the fund.')}</div>}
      {d && Object.keys(d.unmapped).length > 0 && (
        <div className="px-5 py-2.5 text-[11px] text-[var(--color-faint)] border-b border-[var(--color-line)]">
          Kept from the earlier form, not part of this template: {Object.keys(d.unmapped).map(k => k.replace(/^(legacy|website)\./, '').replace(/_/g, ' ')).join(', ')}
          {' '}(website disclosures belong to SFDR Art. 10).
        </div>
      )}
      {d && d.interpretations.map((i, n) => <div key={n} className="px-5 py-2 text-[11px] text-[var(--color-faint)] border-b border-[var(--color-line)]">Declared reading ({i.declared_by}): {i.reading}</div>)}
      {d && <DocumentItems items={d.items} onAnswer={answer} />}
      {filing && <FilingPreflight framework={`sfdr_${doc}`} fund={{ fund_id: fundId, name: fundName }} onClose={() => setFiling(false)}
        onGenerated={id => { setFiling(false); nav(`/filings?filing=${id}`) }} />}
    </Card>
  )
}
