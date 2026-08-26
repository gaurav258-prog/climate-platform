import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, ShieldCheck, Copy, RefreshCw, CheckCircle2 } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader } from '../components/ui'

interface Config {
  enabled: boolean; protocol?: string; oidc_issuer?: string | null; oidc_client_id?: string | null
  oidc_client_secret?: string | null; saml_idp_entity_id?: string | null; saml_idp_sso_url?: string | null
  saml_idp_x509_cert?: string | null; allowed_email_domain?: string | null
  jit_provisioning?: boolean; default_role?: string; scim_enabled?: boolean; scim_configured?: boolean
}
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'
function msg(e: unknown, f: string) { return e instanceof ApiError ? (e.body as { error?: { message?: string } })?.error?.message ?? f : f }

export default function SingleSignOn() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['sso-config'], queryFn: () => api.get<Config>('/v1/sso/config') })
  const [f, setF] = useState<Config | null>(null)
  const [busy, setBusy] = useState(false)
  const [token, setToken] = useState<{ scim_token: string; scim_base_url: string } | null>(null)
  const origin = window.location.origin

  if (q.error) return <Center>Single sign-on is available to your organization's admins.</Center>
  const c = f ?? q.data
  if (!c) return <Center>loading…</Center>
  const set = (k: keyof Config, v: unknown) => setF({ ...(f ?? q.data!), [k]: v })

  async function save() {
    setBusy(true)
    try {
      const body = {
        protocol: c!.protocol ?? 'oidc', enabled: c!.enabled,
        oidc_issuer: c!.oidc_issuer, oidc_client_id: c!.oidc_client_id,
        oidc_client_secret: c!.oidc_client_secret && c!.oidc_client_secret !== '********' ? c!.oidc_client_secret : undefined,
        saml_idp_entity_id: c!.saml_idp_entity_id, saml_idp_sso_url: c!.saml_idp_sso_url, saml_idp_x509_cert: c!.saml_idp_x509_cert,
        allowed_email_domain: c!.allowed_email_domain, jit_provisioning: c!.jit_provisioning ?? true,
        default_role: c!.default_role ?? 'viewer',
      }
      await api.put('/v1/sso/config', body)
      qc.invalidateQueries({ queryKey: ['sso-config'] }); setF(null)
      toast.success('SSO settings saved.')
    } catch (e) { toast.error(msg(e, 'Could not save.')) } finally { setBusy(false) }
  }
  async function genToken() {
    setBusy(true)
    try { setToken(await api.post('/v1/sso/config/scim-token')); qc.invalidateQueries({ queryKey: ['sso-config'] }); toast.success('SCIM token generated.') }
    catch (e) { toast.error(msg(e, 'Could not generate a token.')) } finally { setBusy(false) }
  }

  return (
    <div className="fadeup space-y-6 max-w-[760px]">
      <PageHeader eyebrow="Set up · identity" title="Single sign-on & provisioning"
        lead="Connect your identity provider (Okta, Microsoft Entra ID) so your team signs in with your directory and is provisioned automatically. Activates once your IdP is connected." />

      {/* SSO */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1"><ShieldCheck size={18} className="text-[var(--color-sky)]" /><h2 className="display text-base font-semibold m-0">Single sign-on</h2></div>
        <p className="text-[12px] text-[var(--color-mute)] mb-4">Users authenticate at your IdP; on return we validate the signed assertion and sign them in.</p>

        {/* protocol switch */}
        <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line)] mb-4 max-w-[260px]">
          {['oidc', 'saml'].map(p => (
            <button key={p} type="button" onClick={() => set('protocol', p)}
              className={`flex-1 rounded-md py-1.5 mono text-[11px] uppercase transition ${(c.protocol ?? 'oidc') === p ? 'bg-[var(--color-bg-2)] text-[var(--color-sky)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
              {p === 'oidc' ? 'OpenID Connect' : 'SAML 2.0'}
            </button>
          ))}
        </div>

        <div className="space-y-3">
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input type="checkbox" checked={!!c.enabled} onChange={e => set('enabled', e.target.checked)} /> Enable SSO for this organization
          </label>

          {(c.protocol ?? 'oidc') === 'saml' ? (
            <>
              <Field label="IdP entity ID"><input className={inp} value={c.saml_idp_entity_id ?? ''} onChange={e => set('saml_idp_entity_id', e.target.value)} placeholder="https://idp.company.com/saml/metadata" /></Field>
              <Field label="IdP SSO URL"><input className={inp} value={c.saml_idp_sso_url ?? ''} onChange={e => set('saml_idp_sso_url', e.target.value)} placeholder="https://idp.company.com/saml/sso" /></Field>
              <Field label="IdP signing certificate (X.509, PEM or base64)">
                <textarea className={inp + ' font-mono text-[11px] h-28'} value={c.saml_idp_x509_cert ?? ''} onChange={e => set('saml_idp_x509_cert', e.target.value)} placeholder="-----BEGIN CERTIFICATE-----" />
              </Field>
            </>
          ) : (
            <>
              <Field label="Issuer URL"><input className={inp} value={c.oidc_issuer ?? ''} onChange={e => set('oidc_issuer', e.target.value)} placeholder="https://your-org.okta.com" /></Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Client ID"><input className={inp} value={c.oidc_client_id ?? ''} onChange={e => set('oidc_client_id', e.target.value)} /></Field>
                <Field label="Client secret"><input className={inp} type="password" value={c.oidc_client_secret ?? ''} onChange={e => set('oidc_client_secret', e.target.value)} placeholder="••••••••" /></Field>
              </div>
            </>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label="Allowed email domain"><input className={inp} value={c.allowed_email_domain ?? ''} onChange={e => set('allowed_email_domain', e.target.value)} placeholder="company.com" /></Field>
            <Field label="Default role for new users"><select className={inp} value={c.default_role ?? 'viewer'} onChange={e => set('default_role', e.target.value)}>{['viewer', 'analyst', 'approver', 'admin'].map(r => <option key={r} value={r}>{r}</option>)}</select></Field>
          </div>
          <label className="flex items-center gap-2 text-[13px] cursor-pointer">
            <input type="checkbox" checked={c.jit_provisioning ?? true} onChange={e => set('jit_provisioning', e.target.checked)} /> Create accounts automatically on first sign-in (JIT)
          </label>
        </div>

        <div className="mt-4 pt-3 border-t border-[var(--color-line)] space-y-3">
          {(c.protocol ?? 'oidc') === 'saml' ? (
            <>
              <div><div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Give your IdP this ACS (reply) URL</div><CopyRow value={`${origin}/v1/sso/saml/acs`} /></div>
              <div><div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">SP entity ID</div><CopyRow value={`${origin}/sp`} /></div>
              <div className="text-[11px] text-[var(--color-faint)]">Or import our <a className="text-[var(--color-sky)]" href={`${origin}/v1/sso/saml/metadata`} target="_blank" rel="noreferrer">SP metadata</a> into your IdP.</div>
            </>
          ) : (
            <div><div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Give your IdP this redirect URI</div><CopyRow value={`${origin}/sso/callback`} /></div>
          )}
        </div>
        <div className="flex justify-end mt-4"><Button onClick={save} disabled={busy || !f}>{busy ? 'Saving…' : 'Save SSO settings'}</Button></div>
      </Card>

      {/* SCIM */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1"><KeyRound size={18} className="text-[var(--color-sky)]" /><h2 className="display text-base font-semibold m-0">SCIM 2.0 provisioning</h2></div>
        <p className="text-[12px] text-[var(--color-mute)] mb-4">Let your IdP create, update, and deactivate accounts here automatically. Point it at the SCIM base URL below with the bearer token.</p>
        <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">SCIM base URL</div>
        <CopyRow value={`${origin}/scim/v2`} />
        {token ? (
          <div className="mt-4">
            <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-good)] mb-1.5"><CheckCircle2 size={14} /> Copy this token now — it won't be shown again.</div>
            <CopyRow value={token.scim_token} />
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-3">
            <Button variant="ghost" onClick={genToken} disabled={busy}><RefreshCw size={14} /> {c.scim_configured ? 'Regenerate SCIM token' : 'Generate SCIM token'}</Button>
            {c.scim_configured && <span className="text-[11px] text-[var(--color-faint)]">A token is configured. Regenerating invalidates the old one.</span>}
          </div>
        )}
      </Card>

      <p className="mono text-[10px] text-[var(--color-faint)] px-1">SSO validates the IdP's signed ID token (RS256 via its JWKS) before creating a session; SCIM users are active with no local password and authenticate through your IdP. SAML is the same pattern and can be added on request.</p>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">{label}</label>{children}</div>
}
function CopyRow({ value }: { value: string }) {
  return (
    <div className="flex items-center gap-2">
      <input readOnly value={value} className="flex-1 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)]" />
      <button onClick={() => { navigator.clipboard?.writeText(value); toast.success('Copied') }} className="shrink-0 text-[var(--color-sky)] hover:text-[var(--color-blue)]"><Copy size={15} /></button>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
