import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { CheckCircle2, KeyRound } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { BrandMark } from '../components/ui'

function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'

export default function ResetPassword() {
  const { token = '' } = useParams()
  const [state, setState] = useState<'loading' | 'invalid' | 'form' | 'done'>('loading')
  const [email, setEmail] = useState('')
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState('')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    api.get<{ email: string }>(`/v1/auth/password/reset/${token}`)
      .then(d => { setEmail(d.email); setState('form') })
      .catch(() => setState('invalid'))
  }, [token])

  async function submit() {
    setErr(null)
    if (pw.length < 10) { setErr('Use at least 10 characters.'); return }
    if (pw !== pw2) { setErr('Passwords don’t match.'); return }
    setBusy(true)
    try { await api.post(`/v1/auth/password/reset/${token}`, { password: pw }); setState('done') }
    catch (e) { setErr(msg(e, 'Could not reset your password.')) } finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen grid place-items-center px-6" style={{ background: 'radial-gradient(1200px 600px at 50% -10%, #0e1a30 0%, var(--color-bg) 60%)' }}>
      <div className="w-full max-w-[400px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={34} /><div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div></div>
        <div className="card p-6">
          {state === 'loading' && <p className="text-[var(--color-faint)] text-sm">Loading…</p>}
          {state === 'invalid' && <div className="text-center py-4"><h1 className="display text-xl font-semibold m-0">This reset link has expired</h1><p className="text-[13px] text-[var(--color-mute)] mt-2">Request a new one from the sign-in screen.</p><a href="/" className="inline-block mt-4 text-[13px] text-[var(--color-sky)]">Back to sign in →</a></div>}
          {state === 'done' && <div className="text-center py-4"><CheckCircle2 size={38} className="text-[var(--color-good)] mx-auto mb-3" /><h1 className="display text-xl font-semibold m-0">Password updated</h1><p className="text-[13px] text-[var(--color-mute)] mt-2">You’ve been signed out everywhere. Sign in with your new password.</p><a href="/" className="inline-flex mt-5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium">Go to sign in →</a></div>}
          {state === 'form' && (
            <div>
              <div className="text-[var(--color-sky)] mb-2"><KeyRound size={20} /></div>
              <h1 className="display text-xl font-semibold m-0">Set a new password</h1>
              <p className="text-[13px] text-[var(--color-mute)] mt-1.5 mb-4">for {email}</p>
              <div className="space-y-3">
                <input type="password" className={inp} value={pw} onChange={e => setPw(e.target.value)} placeholder="New password (min 10 characters)" />
                <input type="password" className={inp} value={pw2} onChange={e => setPw2(e.target.value)} placeholder="Confirm new password" />
              </div>
              {err && <div className="text-[13px] text-[var(--color-bad)] mt-3">{err}</div>}
              <button onClick={submit} disabled={busy || !pw || !pw2}
                className="w-full mt-5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition disabled:opacity-60">
                {busy ? 'Updating…' : 'Update password →'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
