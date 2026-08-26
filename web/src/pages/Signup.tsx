import { useState } from 'react'
import { api, ApiError, setToken, setRefreshToken } from '../lib/api'
import { BrandMark } from '../components/ui'

function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'
const SECTORS = [['bank', 'Bank'], ['insurer', 'Insurer'], ['asset_manager', 'Asset manager'], ['reit', 'REIT'], ['manufacturer', 'Manufacturer / agri']]

export default function Signup() {
  const [f, setF] = useState({ company_name: '', org_type: 'bank', country: '', admin_email: '', admin_full_name: '', password: '' })
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)
  const set = (k: string, v: string) => setF(p => ({ ...p, [k]: v }))

  async function submit(e?: React.FormEvent) {
    e?.preventDefault(); setErr(null)
    if (!f.company_name || !f.admin_email || f.password.length < 10 || !f.country) { setErr('Fill every field; password ≥ 10 characters.'); return }
    setBusy(true)
    try {
      const d = await api.post<{ access_token: string; refresh_token: string }>('/v1/signup', f)
      setToken(d.access_token); setRefreshToken(d.refresh_token)
      window.location.href = '/'   // land in the fresh workspace
    } catch (e) { setErr(msg(e, 'Could not create your workspace.')); setBusy(false) }
  }

  return (
    <div className="min-h-screen grid place-items-center px-6 py-10" style={{ background: 'radial-gradient(1200px 600px at 50% -10%, #0e1a30 0%, var(--color-bg) 60%)' }}>
      <div className="w-full max-w-[440px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={36} />
          <div><div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div>
            <div className="mono text-[10px] tracking-[0.25em] text-[var(--color-blue)] mt-0.5">START A 14-DAY TRIAL</div></div>
        </div>
        <form onSubmit={submit} className="card p-6 space-y-3">
          <h1 className="display text-lg font-semibold m-0">Create your workspace</h1>
          <p className="text-[13px] text-[var(--color-mute)] -mt-1 mb-2">Physical climate-risk for your portfolio — live in a couple of minutes.</p>
          <Field label="Company name"><input className={inp} value={f.company_name} onChange={e => set('company_name', e.target.value)} placeholder="Acme Capital" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Sector"><select className={inp} value={f.org_type} onChange={e => set('org_type', e.target.value)}>{SECTORS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
            <Field label="Country (ISO-2)"><input className={inp} value={f.country} onChange={e => set('country', e.target.value.toUpperCase().slice(0, 2))} placeholder="IE" /></Field>
          </div>
          <Field label="Your name"><input className={inp} value={f.admin_full_name} onChange={e => set('admin_full_name', e.target.value)} placeholder="Alex Rivera" /></Field>
          <Field label="Work email"><input className={inp} value={f.admin_email} onChange={e => set('admin_email', e.target.value)} placeholder="you@company.com" /></Field>
          <Field label="Password"><input type="password" className={inp} value={f.password} onChange={e => set('password', e.target.value)} placeholder="At least 10 characters" /></Field>
          {err && <div className="text-[13px] text-[var(--color-bad)]">{err}</div>}
          <button type="submit" disabled={busy}
            className="w-full mt-1 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition disabled:opacity-60">
            {busy ? 'Creating…' : 'Create workspace →'}
          </button>
          <a href="/" className="block text-center text-[12px] text-[var(--color-sky)] pt-1">Already have an account? Sign in</a>
        </form>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">{label}</label>{children}</div>
}
