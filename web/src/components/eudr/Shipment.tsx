import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FileCheck2 } from 'lucide-react'
import { Button, SectionHead } from '../ui'
import { HEADING, InfoButton, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Concerns } from './TradeRecord'
import { EvidenceForm, EventForm, ReferenceForm, RiskForm, ScopeForm, WithdrawForm } from './EudrForms'
import { Checks, ReadingChip, RefusalLine, Stepper, Tile, Timeline, WindowBar } from './parts'
import { STATEMENT_TONE, linkBtn, refusal, statementWord, worst, type Refusal } from './words'
import { ShipmentDrawer } from './ShipmentDrawer'
import { fmtDate, kg, named, type DdsEvent, type Movement, type Names, type Records, type Statement, type StatementFiling, type Window } from './types'

// One shipment of an operator: the checks its statement runs (each with its meaning and legal basis one click away),
// what the statement rests on, the plots with their readings, and its statements — prepared here, signed off in the
// filings register (four eyes, attestation, submission), then the reference number, the window to amend or withdraw
// and what happened to it in the information system.

type Open = null | 'evidence' | 'risk' | 'scope'

export default function Shipment({ m, rec, onChanged, onClose }: { m: Movement; rec: Records; onChanged: () => void; onClose: () => void }) {
  const st = useQuery({ queryKey: ['eudr-statement', m.movement_id], queryFn: () => api.get<Statement>(`/v1/eudr/movements/${m.movement_id}/statement`) })
  const [open, setOpen] = useState<Open>(null)
  const [err, setErr] = useState<Refusal>(null)
  const names = rec.names
  const refresh = () => { setOpen(null); st.refetch(); onChanged() }
  const prepare = useMutation({
    mutationFn: () => api.post<{ filing_id: string }>(`/v1/eudr/movements/${m.movement_id}/filing`, {}),
    onSuccess: () => { setErr(null); toast.success('Statement prepared — sign it off in the filings register.'); refresh() },
    onError: (e) => setErr(refusal(e, 'Could not prepare the statement')),
  })
  const s = st.data
  const blocking = s ? s.checks.filter(c => !c.passed && c.severity === 'blocking').length : 0
  const live = m.filings.find(f => !['withdrawn', 'superseded', 'rejected'].includes(f.status))
  const pendingRisk = rec.pending.some(x => x.request_type === 'eudr.risk' && x.movement_id === m.movement_id)

  return (
    <ShipmentDrawer m={m} names={names} onClose={onClose}
      chip={live ? <StatusChip tone={STATEMENT_TONE[live.status]} label={statementWord(live.status)} /> : <StatusChip tone="neutral" label="No statement yet" />}
      actions={!live && s && (
        <Button onClick={() => prepare.mutate()} disabled={prepare.isPending || blocking > 0}>
          <FileCheck2 size={14} /> {prepare.isPending ? 'Preparing…' : 'Prepare statement'}
        </Button>)}
      product={s ? productDetails(s) : undefined}>
      <RefusalLine m={err} />
      {st.isError ? <RefusalLine m={refusal(st.error, 'Could not load the statement')} />
        : !s ? <div className="text-[13px] text-[var(--color-faint)]">Loading…</div> : <>
          <Checks checks={s.checks} about="Every check the statement runs before it can be prepared, on what your records say for this shipment today. The same checks run again on the frozen statement in the filings register." />

          <section className="space-y-2">
            <SectionHead>What it rests on</SectionHead>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              <Tile title="Your undertaking" state={worst(s.checks, 'annex_ii_1', 'application', 'filer')}
                value={s.annex_ii['1'].name ?? '—'} details={operatorDetails(s)} />
              <Tile title="Product scope" state={worst(s.checks, 'scope')} value={s.scope.msg.label}
                details={scopeDetails(s)}
                action={s.scope.in_scope === null && <button type="button" className={linkBtn} onClick={() => setOpen('scope')}>State scope</button>} />
              <Tile title="Supplier and customer" state={worst(s.checks, 'supplier', 'customer')}
                value={<>{s.art9.supplier?.name ?? 'No supplier on file'}<span className="block text-[11.5px] text-[var(--color-mute)]">{s.art9.customer?.name ? `To ${s.art9.customer.name}` : 'No customer yet'}</span></>}
                details={partyDetails(s)} />
              <Tile title="Plots" state={worst(s.checks, 'annex_ii_3', 'country', 'decimals', 'polygon', 'area', 'reading')}
                value={`${s.plots.length} plot${s.plots.length === 1 ? '' : 's'}${s.annex_ii['3'].countries.length ? ` · ${s.annex_ii['3'].countries.join(', ')}` : ''}`} />
              <Tile title="Legality evidence" state={worst(s.checks, 'legality')}
                value={s.legality_evidence.length ? `${s.legality_evidence.length} document${s.legality_evidence.length === 1 ? '' : 's'}` : 'None on file'}
                details={evidenceDetails(s, names)}
                action={<button type="button" className={linkBtn} onClick={() => setOpen('evidence')}>Add evidence</button>} />
              <Tile title="Risk assessment" state={pendingRisk && !s.risk_assessment ? 'warn' : worst(s.checks, 'risk_assessment', 'simplified', 'risk_review', 'informed')}
                value={s.risk_assessment ? named(names, 'conclusion', s.risk_assessment.conclusion) : pendingRisk ? 'Awaiting approval' : 'None approved'}
                details={riskDetails(s, names)}
                action={<button type="button" className={linkBtn} onClick={() => setOpen('risk')}>{s.risk_assessment ? 'State again' : 'State it'}</button>} />
            </div>
          </section>

          <section className="space-y-2">
            <SectionHead>Plots</SectionHead>
            <div className="overflow-x-auto">
              <table className="w-full text-[12.5px]">
                <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
                  <th className="font-normal py-1.5 pr-3">Plot</th><th className="font-normal pr-3">Country</th>
                  <th className="font-normal pr-3">Area</th><th className="font-normal">Forest reading</th>
                </tr></thead>
                <tbody>{s.plots.map(p => (
                  <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                    <td className="py-1.5 pr-3"><Link to={`/detail/plot/${p.plot_id}`} className="hover:text-[var(--color-sky)] hover:underline">{p.plot_name ?? p.external_ref ?? '—'}</Link></td>
                    <td className="pr-3 whitespace-nowrap">{p.country ?? '—'}{p.country_risk && <span className="ml-1.5 text-[11px] text-[var(--color-mute)]">{named(names, 'country_risk', p.country_risk)}</span>}</td>
                    <td className="pr-3 whitespace-nowrap text-[var(--color-mute)]">{p.area_ha != null ? `${p.area_ha.toLocaleString('en-GB')} ha` : '—'} · {p.has_polygon ? 'boundary' : 'point'}</td>
                    <td><ReadingChip r={p.reading} names={names} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
          </section>

          <section className="space-y-2">
            <SectionHead>Statements</SectionHead>
            {m.filings.length === 0
              ? <p className="text-[12.5px] text-[var(--color-mute)]">{blocking ? 'Clear the blocking checks, then prepare it.' : 'Ready to prepare.'}</p>
              : <div className="space-y-2.5">{m.filings.map(f => <FilingRow key={f.filing_id} f={f} names={names} onChanged={refresh} />)}</div>}
          </section>

          <Concerns movementId={m.movement_id} concerns={s.concerns ?? []} names={names} onChanged={() => st.refetch()} />

          {open === 'evidence' && <EvidenceForm rec={rec} movementId={m.movement_id} plots={s.plots} onClose={() => setOpen(null)} onDone={refresh} />}
          {open === 'risk' && <RiskForm rec={rec} movementId={m.movement_id} onClose={() => setOpen(null)} onDone={refresh} />}
          {open === 'scope' && <ScopeForm movementId={m.movement_id} scope={s.scope.msg} onClose={() => setOpen(null)} onDone={refresh} />}
        </>}
    </ShipmentDrawer>
  )
}

// ── what each tile opens ──

function productDetails(s: Statement): DetailSection[] {
  const a = s.annex_ii['2'], q = a.quantity
  return [
    { heading: 'Product', body: [a.description, a.trade_name].filter(Boolean).join(' · ') || '—' },
    { heading: 'Quantity', body: [typeof q.net_mass_kg === 'number' ? `${kg(q.net_mass_kg)} net${typeof q.mass_deviation_pct === 'number' ? ` ± ${q.mass_deviation_pct} %` : ''}` : null,
      typeof q.volume_m3 === 'number' ? `${q.volume_m3} m³` : null, typeof q.items_count === 'number' ? `${q.items_count} items` : null].filter(Boolean).join(' · ') || '—' },
    ...(a.scientific_names.length ? [{ heading: 'Species', body: a.scientific_names.join(', ') }] : []),
  ]
}
function operatorDetails(s: Statement): DetailSection[] {
  const o = s.annex_ii['1']
  return [
    { heading: HEADING.shows, body: 'The operator the statement names: the undertaking the shipment is booked to, as its status in force on the shipment date states it.' },
    { heading: 'Address', body: o.address ?? 'Not stated' },
    { heading: 'Country', body: o.country ?? 'Not stated' },
    { heading: 'EORI number', body: o.eori ?? (s.movement.customs_flow ? 'Not stated — required, the goods go through customs' : 'Not stated') },
  ]
}
function scopeDetails(s: Statement): DetailSection[] {
  const d = s.scope.msg.detail ?? {}
  return [
    ...(['what', 'why', 'next'] as const).filter(k => d[k]).map(k => ({ heading: k === 'what' ? HEADING.shows : k === 'why' ? 'Why' : 'What you can do', body: d[k] })),
    ...(s.movement.scope_in != null ? [{ heading: 'Your statement', body: `${s.movement.scope_in ? 'Covered' : 'Not covered'}: ${s.movement.scope_basis ?? ''}` }] : []),
    { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Article 2(2) and Annex I, in the version in force on the shipment date.' },
  ]
}
function partyDetails(s: Statement): DetailSection[] {
  const sup = s.art9.supplier, cus = s.art9.customer
  return [
    { heading: 'Supplier', body: sup ? [sup.name, sup.address, sup.email].filter(Boolean).join(' · ') : 'None on file' },
    { heading: 'Customer', body: cus ? [cus.name, cus.address, cus.email].filter(Boolean).join(' · ') : 'None on file' },
    { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Article 9(1)(e) and (f).' },
  ]
}
function evidenceDetails(s: Statement, names: Names): DetailSection[] {
  return [
    { heading: HEADING.shows, body: 'The legality evidence in force on the shipment date for its plots, its supplier and the shipment itself.' },
    ...s.legality_evidence.map(e => ({ heading: named(names, 'aspect', e.aspect), body: [e.document_kind, e.document_ref, e.issued_by].filter(Boolean).join(' · ') })),
    { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Articles 3(b), 9(1)(h) and 2(40).' },
  ]
}
function riskDetails(s: Statement, names: Names): DetailSection[] {
  const r = s.risk_assessment
  return [
    { heading: HEADING.shows, body: 'Your approved assessment of this shipment. Products are placed on the market or exported only when it finds no or only a negligible risk; your assessment concludes, not the platform.' },
    ...(r ? [{ heading: 'Assessment', body: `${named(names, 'path', r.path)} · ${named(names, 'conclusion', r.conclusion)} · ${fmtDate(r.recorded_at)}` },
      { heading: 'Four eyes', body: `Stated by ${r.requested_by ?? '—'}, approved by ${r.approved_by ?? '—'}` }] : []),
    { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Articles 10, 11 and 13.' },
  ]
}

// ── one statement of the shipment ──

function FilingRow({ f, names, onChanged }: { f: StatementFiling; names: Names; onChanged: () => void }) {
  const [open, setOpen] = useState<null | 'reference' | 'event' | 'withdraw'>(null)
  const [err, setErr] = useState<Refusal>(null)
  const filed = f.status === 'submitted' || f.status === 'accepted'
  const w = useQuery({ queryKey: ['eudr-window', f.filing_id, f.status], enabled: filed,
    queryFn: () => api.get<{ window: Window; events: DdsEvent[] }>(`/v1/eudr/filings/${f.filing_id}/window`) })
  const done = () => { setOpen(null); w.refetch(); onChanged() }
  const post = (path: string, ok: string) => api.post(path, {}).then(() => { setErr(null); toast.success(ok); done() })
    .catch(e => setErr(refusal(e, 'Not done')))
  const win = w.data?.window
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-4 py-3 space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={STATEMENT_TONE[f.status]} label={statementWord(f.status)} />
        {f.reference_number && <span className="text-[12px] text-[var(--color-mute)]">Reference <span className="text-[var(--color-ink)] tabular-nums">{f.reference_number}</span></span>}
        {f.verification_number && <InfoButton compact details={{ title: 'Reference and verification numbers', sections: [
          { heading: 'Reference number', body: f.reference_number ?? '—' }, { heading: 'Verification number', body: f.verification_number }] }} />}
        <div className="ml-auto flex flex-wrap gap-2 items-center">
          <Link to={`/filings?filing=${f.filing_id}`} className={linkBtn}>Open in filings</Link>
          {(f.status === 'draft' || f.status === 'returned') && <Button variant="ghost" onClick={() => post(`/v1/eudr/filings/${f.filing_id}/refresh`, 'Statement refreshed from the shipment.')}>Refresh</Button>}
          {f.status === 'submitted' && <Button onClick={() => setOpen('reference')}>Record reference</Button>}
          {filed && <Button variant="ghost" onClick={() => setOpen('event')}>Record event</Button>}
          {f.status === 'accepted' && win?.open && <>
            <Button variant="ghost" onClick={() => post(`/v1/eudr/filings/${f.filing_id}/amend`, 'Amendment prepared as a new draft.')}>Amend</Button>
            <Button variant="ghost" onClick={() => setOpen('withdraw')}>Withdraw</Button>
          </>}
        </div>
      </div>
      <Stepper status={f.status} last="Reference received" />
      {f.status === 'accepted' && win && <WindowBar w={win} />}
      <Timeline events={w.data?.events ?? []} />
      <RefusalLine m={err} />
      {open === 'reference' && <ReferenceForm filingId={f.filing_id} names={names} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'event' && <EventForm filingId={f.filing_id} status={f.status} names={names} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'withdraw' && <WithdrawForm filingId={f.filing_id} onClose={() => setOpen(null)} onDone={done} />}
    </div>
  )
}
