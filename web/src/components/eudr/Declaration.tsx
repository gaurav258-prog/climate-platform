import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { FileSignature, MapPin, Trash2 } from 'lucide-react'
import { Button, Card, SectionHead } from '../ui'
import { HEADING, InfoButton, MESSAGE_HEADING, type DetailSection, type Message } from '../Details'
import { StatusChip } from '../StatusChip'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Form, Lead, WithdrawForm } from './EudrForms'
import { Checks, RefusalLine, Stepper, Timeline } from './parts'
import { STATEMENT_TONE, linkBtn, refusal, statementWord, useSend, type Refusal } from './words'
import { inp, kg, lbl, named, type Check, type DdsEvent, type Names } from './types'

// The one-time simplified declaration of a micro or small primary operator (EUDR Art. 4a, Annex III; E115): the products
// with their estimated yearly quantity, every plot with its location or postal address, then the declaration as a filing
// — four eyes in the filings register, then the declaration identifier, updates that keep it, withdrawal until grouped.

interface Line { line_id: string; hs_code: string; description: string; trade_name: string | null; customs_flow: boolean
  est_net_mass_kg: number | null; mass_deviation_pct: number | null; volume_m3: number | null; items_count: number | null
  annex_scope: { in_scope: boolean | null; msg: Message } }
interface DeclPlot { plot_id: string; plot_name: string | null; country: string | null; coordinate_decimals: number | null; has_polygon: boolean; postal_address: string | null }
interface History { filing_id: string; status: string; period_end: string; declaration_identifier: string | null; verification_number: string | null; events: DdsEvent[]; grouped: boolean }
interface Declaration { on: string; annex_iii: { '2': Line[]; '3': { countries: string[]; plots: DeclPlot[] } }; checks: Check[]; history: History[] }

const word = (s: string) => statementWord(s, 'Identifier assigned')
const quantity = (x: Line) => [x.est_net_mass_kg != null ? `${kg(x.est_net_mass_kg)}${x.mass_deviation_pct != null ? ` ± ${x.mass_deviation_pct} %` : ''}` : null,
  x.volume_m3 != null ? `${x.volume_m3} m³` : null, x.items_count != null ? `${x.items_count} items` : null].filter(Boolean).join(' · ')

export default function DeclarationCard({ entityId, names }: { entityId?: string | null; names: Names }) {
  const q = useQuery({ queryKey: ['eudr-declaration', entityId], queryFn: () => api.get<Declaration>(`/v1/eudr/declaration${entityId ? `?entity_id=${entityId}` : ''}`) })
  const [adding, setAdding] = useState(false)
  const [err, setErr] = useState<Refusal>(null)
  const done = () => { setAdding(false); q.refetch() }
  const prepare = useMutation({
    mutationFn: () => api.post('/v1/eudr/declaration/filing', { entity_id: entityId ?? null }),
    onSuccess: () => { setErr(null); toast.success('Declaration prepared — sign it off in the filings register.'); q.refetch() },
    onError: (e) => setErr(refusal(e, 'Could not prepare the declaration')),
  })
  const remove = (id: string) => api.del(`/v1/eudr/declaration/lines/${id}`).then(() => { setErr(null); q.refetch() }).catch(e => setErr(refusal(e, 'Not removed')))
  const d = q.data
  const blocking = d ? d.checks.filter(c => !c.passed && c.severity === 'blocking').length : 0
  const live = d?.history.find(h => !['withdrawn', 'superseded', 'rejected'].includes(h.status))
  const plots = d?.annex_iii['3'].plots ?? []
  const byPostal = plots.filter(p => !(p.coordinate_decimals != null && p.coordinate_decimals >= 6) && p.postal_address).length

  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <SectionHead icon={FileSignature}>Simplified declaration</SectionHead>
        <InfoButton compact details={{ title: 'Simplified declaration', sections: [
          { heading: HEADING.shows, body: 'For a micro or small primary operator: one declaration, made before it first places products on the market or exports them, instead of a statement for each shipment. It lists the products with their estimated yearly quantity and where they are produced.' },
          { heading: HEADING.read, body: 'Clear the checks, add each product, then prepare it. It is signed off with four eyes in the filings register; record the declaration identifier once it is assigned. An update after a major change keeps the identifier.' },
          { heading: 'Legal basis', body: 'EU Deforestation Regulation (EU) 2023/1115, Article 4a and Annex III; Implementing Regulation (EU) 2024/3084, Articles 4a and 7.' }] }} />
        {live && <StatusChip tone={STATEMENT_TONE[live.status]} label={word(live.status)} />}
        <div className="ml-auto flex gap-2">
          <Button variant="ghost" onClick={() => setAdding(true)}>Add product</Button>
          {d && !live && <Button onClick={() => prepare.mutate()} disabled={prepare.isPending || blocking > 0}>{prepare.isPending ? 'Preparing…' : 'Prepare declaration'}</Button>}
        </div>
      </div>
      <RefusalLine m={err} />
      {q.isError ? <RefusalLine m={refusal(q.error, 'No simplified declaration applies')} />
        : !d ? <div className="text-[13px] text-[var(--color-faint)]">Loading…</div> : <>
          <div className="grid lg:grid-cols-2 gap-6">
            <Checks checks={d.checks} about="Every check the declaration runs before it can be prepared, on what your records say today: who may declare, the products and where they are produced." />
            <div className="space-y-4">
              <section className="space-y-2">
                <SectionHead hint={`${d.annex_iii['2'].length} declared`}>Products</SectionHead>
                {d.annex_iii['2'].length === 0 ? <p className="text-[12.5px] text-[var(--color-mute)]">None declared yet.</p> :
                  <ul className="space-y-1.5">{d.annex_iii['2'].map(x => (
                    <li key={x.line_id} className="flex items-center gap-2 text-[12.5px] border-b border-[var(--color-line)] pb-1.5">
                      <StatusChip tone="neutral" label={`HS ${x.hs_code}`} />
                      <span className="text-[var(--color-mute)] tabular-nums">{quantity(x) || '—'}</span>
                      <InfoButton compact details={{ title: `HS ${x.hs_code}`, sections: lineDetails(x) }} />
                      <button type="button" onClick={() => remove(x.line_id)} aria-label={`Remove HS ${x.hs_code}`}
                        className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-bad)]"><Trash2 size={13} /></button>
                    </li>))}</ul>}
              </section>
              <section className="space-y-2">
                <SectionHead>Where it is produced</SectionHead>
                <div className="flex flex-wrap items-center gap-1.5 text-[12.5px]">
                  <MapPin size={13} className="text-[var(--color-faint)]" />
                  <span>{plots.length} plot{plots.length === 1 ? '' : 's'}</span>
                  {d.annex_iii['3'].countries.map(c => <StatusChip key={c} tone="neutral" label={c} />)}
                  {byPostal > 0 && <StatusChip tone="neutral" label={`${byPostal} by postal address`} />}
                </div>
              </section>
            </div>
          </div>

          <section className="space-y-2">
            <SectionHead>Declarations</SectionHead>
            {d.history.length === 0
              ? <p className="text-[12.5px] text-[var(--color-mute)]">{blocking ? 'Clear the blocking checks, then prepare it.' : 'Ready to prepare.'}</p>
              : <div className="space-y-2.5">{d.history.map(h => <DeclarationRow key={h.filing_id} h={h} names={names} onChanged={() => q.refetch()} />)}</div>}
          </section>
        </>}
      {adding && <LineForm entityId={entityId} onClose={() => setAdding(false)} onDone={done} />}
    </Card>
  )
}

function lineDetails(x: Line): DetailSection[] {
  const d = x.annex_scope.msg.detail ?? {}
  return [
    { heading: 'Product', body: [x.description, x.trade_name].filter(Boolean).join(' · ') },
    { heading: 'Estimated yearly quantity', body: quantity(x) || '—' },
    { heading: 'Through customs', body: x.customs_flow ? 'Yes' : 'No' },
    { heading: x.annex_scope.msg.label, body: d.what ?? '' },
    ...(d.next ? [{ heading: MESSAGE_HEADING.next, body: d.next }] : []),
  ]
}

function DeclarationRow({ h, names, onChanged }: { h: History; names: Names; onChanged: () => void }) {
  const [open, setOpen] = useState<null | 'identifier' | 'event' | 'withdraw'>(null)
  const [err, setErr] = useState<Refusal>(null)
  const done = () => { setOpen(null); onChanged() }
  const post = (path: string, ok: string) => api.post(path, {}).then(() => { setErr(null); toast.success(ok); onChanged() })
    .catch(e => setErr(refusal(e, 'Not done')))
  const filed = h.status === 'submitted' || h.status === 'accepted'
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-4 py-3 space-y-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip tone={STATEMENT_TONE[h.status]} label={word(h.status)} />
        {h.declaration_identifier && <span className="text-[12px] text-[var(--color-mute)]">Identifier <span className="text-[var(--color-ink)] tabular-nums">{h.declaration_identifier}</span></span>}
        {h.verification_number && <InfoButton compact details={{ title: 'Declaration identifier', sections: [
          { heading: 'Identifier', body: h.declaration_identifier ?? '—' }, { heading: 'Verification number', body: h.verification_number }] }} />}
        <div className="ml-auto flex flex-wrap gap-2 items-center">
          <Link to={`/filings?filing=${h.filing_id}`} className={linkBtn}>Open in filings</Link>
          {(h.status === 'draft' || h.status === 'returned') && <Button variant="ghost" onClick={() => post(`/v1/eudr/declaration/filings/${h.filing_id}/refresh`, 'Draft refreshed from your records.')}>Refresh</Button>}
          {h.status === 'submitted' && <Button onClick={() => setOpen('identifier')}>Record identifier</Button>}
          {filed && <Button variant="ghost" onClick={() => setOpen('event')}>Record event</Button>}
          {h.status === 'accepted' && !h.grouped && <Button variant="ghost" onClick={() => post(`/v1/eudr/declaration/filings/${h.filing_id}/update`, 'Update prepared as a new draft — it keeps the identifier.')}>Update</Button>}
          {filed && !h.grouped && <Button variant="ghost" onClick={() => setOpen('withdraw')}>Withdraw</Button>}
        </div>
      </div>
      <Stepper status={h.status} last="Identifier assigned" />
      <Timeline events={h.events} />
      <RefusalLine m={err} />
      {open === 'identifier' && <IdentifierForm filingId={h.filing_id} names={names} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'event' && <DeclEventForm filingId={h.filing_id} names={names} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'withdraw' && <WithdrawForm filingId={h.filing_id} what="declaration" path={`/v1/eudr/declaration/filings/${h.filing_id}/withdraw`} onClose={() => setOpen(null)} onDone={done} />}
    </div>
  )
}

function LineForm({ entityId, onClose, onDone }: { entityId?: string | null; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ hs_code: '', description: '', trade_name: '', customs: '', mass: '', dev: '', volume: '', items: '', scope: '', basis: '' })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const num = (v: string) => (v.trim() ? Number(v) : null)
  const m = useSend(() => api.post('/v1/eudr/declaration/lines', {
    entity_id: entityId ?? null, hs_code: f.hs_code, description: f.description, trade_name: f.trade_name || null,
    customs_flow: f.customs === 'yes', est_net_mass_kg: num(f.mass), mass_deviation_pct: num(f.dev), volume_m3: num(f.volume),
    items_count: num(f.items), scope_in: f.scope ? f.scope === 'yes' : null, scope_basis: f.basis || null }), 'Product declared.', onDone)
  return (
    <Form title="Declare a product" onClose={onClose} busy={m.isPending} error={m.error} ready={!!f.hs_code && !!f.description && !!f.customs} onSubmit={() => m.mutate()} submit="Declare">
      <Lead>The HS code, a description with the trade name, and the one-off estimated yearly quantity: kilograms of net mass when it enters or leaves the market through customs; otherwise net mass with a percentage estimate or deviation, or volume, or number of items (Annex III point 2).</Lead>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>HS code *</label><input className={inp} value={f.hs_code} onChange={set('hs_code')} placeholder="180100" /></div>
        <div><label className={lbl}>Through customs *</label>
          <select className={inp} value={f.customs} onChange={set('customs')}><option value="">— state it —</option><option value="yes">Yes</option><option value="no">No</option></select></div>
      </div>
      <div><label className={lbl}>Description *</label><input className={inp} value={f.description} onChange={set('description')} /></div>
      <div><label className={lbl}>Trade name</label><input className={inp} value={f.trade_name} onChange={set('trade_name')} /></div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Estimated net mass a year (kg)</label><input className={inp} inputMode="decimal" value={f.mass} onChange={set('mass')} /></div>
        <div><label className={lbl}>Estimate or deviation (%)</label><input className={inp} inputMode="decimal" value={f.dev} onChange={set('dev')} /></div>
        <div><label className={lbl}>Or volume (m³)</label><input className={inp} inputMode="decimal" value={f.volume} onChange={set('volume')} /></div>
        <div><label className={lbl}>Or number of items</label><input className={inp} inputMode="numeric" value={f.items} onChange={set('items')} /></div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Covered (only where the list leaves it open)</label>
          <select className={inp} value={f.scope} onChange={set('scope')}><option value="">— the list decides —</option><option value="yes">Yes</option><option value="no">No</option></select></div>
        <div><label className={lbl}>Why</label><input className={inp} value={f.basis} onChange={set('basis')} /></div>
      </div>
    </Form>
  )
}

function IdentifierForm({ filingId, names, onClose, onDone }: { filingId: string; names: Names; onClose: () => void; onDone: () => void }) {
  const [id, setId] = useState('')
  const [ver, setVer] = useState('')
  const [source, setSource] = useState('manual_entry')
  const m = useSend(() => api.post(`/v1/eudr/declaration/filings/${filingId}/identifier`, { identifier: id.trim(), verification_number: ver.trim() || null, source }),
    'Declaration identifier recorded.', onDone)
  return (
    <Form title="Declaration identifier assigned" onClose={onClose} busy={m.isPending} error={m.error} ready={id.trim().length >= 4} onSubmit={() => m.mutate()} submit="Record">
      <Lead>The declaration identifier and verification number the information system assigned (Implementing Regulation (EU) 2024/3084, Art. 7), or that the Member State communicated (Art. 4a(2)). An update keeps the same identifier.</Lead>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Declaration identifier *</label><input className={inp} value={id} onChange={e => setId(e.target.value)} /></div>
        <div><label className={lbl}>Verification number</label><input className={inp} value={ver} onChange={e => setVer(e.target.value)} /></div>
      </div>
      <div><label className={lbl}>How it was received</label>
        <select className={inp} value={source} onChange={e => setSource(e.target.value)}>
          {['manual_entry', 'information_system', 'member_state', 'contingency'].map(k => <option key={k} value={k}>{named(names, 'source', k)}</option>)}
        </select></div>
    </Form>
  )
}

const DECL_EVENTS = ['grouped', 'check_notified', 'check_ended', 'rejected']

function DeclEventForm({ filingId, names, onClose, onDone }: { filingId: string; names: Names; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/declaration/filings/${filingId}/events`, { kind, detail: detail || null }), 'Recorded.', onDone)
  return (
    <Form title="What happened to the declaration" onClose={onClose} busy={m.isPending} error={m.error} ready={!!kind} onSubmit={() => m.mutate()} submit="Record">
      <div><label className={lbl}>Event *</label>
        <select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{DECL_EVENTS.map(k => <option key={k} value={k}>{named(names, 'event', k)}</option>)}
        </select></div>
      <div><label className={lbl}>Your note</label><textarea className={inp} rows={2} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}
