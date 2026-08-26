import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, ShieldCheck, KeyRound } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { BrandMark } from '../components/ui'

interface Activation { email: string; full_name: string | null; org_name: string; password_set: boolean; mfa_enrolled: boolean }
function msg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return (e.body as { error?: { message?: string } })?.error?.message ?? fallback
  return fallback
}
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'

export default function Activate() {
  const { token = '' } = useParams()
  const [a, setA] = useState<Activation | null>(null)
  const [step, setStep] = useState<'loading' | 'invalid' | 'password' | 'mfa' | 'done'>('loading')
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState('')
  const [mfa, setMfa] = useState<{ qr_data_uri: string | null; secret: string } | null>(null)
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.get<Activation>(`/v1/onboarding/activate/${token}`).then(d => {
      setA(d)
      setStep(!d.password_set ? 'password' : !d.mfa_enrolled ? 'mfa' : 'done')
    }).catch(() => setStep('invalid'))
  }, [token])

  useEffect(() => { if (step === 'mfa' && !mfa) beginMfa() }, [step]) // eslint-disable-line react-hooks/exhaustive-deps

  async function setPassword() {
    setErr(null)
    if (pw.length < 10) { setErr('Use at least 10 characters.'); return }
    if (pw !== pw2) { setErr('Passwords don’t match.'); return }
    setBusy(true)
    try { await api.post(`/v1/onboarding/activate/${token}/password`, { password: pw }); setStep('mfa') }
    catch (e) { setErr(msg(e, 'Could not set your password.')) } finally { setBusy(false) }
  }
  async function beginMfa() {
    try { setMfa(await api.post(`/v1/onboarding/activate/${token}/mfa/begin`)) }
    catch (e) { setErr(msg(e, 'Could not start two-factor setup.')) }
  }
  async function confirmMfa() {
    setErr(null); setBusy(true)
    try { await api.post(`/v1/onboarding/activate/${token}/mfa/confirm`, { code }); setStep('done') }
    catch (e) { setErr(msg(e, 'That code didn’t match — try again.')) } finally { setBusy(false) }
  }

  return (
    <Frame>
      {step === 'loading' && <p className="text-[var(--color-faint)] text-sm">Loading…</p>}
      {step === 'invalid' && <Panel title="This activation link is invalid or has expired"
        body="Ask your administrator to re-send your invitation, then open the new link." />}

      {step === 'password' && a && (
        <div>
          <Head icon={<KeyRound size={20} />} eyebrow={`${a.org_name} · activate your account`} title={`Welcome${a.full_name ? `, ${a.full_name.split(' ')[0]}` : ''}`}
            sub={`Set a password for ${a.email}.`} />
          <div className="space-y-3 mt-5">
            <Field label="New password"><input type="password" className={inp} value={pw} onChange={e => setPw(e.target.value)} placeholder="At least 10 characters" /></Field>
            <Field label="Confirm password"><input type="password" className={inp} value={pw2} onChange={e => setPw2(e.target.value)} /></Field>
          </div>
          {err && <div className="text-[13px] text-[var(--color-bad)] mt-3">{err}</div>}
          <Btn onClick={setPassword} busy={busy} disabled={!pw || !pw2}>Continue →</Btn>
        </div>
      )}

      {step === 'mfa' && a && (
        <div>
          <Head icon={<ShieldCheck size={20} />} eyebrow={`${a.org_name} · two-factor authentication`} title="Secure your account"
            sub="Scan this with an authenticator app (Google Authenticator, Authy, 1Password, Microsoft Authenticator), then enter the 6-digit code. This is required." />
          <div className="mt-5 flex flex-col items-center gap-3">
            {mfa?.qr_data_uri
              ? <img src={mfa.qr_data_uri} alt="Scan to set up two-factor" className="w-44 h-44 rounded-lg bg-white p-2" />
              : <p className="text-[12px] text-[var(--color-faint)]">Preparing…</p>}
            {mfa?.secret && <div className="text-center">
              <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Can’t scan? Enter this key</div>
              <div className="mono text-[12px] text-[var(--color-ink)] break-all">{mfa.secret}</div>
            </div>}
            <input value={code} onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric"
              className={inp + ' tracking-[0.4em] text-center max-w-[200px]'} placeholder="123456" />
          </div>
          {err && <div className="text-[13px] text-[var(--color-bad)] mt-3 text-center">{err}</div>}
          <Btn onClick={confirmMfa} busy={busy} disabled={code.length < 6}>Verify & finish →</Btn>
        </div>
      )}

      {step === 'done' && (
        <div className="text-center py-4">
          <CheckCircle2 size={40} className="text-[var(--color-good)] mx-auto mb-3" />
          <h1 className="display text-xl font-semibold m-0">You’re all set</h1>
          <p className="text-[13px] text-[var(--color-mute)] mt-2 max-w-[40ch] mx-auto">Your account is active and protected with two-factor authentication. Sign in to get started.</p>
          <a href="/" className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition mt-5">Go to sign in →</a>
        </div>
      )}
    </Frame>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen grid place-items-center px-6" style={{ background: 'radial-gradient(1200px 600px at 50% -10%, #0e1a30 0%, var(--color-bg) 60%)' }}>
      <div className="w-full max-w-[420px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={34} />
          <div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div>
        </div>
        <div className="card p-6">{children}</div>
      </div>
    </div>
  )
}
function Head({ icon, eyebrow, title, sub }: { icon: React.ReactNode; eyebrow: string; title: string; sub: string }) {
  return (
    <div>
      <div className="text-[var(--color-sky)] mb-2">{icon}</div>
      <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">{eyebrow}</div>
      <h1 className="display text-xl font-semibold m-0">{title}</h1>
      <p className="text-[13px] text-[var(--color-mute)] mt-1.5">{sub}</p>
    </div>
  )
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">{label}</label>{children}</div>
}
function Btn({ children, onClick, busy, disabled }: { children: React.ReactNode; onClick: () => void; busy: boolean; disabled?: boolean }) {
  return <button onClick={onClick} disabled={busy || disabled}
    className="w-full justify-center inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition disabled:opacity-60 mt-5">
    {busy ? 'Working…' : children}
  </button>
}
function Panel({ title, body }: { title: string; body: string }) {
  return <div className="text-center py-4"><h1 className="display text-xl font-semibold m-0">{title}</h1><p className="text-[13px] text-[var(--color-mute)] mt-2">{body}</p></div>
}
