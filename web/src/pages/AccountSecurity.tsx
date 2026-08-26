import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Monitor, KeyRound, Fingerprint, Trash2, LogOut } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader } from '../components/ui'
import * as webauthn from '../lib/webauthn'

interface Session { token_id: string; user_agent: string | null; ip: string | null; created_at: string; last_used_at: string | null }
interface Cred { credential_id: string; name: string | null; created_at: string; last_used_at: string | null }
function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }

export default function AccountSecurity() {
  const qc = useQueryClient()
  const sessionsQ = useQuery({ queryKey: ['sessions'], queryFn: () => api.get<{ sessions: Session[] }>('/v1/auth/sessions') })
  const credsQ = useQuery({ queryKey: ['passkeys'], queryFn: () => api.get<{ credentials: Cred[] }>('/v1/auth/passkey/credentials') })
  const [codes, setCodes] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)

  async function revoke(id: string) {
    await api.del(`/v1/auth/sessions/${id}`); qc.invalidateQueries({ queryKey: ['sessions'] }); toast.success('Session revoked.')
  }
  async function logoutAll() {
    await api.post('/v1/auth/logout-all'); toast.success('Signed out everywhere. Re-login required.'); setTimeout(() => { window.location.href = '/' }, 800)
  }
  async function genCodes() {
    setBusy(true)
    try { const r = await api.post<{ codes: string[] }>('/v1/auth/mfa/backup-codes'); setCodes(r.codes); toast.success('New recovery codes generated.') }
    catch (e) { toast.error(msg(e, 'Enrol MFA first, then generate codes.')) } finally { setBusy(false) }
  }
  async function addPasskey() {
    if (!webauthn.supported()) { toast.error('This browser does not support passkeys.'); return }
    setBusy(true)
    try {
      const opts = await api.post('/v1/auth/passkey/register/options')
      const credential = await webauthn.startRegistration(opts)
      await api.post('/v1/auth/passkey/register/verify', { credential, name: 'Passkey' })
      qc.invalidateQueries({ queryKey: ['passkeys'] }); toast.success('Passkey added.')
    } catch (e) { toast.error(msg(e, 'Could not add a passkey.')) } finally { setBusy(false) }
  }
  async function delPasskey(id: string) {
    await api.del(`/v1/auth/passkey/credentials/${encodeURIComponent(id)}`); qc.invalidateQueries({ queryKey: ['passkeys'] }); toast.success('Passkey removed.')
  }

  const sessions = sessionsQ.data?.sessions ?? []
  const creds = credsQ.data?.credentials ?? []

  return (
    <div className="fadeup space-y-6 max-w-[760px]">
      <PageHeader eyebrow="Set up · account security" title="Security"
        lead="Manage the devices signed into your account, your two-factor recovery codes, and passkeys." />

      {/* passkeys */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2"><Fingerprint size={18} className="text-[var(--color-sky)]" /><h2 className="display text-base font-semibold m-0">Passkeys</h2></div>
          <Button variant="ghost" onClick={addPasskey} disabled={busy}>Add a passkey</Button>
        </div>
        <p className="text-[12px] text-[var(--color-mute)] mb-3">Sign in with Face ID, Touch ID, Windows Hello, or a security key — phishing-resistant, no password.</p>
        {creds.length === 0
          ? <div className="text-[13px] text-[var(--color-faint)]">No passkeys yet.</div>
          : <div className="space-y-1">{creds.map(c => (
              <div key={c.credential_id} className="flex items-center gap-3 text-[13px] py-1.5 border-t border-[var(--color-line)] first:border-0">
                <KeyRound size={14} className="text-[var(--color-faint)]" />
                <span className="flex-1 text-[var(--color-ink)]">{c.name || 'Passkey'}</span>
                <span className="text-[var(--color-faint)] mono text-[11px]">added {new Date(c.created_at).toLocaleDateString()}</span>
                <button onClick={() => delPasskey(c.credential_id)} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]"><Trash2 size={14} /></button>
              </div>))}
            </div>}
      </Card>

      {/* backup codes */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2"><KeyRound size={18} className="text-[var(--color-sky)]" /><h2 className="display text-base font-semibold m-0">Two-factor recovery codes</h2></div>
          <Button variant="ghost" onClick={genCodes} disabled={busy}>Generate new codes</Button>
        </div>
        <p className="text-[12px] text-[var(--color-mute)] mb-3">One-time codes to sign in if you lose your authenticator. Generating replaces any previous set.</p>
        {codes && (
          <div>
            <div className="text-[12px] text-[var(--color-good)] mb-2">Save these now — they won’t be shown again.</div>
            <div className="grid grid-cols-2 gap-1.5 mono text-[13px]">{codes.map(c => <div key={c} className="bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded px-2 py-1 text-center">{c}</div>)}</div>
          </div>
        )}
      </Card>

      {/* sessions */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2"><Monitor size={18} className="text-[var(--color-sky)]" /><h2 className="display text-base font-semibold m-0">Active sessions</h2></div>
          <Button variant="ghost" onClick={logoutAll}><LogOut size={14} /> Sign out everywhere</Button>
        </div>
        <div className="mt-2 space-y-1">
          {sessions.length === 0 && <div className="text-[13px] text-[var(--color-faint)]">No other active sessions.</div>}
          {sessions.map(s => (
            <div key={s.token_id} className="flex items-center gap-3 text-[13px] py-1.5 border-t border-[var(--color-line)] first:border-0">
              <Monitor size={14} className="text-[var(--color-faint)]" />
              <span className="flex-1 text-[var(--color-ink)] truncate">{(s.user_agent || 'Unknown device').slice(0, 60)}</span>
              <span className="text-[var(--color-faint)] mono text-[11px]">{s.ip || ''}</span>
              <button onClick={() => revoke(s.token_id)} className="text-[var(--color-sky)] hover:text-[var(--color-blue)] text-[12px]">Revoke</button>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
