import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, download, getToken } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Button, Card, StatGrid } from '../components/ui'

// Board climate-risk pack — one immutable, hashed document per period that the board reviews, and that named
// members attest to after re-authenticating. Everything shown is the pack's own stored summary.
interface Attestation { attestation_id: string; full_name: string; email: string; capacity: string; statement: string; comment: string | null; sha256: string; attested_at: string }
interface Pack { pack_id: string; version: number; period_from: string; period_to: string; basis: { scenario: string; horizon: string }; sha256: string; note: string | null
  generated_at: string; generated_by: string | null; n_attestations: number; attestations: Attestation[]
  summary: { red: number; amber: number; indicators: number; breaches_open: number; never_filed: number; due_next: number; exceptions_open: number; readiness: string; decisions: number; requests_open: number; reg_changes: number; models_active: number } }
interface Resp { packs: Pack[]; statements: Record<string, string>; sections: string[]; can_generate: boolean; can_attest: boolean }
const dt = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

export default function BoardPack() {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const me = profile?.user?.email
  const q = useQuery({ queryKey: ['board-packs'], queryFn: () => api.get<Resp>('/v1/board-pack') })
  const [busy, setBusy] = useState(false); const [note, setNote] = useState(''); const [from, setFrom] = useState(''); const [to, setTo] = useState('')
  const [attest, setAttest] = useState<Pack | null>(null)
  const d = q.data
  const generate = async () => {
    setBusy(true)
    try { const p = await api.post<{ version: number }>('/v1/board-pack', { note: note || null, period_from: from || null, period_to: to || null }); toast.success(`Board pack v${p.version} generated.`); setNote(''); await qc.invalidateQueries({ queryKey: ['board-packs'] }) }
    catch (e) { toast.error((e as Error).message || 'Could not generate the pack.') } finally { setBusy(false) }
  }
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  if (!d) return <div className="text-[12.5px] text-[var(--color-bad)]">Board packs are not available for this organisation.</div>
  const latest = d.packs[0]
  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div className="max-w-[720px]">
            <div className="text-[13px] font-medium text-[var(--color-ink)]">Board climate-risk pack</div>
            <div className="text-[12px] text-[var(--color-mute)] mt-1">One document per period, generated from the same engine results the screens show: indicators against the board's appetite, breach episodes, filings and obligations, controls, decisions, supervision, regulatory change and the models behind the figures. Each version is immutable with its content hash; board or committee members attest to that hash by name after re-authenticating, and the attestation record prints on the pack.</div>
          </div>
          {d.can_generate && (
            <div className="flex items-end gap-2 flex-wrap">
              <label className="text-[10.5px] mono uppercase tracking-wide text-[var(--color-faint)]">From<input type="date" value={from} onChange={e => setFrom(e.target.value)} className={inp + ' mt-1 w-40'} /></label>
              <label className="text-[10.5px] mono uppercase tracking-wide text-[var(--color-faint)]">To<input type="date" value={to} onChange={e => setTo(e.target.value)} className={inp + ' mt-1 w-40'} /></label>
              <input value={note} onChange={e => setNote(e.target.value)} placeholder="Note (e.g. Q3 board meeting)" className={inp + ' w-56'} />
              <Button onClick={generate} disabled={busy}>{busy ? 'Generating…' : 'Generate pack'}</Button>
            </div>)}
        </div>
        <div className="text-[11px] text-[var(--color-faint)] mt-2">Leave the dates blank for the last 90 days.</div>
      </Card>
      {latest && (
        <StatGrid cols={4} items={[
          { label: 'Indicators red / amber', value: `${latest.summary.red} / ${latest.summary.amber}`, sub: `${latest.summary.indicators} indicators · pack v${latest.version}`, accent: latest.summary.red ? 'var(--color-bad)' : latest.summary.amber ? 'var(--color-warn)' : 'var(--color-good)' },
          { label: 'Breach episodes open', value: String(latest.summary.breaches_open), sub: `${latest.summary.decisions} decisions in the period`, accent: latest.summary.breaches_open ? 'var(--color-warn)' : undefined },
          { label: 'Filings', value: latest.summary.never_filed ? `${latest.summary.never_filed} never filed` : 'all filed', sub: `${latest.summary.due_next} due in 120 days · readiness ${latest.summary.readiness}`, accent: latest.summary.never_filed ? 'var(--color-warn)' : 'var(--color-good)' },
          { label: 'Supervision', value: `${latest.summary.requests_open} open`, sub: `${latest.summary.reg_changes} regulatory changes · ${latest.summary.models_active} active models` },
        ]} />)}
      <Card className="p-5">
        <div className="text-[13px] font-medium text-[var(--color-ink)] mb-2">Versions</div>
        {d.packs.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No pack generated yet.</div> : (
          <div className="divide-y divide-[var(--color-line)]">{d.packs.map(p => (
            <div key={p.pack_id} className="py-2.5 text-[12.5px]">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="mono text-[11px] text-[var(--color-ink)] w-8">v{p.version}</span>
                <span className="text-[var(--color-ink)]">{p.period_from} → {p.period_to}</span>
                <span className="text-[var(--color-mute)]">{p.basis.scenario} · {p.basis.horizon}{p.note ? ` · ${p.note}` : ''}</span>
                <span className="mono text-[10.5px] text-[var(--color-faint)]" title={p.sha256}>sha256 {p.sha256.slice(0, 12)}… · {dt(p.generated_at)} · {p.generated_by ?? '—'}</span>
                <span className="mono text-[10.5px] ml-auto" style={{ color: p.n_attestations ? 'var(--color-good)' : 'var(--color-faint)' }}>{p.n_attestations ? `${p.n_attestations} attestation${p.n_attestations === 1 ? '' : 's'}` : 'not attested'}</span>
                <button onClick={() => download(`/v1/board-pack/${p.pack_id}.pdf`, `board-pack-v${p.version}.pdf`)} className="text-[var(--color-sky)] hover:underline">PDF ↓</button>
                <button onClick={() => download(`/v1/board-pack/${p.pack_id}.json`, `board-pack-v${p.version}.json`)} className="text-[var(--color-sky)] hover:underline">JSON ↓</button>
                {d.can_attest && !p.attestations.some(a => a.email === me) && <button onClick={() => setAttest(p)} className="text-[var(--color-sky)] hover:underline font-medium">Attest →</button>}
              </div>
              {p.attestations.length > 0 && <div className="mt-1 pl-11 space-y-0.5">{p.attestations.map(a => (
                <div key={a.attestation_id} className="text-[11.5px] text-[var(--color-mute)]"><span className="text-[var(--color-ink)]">{a.full_name}</span> · {a.capacity} · {d.statements[a.statement] ?? a.statement}{a.comment ? ` “${a.comment}”` : ''} · <span className="mono text-[10.5px]">{dt(a.attested_at)}</span></div>))}</div>}
            </div>))}</div>)}
      </Card>
      {attest && <AttestDialog pack={attest} statements={d.statements} onClose={() => setAttest(null)} />}
    </div>
  )
}

// Attest = name + capacity + statement, bound to the pack's hash after step-up re-authentication (password and,
// where enrolled, the authenticator code). The step-up token is used once and never stored.
function AttestDialog({ pack, statements, onClose }: { pack: Pack; statements: Record<string, string>; onClose: () => void }) {
  const qc = useQueryClient()
  const [capacity, setCapacity] = useState(''); const [statement, setStatement] = useState('reviewed'); const [comment, setComment] = useState('')
  const [pw, setPw] = useState(''); const [otp, setOtp] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)
  const submit = async () => {
    setBusy(true); setErr(null)
    try {
      const su = await api.post<{ step_up_token: string }>('/v1/auth/step-up', { password: pw, otp: otp || null })
      const token = getToken() ?? ''
      const res = await fetch(`/v1/board-pack/${pack.pack_id}/attest`, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}`, 'X-Step-Up': su.step_up_token },
        body: JSON.stringify({ capacity, statement, comment: comment || null }) })
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j?.error?.message ?? j?.detail?.message ?? 'Could not record the attestation.') }
      toast.success(`Attested pack v${pack.version}.`); await qc.invalidateQueries({ queryKey: ['board-packs'] }); onClose()
    } catch (e) { setErr((e as Error).message || 'Could not record the attestation.') } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[560px] rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Attestation · board pack v{pack.version} · {pack.period_from} → {pack.period_to}</div>
        <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">Attest this pack by name</h2>
        <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-4">Your attestation binds you, in the capacity you state, to content hash <span className="mono text-[11px]">{pack.sha256.slice(0, 16)}…</span>. It is recorded on the audit trail and printed on the pack. Re-authenticate to confirm.</p>
        <div className="space-y-3">
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Capacity<input value={capacity} onChange={e => setCapacity(e.target.value)} placeholder="e.g. Chair of the Risk Committee" className={inp + ' mt-1'} /></label>
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Statement<select value={statement} onChange={e => setStatement(e.target.value)} className={inp + ' mt-1'}>{Object.entries(statements).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Comment{statement === 'reviewed_with_reservations' ? ' (required)' : ' (optional)'}<textarea value={comment} onChange={e => setComment(e.target.value)} rows={2} className={inp + ' mt-1'} /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Password<input type="password" value={pw} onChange={e => setPw(e.target.value)} className={inp + ' mt-1'} /></label>
            <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Authenticator code (if enrolled)<input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" className={inp + ' mt-1'} /></label>
          </div>
          {err && <div className="text-[12.5px] text-[var(--color-bad)]">{err}</div>}
          <div className="flex justify-end gap-2 pt-1"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={submit} disabled={busy || !capacity || !pw}>{busy ? 'Recording…' : 'Attest'}</Button></div>
        </div>
      </div>
    </div>
  )
}
