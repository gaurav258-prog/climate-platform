import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import { Button, Card, SectionHead, StatusPill } from '../ui'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { EvidenceForm, EventForm, ReferenceForm, RiskForm, ScopeForm, WithdrawForm } from './EudrForms'
import { ASPECT_LABEL, EVENT_LABEL, KIND_LABEL, type DdsEvent, type Movement, type Records, type Statement, type StatementFiling, type Window } from './types'

// One shipment: the statement as it stands, the checks the filing will run (each with its article), what it rests on,
// and its statements — prepared here, signed off in the filings cockpit (four eyes, attestation, submission), then the
// reference number and what happens to it in the information system (IR 2024/3084 Art. 5, 8).

const SEV = {
  blocking: { icon: AlertTriangle, cls: 'text-[var(--color-bad)]' },
  warning: { icon: AlertTriangle, cls: 'text-[var(--color-warn)]' },
  info: { icon: Info, cls: 'text-[var(--color-faint)]' },
}
const STAGE: Record<string, string> = {
  draft: 'Draft — four eyes next', in_review: 'In review', returned: 'Returned to the preparer', approved: 'Approved — attest next',
  attested: 'Attested — submit next', submitted: 'Submitted — record the reference', accepted: 'Reference made available',
  rejected: 'Rejected (Art. 8)', withdrawn: 'Withdrawn', superseded: 'Amended — superseded',
}

type Open = null | 'evidence' | 'risk' | 'scope'

export default function Shipment({ m, rec, onChanged }: { m: Movement; rec: Records; onChanged: () => void }) {
  const st = useQuery({ queryKey: ['eudr-statement', m.movement_id], queryFn: () => api.get<Statement>(`/v1/eudr/movements/${m.movement_id}/statement`) })
  const [open, setOpen] = useState<Open>(null)
  const refresh = () => { setOpen(null); st.refetch(); onChanged() }
  const prepare = useMutation({
    mutationFn: () => api.post<{ filing_id: string }>(`/v1/eudr/movements/${m.movement_id}/filing`, {}),
    onSuccess: () => { toast.success('Statement prepared — sign it off in the filings cockpit.'); refresh() },
    onError: (e) => toast.error(apiMessage(e, 'Could not prepare the statement.')),
  })
  if (st.isLoading) return <Card className="p-5 text-[13px] text-[var(--color-faint)]">Loading the statement…</Card>
  if (st.error || !st.data) return <Card className="p-5 text-[13px] text-[var(--color-bad)]">{apiMessage(st.error, 'Could not load the statement.')}</Card>
  const s = st.data
  const failing = s.checks.filter(c => !c.passed)
  const blocking = failing.filter(c => c.severity === 'blocking')
  const live = m.filings.find(f => !['withdrawn', 'superseded', 'rejected'].includes(f.status))
  const scopeOpen = s.scope.in_scope === null

  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-[15px] font-semibold">{m.external_ref ?? m.movement_id.slice(0, 8)} · {m.description ?? `HS ${m.hs_code}`}</div>
          <div className="mono text-[11.5px] text-[var(--color-mute)] mt-0.5">{KIND_LABEL[m.kind] ?? m.kind} · {m.planned_on} · HS {m.hs_code} · {m.actor_role.replace(/_/g, ' ')}{m.net_mass_kg != null ? ` · ${m.net_mass_kg.toLocaleString()} kg` : ''}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          {scopeOpen && <Button variant="ghost" onClick={() => setOpen('scope')}>State scope</Button>}
          <Button variant="ghost" onClick={() => setOpen('evidence')}>Add legality evidence</Button>
          <Button variant="ghost" onClick={() => setOpen('risk')}>Risk assessment</Button>
          {!live && <Button onClick={() => prepare.mutate()} disabled={prepare.isPending || blocking.length > 0}>{prepare.isPending ? 'Preparing…' : 'Prepare statement'}</Button>}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-5">
        <div>
          <SectionHead hint={blocking.length ? `${blocking.length} blocking` : 'ready'} className="mb-2">Checks</SectionHead>
          {failing.length === 0
            ? <div className="flex items-center gap-2 text-[13px] text-[var(--color-good)]"><CheckCircle2 size={15} /> Every check passes.</div>
            : <ul className="space-y-1.5">{failing.map(c => {
              const S = SEV[c.severity]
              return (
                <li key={c.rule} className="flex gap-2 text-[12.5px]">
                  <S.icon size={14} className={`${S.cls} mt-0.5 shrink-0`} />
                  <span className="text-[var(--color-mute)]">{c.message}{c.ref && <span className="mono text-[10.5px] text-[var(--color-faint)]"> · {c.ref}</span>}</span>
                </li>)
            })}</ul>}
        </div>
        <div className="text-[12.5px] space-y-2">
          <SectionHead className="mb-2">What it rests on</SectionHead>
          <Row k="Operator (Annex II 1)" v={s.annex_ii['1'].address ? `${s.annex_ii['1'].name ?? ''} · ${s.annex_ii['1'].country ?? ''}${s.annex_ii['1'].eori ? ` · EORI ${s.annex_ii['1'].eori}` : ''}` : 'status not stated'} />
          <Row k="Supplier (Art. 9(1)(e))" v={s.art9.supplier ? `${s.art9.supplier.name}${s.art9.supplier.email ? ` · ${s.art9.supplier.email}` : ''}` : 'none'} />
          <Row k="Countries (Annex II 3)" v={s.annex_ii['3'].countries.join(', ') || '—'} />
          <Row k="Legality evidence" v={s.legality_evidence.length ? s.legality_evidence.map(e => `${ASPECT_LABEL[e.aspect] ?? e.aspect}: ${e.document_kind}`).join(' · ') : 'none'} />
          <Row k="Risk assessment" v={s.risk_assessment ? `${s.risk_assessment.path} · ${s.risk_assessment.conclusion === 'negligible' ? 'no or only a negligible risk' : 'not negligible'} · ${s.risk_assessment.recorded_at.slice(0, 10)}`
            : rec.pending.some(x => x.request_type === 'eudr.risk' && x.movement_id === m.movement_id) ? 'waiting for a second person (Approvals)' : 'none approved'} />
          {scopeOpen && <Row k="Annex I scope" v={s.movement.scope_in == null ? 'open — state it' : `${s.movement.scope_in ? 'in' : 'out of'} scope: ${s.movement.scope_basis}`} />}
        </div>
      </div>

      <div>
        <SectionHead className="mb-2">Plots ({s.plots.length})</SectionHead>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="font-normal py-1.5 pr-3">Plot</th><th className="font-normal pr-3">Country</th><th className="font-normal pr-3">Country risk</th>
              <th className="font-normal pr-3">Area</th><th className="font-normal pr-3">Decimals</th><th className="font-normal">Satellite reading</th>
            </tr></thead>
            <tbody>{s.plots.map(p => (
              <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                <td className="py-1.5 pr-3"><Link to={`/detail/plot/${p.plot_id}`} className="hover:text-[var(--color-sky)] hover:underline">{p.plot_name ?? p.plot_id.slice(0, 8)}</Link></td>
                <td className="pr-3 mono text-[var(--color-mute)]">{p.country ?? '—'}</td>
                <td className="pr-3 text-[var(--color-mute)]">{p.country_risk ?? '—'}</td>
                <td className="pr-3 mono text-[var(--color-mute)]">{p.area_ha != null ? `${p.area_ha} ha` : '—'}{p.has_polygon ? ' · polygon' : ' · point'}</td>
                <td className="pr-3 mono text-[var(--color-mute)]">{p.coordinate_decimals ?? '—'}</td>
                <td><StatusPill status={p.reading?.outcome ?? 'unread'} /></td>
              </tr>))}</tbody>
          </table>
        </div>
      </div>

      <div>
        <SectionHead className="mb-2">Statements</SectionHead>
        {m.filings.length === 0
          ? <p className="text-[12.5px] text-[var(--color-mute)]">{blocking.length ? 'Clear the blocking checks, then prepare the statement.' : 'Ready to prepare.'}</p>
          : <div className="space-y-2">{m.filings.map(f => <FilingRow key={f.filing_id} f={f} onChanged={refresh} />)}</div>}
      </div>

      {open === 'evidence' && <EvidenceForm rec={rec} movementId={m.movement_id} plots={s.plots} onClose={() => setOpen(null)} onDone={refresh} />}
      {open === 'risk' && <RiskForm rec={rec} movementId={m.movement_id} onClose={() => setOpen(null)} onDone={refresh} />}
      {open === 'scope' && <ScopeForm movementId={m.movement_id} why={s.scope.why} onClose={() => setOpen(null)} onDone={refresh} />}
    </Card>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex gap-3"><span className="w-[150px] shrink-0 text-[var(--color-faint)]">{k}</span><span className="text-[var(--color-ink)]">{v}</span></div>
}

function FilingRow({ f, onChanged }: { f: StatementFiling; onChanged: () => void }) {
  const [open, setOpen] = useState<null | 'reference' | 'event' | 'withdraw'>(null)
  const filed = f.status === 'submitted' || f.status === 'accepted'
  const w = useQuery({ queryKey: ['eudr-window', f.filing_id, f.status], enabled: filed,
    queryFn: () => api.get<{ window: Window; events: DdsEvent[] }>(`/v1/eudr/filings/${f.filing_id}/window`) })
  const done = () => { setOpen(null); w.refetch(); onChanged() }
  const post = (path: string, ok: string) => api.post(path, {}).then(() => { toast.success(ok); done() }).catch(e => toast.error(apiMessage(e, 'Not done.')))
  const win = w.data?.window
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-[13px]">
          <span className="font-medium">{STAGE[f.status] ?? f.status}</span>
          {f.reference_number && <span className="mono text-[12px] text-[var(--color-mute)]"> · ref {f.reference_number}{f.verification_number ? ` · ver ${f.verification_number}` : ''}</span>}
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/filings?filing=${f.filing_id}`} className="text-[12.5px] text-[var(--color-sky)] hover:underline self-center">Open in filings</Link>
          {(f.status === 'draft' || f.status === 'returned') && <Button variant="ghost" onClick={() => post(`/v1/eudr/filings/${f.filing_id}/refresh`, 'Statement refreshed from the shipment.')}>Refresh from shipment</Button>}
          {f.status === 'submitted' && <Button onClick={() => setOpen('reference')}>Record reference</Button>}
          {filed && <Button variant="ghost" onClick={() => setOpen('event')}>Record event</Button>}
          {f.status === 'accepted' && win?.open && <>
            <Button variant="ghost" onClick={() => post(`/v1/eudr/filings/${f.filing_id}/amend`, 'Amendment prepared as a new draft.')}>Amend</Button>
            <Button variant="ghost" onClick={() => setOpen('withdraw')}>Withdraw</Button>
          </>}
        </div>
      </div>
      {f.status === 'accepted' && win && (
        <div className={`text-[12px] mt-1.5 ${win.open ? 'text-[var(--color-good)]' : 'text-[var(--color-mute)]'}`}>
          {win.open ? `Amend or withdraw until ${new Date(win.closes!).toLocaleString()}` : `Can no longer be amended or withdrawn: ${win.why}`}
        </div>)}
      {(w.data?.events.length ?? 0) > 0 && (
        <ul className="mt-2 space-y-0.5">{w.data!.events.map((e, i) => (
          <li key={i} className="text-[11.5px] text-[var(--color-faint)]"><span className="mono">{new Date(e.at).toLocaleString()}</span> · {EVENT_LABEL[e.kind] ?? e.kind}
            {e.until ? ` until ${new Date(e.until).toLocaleString()}` : ''}{e.detail ? ` — ${e.detail}` : ''}</li>))}</ul>)}
      {open === 'reference' && <ReferenceForm filingId={f.filing_id} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'event' && <EventForm filingId={f.filing_id} status={f.status} onClose={() => setOpen(null)} onDone={done} />}
      {open === 'withdraw' && <WithdrawForm filingId={f.filing_id} onClose={() => setOpen(null)} onDone={done} />}
    </div>
  )
}
