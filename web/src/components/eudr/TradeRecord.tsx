import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Archive, Download } from 'lucide-react'
import { Button, SectionHead } from '../ui'
import { HEADING, InfoButton, type DetailSection } from '../Details'
import { StatusChip } from '../StatusChip'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Form } from './EudrForms'
import { Checks, RefusalLine, Tile } from './parts'
import { linkBtn, refusal, useSend, worst, type Refusal } from './words'
import { ShipmentDrawer } from './ShipmentDrawer'
import { fmtDate, fmtWhen, inp, lbl, named, type Check, type Concern, type Movement, type Names } from './types'

// A downstream operator's or trader's shipment (EUDR Art. 5; E122): it files no statement. What it must hold before it
// places, makes available or exports (5(1), 5(3)), kept as a frozen record for five years from the shipment (5(4)); and,
// for every role, new information and substantiated concerns with what was done about them (Art. 4(5), 5(5)-(6)).

interface Party { name: string | null; trade_name: string | null; postal_address: string | null; email: string | null; web_address: string | null }
interface Trade {
  movement: { kind: string; on: string; actor_role: string }
  art5_3_a: { supplier: Party | null; supplier_role: string | null; references: string[] }
  art5_3_b: { customer: Party | null }
  concerns: Concern[]; keep_until: string; checks: Check[]
  kept: { record_id: string; keep_until: string; recorded_at: string }[]
}

const partyLine = (p: Party | null) => p ? [p.name ?? p.trade_name, p.postal_address, p.email, p.web_address].filter(Boolean).join(' · ') : 'None on file'
const partyDetails = (who: string, p: Party | null, basis: string): DetailSection[] => [
  { heading: who, body: partyLine(p) },
  ...(p?.trade_name && p.name ? [{ heading: 'Registered trade name', body: p.trade_name }] : []),
  { heading: 'Legal basis', body: `EU Deforestation Regulation (EU) 2023/1115, ${basis}` },
]

export default function TradeRecord({ m, names, onClose }: { m: Movement; names: Names; onClose: () => void }) {
  const q = useQuery({ queryKey: ['eudr-trade', m.movement_id], queryFn: () => api.get<Trade>(`/v1/eudr/movements/${m.movement_id}/trade`) })
  const [err, setErr] = useState<Refusal>(null)
  const keep = useMutation({
    mutationFn: () => api.post(`/v1/eudr/movements/${m.movement_id}/trade/keep`, {}),
    onSuccess: () => { setErr(null); toast.success('Record kept — frozen and fingerprinted.'); q.refetch() },
    onError: (e) => setErr(refusal(e, 'Could not keep the record')),
  })
  const download = (id: string) => api.get(`/v1/eudr/trade-records/${id}`).then(r => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' }))
    a.download = `eudr-record-${m.external_ref ?? m.movement_id}-${id.slice(0, 8)}.json`; a.click()
  }).catch(e => setErr(refusal(e, 'Could not download the record')))
  const t = q.data
  const blocking = t ? t.checks.filter(c => !c.passed && c.severity === 'blocking').length : 0
  const role = named(names, 'actor', m.actor_role)
  // how long the record is kept: from the shipment's date to the date the server keeps it until (its retention rule)
  const years = t ? new Date(t.keep_until).getFullYear() - new Date(t.movement.on).getFullYear() : null
  return (
    <ShipmentDrawer m={m} names={names} onClose={onClose}
      chip={<span className="inline-flex items-center gap-1">
        <StatusChip tone={t?.kept.length ? 'good' : 'neutral'} label={t?.kept.length ? 'Record kept' : 'Files no statement'} />
        <InfoButton compact details={{ title: `${role}: no statement`, sections: [
          { heading: HEADING.shows, body: `A ${role.toLowerCase()} submits no due diligence statement. Before it places, makes available or exports, it holds who supplied it and whom it supplied, and keeps that record${years ? ` for ${years} years from the shipment` : ''}.` },
          { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Article 5(1), (3) and (4).' }] }} />
      </span>}
      actions={t && <Button onClick={() => keep.mutate()} disabled={keep.isPending || blocking > 0}><Archive size={14} /> {keep.isPending ? 'Keeping…' : 'Keep the record'}</Button>}>
      <RefusalLine m={err} />
      {q.isError ? <RefusalLine m={refusal(q.error, 'Could not load the record')} />
        : !t ? <div className="text-[13px] text-[var(--color-faint)]">Loading…</div> : <>
          <Checks checks={t.checks} about="Every check the record runs: the information you hold before you place, make available or export, and what was done about any new information or concern." />

          <section className="space-y-2">
            <SectionHead>What it holds</SectionHead>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <Tile title="Supplier" state={worst(t.checks, 'supplier')} value={t.art5_3_a.supplier?.name ?? t.art5_3_a.supplier?.trade_name ?? 'None on file'}
                details={partyDetails('Supplier', t.art5_3_a.supplier, 'Article 5(3)(a).')} />
              <Tile title="Supplier's role" state={worst(t.checks, 'supplier_role', 'references')}
                value={t.art5_3_a.supplier_role ? named(names, 'actor', t.art5_3_a.supplier_role) : 'Not stated'}
                details={t.art5_3_a.supplier_role === 'operator' ? [{ heading: 'Its reference numbers', body: t.art5_3_a.references.join(', ') || 'None on file' }] : undefined} />
              <Tile title="Supplied to" state={worst(t.checks, 'customer')} value={t.art5_3_b.customer?.name ?? t.art5_3_b.customer?.trade_name ?? 'None on file'}
                details={partyDetails('Supplied to', t.art5_3_b.customer, 'Article 5(3)(b).')} />
              <Tile title="Kept until" state={t.kept.length ? 'good' : 'none'} value={fmtDate(t.keep_until)}
                details={[{ heading: HEADING.shows, body: `${years} years from the date of the shipment, the retention the Regulation sets.` },
                  { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Article 5(4).' }]} />
            </div>
          </section>

          {t.kept.length > 0 && (
            <section className="space-y-2">
              <SectionHead>Kept records</SectionHead>
              <ul className="space-y-1.5">{t.kept.map(k => (
                <li key={k.record_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px] border-b border-[var(--color-line)] pb-1.5">
                  <span className="tabular-nums">{fmtWhen(k.recorded_at)}</span>
                  <span className="text-[var(--color-mute)]">kept until {fmtDate(k.keep_until)}</span>
                  <button type="button" onClick={() => download(k.record_id)} className={`${linkBtn} ml-auto inline-flex items-center gap-1`}><Download size={12} /> For the authorities</button>
                </li>))}</ul>
            </section>)}

          <Concerns movementId={m.movement_id} concerns={t.concerns} names={names} onChanged={() => q.refetch()} />
        </>}
    </ShipmentDrawer>
  )
}

// ── new information and substantiated concerns, and what was done about them ──

export function Concerns({ movementId, concerns, names, onChanged }: { movementId: string; concerns: Concern[]; names: Names; onChanged: () => void }) {
  const [adding, setAdding] = useState(false)
  const [stepFor, setStepFor] = useState<string | null>(null)
  return (
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <SectionHead>New information and concerns</SectionHead>
        <InfoButton compact details={{ title: 'New information and concerns', sections: [
          { heading: HEADING.shows, body: 'Relevant new information or a substantiated concern about this shipment, and each step taken: the competent authorities informed, those you supplied informed, and — for a substantiated concern — the verification and its conclusion.' },
          { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Articles 4(5), 5(5) and 5(6).' }] }} />
        <Button variant="ghost" className="ml-auto" onClick={() => setAdding(true)}>Record</Button>
      </div>
      {concerns.length === 0 ? <p className="text-[12.5px] text-[var(--color-mute)]">None recorded.</p> :
        <ul className="space-y-2">{concerns.map(c => {
          const informed = c.steps.some(s => s.kind === 'authorities_informed')
          return (
            <li key={c.concern_id} className="rounded-lg border border-[var(--color-line)] px-3 py-2.5 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
                <StatusChip tone={c.kind === 'substantiated_concern' ? 'warn' : 'neutral'} label={named(names, 'concern', c.kind)} />
                <span className="text-[var(--color-mute)]">received {fmtDate(c.received_on)}</span>
                <InfoButton compact details={{ title: named(names, 'concern', c.kind), sections: [{ heading: 'What was learned', body: c.detail }] }} />
                {!informed && <StatusChip tone="bad" label="Authorities not informed" />}
                <button type="button" onClick={() => setStepFor(c.concern_id)} className={`${linkBtn} ml-auto`}>Record a step</button>
              </div>
              {c.steps.length > 0 && <ol className="flex flex-wrap gap-1.5">{c.steps.map((s, i) => (
                <li key={i} className="inline-flex items-center gap-1 text-[11.5px] rounded-full border border-[var(--color-line)] px-2 py-0.5">
                  <span className="text-[var(--color-mute)] tabular-nums">{fmtDate(s.on_date)}</span>
                  <span>{named(names, 'step', s.kind)}</span>
                  {(s.conclusion || s.detail) && <InfoButton compact details={{ title: named(names, 'step', s.kind), sections: [
                    ...(s.conclusion ? [{ heading: 'Conclusion', body: named(names, 'conclusion', s.conclusion) }] : []),
                    ...(s.detail ? [{ heading: 'Your note', body: s.detail }] : [])] }} />}
                </li>))}</ol>}
            </li>)
        })}</ul>}
      {adding && <ConcernForm movementId={movementId} names={names} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChanged() }} />}
      {stepFor && <StepForm concernId={stepFor} names={names} onClose={() => setStepFor(null)} onDone={() => { setStepFor(null); onChanged() }} />}
    </section>
  )
}

function ConcernForm({ movementId, names, onClose, onDone }: { movementId: string; names: Names; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [on, setOn] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/movements/${movementId}/concerns`, { kind, received_on: on, detail }), 'Recorded — inform the authorities now.', onDone)
  return (
    <Form title="New information or a substantiated concern" onClose={onClose} busy={m.isPending} error={m.error} ready={!!kind && !!on && detail.trim().length >= 10} onSubmit={() => m.mutate()} submit="Record">
      <p className="text-[12.5px] text-[var(--color-mute)] leading-relaxed">Information that a product is at risk of not complying is reported to the competent authorities immediately (Art. 4(5), 5(5)); a large undertaking verifies before placing (Art. 5(6)).</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Kind *</label><select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{Object.keys(names.concern ?? {}).map(k => <option key={k} value={k}>{named(names, 'concern', k)}</option>)}</select></div>
        <div><label className={lbl}>Received on *</label><input type="date" className={inp} value={on} onChange={e => setOn(e.target.value)} /></div>
      </div>
      <div><label className={lbl}>What was learned * (at least ten characters)</label><textarea className={inp} rows={3} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}

function StepForm({ concernId, names, onClose, onDone }: { concernId: string; names: Names; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [on, setOn] = useState('')
  const [conclusion, setConclusion] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/concerns/${concernId}/steps`, { kind, on_date: on, conclusion: kind === 'verified' ? conclusion : null, detail: detail || null }), 'Recorded.', onDone)
  return (
    <Form title="What was done" onClose={onClose} busy={m.isPending} error={m.error} ready={!!kind && !!on && (kind !== 'verified' || !!conclusion)} onSubmit={() => m.mutate()} submit="Record">
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Step *</label><select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{Object.keys(names.step ?? {}).map(k => <option key={k} value={k}>{named(names, 'step', k)}</option>)}</select></div>
        <div><label className={lbl}>On *</label><input type="date" className={inp} value={on} onChange={e => setOn(e.target.value)} /></div>
      </div>
      {kind === 'verified' && <div><label className={lbl}>Conclusion *</label><select className={inp} value={conclusion} onChange={e => setConclusion(e.target.value)}>
        <option value="">— state it —</option>{Object.keys(names.conclusion ?? {}).map(k => <option key={k} value={k}>{named(names, 'conclusion', k)}</option>)}</select></div>}
      <div><label className={lbl}>Your note</label><textarea className={inp} rows={2} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}
