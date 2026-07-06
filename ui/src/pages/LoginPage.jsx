import { useState } from 'react'
import { ArrowLeft, ArrowRight, Loader2, Lock } from 'lucide-react'
import { login as apiLogin } from '../api/client'

// Demo accounts — shown as click-to-prefill chips so a reviewer can experience
// each tenant and role without hunting for credentials.
const DEMO = [
  { email: 'admin@meridian.demo',    pw: 'Demo!admin1',   label: 'Meridian · Admin' },
  { email: 'analyst@meridian.demo',  pw: 'Demo!analyst1', label: 'Meridian · Analyst' },
  { email: 'approver@meridian.demo', pw: 'Demo!approve1', label: 'Meridian · Approver' },
  { email: 'admin@iberia.demo',      pw: 'Demo!admin1',   label: 'Iberia · Admin' },
  { email: 'analyst@terra.demo',     pw: 'Demo!analyst1', label: 'Terra · Agri' },
  { email: 'admin@stellar.demo',     pw: 'Demo!admin1',   label: 'Stellar · Admin' },
]

export default function LoginPage({ onSuccess, onHome }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState(null)
  const [busy, setBusy] = useState(false)

  async function submit(e) {
    e?.preventDefault()
    setErr(null); setBusy(true)
    try {
      const auth = await apiLogin(email.trim(), password)
      onSuccess(auth)
    } catch (e) {
      setErr(e?.status === 401 ? 'Email or password is incorrect.' : (e.message || 'Login failed.'))
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen flex-col bg-[#f5f5f7] text-[#1d1d1f]">
      <nav className="flex items-center justify-between px-8 py-4">
        <button onClick={onHome} className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
          <ArrowLeft size={16} className="text-gray-400" />
          <span>Tel<span className="text-[#0071e3]">lumen</span></span>
        </button>
      </nav>

      <div className="flex flex-1 items-center justify-center px-6">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl bg-[#0071e3]/10 text-[#0071e3]">
              <Lock size={20} />
            </span>
            <h1 className="mt-4 text-2xl font-semibold tracking-tight">Sign in to your workspace</h1>
            <p className="mt-1 text-[14px] text-gray-500">Light on the Earth — your risk platform, scoped to your organization.</p>
          </div>

          <form onSubmit={submit} className="rounded-2xl border border-gray-200/70 bg-white p-6 shadow-sm">
            <label className="block text-[12px] font-medium text-gray-500">Email</label>
            <input type="email" autoComplete="username" value={email} onChange={e => setEmail(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]"
              placeholder="you@company.com" />

            <label className="mt-4 block text-[12px] font-medium text-gray-500">Password</label>
            <input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]"
              placeholder="••••••••" />

            {err && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{err}</p>}

            <button type="submit" disabled={busy || !email || !password}
              className="mt-5 flex w-full items-center justify-center gap-2 rounded-full bg-[#0071e3] px-5 py-2.5 text-[14px] font-medium text-white transition hover:brightness-110 disabled:opacity-50">
              {busy ? <><Loader2 size={16} className="animate-spin" /> Signing in…</> : <>Sign in <ArrowRight size={16} /></>}
            </button>
          </form>

          <div className="mt-5">
            <p className="text-center text-[11px] uppercase tracking-[0.15em] text-gray-400">Demo accounts — click to fill</p>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {DEMO.map(d => (
                <button key={d.email} onClick={() => { setEmail(d.email); setPassword(d.pw); setErr(null) }}
                  className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-[12px] text-gray-600 transition hover:border-[#0071e3] hover:text-[#1d1d1f]">
                  {d.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
