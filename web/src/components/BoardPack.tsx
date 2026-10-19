import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileSignature, Stamp, Users } from 'lucide-react'
import { api, apiDetail, apiMessage, download, getToken } from '../lib/api'
import { horizonLabel, scenarioLabel } from '../lib/hazards'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Button, Card, SectionHead, StatGrid } from '../components/ui'
import { HEADING, InfoButton, MessageLine, type Message, type DetailSection } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog, CloseButton } from './Dialog'
import { version } from './filing/words'

// The board climate-risk pack: one unchangeable, fingerprinted document per period that the board reviews, and that
// named members attest to after signing in again. Everything shown is the pack's own stored summary.
interface Attestation { attestation_id: string; full_name: string; email: string; capacity: string; statement: string; comment: string | null; attested_at: string }
interface Pack { pack_id: string; version: number; period_from: string; period_to: string; basis: { scenario: string; horizon: string }; sha256: string; note: string | null
  generated_at: string; generated_by: string | null; n_attestations: number; attestations: Attestation[]
  summary: { red: number; amber: number; indicators: number; breaches_open: number; never_filed: number; due_next: number; due_window_days: number; exceptions_open: number; readiness: string; decisions: number; requests_open: number; reg_changes: number; models_active: number } }
interface Resp { packs: Pack[]; statements: Record<string, string>; can_generate: boolean; can_attest: boolean }
const day = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
const when = (s: string) => new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
const field = 'text-[12px] text-[var(--color-mute)]'

export default function BoardPack() {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const me = profile?.user?.email
  const q = useQuery({ queryKey: ['board-packs'], queryFn: () => api.get<Resp>('/v1/board-pack') })
  const [busy, setBusy] = useState(false); const [note, setNote] = useState(''); const [from, setFrom] = useState(''); const [to, setTo] = useState('')
  const [err, setErr] = useState<Message | null>(null)
  const [attest, setAttest] = useState<Pack | null>(null)
  const d = q.data
  const generate = async () => {
    setBusy(true); setErr(null)
    try { const p = await api.post<{ version: number }>('/v1/board-pack', { note: note || null, period_from: from || null, period_to: to || null }); toast.success(`Board pack ${version(p.version).toLowerCase()} generated.`); setNote(''); await qc.invalidateQueries({ queryKey: ['board-packs'] }) }
    catch (e) { setErr({ label: apiMessage(e, 'Could not generate the pack'), detail: apiDetail(e) }) } finally { setBusy(false) }
  }
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
  if (!d) return <MessageLine m={{ label: apiMessage(q.error, 'Board packs are not available'), detail: apiDetail(q.error) }} className="text-[12.5px] text-[var(--color-bad)]" />
  const latest = d.packs[0]
  const [passed, total] = (latest?.summary.readiness ?? '').split('/')
  return (
    <div className="space-y-5">
      <Card className="p-5 space-y-3">
        <div className="flex items-center gap-1.5">
          <SectionHead icon={FileSignature}>Board climate-risk pack</SectionHead>
          <InfoButton compact details={{ title: 'Board climate-risk pack', sections: [
            { heading: HEADING.shows, body: "One document per period, made from the same results the screens show: indicators against the board's appetite, breach episodes, filings and obligations, controls, decisions, supervision, regulatory change and the models behind the figures." },
            { heading: HEADING.read, body: 'Each version is unchangeable and fingerprinted. Board or committee members attest to it by name after signing in again, and the attestations print on the pack.' }] }} />
        </div>
        {d.can_generate && (
          <div className="flex items-end gap-2 flex-wrap">
            <label className={field}>From<input type="date" value={from} onChange={e => setFrom(e.target.value)} className={inp + ' mt-1 w-40'} /></label>
            <label className={field}>To<input type="date" value={to} onChange={e => setTo(e.target.value)} className={inp + ' mt-1 w-40'} /></label>
            <label className={`${field} flex-1 min-w-[200px]`}>Note<input value={note} onChange={e => setNote(e.target.value)} placeholder="For example Q3 board meeting" className={inp + ' mt-1'} /></label>
            <Button onClick={generate} disabled={busy}>{busy ? 'Generating…' : 'Generate pack'}</Button>
            <InfoButton compact details={{ title: 'The period', sections: [{ heading: HEADING.read, body: 'Leave the dates blank for the last 90 days.' }] }} />
          </div>)}
        {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}
      </Card>
      {latest && (
        <StatGrid cols={4} items={[
          { label: 'Indicators red / amber', value: `${latest.summary.red} / ${latest.summary.amber}`, sub: `of ${latest.summary.indicators} · ${version(latest.version).toLowerCase()}`, accent: latest.summary.red ? 'var(--color-bad)' : latest.summary.amber ? 'var(--color-warn)' : 'var(--color-good)' },
          { label: 'Breach episodes open', value: String(latest.summary.breaches_open), sub: `${latest.summary.decisions} decisions in the period`, accent: latest.summary.breaches_open ? 'var(--color-warn)' : undefined },
          { label: 'Filings never filed', value: String(latest.summary.never_filed), sub: `${latest.summary.due_next} due in ${latest.summary.due_window_days} days · readiness ${passed ?? '—'} of ${total ?? '—'}`, accent: latest.summary.never_filed ? 'var(--color-warn)' : 'var(--color-good)' },
          { label: 'Supervisory requests open', value: String(latest.summary.requests_open), sub: `${latest.summary.reg_changes} regulatory changes · ${latest.summary.models_active} models in use` },
        ]} />)}
      <Card className="p-5">
        <SectionHead icon={Users} className="mb-2">Versions</SectionHead>
        {d.packs.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No pack generated yet.</div> : (
          <div className="divide-y divide-[var(--color-line)]">{d.packs.map(p => {
            const about: DetailSection[] = [
              { heading: 'Scenario', body: `${scenarioLabel(p.basis.scenario)}, ${horizonLabel(p.basis.horizon)}` },
              ...(p.note ? [{ heading: 'Note', body: p.note }] : []),
              { heading: 'Generated', body: `${when(p.generated_at)}${p.generated_by ? ` by ${p.generated_by}` : ''}` },
              { heading: 'Fingerprint', body: <span className="mono text-[11.5px] break-all">{p.sha256}</span> },
              ...(p.attestations.length ? [{ heading: 'Attestations', body: <ul className="space-y-1">{p.attestations.map(a => <li key={a.attestation_id}>{`${a.full_name}, ${a.capacity} · ${d.statements[a.statement] ?? 'Attested'} · ${when(a.attested_at)}`}{a.comment ? ` · “${a.comment}”` : ''}</li>)}</ul> }] : []),
            ]
            return (
              <div key={p.pack_id} className="py-2.5 text-[12.5px] flex items-center gap-3 flex-wrap">
                <StatusChip tone="neutral" label={version(p.version)} />
                <span className="text-[var(--color-ink)]">{day(p.period_from)} to {day(p.period_to)}</span>
                <InfoButton compact details={{ title: `Board pack · ${version(p.version).toLowerCase()}`, sections: about }} />
                <StatusChip tone={p.n_attestations ? 'good' : 'neutral'} label={p.n_attestations ? `${p.n_attestations} ${p.n_attestations === 1 ? 'attestation' : 'attestations'}` : 'Not attested'} />
                <span className="ml-auto inline-flex items-center gap-3">
                  <button onClick={() => download(`/v1/board-pack/${p.pack_id}.pdf`, `board-pack-v${p.version}.pdf`)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><Download size={12} /> PDF</button>
                  <button onClick={() => download(`/v1/board-pack/${p.pack_id}.json`, `board-pack-v${p.version}.json`)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><Download size={12} /> JSON</button>
                  {d.can_attest && !p.attestations.some(a => a.email === me) && <button onClick={() => setAttest(p)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline font-medium"><Stamp size={12} /> Attest</button>}
                </span>
              </div>)
          })}</div>)}
      </Card>
      {attest && <AttestDialog pack={attest} statements={d.statements} onClose={() => setAttest(null)} />}
    </div>
  )
}

// Attest = name + capacity + statement, bound to the pack's fingerprint after signing in again (password and, where
// enrolled, the authenticator code). The one-time token is used once and never stored.
function AttestDialog({ pack, statements, onClose }: { pack: Pack; statements: Record<string, string>; onClose: () => void }) {
  const qc = useQueryClient()
  const [capacity, setCapacity] = useState(''); const [statement, setStatement] = useState('reviewed'); const [comment, setComment] = useState('')
  const [pw, setPw] = useState(''); const [otp, setOtp] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState<Message | null>(null)
  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const su = await api.post<{ step_up_token: string }>('/v1/auth/step-up', { password: pw, otp: otp || null })
      const res = await fetch(`/v1/board-pack/${pack.pack_id}/attest`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken() ?? ''}`, 'X-Step-Up': su.step_up_token },
        body: JSON.stringify({ capacity, statement, comment: comment || null }) })
      if (!res.ok) {
        const j = await res.json().catch(() => ({}))
        setErr({ label: j?.error?.message ?? 'Could not record the attestation', detail: j?.error?.detail ?? null }); return
      }
      toast.success(`Attested ${version(pack.version).toLowerCase()}.`); await qc.invalidateQueries({ queryKey: ['board-packs'] }); onClose()
    } catch (e) { setErr({ label: apiMessage(e, 'Could not record the attestation'), detail: apiDetail(e) }) } finally { setBusy(false) }
  }
  return (
    <Dialog bare title="Attest this pack by name" onClose={onClose} className="w-full max-w-[560px] rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl">
      <CloseButton onClick={onClose} className="absolute top-4 right-4" />
      <div className="text-[12px] text-[var(--color-blue)] mb-1">Board pack · {version(pack.version).toLowerCase()} · {day(pack.period_from)} to {day(pack.period_to)}</div>
      <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)] flex items-center gap-2">Attest this pack by name
        <InfoButton compact details={{ title: 'Attesting', sections: [
          { heading: HEADING.shows, body: 'Your attestation binds you, in the capacity you state, to this exact version of the pack (its fingerprint). It is recorded on the audit trail and printed on the pack.' },
          { heading: 'Fingerprint', body: <span className="mono text-[11.5px] break-all">{pack.sha256}</span> },
          { heading: HEADING.read, body: 'Sign in again to confirm it is you.' }] }} /></h2>
      <div className="space-y-3 mt-4">
        <label className={`block ${field}`}>Capacity<input value={capacity} onChange={e => setCapacity(e.target.value)} placeholder="For example Chair of the Risk Committee" className={inp + ' mt-1'} /></label>
        <label className={`block ${field}`}>Statement<select value={statement} onChange={e => setStatement(e.target.value)} className={inp + ' mt-1'}>{Object.entries(statements).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label className={`block ${field}`}>Comment{statement === 'reviewed_with_reservations' ? ' (required)' : ' (optional)'}<textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} className={inp + ' mt-1'} /></label>
        <div className="grid grid-cols-2 gap-3">
          <label className={field}>Password<input type="password" value={pw} onChange={e => setPw(e.target.value)} className={inp + ' mt-1'} /></label>
          <label className={field}>Authenticator code<input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" placeholder="If enrolled" className={inp + ' mt-1'} /></label>
        </div>
        {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}
        <div className="flex justify-end gap-2 pt-1"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={busy || !capacity || !pw}>{busy ? 'Recording…' : 'Attest'}</Button></div>
      </div>
    </Dialog>
  )
}
