import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Building2, FileCheck2, Satellite, Ship, Trees, Upload } from 'lucide-react'
import { api } from '../lib/api'
import { pressable } from '../lib/pressable'
import { Button, Card, PageHeader, SectionHead } from '../components/ui'
import { HEADING, InfoButton } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import ReportTabs from '../components/ReportTabs'
import ValidatedUpload from '../components/ValidatedUpload'
import Shipment from '../components/eudr/Shipment'
import DeclarationCard from '../components/eudr/Declaration'
import TradeRecord from '../components/eudr/TradeRecord'
import { ReadForm, StatusForm } from '../components/eudr/EudrForms'
import { ReadingChip, RefusalLine, Segments } from '../components/eudr/parts'
import { OUTCOME_TONE, STATEMENT_TONE, TONE, refusal, statementWord } from '../components/eudr/words'
import { fmtDate, named, type Movement, type Records } from '../components/eudr/types'

// EUDR (Regulation (EU) 2023/1115): one due diligence statement per shipment. The operator's records — its status, each
// plot's satellite reading, legality evidence, the risk assessment — feed the statement; the statement is a filing
// (services/eudr/filing.py), signed off with four eyes in the filings register. The page leads with where things stand
// (the undertaking, the readings, the statements), lists the shipments — each opens in a drawer — and the plots; the
// platform gives readings and checks, never a conclusion on compliance: the undertaking concludes.

const BOOKS = ['eudr_suppliers', 'eudr_customers', 'eudr_movements', 'eudr_movement_plots']
const FILES_NO_STATEMENT = new Set(['downstream_operator', 'trader'])
const PREPARING = new Set(['draft', 'returned', 'in_review', 'approved', 'attested'])

const ABOUT = [
  { heading: HEADING.shows, body: 'Your shipments of products the EU Deforestation Regulation covers, the due diligence statement each needs, and the records it rests on: your undertaking’s status, each plot’s forest reading, legality evidence and your risk assessment. A micro or small primary operator makes one simplified declaration instead; a downstream operator or trader keeps a record of each shipment.' },
  { heading: HEADING.read, body: 'Select a shipment for its checks, what its statement rests on and where it stands. A statement is prepared once no check blocks it, signed off with four eyes in the filings register, and then you record the reference number the information system made available.' },
  { heading: HEADING.sources, body: 'Your books uploaded here (suppliers, customers, shipments and their plots); plots from Sourcing; the forest reading from Global Forest Change tree-cover loss; the list of covered products and the country classification as published in the Official Journal of the EU.' },
  { heading: HEADING.limits, body: 'A forest reading shows tree-cover loss inside a plot, not land use or tree height: it is a risk your assessment weighs. The platform does not conclude whether a product complies; you do, in your risk assessment. Submission to the information system is recorded here, not sent from here.' },
  { heading: 'Legal basis', body: 'Regulation (EU) 2023/1115 as amended; Implementing Regulation (EU) 2024/3084 (the information system); Implementing Regulation (EU) 2025/1093 (the country classification).' },
]

export default function Eudr() {
  const [entity, setEntity] = useState<string>('')                 // '' = the organisation itself
  const qs = entity ? `?entity_id=${entity}` : ''
  const rec = useQuery({ queryKey: ['eudr-records', entity], queryFn: () => api.get<Records>(`/v1/eudr/records${qs}`) })
  const mv = useQuery({ queryKey: ['eudr-movements', entity], queryFn: () => api.get<{ movements: Movement[] }>(`/v1/eudr/movements${qs}`) })
  const [sel, setSel] = useState<string | null>(null)
  const [form, setForm] = useState<null | 'status' | 'read'>(null)
  const [book, setBook] = useState(BOOKS[2])
  const reload = () => { rec.refetch(); mv.refetch() }

  if (rec.isLoading || mv.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">Loading…</div>
  if (!rec.data || !mv.data) return <div className="h-[60vh] grid place-items-center"><RefusalLine m={refusal(rec.error ?? mv.error, 'This page could not be loaded')} /></div>
  const r = rec.data, t = r.readings_tally, moves = mv.data.movements, names = r.names
  const unread = r.plots.filter(p => !p.reading)
  const current = moves.find(m => m.movement_id === sel)
  const pendingStatus = r.pending.filter(x => x.request_type === 'eudr.status')

  // where each shipment's newest statement stands
  const stage = (m: Movement) => FILES_NO_STATEMENT.has(m.actor_role) ? 'record' : m.filings[0]?.status ?? 'none'
  const count = (f: (s: string) => boolean) => moves.filter(m => f(stage(m))).length
  const statementParts = [
    { n: count(s => s === 'accepted'), c: TONE.good, l: 'reference received' },
    { n: count(s => s === 'submitted'), c: TONE.info, l: 'submitted' },
    { n: count(s => PREPARING.has(s)), c: TONE.warn, l: 'in preparation' },
    { n: count(s => s === 'none'), c: TONE.none, l: 'no statement yet' },
    { n: count(s => s === 'rejected' || s === 'withdrawn' || s === 'superseded'), c: TONE.bad, l: 'rejected or withdrawn' },
    { n: count(s => s === 'record'), c: TONE.slate, l: 'keep a record instead' },
  ]

  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <PageHeader eyebrow="Agriculture · EUDR" title="EUDR due diligence" lead="One statement per shipment, prepared from your records." about={ABOUT} />

      {r.entities.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="eudr-undertaking" className="text-[12px] text-[var(--color-mute)]">Undertaking</label>
          <select id="eudr-undertaking" value={entity} onChange={e => { setEntity(e.target.value); setSel(null) }}
            className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)]">
            <option value="">The organisation</option>
            {r.entities.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}{e.country ? ` · ${e.country}` : ''}</option>)}
          </select>
          <InfoButton compact details={{ title: 'Undertaking', sections: [{ heading: HEADING.shows, body: 'The status, the shipments and the simplified declaration belong to one undertaking: the organisation itself or one of its legal entities.' }] }} />
        </div>)}

      <div className="grid md:grid-cols-3 gap-4">
        <Card className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <SectionHead icon={Building2}>Your undertaking</SectionHead>
            <InfoButton compact details={{ title: 'Your undertaking', sections: [
              { heading: HEADING.shows, body: 'Your undertaking’s status in force today: its size, country, address and EORI number. Every statement names the operator from it, and the size decides when the rules apply to you.' },
              { heading: HEADING.read, body: 'A restated status takes effect from the date you give, once a second person approves it.' },
              ...(r.status ? [{ heading: 'Address', body: r.status.address }] : []),
              { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Annex II point 1 and Article 38.' }] }} />
          </div>
          {r.status ? (
            <div className="flex flex-wrap gap-1.5">
              <StatusChip tone="neutral" label={named(names, 'size', r.status.size_class)} />
              <StatusChip tone="neutral" label={r.status.country} />
              <StatusChip tone={r.status.eori ? 'good' : 'neutral'} label={r.status.eori ? `EORI ${r.status.eori}` : 'No EORI number'} />
              <StatusChip tone="neutral" label={`From ${fmtDate(r.status.effective_from)}`} />
            </div>
          ) : <StatusChip tone="warn" label="Not stated" />}
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={() => setForm('status')}>{r.status ? 'Restate' : 'State status'}</Button>
            {pendingStatus.length > 0 && <Link to="/approvals"><StatusChip tone="warn" label={`${pendingStatus.length} awaiting approval`} /></Link>}
          </div>
        </Card>

        <Card className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <SectionHead icon={Satellite}>Forest readings</SectionHead>
            <InfoButton compact details={{ title: 'Forest readings', sections: [
              { heading: HEADING.shows, body: 'For each plot of a covered commodity, what the forest dataset shows inside it after 31 December 2020: tree-cover loss, no loss, or why it could not be read.' },
              { heading: HEADING.read, body: 'A reading is a risk your assessment weighs, never a conclusion: tree-cover loss does not show the land use or tree height that the definitions of forest and deforestation rest on. A plot moved or redrawn since it was read needs a new reading.' },
              { heading: HEADING.sources, body: 'Global Forest Change tree-cover loss (Hansen et al.), read inside each plot as last drawn.' },
              { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Articles 2(13), 9(1)(g) and 10.' }] }} />
          </div>
          <Segments parts={(['no_loss_detected', 'loss_after_cutoff', 'not_assessable', 'unread'] as const).map(k => ({ n: t[k], c: OUTCOME_TONE[k], l: named(names, 'outcome', k).toLowerCase() }))} empty="No plots of covered commodities yet." />
          <Button variant="ghost" onClick={() => setForm('read')} disabled={r.plots.length === 0}>{unread.length ? `Read ${unread.length} unread` : 'Read again'}</Button>
        </Card>

        <Card className="p-5 space-y-3">
          <div className="flex items-center gap-2">
            <SectionHead icon={FileCheck2}>Statements</SectionHead>
            <InfoButton compact details={{ title: 'Statements', sections: [
              { heading: HEADING.shows, body: 'Where each shipment’s newest due diligence statement stands. A downstream operator or trader files none: it keeps a record of the shipment instead.' },
              { heading: HEADING.read, body: 'Prepared statements are signed off in the filings register; once submitted, record the reference number the information system made available.' }] }} />
          </div>
          <Segments parts={statementParts} label={`${moves.length} shipments`} empty="No shipments on file yet." />
          <Link to="/filings" className="inline-block text-[12.5px] text-[var(--color-sky)] hover:underline">Open the filings register</Link>
        </Card>
      </div>

      <Card className="p-5">
        <SectionHead icon={Ship} hint={`${moves.length} on file`} className="mb-3">Shipments</SectionHead>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
              <th className="font-normal py-2 pr-3">Shipment</th><th className="font-normal pr-3">Movement</th><th className="font-normal pr-3">Date</th>
              <th className="font-normal pr-3">Product</th><th className="font-normal pr-3">Plots</th><th className="font-normal pr-3">Supplier</th><th className="font-normal">Statement</th>
            </tr></thead>
            <tbody>{moves.map(m => {
              const s = stage(m)
              return (
                <tr key={m.movement_id} {...pressable(() => setSel(m.movement_id), { row: true })}
                  className="border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)]">
                  <td className="py-2 pr-3 text-[var(--color-ink)]">{m.external_ref ?? '—'}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{named(names, 'kind', m.kind)}</td>
                  <td className="pr-3 text-[var(--color-mute)] whitespace-nowrap tabular-nums">{fmtDate(m.planned_on)}</td>
                  <td className="pr-3 text-[var(--color-mute)] whitespace-nowrap">HS {m.hs_code}</td>
                  <td className="pr-3 text-[var(--color-mute)] tabular-nums">{m.n_plots}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{m.supplier ?? '—'}</td>
                  <td>{s === 'record' ? <StatusChip tone="neutral" label="Keeps a record" />
                    : s === 'none' ? <StatusChip tone="neutral" label="None yet" />
                    : <StatusChip tone={STATEMENT_TONE[s]} label={statementWord(s)} />}</td>
                </tr>)
            })}
              {moves.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-[var(--color-faint)]">No shipments on file — upload them below.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {r.status && (r.status.size_class === 'micro' || r.status.size_class === 'small') && <DeclarationCard key={entity} entityId={entity || null} names={names} />}

      {r.plots.length > 0 && (
        <Card className="p-5">
          <SectionHead icon={Trees} hint={`${r.plots.length} of covered commodities`} className="mb-3">Plots</SectionHead>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
                <th className="font-normal py-1.5 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th><th className="font-normal pr-3">Country</th><th className="font-normal pr-3">Area</th><th className="font-normal">Forest reading</th>
              </tr></thead>
              <tbody>{r.plots.map(p => (
                <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                  <td className="py-1.5 pr-3"><Link to={`/detail/plot/${p.plot_id}`} className="hover:text-[var(--color-sky)] hover:underline">{p.plot_name ?? p.external_ref ?? '—'}</Link></td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.country ?? '—'}</td>
                  <td className="pr-3 text-[var(--color-mute)] whitespace-nowrap">{p.area_ha != null ? `${p.area_ha.toLocaleString('en-GB')} ha` : '—'} · {p.has_polygon ? 'boundary' : 'point'}</td>
                  <td><ReadingChip r={p.reading} names={names} /></td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
      )}

      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3">
          <SectionHead icon={Upload}>Upload your EUDR books</SectionHead>
          <InfoButton compact details={{ title: 'Upload your EUDR books', sections: [
            { heading: HEADING.shows, body: 'Your suppliers, customers, shipments and the plots each shipment came from, from a file in the template or your own layout.' },
            { heading: HEADING.read, body: 'Every row is checked before anything is saved. An import with a failed check needs a second person to approve it. The plots themselves arrive through Sourcing.' }] }} />
        </div>
        <div className="flex gap-1 flex-wrap mb-3">{BOOKS.map(b => (
          <button key={b} type="button" onClick={() => setBook(b)} aria-pressed={book === b}
            className={`px-3 py-1.5 rounded-lg text-[12.5px] border ${book === b ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{named(names, 'book', b)}</button>))}
        </div>
        <ValidatedUpload key={book} dropLabel={`${named(names, 'book', book).toLowerCase()} file`} onDone={reload}
          intro={<>Checked row by row <b className="text-[var(--color-ink)]">before</b> anything is saved.</>}
          endpoints={{ validate: `/v1/eudr/intake/${book}/validate`, upload: `/v1/eudr/intake/${book}/upload`, template: `/v1/eudr/intake/${book}/template.xlsx`, templateFile: `tellumen_${book}_template.xlsx` }}
          renderDone={res => <>{Number(res.n_uploaded) || 0} row{Number(res.n_uploaded) === 1 ? '' : 's'} imported.</>} />
      </Card>

      {current && (FILES_NO_STATEMENT.has(current.actor_role)
        ? <TradeRecord key={current.movement_id} m={current} names={names} onClose={() => setSel(null)} />
        : <Shipment key={current.movement_id} m={current} rec={r} onChanged={reload} onClose={() => setSel(null)} />)}
      {form === 'status' && <StatusForm rec={r} onClose={() => setForm(null)} onDone={() => { setForm(null); reload() }} />}
      {form === 'read' && <ReadForm plots={unread.length ? unread : r.plots} onClose={() => setForm(null)} onDone={() => { setForm(null); reload() }} />}
    </div>
  )
}
