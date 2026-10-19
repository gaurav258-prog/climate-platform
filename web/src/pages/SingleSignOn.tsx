import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, RefreshCw, ShieldCheck } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, PageHeader, SectionHead } from '../components/ui'
import { HEADING } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'
import { CopyRow, Field, ShownOnce, refused } from './admin/parts'

// Single sign-on and provisioning, to the UI standard (2026-10-16). The sign-in itself works exactly as before; the
// screen shows the set-up in customer words. The addresses to give the identity provider come from the server — the
// ones every sign-in is validated against (api/routers/sso_scim.py) — never from the browser's own address.

interface Config {
  enabled: boolean; protocol?: string; oidc_issuer?: string | null; oidc_client_id?: string | null
  oidc_client_secret?: string | null; saml_idp_entity_id?: string | null; saml_idp_sso_url?: string | null
  saml_idp_x509_cert?: string | null; allowed_email_domain?: string | null
  jit_provisioning?: boolean; default_role?: string; scim_configured?: boolean
  addresses: { acs: string; sp_entity_id: string; metadata: string; redirect: string; scim: string }
}
const ROLES: [string, string][] = [['viewer', 'Viewer'], ['analyst', 'Analyst'], ['approver', 'Approver'], ['admin', 'Administrator']]
const inp = 'w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-sm outline-none focus:border-[var(--color-sky)]'
const ABOUT = [
  { heading: HEADING.shows, body: 'How your team signs in with your own directory (Okta, Microsoft Entra ID or another identity provider) and how its accounts are created and closed automatically.' },
  { heading: HEADING.read, body: 'People sign in at your identity provider; on their return the platform checks the provider’s signed answer before opening a session. Provisioning lets your provider create, update and close accounts here; those accounts have no password of their own.' },
  { heading: HEADING.limits, body: 'Single sign-on starts working once your identity provider is connected with the addresses shown here.' },
]

export default function SingleSignOn() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['sso-config'], queryFn: () => api.get<Config>('/v1/sso/config') })
  const [f, setF] = useState<Config | null>(null)
  const [busy, setBusy] = useState(false)
  const [token, setToken] = useState<string | null>(null)
  if (q.error) return <Center>Single sign-on is for your organisation’s administrators.</Center>
  const c = f ?? q.data
  if (!c) return <Center>Loading…</Center>
  const set = (k: keyof Config, v: unknown) => setF({ ...(f ?? q.data!), [k]: v })
  const saml = (c.protocol ?? 'oidc') === 'saml'

  const save = async () => {
    setBusy(true)
    try {
      await api.put('/v1/sso/config', {
        protocol: c.protocol ?? 'oidc', enabled: c.enabled, oidc_issuer: c.oidc_issuer, oidc_client_id: c.oidc_client_id,
        oidc_client_secret: c.oidc_client_secret && c.oidc_client_secret !== '********' ? c.oidc_client_secret : undefined,
        saml_idp_entity_id: c.saml_idp_entity_id, saml_idp_sso_url: c.saml_idp_sso_url, saml_idp_x509_cert: c.saml_idp_x509_cert,
        allowed_email_domain: c.allowed_email_domain, jit_provisioning: c.jit_provisioning ?? true, default_role: c.default_role ?? 'viewer',
      })
      qc.invalidateQueries({ queryKey: ['sso-config'] }); setF(null); toast.success('Single sign-on saved.')
    } catch (e) { refused(e, 'Single sign-on could not be saved.') } finally { setBusy(false) }
  }
  const newToken = async () => {
    setBusy(true)
    try { const r = await api.post<{ scim_token: string }>('/v1/sso/config/scim-token'); setToken(r.scim_token); qc.invalidateQueries({ queryKey: ['sso-config'] }) }
    catch (e) { refused(e, 'A provisioning token could not be created.') } finally { setBusy(false) }
  }

  return (
    <div className="fadeup space-y-6 max-w-[780px]">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Set up · identity" title="Single sign-on" lead="Your team signs in with your own directory." about={ABOUT} />
      <div className="flex flex-wrap gap-2">
        <StatusChip tone={q.data?.enabled ? 'good' : 'neutral'} label={q.data?.enabled ? 'Single sign-on on' : 'Single sign-on off'} />
        <StatusChip tone="neutral" label={(q.data?.protocol ?? 'oidc') === 'saml' ? 'SAML' : 'OpenID Connect'} />
        <StatusChip tone={q.data?.jit_provisioning ?? true ? 'good' : 'neutral'} label={q.data?.jit_provisioning ?? true ? 'Accounts made at first sign-in' : 'Accounts added by hand'} />
        <StatusChip tone={q.data?.scim_configured ? 'good' : 'neutral'} label={q.data?.scim_configured ? 'Provisioning connected' : 'Provisioning not connected'} />
      </div>

      <Card className="p-5 space-y-4">
        <SectionHead icon={ShieldCheck}>Single sign-on</SectionHead>
        <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line)] max-w-[300px]" role="radiogroup" aria-label="Sign-in standard">
          {[['oidc', 'OpenID Connect'], ['saml', 'SAML']].map(([p, label]) => (
            <button key={p} type="button" role="radio" aria-checked={(c.protocol ?? 'oidc') === p} onClick={() => set('protocol', p)}
              className={clsx('flex-1 rounded-md py-1.5 text-[12.5px] transition', (c.protocol ?? 'oidc') === p ? 'bg-[var(--color-bg-2)] text-[var(--color-sky)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{label}</button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] cursor-pointer"><input type="checkbox" checked={!!c.enabled} onChange={e => set('enabled', e.target.checked)} /> Switch single sign-on on for your organisation</label>
        {saml ? (<>
          <Field label="Your identity provider’s identifier"><input className={inp} value={c.saml_idp_entity_id ?? ''} onChange={e => set('saml_idp_entity_id', e.target.value)} placeholder="https://idp.company.com/saml/metadata" /></Field>
          <Field label="Its sign-in address"><input className={inp} value={c.saml_idp_sso_url ?? ''} onChange={e => set('saml_idp_sso_url', e.target.value)} placeholder="https://idp.company.com/saml/sso" /></Field>
          <Field label="Its signing certificate"><textarea className={`${inp} font-mono text-[11px] h-28`} value={c.saml_idp_x509_cert ?? ''} onChange={e => set('saml_idp_x509_cert', e.target.value)} placeholder="-----BEGIN CERTIFICATE-----" /></Field>
        </>) : (<>
          <Field label="Issuer address"><input className={inp} value={c.oidc_issuer ?? ''} onChange={e => set('oidc_issuer', e.target.value)} placeholder="https://your-organisation.okta.com" /></Field>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Client identifier"><input className={inp} value={c.oidc_client_id ?? ''} onChange={e => set('oidc_client_id', e.target.value)} /></Field>
            <Field label="Client secret"><input className={inp} type="password" autoComplete="new-password" value={c.oidc_client_secret ?? ''} onChange={e => set('oidc_client_secret', e.target.value)} placeholder="••••••••" /></Field>
          </div>
        </>)}
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Allowed e-mail domain"><input className={inp} value={c.allowed_email_domain ?? ''} onChange={e => set('allowed_email_domain', e.target.value)} placeholder="company.com" /></Field>
          <Field label="Role for a new person"><select className={inp} value={c.default_role ?? 'viewer'} onChange={e => set('default_role', e.target.value)}>{ROLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></Field>
        </div>
        <label className="flex items-center gap-2 text-[13px] cursor-pointer"><input type="checkbox" checked={c.jit_provisioning ?? true} onChange={e => set('jit_provisioning', e.target.checked)} /> Create an account at a person’s first sign-in</label>
        <div className="pt-3 border-t border-[var(--color-line)] space-y-3">
          <div className="text-[12.5px] text-[var(--color-ink)]">Give your identity provider</div>
          {saml ? (<>
            <CopyRow label="The reply address" value={c.addresses.acs} />
            <CopyRow label="Our identifier" value={c.addresses.sp_entity_id} />
            <CopyRow label="Or import our set-up file" value={c.addresses.metadata} />
          </>) : <CopyRow label="The return address" value={c.addresses.redirect} />}
        </div>
        <div className="flex justify-end"><Button onClick={save} disabled={busy || !f}>{busy ? 'Saving…' : 'Save'}</Button></div>
      </Card>

      <Card className="p-5 space-y-4">
        <SectionHead icon={KeyRound}>Provisioning</SectionHead>
        <p className="m-0 text-[12.5px] text-[var(--color-mute)]">Your identity provider creates, updates and closes accounts here, using this address and a token.</p>
        <CopyRow label="Provisioning address" value={c.addresses.scim} />
        {token ? <ShownOnce title="Copy the token now — it is shown only once." value={token} /> : (
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="ghost" onClick={newToken} disabled={busy}><RefreshCw size={14} /> {c.scim_configured ? 'Replace the token' : 'Create a token'}</Button>
            {c.scim_configured && <span className="text-[12px] text-[var(--color-faint)]">A token is in use; replacing it stops the old one.</span>}
          </div>
        )}
      </Card>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[55vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
