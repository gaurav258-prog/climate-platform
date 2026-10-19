import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Download, Send, BookOpen } from 'lucide-react'
import { api, apiMessage, apiDetail, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead } from './ui'
import { DocumentItems, sectorName, type DocItem } from './SfdrDocumentItems'
import FilingPreflight from './FilingPreflight'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Ring, SidePanel, Stack, TONE, pct } from './sfdr/visuals'
import { DOCUMENT, fmtDate } from './sfdr/words'

// A fund's SFDR product documents — pre-contractual and periodic — as they stand now: how far they are filled, and the
// figures computed from the fund, with the template itself, item by item as the Regulation prints it, one click away.
// Filing freezes one of them through the ordinary lifecycle (Reports & filings).

interface Doc {
  document: string; title: string; citation: string; period_end: string | null
  items: DocItem[]; missing: string[]; unmapped: Record<string, unknown>
  interpretations: { reading: string; declared_by: string }[]
}
type Kind = keyof typeof DOCUMENT
type Refused = { item: string; msg: Message }
const BASIS: Record<string, string> = { turnover: 'Turnover', capex: 'CapEx', opex: 'OpEx' }

export default function SfdrDocument({ fundId, fundName }: { fundId: string; fundName: string }) {
  const qc = useQueryClient()
  const [doc, setDoc] = useState<Kind>('precontractual')
  const [filing, setFiling] = useState(false)
  const [open, setOpen] = useState(false)
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['sfdr-doc', fundId, doc], queryFn: () => api.get<Doc>(`/v1/funds/${fundId}/sfdr-documents/${doc}`) })
  const d = q.data
  const answer = async (id: string, value: unknown) => {
    try {
      const r = await api.put<{ refused: Refused[] }>(`/v1/funds/${fundId}/sfdr-documents/${doc}/answers`, { answers: { [id]: value } })
      if (r.refused?.length) toast.error(r.refused[0].msg.label)
      else toast.success('Answer saved')
      qc.invalidateQueries({ queryKey: ['sfdr-doc', fundId, doc] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the answer.')); throw e }
  }
  const toFill = d ? d.items.filter(i => i.source !== 'fixed' && i.kind !== 'chart_label' && i.kind !== 'table_column') : []
  const n = (f: (i: DocItem) => boolean) => toFill.filter(f).length
  const computed = n(i => i.source === 'computed' && i.status === 'filled')
  const answered = n(i => i.source === 'input' && i.status === 'filled')
  const missing = d?.missing.length ?? 0
  const filled = toFill.length ? ((computed + answered) / toFill.length) * 100 : 0
  const value = (id: string) => d?.items.find(i => i.id === id)?.value
  const sectors = (value('q_proportion.sectors') as { sectors?: { sector: string; pct: number }[] } | undefined)?.sectors ?? []
  const graph = (value('chart_tax_incl') as { graph?: Record<string, { aligned: number | null; fossil_gas: number | null; nuclear: number | null }> } | undefined)?.graph
  const plan = d?.items.find(i => i.kind === 'chart' && i.source === 'input' && i.value?.values)
  const unmapped = d ? Object.keys(d.unmapped) : []

  const about = d && {
    title: d.title, sections: [
      { heading: HEADING.shows, body: `The fund's ${DOCUMENT[doc].toLowerCase()} disclosure, filled from its holdings and your answers. The template itself opens item by item, as the Regulation prints it.` },
      { heading: 'Legal basis', body: d.citation },
      ...(d.interpretations.length ? [{ heading: 'How the text is read', body: <ul className="list-disc pl-4 space-y-1">{d.interpretations.map((i, k) => <li key={k}>{i.reading} <span className="text-[var(--color-faint)]">— {i.declared_by}</span></li>)}</ul> }] : []),
    ],
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <SectionHead icon={FileText}>Product disclosures</SectionHead>
          {about && <InfoButton compact details={about} />}
        </div>
        <div className="flex rounded border border-[var(--color-line-2)] overflow-hidden" role="group" aria-label="Document">
          {(Object.keys(DOCUMENT) as Kind[]).map(k => (
            <button key={k} onClick={() => setDoc(k)} aria-pressed={doc === k}
              className={`text-[12px] px-2.5 py-1 ${doc === k ? 'bg-[var(--color-line-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>{DOCUMENT[k]}</button>
          ))}
        </div>
      </div>
      {q.isLoading && <div className="px-5 py-6 text-[12.5px] text-[var(--color-faint)]">Reading the template…</div>}
      {q.isError && <div className="px-5 py-6"><MessageLine m={{ label: apiMessage(q.error, 'This document does not apply to the fund.'), detail: apiDetail(q.error) }} className="text-[12.5px] text-[var(--color-mute)]" /></div>}
      {d && (
        <div className="p-5 space-y-5">
          <div className="flex flex-wrap items-center gap-5">
            <Ring value={filled} tone={missing ? TONE.warn : TONE.good} />
            <div className="flex-1 min-w-[220px] space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                {missing ? <StatusChip tone="warn" label={`${missing} to answer`} /> : <StatusChip tone="good" label="Every item answered" />}
                {d.period_end && <StatusChip tone="neutral" label={`Period ending ${fmtDate(d.period_end)}`} />}
                {unmapped.length > 0 && <span className="inline-flex items-center gap-1"><StatusChip tone="neutral" label={`${unmapped.length} earlier answer${unmapped.length === 1 ? '' : 's'} kept`} />
                  <InfoButton compact details={{ title: 'Earlier answers kept', sections: [{ heading: HEADING.shows, body: `Answers from the earlier form that this template does not ask: ${unmapped.map(k => k.replace(/^(legacy|website)\./, '').replace(/_/g, ' ')).join(', ')}.` }, { heading: HEADING.read, body: 'Website disclosures are published on the fund\'s web page, not in this document.' }] }} /></span>}
              </div>
              <Stack parts={[{ n: computed, tone: TONE.good, label: 'computed' }, { n: answered, tone: TONE.sky, label: 'answered' }, { n: missing, tone: TONE.warn, label: 'to answer' }]} />
            </div>
          </div>

          {/* the figures the document carries */}
          {(graph || sectors.length > 0 || plan) && (
            <div className="grid gap-4 md:grid-cols-2">
              {graph && (
                <div className="rounded-lg border border-[var(--color-line)] p-3">
                  <div className="text-[12.5px] text-[var(--color-ink)] mb-2">Taxonomy-aligned investments</div>
                  <div className="space-y-2">
                    {Object.entries(graph).map(([b, g]) => (
                      <div key={b} className="grid grid-cols-[4rem_1fr_3rem] items-center gap-2 text-[11.5px]">
                        <span className="text-[var(--color-mute)]">{BASIS[b] ?? b}</span>
                        <span className="flex h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-panel-2)' }}>
                          {g.fossil_gas ? <span style={{ width: `${g.fossil_gas}%`, background: '#e8b24c' }} /> : null}
                          {g.nuclear ? <span style={{ width: `${g.nuclear}%`, background: '#a78bfa' }} /> : null}
                          {g.aligned != null && <span style={{ width: `${Math.max(0, g.aligned - (g.fossil_gas ?? 0) - (g.nuclear ?? 0))}%`, background: TONE.good }} />}
                        </span>
                        <span className="text-right tabular-nums text-[var(--color-ink)]">{pct(g.aligned, 1)}</span>
                      </div>))}
                  </div>
                </div>)}
              {sectors.length > 0 && (
                <div className="rounded-lg border border-[var(--color-line)] p-3">
                  <div className="text-[12.5px] text-[var(--color-ink)] mb-2">Largest sectors</div>
                  <div className="space-y-1.5">
                    {sectors.slice(0, 5).map(x => (
                      <div key={x.sector} className="grid grid-cols-[1fr_6rem_3rem] items-center gap-2 text-[11.5px]">
                        <span className="text-[var(--color-mute)] truncate">{sectorName(x.sector)}</span>
                        <span className="h-1.5 rounded-full" style={{ width: `${Math.max(3, (x.pct / Math.max(1, sectors[0].pct)) * 100)}%`, background: 'var(--color-sky)' }} />
                        <span className="text-right tabular-nums text-[var(--color-ink)]">{pct(x.pct, 1)}</span>
                      </div>))}
                  </div>
                </div>)}
              {plan && (
                <div className="rounded-lg border border-[var(--color-line)] p-3">
                  <div className="text-[12.5px] text-[var(--color-ink)] mb-2">{doc === 'precontractual' ? 'Planned asset allocation' : 'Asset allocation'}</div>
                  <div className="space-y-1.5">
                    {Object.entries(plan.value.values as Record<string, number>).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-[1fr_6rem_3rem] items-center gap-2 text-[11.5px]">
                        <span className="text-[var(--color-mute)] truncate">{d.items.find(c => c.id === k)?.label ?? 'A category'}</span>
                        <span className="h-1.5 rounded-full" style={{ width: `${Math.max(3, v)}%`, background: 'var(--color-sky)' }} />
                        <span className="text-right tabular-nums text-[var(--color-ink)]">{pct(v, 1)}</span>
                      </div>))}
                  </div>
                </div>)}
            </div>)}

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" onClick={() => setOpen(true)}><BookOpen size={14} /> Open the template</Button>
            <Button variant="ghost" onClick={() => download(`/v1/funds/${fundId}/sfdr-documents/${doc}/annex.html`, `SFDR_${doc}_${fundName.replace(/\W+/g, '_')}.html`).catch(() => toast.error('Could not download.'))}>
              <Download size={14} /> Draft document</Button>
            <Button variant="ghost" onClick={() => setFiling(true)}><Send size={14} /> Prepare filing</Button>
          </div>
        </div>
      )}
      {open && d && (
        <SidePanel title={`${DOCUMENT[doc]} document`} wide onClose={() => setOpen(false)} about={about ?? undefined}>
          <div className="-mx-6 -mt-2"><DocumentItems items={d.items} onAnswer={answer} /></div>
        </SidePanel>)}
      {filing && <FilingPreflight framework={`sfdr_${doc}`} fund={{ fund_id: fundId, name: fundName }} onClose={() => setFiling(false)}
        onGenerated={id => { setFiling(false); nav(`/filings?filing=${id}`) }} />}
    </Card>
  )
}
