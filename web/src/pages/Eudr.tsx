import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Satellite, Building2, Ship } from 'lucide-react'
import { api } from '../lib/api'
import { pressable } from '../lib/pressable'
import { Button, Card, PageHeader, SectionHead, StatusPill } from '../components/ui'
import ReportTabs from '../components/ReportTabs'
import ValidatedUpload from '../components/ValidatedUpload'
import Shipment from '../components/eudr/Shipment'
import DeclarationCard from '../components/eudr/Declaration'
import TradeRecord from '../components/eudr/TradeRecord'
import { ReadForm, StatusForm } from '../components/eudr/EudrForms'
import { KIND_LABEL, type Movement, type Records } from '../components/eudr/types'

// EUDR (Regulation (EU) 2023/1115): one due diligence statement per shipment. The operator's records — its status, each
// plot's satellite reading, legality evidence, the risk assessment — feed the statement; the statement is a filing
// (services/eudr/filing.py), signed off with four eyes in the filings cockpit.

const BOOKS = [
  { key: 'eudr_suppliers', label: 'Suppliers' }, { key: 'eudr_customers', label: 'Customers' },
  { key: 'eudr_movements', label: 'Shipments' }, { key: 'eudr_movement_plots', label: 'Shipment plots' },
]

export default function Eudr() {
  const [entity, setEntity] = useState<string>('')                 // '' = the organisation itself
  const qs = entity ? `?entity_id=${entity}` : ''
  const rec = useQuery({ queryKey: ['eudr-records', entity], queryFn: () => api.get<Records>(`/v1/eudr/records${qs}`) })
  const mv = useQuery({ queryKey: ['eudr-movements', entity], queryFn: () => api.get<{ movements: Movement[] }>(`/v1/eudr/movements${qs}`) })
  const [sel, setSel] = useState<string | null>(null)
  const [form, setForm] = useState<null | 'status' | 'read'>(null)
  const [book, setBook] = useState(BOOKS[2].key)
  const reload = () => { rec.refetch(); mv.refetch() }

  if (rec.isLoading || mv.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">loading EUDR…</div>
  if (!rec.data || !mv.data) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">We couldn't load this data. Please retry.</div>
  const r = rec.data, t = r.readings_tally, moves = mv.data.movements
  const unread = r.plots.filter(p => !p.reading)
  const current = moves.find(m => m.movement_id === sel)

  return (
    <div className="fadeup space-y-6">
      <ReportTabs />
      <PageHeader eyebrow="Agriculture · EUDR" title="EUDR due diligence statements"
        lead="One statement per shipment, prepared from your records once every check passes, signed off with four eyes, then the reference number and what happens to it in the information system." />

      {r.entities.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className={'mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]'}>Undertaking</span>
          <select aria-label="Undertaking" value={entity} onChange={e => { setEntity(e.target.value); setSel(null) }}
            className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)]">
            <option value="">The organisation</option>
            {r.entities.map(e => <option key={e.entity_id} value={e.entity_id}>{e.name}{e.country ? ` · ${e.country}` : ''}</option>)}
          </select>
          <span className="text-[11.5px] text-[var(--color-faint)]">Status, shipments and the declaration belong to one undertaking.</span>
        </div>)}

      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <SectionHead icon={Building2}>Your undertaking</SectionHead>
            <Button variant="ghost" onClick={() => setForm('status')}>{r.status ? 'Restate' : 'State status'}</Button>
          </div>
          {r.status ? (
            <div className="text-[12.5px] text-[var(--color-mute)] space-y-0.5">
              <div><span className="text-[var(--color-ink)]">{r.status.size_class}</span> · {r.status.country} · in force from {r.status.effective_from}</div>
              <div>{r.status.address}</div>
              <div>{r.status.eori ? `EORI ${r.status.eori}` : 'no EORI stated'}</div>
            </div>
          ) : <p className="text-[12.5px] text-[var(--color-warn)]">Not stated for {r.on}. Every statement needs it (Annex II point 1).</p>}
          {r.pending.filter(x => x.request_type === 'eudr.status').map(x => (
            <p key={x.request_id} className="text-[12px] text-[var(--color-sky)] mt-2">Waiting for a second person: {x.title} — <Link to="/approvals" className="underline">Approvals</Link></p>))}
        </Card>
        <Card className="p-5">
          <div className="flex items-start justify-between gap-3 mb-2">
            <SectionHead icon={Satellite}>Plot readings</SectionHead>
            <Button variant="ghost" onClick={() => setForm('read')} disabled={r.plots.length === 0}>{unread.length ? `Read ${unread.length} unread` : 'Read again'}</Button>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-[var(--color-mute)]">
            <span><b className="text-[var(--color-ink)]">{t.plots}</b> EUDR plots</span>
            <span><b className="text-[var(--color-good)]">{t.no_loss_detected}</b> no loss read</span>
            <span><b className="text-[var(--color-warn)]">{t.loss_after_cutoff}</b> loss after 2020</span>
            <span><b>{t.not_assessable}</b> not assessable</span>
            <span><b>{t.unread}</b> not read</span>
          </div>
          <p className="text-[11.5px] text-[var(--color-faint)] mt-2">A reading is what the forest dataset shows inside the plot after 31 December 2020 — a risk the assessment weighs (Art. 10), never a verdict.</p>
        </Card>
      </div>

      <Card className="p-5">
        <SectionHead icon={Ship} hint={`${moves.length} on file`} className="mb-3">Shipments</SectionHead>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="font-normal py-2 pr-3">Shipment</th><th className="font-normal pr-3">Kind</th><th className="font-normal pr-3">Date</th>
              <th className="font-normal pr-3">HS</th><th className="font-normal pr-3">Plots</th><th className="font-normal pr-3">Supplier</th><th className="font-normal">Statement</th>
            </tr></thead>
            <tbody>{moves.map(m => {
              const f = m.filings[0]
              return (
                <tr key={m.movement_id} {...pressable(() => setSel(m.movement_id === sel ? null : m.movement_id), { row: true, expanded: m.movement_id === sel })}
                  className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] ${m.movement_id === sel ? 'bg-[var(--color-bg-2)]' : ''}`}>
                  <td className="py-2 pr-3 text-[var(--color-ink)]">{m.external_ref ?? m.movement_id.slice(0, 8)}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{KIND_LABEL[m.kind] ?? m.kind}</td>
                  <td className="pr-3 mono text-[12px] text-[var(--color-mute)]">{m.planned_on}</td>
                  <td className="pr-3 mono text-[12px] text-[var(--color-mute)]">{m.hs_code}</td>
                  <td className="pr-3 mono text-[12px] text-[var(--color-mute)]">{m.n_plots}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{m.supplier ?? '—'}</td>
                  <td className="text-[12px] text-[var(--color-mute)]">{f ? `${f.status}${f.reference_number ? ` · ${f.reference_number}` : ''}` : 'none yet'}</td>
                </tr>)
            })}
              {moves.length === 0 && <tr><td colSpan={7} className="py-6 text-center text-[var(--color-faint)]">No shipments on file — upload them below.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {current && (current.actor_role === 'downstream_operator' || current.actor_role === 'trader'
        ? <TradeRecord key={current.movement_id} m={current} />
        : <Shipment key={current.movement_id} m={current} rec={r} onChanged={reload} />)}

      {r.status && (r.status.size_class === 'micro' || r.status.size_class === 'small') && <DeclarationCard key={entity} entityId={entity || null} />}

      <Card className="p-5">
        <SectionHead className="mb-3">Upload your EUDR books</SectionHead>
        <div className="flex gap-1 flex-wrap mb-3">{BOOKS.map(b => (
          <button key={b.key} type="button" onClick={() => setBook(b.key)}
            className={`px-3 py-1.5 rounded-lg text-[12.5px] border ${book === b.key ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{b.label}</button>))}
        </div>
        <ValidatedUpload key={book} dropLabel={`${BOOKS.find(b => b.key === book)!.label.toLowerCase()} file`} onDone={reload}
          intro={<>Every row is checked <b className="text-[var(--color-ink)]">before</b> anything is saved; a failed check needs a second person to approve the import. Plots themselves arrive through Sourcing.</>}
          endpoints={{ validate: `/v1/eudr/intake/${book}/validate`, upload: `/v1/eudr/intake/${book}/upload`, template: `/v1/eudr/intake/${book}/template.xlsx`, templateFile: `tellumen_${book}_template.xlsx` }}
          renderDone={res => <>{Number(res.n_uploaded) || 0} row{Number(res.n_uploaded) === 1 ? '' : 's'} imported.</>} />
      </Card>

      {r.plots.length > 0 && (
        <Card className="p-5">
          <SectionHead className="mb-3">EUDR plots</SectionHead>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-1.5 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th><th className="font-normal pr-3">Country</th><th className="font-normal pr-3">Geometry</th><th className="font-normal">Reading</th>
              </tr></thead>
              <tbody>{r.plots.map(p => (
                <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                  <td className="py-1.5 pr-3">{p.plot_name ?? p.external_ref ?? p.plot_id.slice(0, 8)}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 mono text-[var(--color-mute)]">{p.country ?? '—'}</td>
                  <td className="pr-3 mono text-[var(--color-mute)]">{p.has_polygon ? 'polygon' : 'point'}{p.area_ha != null ? ` · ${p.area_ha} ha` : ''}</td>
                  <td><StatusPill status={p.reading?.outcome ?? 'unread'} />{p.reading?.outcome === 'loss_after_cutoff' && <span className="mono text-[11px] text-[var(--color-mute)] ml-2">first {p.reading.first_loss_year} · {p.reading.loss_ha} ha</span>}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
      )}

      {form === 'status' && <StatusForm rec={r} onClose={() => setForm(null)} onDone={() => { setForm(null); reload() }} />}
      {form === 'read' && <ReadForm plots={unread.length ? unread : r.plots} onClose={() => setForm(null)} onDone={() => { setForm(null); reload() }} />}
    </div>
  )
}
