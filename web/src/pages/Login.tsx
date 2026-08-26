import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { ApiError } from '../lib/api'
import { BrandMark, Button } from '../components/ui'

function errCode(e: unknown): string | undefined {
  if (e instanceof ApiError) {
    const b = e.body as { error?: { error?: string } } | undefined
    return b?.error?.error
  }
  return undefined
}

// one demo tenant per sector; pick the ROLE first, then a sector — every tenant has all three roles,
// so you can sign in as the approver to see the maker-checker decision + assignment flow.
const ROLE_PW: Record<string, string> = { admin: 'Demo!admin1', analyst: 'Demo!analyst1', approver: 'Demo!approve1' }
const ROLES: { key: string; label: string; hint: string }[] = [
  { key: 'admin', label: 'Admin', hint: 'setup, users, everything' },
  { key: 'approver', label: 'Approver', hint: 'the 2nd pair of eyes — approve / reject / send back / assign' },
  { key: 'analyst', label: 'Analyst', hint: 'data & filings, raises approvals' },
]
const DEMOS = [
  { label: 'Bank', sub: 'financed assets', tenant: 'meridian' },
  { label: 'Insurer', sub: 'insured locations', tenant: 'iberia' },
  { label: 'Asset manager', sub: 'holdings', tenant: 'nordkap' },
  { label: 'REIT', sub: 'properties', tenant: 'stellar' },
  { label: 'Agriculture', sub: 'sites & origins', tenant: 'terra' },
]

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [role, setRole] = useState('admin')
  const [mfa, setMfa] = useState(false)   // second factor required for this account
  const [otp, setOtp] = useState('')

  async function submit(e?: React.FormEvent) {
    e?.preventDefault()
    setBusy(true); setErr(null)
    try { await login(email.trim(), pw, mfa ? otp.trim() : undefined) }
    catch (e) {
      const code = errCode(e)
      if (code === 'mfa_required') { setMfa(true); setErr(null) }
      else if (code === 'mfa_invalid') { setMfa(true); setErr("That code didn't match. Try again.") }
      else setErr('Email or password is incorrect.')
    }
    finally { setBusy(false) }
  }

  async function demoLogin(tenant: string) {
    setBusy(true); setErr(null)
    try { await login(`${role}@${tenant}.demo`, ROLE_PW[role]) }  // login() reloads on success
    catch { setErr(`Could not open the demo tenant as ${role}.`); setBusy(false) }
  }

  return (
    <div className="min-h-screen grid place-items-center px-6"
      style={{ background: 'radial-gradient(1200px 600px at 50% -10%, #0e1a30 0%, var(--color-bg) 60%)' }}>
      <div className="w-full max-w-[380px] fadeup">
        <div className="flex items-center gap-3 mb-8">
          <BrandMark size={40} />
          <div>
            <div className="display text-2xl font-semibold leading-none">
              Tel<span className="text-[var(--color-sky)]">lumen</span>
            </div>
            <div className="mono text-[10px] tracking-[0.25em] text-[var(--color-blue)] mt-1">LIGHT ON THE EARTH</div>
          </div>
        </div>

        <form onSubmit={submit} className="card p-6">
          <h1 className="display text-lg font-semibold m-0">Sign in</h1>
          <p className="text-[13px] text-[var(--color-mute)] mt-1 mb-5">Physical climate-risk workspace · every sector</p>

          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Email</label>
          <input value={email} onChange={e => setEmail(e.target.value)} type="email" autoComplete="username"
            className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)] mb-4"
            placeholder="you@company.com" />

          <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Password</label>
          <input value={pw} onChange={e => setPw(e.target.value)} type="password" autoComplete="current-password"
            className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)] mb-5"
            placeholder="••••••••" />

          {mfa && (
            <div className="mb-5">
              <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Authenticator code</label>
              <input value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))} inputMode="numeric" autoFocus
                className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)] tracking-[0.4em] text-center"
                placeholder="123456" />
              <p className="text-[11px] text-[var(--color-faint)] mt-1.5">Enter the 6-digit code from your authenticator app.</p>
            </div>
          )}

          {err && <div className="text-[13px] text-[var(--color-bad)] mb-4">{err}</div>}
          <Button variant="primary" disabled={busy || !email || !pw || (mfa && otp.length < 6)} className="w-full justify-center">
            {busy ? 'Signing in…' : mfa ? 'Verify & sign in →' : 'Sign in →'}
          </Button>
        </form>

        <div className="mt-5">
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-faint)] mb-2">Jump into a demo sector</div>
          {/* pick the role first — approver reaches the maker-checker decision + assignment flow */}
          <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line)] mb-1">
            {ROLES.map(rr => (
              <button key={rr.key} onClick={() => setRole(rr.key)} type="button"
                className={`flex-1 rounded-md py-1.5 mono text-[11px] transition ${role === rr.key ? 'bg-[var(--color-bg-2)] text-[var(--color-sky)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{rr.label}</button>
            ))}
          </div>
          <div className="mono text-[10px] text-[var(--color-faint)] mb-2.5 h-3.5">{ROLES.find(r => r.key === role)?.hint}</div>
          <div className="flex flex-col gap-2">
            {DEMOS.map(d => (
              <button key={d.tenant} onClick={() => demoLogin(d.tenant)} disabled={busy}
                className="w-full text-left card px-4 py-2.5 hover:border-[var(--color-sky)] transition disabled:opacity-60 flex items-center justify-between gap-3">
                <span>
                  <span className="text-[13px] text-[var(--color-ink)]">{d.label}</span>
                  <span className="text-[var(--color-faint)] mono text-[11px]"> · {d.sub}</span>
                </span>
                <span className="mono text-[11px] text-[var(--color-sky)] shrink-0">open as {role} →</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
