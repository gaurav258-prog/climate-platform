import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { BrandMark, Button } from '../components/ui'

const DEMOS = [
  { label: 'Terra · Agriculture', email: 'analyst@terra.demo', pw: 'Demo!analyst1' },
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
          <p className="text-[13px] text-[var(--color-mute)] mt-1 mb-5">Agriculture · supply-chain risk workspace</p>

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
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-faint)] mb-2">Demo account</div>
          {DEMOS.map(d => (
            <button key={d.email} onClick={() => { setEmail(d.email); setPw(d.pw) }}
              className="w-full text-left card px-4 py-2.5 text-[13px] hover:border-[var(--color-sky)] transition">
              {d.label} <span className="text-[var(--color-faint)] mono text-[11px]">· {d.email}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
