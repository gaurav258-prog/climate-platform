import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, FileSignature, Info } from 'lucide-react'
import { Button, Card, SectionHead } from '../ui'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Form, useSend, WithdrawForm } from './EudrForms'
import { EVENT_LABEL, inp, lbl, type Check, type DdsEvent } from './types'

// The one-time simplified declaration of a micro or small primary operator (EUDR Art. 4a, Annex III; E115): the products
// with their estimated annual quantity, every plot with a geolocation or its postal address, then the declaration as a
// filing — four eyes in the filings cockpit, then the declaration identifier, updates that keep it, withdrawal until grouped.

interface Line { line_id: string; hs_code: string; description: string; trade_name: string | null; customs_flow: boolean
  est_net_mass_kg: number | null; mass_deviation_pct: number | null; volume_m3: number | null; items_count: number | null }
interface DeclPlot { plot_id: string; plot_name: string | null; country: string | null; coordinate_decimals: number | null; has_polygon: boolean; postal_address: string | null }
interface History { filing_id: string; status: string; period_end: string; declaration_identifier: string | null; verification_number: string | null; events: DdsEvent[]; grouped: boolean }
interface Declaration { on: string; annex_iii: { '2': Line[]; '3': { countries: string[]; plots: DeclPlot[] } }; checks: Check[]; history: History[] }

const STAGE: Record<string, string> = {
  draft: 'Draft — four eyes next', in_review: 'In review', returned: 'Returned to the preparer', approved: 'Approved — attest next',
  attested: 'Attested — submit next', submitted: 'Submitted — record the identifier', accepted: 'Declaration identifier assigned',
  rejected: 'Rejected (Art. 8)', withdrawn: 'Withdrawn', superseded: 'Updated — superseded',
}
const SEV = { blocking: { icon: AlertTriangle, cls: 'text-[var(--color-bad)]' }, warning: { icon: AlertTriangle, cls: 'text-[var(--color-warn)]' }, info: { icon: Info, cls: 'text-[var(--color-faint)]' } }

export default function DeclarationCard({ entityId }: { entityId?: string | null }) {
  const q = useQuery({ queryKey: ['eudr-declaration', entityId], queryFn: () => api.get<Declaration>(`/v1/eudr/declaration${entityId ? `?entity_id=${entityId}` : ''}`) })
  const [adding, setAdding] = useState(false)
  const done = () => { setAdding(false); q.refetch() }
  const prepare = useMutation({
    mutationFn: () => api.post('/v1/eudr/declaration/filing', { entity_id: entityId ?? null }),
    onSuccess: () => { toast.success('Declaration prepared — sign it off in the filings cockpit.'); q.refetch() },
    onError: (e) => toast.error(apiMessage(e, 'Could not prepare the declaration.')),
  })
  const remove = (id: string) => api.del(`/v1/eudr/declaration/lines/${id}`).then(() => q.refetch()).catch(e => toast.error(apiMessage(e, 'Not removed.')))
  if (q.isLoading) return <Card className="p-5 text-[13px] text-[var(--color-faint)]">Loading the simplified declaration…</Card>
  if (!q.data) return <Card className="p-5 text-[13px] text-[var(--color-mute)]">{apiMessage(q.error, 'No simplified declaration applies.')}</Card>
  const d = q.data
  const failing = d.checks.filter(c => !c.passed)
  const blocking = failing.filter(c => c.severity === 'blocking')
  const live = d.history.find(h => !['withdrawn', 'superseded', 'rejected'].includes(h.status))
  const plots = d.annex_iii['3'].plots
  const byPostal = plots.filter(p => !(p.coordinate_decimals != null && p.coordinate_decimals >= 6) && p.postal_address).length

  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <SectionHead icon={FileSignature}>Simplified declaration</SectionHead>
          <p className="text-[12px] text-[var(--color-mute)] mt-1 max-w-[62ch]">For a micro or small primary operator (Art. 4a): one declaration, before the first placing on the market or export, instead of a statement per shipment.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => setAdding(true)}>Add product</Button>
          {!live && <Button onClick={() => prepare.mutate()} disabled={prepare.isPending || blocking.length > 0}>{prepare.isPending ? 'Preparing…' : 'Prepare declaration'}</Button>}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <div>
          <SectionHead hint={blocking.length ? `${blocking.length} blocking` : 'ready'} className="mb-2">Checks</SectionHead>
          {failing.length === 0
            ? <div className="flex items-center gap-2 text-[13px] text-[var(--color-good)]"><CheckCircle2 size={15} /> Every check passes.</div>
            : <ul className="space-y-1.5">{failing.map(c => {
              const S = SEV[c.severity]
              return <li key={c.rule} className="flex gap-2 text-[12.5px]"><S.icon size={14} className={`${S.cls} mt-0.5 shrink-0`} />
                <span className="text-[var(--color-mute)]">{c.message}{c.ref && <span className="mono text-[10.5px] text-[var(--color-faint)]"> · {c.ref}</span>}</span></li>
            })}</ul>}
          {d.checks.filter(c => c.passed && c.severity === 'info' && c.rule !== 'ready').map(c => <p key={c.rule} className="text-[12px] text-[var(--color-sky)] mt-2">{c.message}</p>)}
        </div>
        <div className="text-[12.5px] space-y-2">
          <SectionHead className="mb-2">Products (Annex III point 2)</SectionHead>
          {d.annex_iii['2'].length === 0 ? <p className="text-[var(--color-mute)]">None declared yet.</p> :
            <ul className="space-y-1">{d.annex_iii['2'].map(x => (
              <li key={x.line_id} className="flex justify-between gap-3 border-b border-[var(--color-line)] pb-1">
                <span>HS {x.hs_code} · {x.description}{x.trade_name ? ` · ${x.trade_name}` : ''}
                  <span className="block text-[11.5px] text-[var(--color-faint)]">{[x.est_net_mass_kg != null && `${x.est_net_mass_kg.toLocaleString()} kg${x.mass_deviation_pct != null ? ` ± ${x.mass_deviation_pct} %` : ''}`,
                    x.volume_m3 != null && `${x.volume_m3} m³`, x.items_count != null && `${x.items_count} items`].filter(Boolean).join(' · ')} a year (estimated){x.customs_flow ? ' · through customs' : ''}</span></span>
                <button type="button" onClick={() => remove(x.line_id)} className="text-[11.5px] text-[var(--color-faint)] hover:text-[var(--color-bad)] self-start">Remove</button>
              </li>))}</ul>}
          <SectionHead className="mb-1 mt-3">Where it is produced (point 3)</SectionHead>
          <p className="text-[var(--color-mute)]">{plots.length} plot{plots.length === 1 ? '' : 's'} · {d.annex_iii['3'].countries.join(', ') || '—'}{byPostal ? ` · ${byPostal} by postal address (Art. 4a(5))` : ''}</p>
        </div>
      </div>

      <div>
        <SectionHead className="mb-2">Declarations</SectionHead>
        {d.history.length === 0
          ? <p className="text-[12.5px] text-[var(--color-mute)]">{blocking.length ? 'Clear the blocking checks, then prepare the declaration.' : 'Ready to prepare.'}</p>
          : <div className="space-y-2">{d.history.map(h => <DeclarationRow key={h.filing_id} h={h} onChanged={() => q.refetch()} />)}</div>}
      </div>
      {adding && <LineForm entityId={entityId} onClose={() => setAdding(false)} onDone={done} />}
    </Card>
  )
}

function DeclarationRow({ h, onChanged }: { h: History; onChanged: () => void }) {
  const [open, setOpen] = useState<null | 'identifier' | 'event' | 'withdraw'>(null)
  const done = () => { setOpen(null); onChanged() }
  const update = () => api.post(`/v1/eudr/declaration/filings/${h.filing_id}/update`, {})
    .then(() => { toast.success('Update prepared as a new draft — it keeps the identifier.'); onChanged() })
    .catch(e => toast.error(apiMessage(e, 'Not updated.')))
  const refresh = () => api.post(`/v1/eudr/declaration/filings/${h.filing_id}/refresh`, {})
    .then(() => { toast.success('Draft refreshed from your records.'); onChanged() }).catch(e => toast.error(apiMessage(e, 'Not refreshed.')))
  const filed = h.status === 'submitted' || h.status === 'accepted'
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px]"><span className="font-medium">{STAGE[h.status] ?? h.status}</span>
          <span className="mono text-[12px] text-[var(--color-mute)]"> · {h.period_end}{h.declaration_identifier ? ` · id ${h.declaration_identifier}` : ''}{h.verification_number ? ` · ver ${h.verification_number}` : ''}</span></div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/filings?filing=${h.filing_id}`} className="text-[12.5px] text-[var(--color-sky)] hover:underline self-center">Open in filings</Link>
          {(h.status === 'draft' || h.status === 'returned') && <Button variant="ghost" onClick={refresh}>Refresh from records</Button>}
          {h.status === 'submitted' && <Button onClick={() => setOpen('identifier')}>Record identifier</Button>}
          {filed && <Button variant="ghost" onClick={() => setOpen('event')}>Record event</Button>}
          {h.status === 'accepted' && !h.grouped && <Button variant="ghost" onClick={update}>Update</Button>}
          {filed && !h.grouped && <Button variant="ghost" onClick={() => setOpen('withdraw')}>Withdraw</Button>}
        </div>
      </div>
      {h.events.length > 0 && <ul className="mt-2 space-y-0.5">{h.events.map((e, i) => (
        <li key={i} className="text-[11.5px] text-[var(--color-faint)]"><span className="mono">{new Date(e.at).toLocaleString()}</span> · {e.kind === 'reference_received' ? 'Declaration identifier assigned' : EVENT_LABEL[e.kind] ?? e.kind}{e.detail ? ` — ${e.detail}` : ''}</li>))}</ul>}
      {open === 'identifier' && <IdentifierForm filingId={h.filing_id} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'event' && <DeclEventForm filingId={h.filing_id} onClose={() => setOpen(null)} onDone={done} />}
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
    <Form title="Declare a relevant product" onClose={onClose} busy={m.isPending} ready={!!f.hs_code && !!f.description && !!f.customs} onSubmit={() => m.mutate()} submit="Declare">
      <p className="text-[12px] text-[var(--color-mute)]">Annex III point 2: the HS code, a description with the trade name, and the one-off estimated annual quantity — in kilograms of net mass when it enters or leaves the market, otherwise net mass with a percentage estimate or deviation, or volume, or number of items.</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>HS code *</label><input className={inp} value={f.hs_code} onChange={set('hs_code')} placeholder="180100" /></div>
        <div><label className={lbl}>Enters or leaves the market *</label>
          <select className={inp} value={f.customs} onChange={set('customs')}><option value="">— state it —</option><option value="yes">yes</option><option value="no">no</option></select></div>
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
        <div><label className={lbl}>In scope (only where Annex I leaves it open)</label>
          <select className={inp} value={f.scope} onChange={set('scope')}><option value="">— Annex I decides —</option><option value="yes">yes</option><option value="no">no</option></select></div>
        <div><label className={lbl}>Why</label><input className={inp} value={f.basis} onChange={set('basis')} /></div>
      </div>
    </Form>
  )
}

function IdentifierForm({ filingId, onClose, onDone }: { filingId: string; onClose: () => void; onDone: () => void }) {
  const [id, setId] = useState('')
  const [ver, setVer] = useState('')
  const [source, setSource] = useState('manual_entry')
  const m = useSend(() => api.post(`/v1/eudr/declaration/filings/${filingId}/identifier`, { identifier: id.trim(), verification_number: ver.trim() || null, source }),
    'Declaration identifier recorded.', onDone)
  return (
    <Form title="Declaration identifier assigned" onClose={onClose} busy={m.isPending} ready={!!id.trim()} onSubmit={() => m.mutate()} submit="Record">
      <p className="text-[12px] text-[var(--color-mute)]">The declaration identifier and verification number the information system assigned (IR 2024/3084 Art. 7) — or that the Member State communicated (Art. 4a(2)). An update keeps the same identifier.</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Declaration identifier *</label><input className={inp} value={id} onChange={e => setId(e.target.value)} /></div>
        <div><label className={lbl}>Verification number</label><input className={inp} value={ver} onChange={e => setVer(e.target.value)} /></div>
      </div>
      <div><label className={lbl}>How it was received</label>
        <select className={inp} value={source} onChange={e => setSource(e.target.value)}>
          <option value="manual_entry">entered in the information system by hand</option><option value="information_system">from the information system</option>
          <option value="member_state">communicated by the Member State (Art. 4a(4))</option><option value="contingency">contingency procedure</option>
        </select></div>
    </Form>
  )
}

const DECL_EVENTS = ['grouped', 'check_notified', 'check_ended', 'rejected']

function DeclEventForm({ filingId, onClose, onDone }: { filingId: string; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/declaration/filings/${filingId}/events`, { kind, detail: detail || null }), 'Recorded.', onDone)
  return (
    <Form title="What happened to the declaration" onClose={onClose} busy={m.isPending} ready={!!kind} onSubmit={() => m.mutate()} submit="Record">
      <div><label className={lbl}>Event *</label>
        <select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{DECL_EVENTS.map(k => <option key={k} value={k}>{EVENT_LABEL[k]}</option>)}
        </select></div>
      <div><label className={lbl}>Detail</label><textarea className={inp} rows={2} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}
