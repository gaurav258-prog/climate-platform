import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, Archive, CheckCircle2, Info } from 'lucide-react'
import { Button, Card, SectionHead } from '../ui'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Form, useSend } from './EudrForms'
import { KIND_LABEL, inp, lbl, type Check, type Movement } from './types'

// A downstream operator's or trader's movement (EUDR Art. 5; E122): the information it must hold before it places, makes
// available or exports (5(1), 5(3)), kept as a frozen record for five years from the movement (5(4)); and, for every
// role, new information and substantiated concerns with what was done about them (Art. 4(5), 5(5)-(6)).

interface Party { name: string | null; trade_name: string | null; postal_address: string | null; email: string | null; web_address: string | null }
interface Concern { concern_id: string; kind: string; received_on: string; detail: string
  steps: { kind: string; on_date: string; conclusion: string | null; detail: string | null }[] }
interface Trade {
  movement: { kind: string; on: string; actor_role: string }
  art5_3_a: { supplier: Party | null; supplier_role: string | null; references: string[] }
  art5_3_b: { customer: Party | null }
  concerns: Concern[]; keep_until: string; checks: Check[]
  kept: { record_id: string; keep_until: string; recorded_at: string }[]
}
const SEV = { blocking: { icon: AlertTriangle, cls: 'text-[var(--color-bad)]' }, warning: { icon: AlertTriangle, cls: 'text-[var(--color-warn)]' }, info: { icon: Info, cls: 'text-[var(--color-faint)]' } }
const STEP: Record<string, string> = { authorities_informed: 'Competent authorities informed', downstream_informed: 'Downstream operators and traders informed', verified: 'Verified' }

function PartyLines({ p }: { p: Party | null }) {
  if (!p) return <span className="text-[var(--color-faint)]">none on the movement</span>
  return <span>{p.name ?? p.trade_name ?? '—'}{p.trade_name && p.name ? ` (${p.trade_name})` : ''} · {p.postal_address ?? 'no postal address'} · {p.email ?? 'no email'}{p.web_address ? ` · ${p.web_address}` : ''}</span>
}

export default function TradeRecord({ m }: { m: Movement }) {
  const q = useQuery({ queryKey: ['eudr-trade', m.movement_id], queryFn: () => api.get<Trade>(`/v1/eudr/movements/${m.movement_id}/trade`) })
  const keep = useMutation({
    mutationFn: () => api.post(`/v1/eudr/movements/${m.movement_id}/trade/keep`, {}),
    onSuccess: () => { toast.success('Record kept — frozen and hashed.'); q.refetch() },
    onError: (e) => toast.error(apiMessage(e, 'Could not keep the record.')),
  })
  const download = (id: string) => api.get(`/v1/eudr/trade-records/${id}`).then(r => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' }))
    a.download = `eudr-article5-${m.external_ref ?? m.movement_id}-${id.slice(0, 8)}.json`; a.click()
  }).catch(e => toast.error(apiMessage(e, 'Could not download the record.')))
  if (q.isLoading) return <Card className="p-5 text-[13px] text-[var(--color-faint)]">Loading the Article 5 record…</Card>
  if (!q.data) return <Card className="p-5 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the record.')}</Card>
  const t = q.data
  const failing = t.checks.filter(c => !c.passed)
  const blocking = failing.filter(c => c.severity === 'blocking')
  const a = t.art5_3_a
  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[15px] font-semibold">{m.external_ref ?? m.movement_id.slice(0, 8)} · {m.description ?? `HS ${m.hs_code}`}</div>
          <div className="mono text-[11.5px] text-[var(--color-mute)] mt-0.5">{KIND_LABEL[m.kind] ?? m.kind} · {m.planned_on} · HS {m.hs_code} · {m.actor_role.replace(/_/g, ' ')}</div>
          <p className="text-[12px] text-[var(--color-mute)] mt-1 max-w-[64ch]">A {m.actor_role.replace(/_/g, ' ')} files no statement. It holds the information of Article 5(3) before it {m.kind === 'making_available' ? 'makes the products available' : m.kind === 'export' ? 'exports' : 'places them on the market'}, and keeps it for five years (Art. 5(1), 5(4)).</p>
        </div>
        <Button onClick={() => keep.mutate()} disabled={keep.isPending || blocking.length > 0}><Archive size={14} /> {keep.isPending ? 'Keeping…' : 'Keep the record'}</Button>
      </div>
      <div className="grid lg:grid-cols-2 gap-5">
        <div>
          <SectionHead hint={blocking.length ? `${blocking.length} blocking` : 'held'} className="mb-2">Checks</SectionHead>
          {failing.length === 0 ? <div className="flex items-center gap-2 text-[13px] text-[var(--color-good)]"><CheckCircle2 size={15} /> The Article 5(3) information is held.</div>
            : <ul className="space-y-1.5">{failing.map(c => { const S = SEV[c.severity]; return (
              <li key={c.rule} className="flex gap-2 text-[12.5px]"><S.icon size={14} className={`${S.cls} mt-0.5 shrink-0`} />
                <span className="text-[var(--color-mute)]">{c.message}{c.ref && <span className="mono text-[10.5px] text-[var(--color-faint)]"> · {c.ref}</span>}</span></li>) })}</ul>}
        </div>
        <div className="text-[12.5px] space-y-2">
          <SectionHead className="mb-2">What it holds</SectionHead>
          <div><span className="text-[var(--color-faint)]">Supplier (5(3)(a)) · </span><PartyLines p={a.supplier} /></div>
          <div><span className="text-[var(--color-faint)]">Supplier is · </span>{a.supplier_role ? a.supplier_role.replace(/_/g, ' ') : 'not stated'}{a.supplier_role === 'operator' && <> · references: {a.references.join(', ') || 'none'}</>}</div>
          <div><span className="text-[var(--color-faint)]">Supplied to (5(3)(b)) · </span><PartyLines p={t.art5_3_b.customer} /></div>
          <div><span className="text-[var(--color-faint)]">Kept until · </span>{t.keep_until}</div>
        </div>
      </div>
      {t.kept.length > 0 && (
        <div>
          <SectionHead className="mb-2">Kept records</SectionHead>
          <ul className="space-y-1 text-[12.5px]">{t.kept.map(k => (
            <li key={k.record_id} className="flex flex-wrap justify-between gap-2 border-b border-[var(--color-line)] pb-1">
              <span className="mono text-[var(--color-mute)]">{new Date(k.recorded_at).toLocaleString()} · kept until {k.keep_until}</span>
              <button type="button" onClick={() => download(k.record_id)} className="text-[var(--color-sky)] hover:underline">Download for the authorities</button>
            </li>))}</ul>
        </div>)}
      <Concerns movementId={m.movement_id} concerns={t.concerns} onChanged={() => q.refetch()} />
    </Card>
  )
}

export function Concerns({ movementId, concerns, onChanged }: { movementId: string; concerns: Concern[]; onChanged: () => void }) {
  const [adding, setAdding] = useState(false)
  const [stepFor, setStepFor] = useState<string | null>(null)
  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <SectionHead className="mb-0">New information and concerns</SectionHead>
        <Button variant="ghost" onClick={() => setAdding(true)}>Record</Button>
      </div>
      {concerns.length === 0 ? <p className="text-[12.5px] text-[var(--color-mute)]">None recorded.</p> :
        <ul className="space-y-2">{concerns.map(c => (
          <li key={c.concern_id} className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-[12.5px]">
            <div className="flex flex-wrap justify-between gap-2">
              <span><span className="font-medium">{c.kind === 'substantiated_concern' ? 'Substantiated concern' : 'New information'}</span> · received {c.received_on} — {c.detail}</span>
              <button type="button" onClick={() => setStepFor(c.concern_id)} className="text-[var(--color-sky)] hover:underline">Record a step</button>
            </div>
            {c.steps.map((s, i) => <div key={i} className="text-[11.5px] text-[var(--color-faint)] mt-0.5">{s.on_date} · {STEP[s.kind] ?? s.kind}{s.conclusion ? ` — ${s.conclusion === 'negligible' ? 'no or only a negligible risk' : 'not negligible'}` : ''}{s.detail ? ` · ${s.detail}` : ''}</div>)}
          </li>))}</ul>}
      {adding && <ConcernForm movementId={movementId} onClose={() => setAdding(false)} onDone={() => { setAdding(false); onChanged() }} />}
      {stepFor && <StepForm concernId={stepFor} onClose={() => setStepFor(null)} onDone={() => { setStepFor(null); onChanged() }} />}
    </div>
  )
}

function ConcernForm({ movementId, onClose, onDone }: { movementId: string; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [on, setOn] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/movements/${movementId}/concerns`, { kind, received_on: on, detail }), 'Recorded — inform the authorities now.', onDone)
  return (
    <Form title="New information or a substantiated concern" onClose={onClose} busy={m.isPending} ready={!!kind && !!on && detail.trim().length >= 10} onSubmit={() => m.mutate()} submit="Record">
      <p className="text-[12px] text-[var(--color-mute)]">Information indicating a product is at risk of not complying is reported to the competent authorities immediately (Art. 4(5), 5(5)); a non-SME verifies before placing (Art. 5(6)).</p>
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Kind *</label><select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option><option value="new_information">relevant new information</option><option value="substantiated_concern">substantiated concern (Art. 2(31))</option></select></div>
        <div><label className={lbl}>Received on *</label><input type="date" className={inp} value={on} onChange={e => setOn(e.target.value)} /></div>
      </div>
      <div><label className={lbl}>What was learned *</label><textarea className={inp} rows={3} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}

function StepForm({ concernId, onClose, onDone }: { concernId: string; onClose: () => void; onDone: () => void }) {
  const [kind, setKind] = useState('')
  const [on, setOn] = useState('')
  const [conclusion, setConclusion] = useState('')
  const [detail, setDetail] = useState('')
  const m = useSend(() => api.post(`/v1/eudr/concerns/${concernId}/steps`, { kind, on_date: on, conclusion: kind === 'verified' ? conclusion : null, detail: detail || null }), 'Recorded.', onDone)
  return (
    <Form title="What was done" onClose={onClose} busy={m.isPending} ready={!!kind && !!on && (kind !== 'verified' || !!conclusion)} onSubmit={() => m.mutate()} submit="Record">
      <div className="grid grid-cols-2 gap-3">
        <div><label className={lbl}>Step *</label><select className={inp} value={kind} onChange={e => setKind(e.target.value)}>
          <option value="">— choose —</option>{Object.entries(STEP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div><label className={lbl}>On *</label><input type="date" className={inp} value={on} onChange={e => setOn(e.target.value)} /></div>
      </div>
      {kind === 'verified' && <div><label className={lbl}>Conclusion *</label><select className={inp} value={conclusion} onChange={e => setConclusion(e.target.value)}>
        <option value="">— state it —</option><option value="negligible">no or only a negligible risk</option><option value="not_negligible">not negligible</option></select></div>}
      <div><label className={lbl}>Detail</label><textarea className={inp} rows={2} value={detail} onChange={e => setDetail(e.target.value)} /></div>
    </Form>
  )
}
