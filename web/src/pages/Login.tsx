import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { BrandMark, Button } from '../components/ui'

// one demo tenant per sector — clicking signs straight in as that sector's admin
const DEMO_PW = 'Demo!admin1'
const DEMOS = [
  { label: 'Bank', sub: 'financed assets', email: 'admin@meridian.demo' },
  { label: 'Insurer', sub: 'insured locations', email: 'admin@iberia.demo' },
  { label: 'Asset manager', sub: 'holdings', email: 'admin@nordkap.demo' },
  { label: 'REIT', sub: 'properties', email: 'admin@stellar.demo' },
  { label: 'Agriculture', sub: 'sites & origins', email: 'admin@terra.demo' },
]

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e?: React.FormEvent) {
    e?.preventDefault()
    setBusy(true); setErr(null)
    try { await login(email.trim(), pw) }
    catch { setErr('Email or password is incorrect.') }
    finally { setBusy(false) }
  }

  async function demoLogin(demoEmail: string) {
    setBusy(true); setErr(null)
    try { await login(demoEmail, DEMO_PW) }  // login() reloads on success
    catch { setErr('Could not open the demo tenant.'); setBusy(false) }
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

          {err && <div className="text-[13px] text-[var(--color-bad)] mb-4">{err}</div>}
          <Button variant="primary" disabled={busy || !email || !pw} className="w-full justify-center">
            {busy ? 'Signing in…' : 'Sign in →'}
          </Button>
        </form>

        <div className="mt-5">
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-faint)] mb-2">Jump into a demo sector</div>
          <div className="flex flex-col gap-2">
            {DEMOS.map(d => (
              <button key={d.email} onClick={() => demoLogin(d.email)} disabled={busy}
                className="w-full text-left card px-4 py-2.5 hover:border-[var(--color-sky)] transition disabled:opacity-60 flex items-center justify-between gap-3">
                <span>
                  <span className="text-[13px] text-[var(--color-ink)]">{d.label}</span>
                  <span className="text-[var(--color-faint)] mono text-[11px]"> · {d.sub}</span>
                </span>
                <span className="mono text-[11px] text-[var(--color-sky)] shrink-0">open →</span>
              </button>
            ))}
          </div>
          <div className="mono text-[10px] text-[var(--color-faint)] mt-2">one-click sign-in as each sector's admin</div>
        </div>
      </div>
    </div>
  )
}
