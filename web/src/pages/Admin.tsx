import { useState, useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserPlus, ShieldCheck, Check, AlertCircle, Building2, CheckSquare, ScrollText, Users as UsersIcon, Pencil, Database, RefreshCw, CloudRain, Leaf, Landmark, ChevronDown, Plug, Copy, Trash2, KeyRound, Webhook, Send, Gauge, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Button, Stat, PageHeader, SectionHead } from '../components/ui'
import Approvals from './Approvals'
import Audit from './Audit'
import AdminEntities from '../components/AdminEntities'
import SectionTabs, { ADMIN_TABS } from '../components/SectionTabs'
import { actionLabel } from '../lib/actionLabels'

interface User { id: string; email: string; full_name: string; status: string; roles: string[]; last_login_at: string | null }
interface Role { id: string; name: string; description: string | null; is_system: boolean; permissions: string[] }
interface Perm { code: string; description: string }
interface Policy { action_key: string; label: string; requires_approval: boolean; material_fields: string[]; org_override: boolean; supports_threshold?: boolean; threshold_eur?: number | null }
interface Check { key: string; label: string; ok: boolean; hint: string | null }
interface CC {
  organization: { name: string | null; legal_name: string | null; type: string | null; country: string | null; lei: string | null; eori: string | null; filing_contact_email: string | null; operator_address: string | null }
  readiness: { passed: number; total: number; checks: Check[] }
  data: { sites: { total: number; scored: number; elevated: number; value_eur: number }; plots: { total: number; eudr_covered: number; eudr_determined: number; needs_polygon: number } }
  governance: { pending_approvals: number; audit_events_30d: number; second_approver: boolean }
  access: { users: number; active: number; ever_logged_in: number }
  entitlements: string[]
}

const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`

export default function Admin() {
  const { profile } = useAuth()
  const perms = profile?.permissions ?? []
  // Tabs are grouped by purpose and ordered as you'd actually set an org up and run it, left→right:
  //  1. Overview (where do I stand)  2. People & access (who, and what they may do)
  //  3. Governance (the approvals + audit those settings drive)  4. Organization & config (structure, appetite, method)
  //  5. Connections. A thin divider between groups makes the grouping visible instead of one undifferentiated row.
  const TAB_GROUPS: { perm: string; tab: string }[][] = [
    [{ perm: 'admin.users.manage', tab: 'Overview' }],
    [{ perm: 'admin.users.manage', tab: 'Users' },
     { perm: 'admin.roles.manage', tab: 'Roles' },
     { perm: 'admin.approval_policy.manage', tab: 'Approval matrix' }],
    [{ perm: 'approvals.view', tab: 'Approvals' },
     { perm: 'admin.audit.view', tab: 'Audit' }],
    [{ perm: 'admin.users.manage', tab: 'Entities' },
     { perm: 'admin.approval_policy.manage', tab: 'KRI appetite' },
     { perm: 'admin.roles.manage', tab: 'Methodology' }],
    [{ perm: 'admin.users.manage', tab: 'Integrations' }],
  ]
  const groups = TAB_GROUPS.map(g => g.filter(x => perms.includes(x.perm)).map(x => x.tab)).filter(g => g.length)
  const tabs = groups.flat()
  const [tab, setTab] = useState(tabs[0] ?? 'Overview')

  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={ADMIN_TABS} />
      <PageHeader eyebrow="Governance · control center" title="Control center"
        lead="Is your organization set up correctly and your data complete enough to trust the numbers? Reporting identity, data readiness, users, roles, and the approval matrix — in one place." />
      <div className="flex gap-2 flex-wrap items-center">
        {groups.map((g, gi) => (
          <div key={gi} className="flex gap-2 items-center">
            {gi > 0 && <span className="w-px h-5 bg-[var(--color-line-2)] mx-1 shrink-0" aria-hidden />}
            {g.map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-3 py-1.5 rounded-lg text-[13px] border transition ${tab === t ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{t}</button>
            ))}
          </div>
        ))}
      </div>
      {tab === 'Overview' && <Overview onTab={setTab} />}
      {tab === 'Approvals' && <Approvals embedded />}
      {tab === 'Audit' && <Audit embedded />}
      {tab === 'Users' && <Users />}
      {tab === 'Roles' && <Roles />}
      {tab === 'Entities' && <AdminEntities />}
      {tab === 'Approval matrix' && <><Matrix /><DecisionPlaybook /></>}
      {tab === 'KRI appetite' && <KriAppetite />}
      {tab === 'Methodology' && <Methodology />}
      {tab === 'Integrations' && <Integrations />}
    </div>
  )
}

interface Token { token_id: string; name: string; token_prefix: string; is_active: boolean; created_by_email: string | null; created_at: string | null; last_used_at: string | null }

interface SwitchSpec { key: string; label: string; description: string; default: string | number; kind: string; allowed?: (string | number)[] | null; min?: number | null; max?: number | null }

function Methodology() {
  const cat = useQuery({ queryKey: ['calc-catalog'], queryFn: () => api.get<{ interpretation: SwitchSpec[] }>('/v1/calc-settings/catalog') })
  const cur = useQuery({ queryKey: ['calc-settings'], queryFn: () => api.get<Record<string, unknown>>('/v1/calc-settings') })
  const [busy, setBusy] = useState<string | null>(null)

  const save = async (key: string, value: string | number) => {
    setBusy(key)
    try {
      const res = await api.patch<{ status: string }>('/v1/calc-settings', { interpretation: { [key]: value } })
      toast.success(res.status === 'pending' ? 'Change submitted for 4-eyes approval.' : 'Interpretation updated.')
      cur.refetch()
    } catch { toast.error('Could not apply the change — check the value.') } finally { setBusy(null) }
  }

  const specs = cat.data?.interpretation ?? []
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-1"><Gauge size={16} className="text-[var(--color-sky)]" />
        <h2 className="display text-xl font-semibold">Methodology &amp; interpretation</h2></div>
      <p className="text-[12.5px] text-[var(--color-mute)] max-w-2xl mb-4">
        Where a regulation leaves a choice to your institution (e.g. the catastrophe PML return period — Solvency II 1-in-200 vs a rating-agency 1-in-250), set it here. Every default reproduces the standard figure; changes are audited (4-eyes if your approval matrix requires it) and stamped onto every frozen filing so a regulator sees which interpretation produced each number.
      </p>
      {specs.length === 0 ? (
        <div className="text-[12.5px] text-[var(--color-faint)]">No interpretation switches apply to this sector.</div>
      ) : (
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {specs.map(s => {
            const value = (cur.data?.[s.key] ?? s.default) as string | number
            const isEnum = s.kind === 'enum' || (Array.isArray(s.allowed) && s.allowed.length > 0)
            return (
              <div key={s.key} className="flex flex-wrap items-center gap-x-4 gap-y-1.5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="text-[13px] font-semibold text-[var(--color-ink)]">{s.label}</div>
                  <div className="text-[11.5px] text-[var(--color-mute)]">{s.description}</div>
                </div>
                {isEnum ? (
                  <select value={String(value)} disabled={busy === s.key}
                    onChange={e => save(s.key, s.kind === 'int' ? Number(e.target.value) : e.target.value)}
                    className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
                    {(s.allowed ?? []).map(a => <option key={String(a)} value={String(a)}>{String(a)}{a === s.default ? ' (default)' : ''}</option>)}
                  </select>
                ) : (
                  <input type="number" defaultValue={Number(value)} min={s.min ?? undefined} max={s.max ?? undefined}
                    step={s.kind === 'float' ? 0.01 : 1} disabled={busy === s.key}
                    onBlur={e => { const v = Number(e.target.value); if (v !== Number(value)) save(s.key, v) }}
                    className="w-28 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] tabular-nums" />
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

function Integrations() {
  const { profile } = useAuth()
  const sector = profile?.org?.type ?? ''
  const q = useQuery({ queryKey: ['ingest-tokens'], queryFn: () => api.get<Token[]>('/v1/ingest/tokens') })
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<{ name: string; raw: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const ago = (iso: string | null) => { if (!iso) return 'never'; const d = (Date.now() - new Date(iso).getTime()) / 86400000; return d < 1 ? 'today' : d < 2 ? 'yesterday' : `${Math.floor(d)}d ago` }

  const create = async () => {
    if (name.trim().length < 2) { toast.error('Give the token a name.'); return }
    setBusy(true)
    try {
      const res = await api.post<{ raw_token: string; name: string }>('/v1/ingest/tokens', { name: name.trim() })
      setRevealed({ name: res.name, raw: res.raw_token }); setName(''); q.refetch()
    } catch { toast.error('Could not create the token.') } finally { setBusy(false) }
  }
  const revoke = async (id: string) => {
    if (!confirm('Revoke this token? Any system using it stops working immediately.')) return
    try { await api.del(`/v1/ingest/tokens/${id}`); q.refetch() } catch { toast.error('Could not revoke.') }
  }
  const copy = () => { if (revealed?.raw) { navigator.clipboard?.writeText(revealed.raw); setCopied(true); setTimeout(() => setCopied(false), 1500) } }

  const origin = window.location.origin
  const isBank = sector === 'bank'
  const rows = q.data ?? []

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2"><Plug size={16} className="text-[var(--color-sky)]" /><h2 className="display text-xl font-semibold">Direct integration</h2></div>
        <p className="text-[13px] text-[var(--color-mute)] mt-1 max-w-2xl">Let your own systems push data straight into your tenant with an API token — the third way to get data in, alongside manual entry and template upload. A token acts as your organization; keep it secret and revoke it if it leaks.</p>
      </div>

      {/* create */}
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[220px]">
            <span className="text-[11.5px] text-[var(--color-mute)]">New token name</span>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Core banking nightly" maxLength={80} className={inp + ' mt-1'} />
          </label>
          <Button onClick={create} disabled={busy}><KeyRound size={15} /> {busy ? 'Creating…' : 'Create token'}</Button>
        </div>
        {revealed && (
          <div className="mt-4 rounded-lg border border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,transparent)] p-3.5">
            <div className="flex items-center gap-2 text-[12px] text-[var(--color-sky)] mb-2"><AlertCircle size={14} /> Copy this now — it is shown only once.</div>
            <div className="flex items-center gap-2">
              <code className="flex-1 mono text-[12.5px] break-all bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded px-3 py-2">{revealed.raw}</code>
              <button onClick={copy} className="shrink-0 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-medium border border-[var(--color-line-2)] hover:border-[var(--color-sky)]"><Copy size={13} /> {copied ? 'Copied' : 'Copy'}</button>
            </div>
            <div className="text-[11px] text-[var(--color-faint)] mt-1.5">Token “{revealed.name}”. Store it in your system's secret manager.</div>
          </div>
        )}
      </Card>

      {/* list */}
      <Card className="p-0 overflow-x-auto">
        {rows.length === 0 ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">No tokens yet.</div> : (
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
              <th className="font-normal py-2.5 px-4">Name</th><th className="font-normal px-4">Prefix</th><th className="font-normal px-4">Created by</th>
              <th className="font-normal px-4">Last used</th><th className="font-normal px-4">Status</th><th className="font-normal px-4"></th>
            </tr></thead>
            <tbody>
              {rows.map(t => (
                <tr key={t.token_id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="py-2.5 px-4 text-[var(--color-ink)]">{t.name}</td>
                  <td className="px-4 mono text-[11.5px] text-[var(--color-mute)]">{t.token_prefix}…</td>
                  <td className="px-4 text-[11.5px] text-[var(--color-mute)]">{t.created_by_email ?? '—'}</td>
                  <td className="px-4 text-[11.5px] text-[var(--color-mute)]">{ago(t.last_used_at)}</td>
                  <td className="px-4">{t.is_active
                    ? <span className="mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]">active</span>
                    : <span className="mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-faint)] bg-[var(--color-panel-2)]">revoked</span>}</td>
                  <td className="px-4 text-right">{t.is_active && <button onClick={() => revoke(t.token_id)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-bad)]"><Trash2 size={13} /> Revoke</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* how to connect */}
      <Card className="p-5">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-3">How to connect</div>
        <ol className="space-y-3 text-[13px] text-[var(--color-mute)]">
          <li><b className="text-[var(--color-ink)]">1. Check the token</b> — confirm it authenticates your tenant:
            <pre className="mono text-[11.5px] mt-1.5 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 overflow-x-auto">curl -H "Authorization: Bearer &lt;token&gt;" {origin}/v1/ingest/ping</pre></li>
          <li><b className="text-[var(--color-ink)]">2. Push your data</b> —
            {isBank
              ? <> POST your loan-tape rows (same fields as the CSV template):
                  <pre className="mono text-[11.5px] mt-1.5 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-3 py-2 overflow-x-auto">{`curl -X POST ${origin}/v1/ingest/bank/assets \\
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \\
  -d '{"rows":[{"asset_name":"Frankfurt Tower 1","asset_type":"commercial_real_estate",
      "latitude":50.11,"longitude":8.68,"appraised_value_eur":12000000,"sector":"Commercial real estate"}]}'`}</pre>
                  Rows are validated, located, and scored against the golden source — exactly like the upload. A row missing a required field is skipped and reported, never guessed.</>
              : <span className="text-[var(--color-faint)]"> the direct-push endpoint for the <b className="capitalize">{sector.replace('_', ' ')}</b> sector is rolling out — your token and the handshake work today; talk to us to be an early integration partner. Template upload remains available now.</span>}
          </li>
        </ol>
        <a href="/docs" className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline mt-3"><Database size={13} /> Full data-in guide in Documentation</a>
      </Card>

      <Webhooks />
      <SourceSystems />
    </div>
  )
}

interface SrcSystem { key: string; name: string; kind: string; deep_link_template: string; active: boolean }
const SRC_KINDS = ['core_banking', 'gl', 'los', 'warehouse', 'gis', 'other']
// Register the customer's systems of record so a user can drill from a Tellumen figure through to the SOURCE
// record. Deep-link only — Tellumen stores the link template, never the source data.
function SourceSystems() {
  const q = useQuery({ queryKey: ['source-systems'], queryFn: () => api.get<{ systems: SrcSystem[] }>('/v1/source-systems') })
  const [f, setF] = useState({ key: '', name: '', kind: 'core_banking', deep_link_template: '' })
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    if (!f.key || !f.name || !f.deep_link_template) { toast.error('Fill key, name and the link template.'); return }
    setBusy(true)
    try {
      await api.post('/v1/source-systems', f)
      toast.success(`Registered ${f.name}.`)
      setF({ key: '', name: '', kind: 'core_banking', deep_link_template: '' }); q.refetch()
    } catch {
      toast.error('Could not register — the link template must be https and contain {id}.')
    } finally { setBusy(false) }
  }
  const systems = q.data?.systems ?? []
  return (
    <Card className="p-5">
      <SectionHead icon={ExternalLink} hint="drill from a figure to its source record">Source systems</SectionHead>
      <p className="text-[12.5px] text-[var(--color-mute)] max-w-3xl mt-1.5 leading-relaxed">
        Register your systems of record (GL, core banking, loan origination, warehouse, GIS). A user can then open a Tellumen figure’s source record in that system from the asset drawer. <span className="text-[var(--color-ink)]">Deep-link only</span> — Tellumen stores the link template, never the source data; the record opens under your own system’s login. Use <span className="mono">{'{id}'}</span> in the URL for the source record id.
      </p>

      {systems.length > 0 && (
        <div className="mt-4 divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {systems.map(s => (
            <div key={s.key} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 py-2.5 text-[12.5px]">
              <span className="font-medium text-[var(--color-ink)]">{s.name}</span>
              <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{s.kind.replace('_', ' ')}</span>
              <span className="flex-1 min-w-0 mono text-[11px] text-[var(--color-faint)] truncate">{s.deep_link_template}</span>
            </div>
          ))}
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-3 mt-4 max-w-3xl">
        <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Display name (e.g. Finacle core banking)"
          className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 text-[13px]" />
        <input value={f.key} onChange={e => setF({ ...f, key: e.target.value.replace(/[^a-z0-9_]/g, '') })} placeholder="key (e.g. core_banking)"
          className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 text-[13px] mono" />
        <select value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })}
          className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 text-[13px]">
          {SRC_KINDS.map(k => <option key={k} value={k}>{k.replace('_', ' ')}</option>)}
        </select>
        <input value={f.deep_link_template} onChange={e => setF({ ...f, deep_link_template: e.target.value })} placeholder="https://gl.example.com/account/{id}"
          className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 text-[13px] mono" />
      </div>
      <div className="mt-3"><Button onClick={submit} disabled={busy}>{busy ? 'Registering…' : 'Register source system'}</Button></div>
    </Card>
  )
}

interface WEndpoint { endpoint_id: string; name: string; url: string; events: string[]; is_active: boolean; created_by_email: string | null; last_delivery_at: string | null }
interface WDelivery { delivery_id: string; event_type: string; status: string; http_status: number | null; error: string | null; endpoint_name: string | null; created_at: string | null }
interface WEvent { type: string; label: string }

function Webhooks() {
  const cat = useQuery({ queryKey: ['wh-events'], queryFn: () => api.get<{ events: WEvent[] }>('/v1/webhooks/events') })
  const eps = useQuery({ queryKey: ['wh-endpoints'], queryFn: () => api.get<WEndpoint[]>('/v1/webhooks') })
  const del = useQuery({ queryKey: ['wh-deliveries'], queryFn: () => api.get<WDelivery[]>('/v1/webhooks/deliveries') })
  const [url, setUrl] = useState(''); const [name, setName] = useState(''); const [sel, setSel] = useState<string[]>([])
  const [busy, setBusy] = useState(false); const [secret, setSecret] = useState<string | null>(null); const [copied, setCopied] = useState(false)
  const ago = (iso: string | null) => { if (!iso) return 'never'; const d = (Date.now() - new Date(iso).getTime()) / 86400000; return d < 0.04 ? 'just now' : d < 1 ? 'today' : `${Math.floor(d)}d ago` }

  const create = async () => {
    if (!/^https?:\/\//.test(url)) { toast.error('URL must start with http:// or https://'); return }
    if (name.trim().length < 2) { toast.error('Name the endpoint.'); return }
    setBusy(true)
    try {
      const r = await api.post<{ secret: string }>('/v1/webhooks', { url: url.trim(), name: name.trim(), events: sel })
      setSecret(r.secret); setUrl(''); setName(''); setSel([]); eps.refetch()
    } catch (e) { toast.error((e as { body?: { message?: string } })?.body?.message || 'Could not create the endpoint.') } finally { setBusy(false) }
  }
  const revoke = async (id: string) => { if (!confirm('Revoke this endpoint? It will stop receiving events.')) return; try { await api.del(`/v1/webhooks/${id}`); eps.refetch() } catch { toast.error('Could not revoke.') } }
  const test = async (id: string) => { try { const r = await api.post<{ status: string; http_status: number | null }>(`/v1/webhooks/${id}/test`); toast.error(r.status === 'delivered' ? `Test delivered (HTTP ${r.http_status}).` : `Test failed (${r.http_status ? 'HTTP ' + r.http_status : 'no response'}). Check the URL.`); del.refetch(); eps.refetch() } catch { toast.error('Could not send the test.') } }
  const toggle = (t: string) => setSel(s => s.includes(t) ? s.filter(x => x !== t) : [...s, t])
  const copy = () => { if (secret) { navigator.clipboard?.writeText(secret); setCopied(true); setTimeout(() => setCopied(false), 1500) } }

  const rows = eps.data ?? []; const dels = del.data ?? []
  return (
    <div className="space-y-4 pt-5 mt-1 border-t border-[var(--color-line)]">
      <div>
        <div className="flex items-center gap-2"><Webhook size={16} className="text-[var(--color-sky)]" /><h2 className="display text-xl font-semibold">Webhooks (outbound)</h2></div>
        <p className="text-[13px] text-[var(--color-mute)] mt-1 max-w-2xl">Push Tellumen events to your GRC, reporting or data systems the moment they happen. We POST a signed JSON payload; your system verifies the <span className="mono text-[11.5px]">X-Tellumen-Signature</span> header with the secret below.</p>
      </div>

      <Card className="p-4 space-y-3">
        <div className="grid sm:grid-cols-2 gap-3">
          <label><span className="text-[11.5px] text-[var(--color-mute)]">Endpoint URL</span>
            <input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://your-system.example.com/tellumen" className={inp + ' mt-1'} /></label>
          <label><span className="text-[11.5px] text-[var(--color-mute)]">Name</span>
            <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. GRC listener" maxLength={80} className={inp + ' mt-1'} /></label>
        </div>
        <div>
          <div className="text-[11.5px] text-[var(--color-mute)] mb-1.5">Events <span className="text-[var(--color-faint)]">(none selected = all)</span></div>
          <div className="flex flex-wrap gap-2">
            {(cat.data?.events ?? []).map(ev => (
              <button key={ev.type} onClick={() => toggle(ev.type)} title={ev.label}
                className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] border transition ${sel.includes(ev.type) ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
                {sel.includes(ev.type) && <Check size={12} />}<span className="mono">{ev.type}</span>
              </button>
            ))}
          </div>
        </div>
        <Button onClick={create} disabled={busy}><Webhook size={15} /> {busy ? 'Adding…' : 'Add endpoint'}</Button>
        {secret && (
          <div className="rounded-lg border border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,transparent)] p-3.5">
            <div className="flex items-center gap-2 text-[12px] text-[var(--color-sky)] mb-2"><AlertCircle size={14} /> Signing secret — copy now, shown only once.</div>
            <div className="flex items-center gap-2">
              <code className="flex-1 mono text-[12.5px] break-all bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded px-3 py-2">{secret}</code>
              <button onClick={copy} className="shrink-0 inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-medium border border-[var(--color-line-2)] hover:border-[var(--color-sky)]"><Copy size={13} /> {copied ? 'Copied' : 'Copy'}</button>
            </div>
          </div>
        )}
      </Card>

      {rows.length > 0 && (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
              <th className="font-normal py-2.5 px-4">Endpoint</th><th className="font-normal px-4">Events</th><th className="font-normal px-4">Last delivery</th><th className="font-normal px-4">Status</th><th className="font-normal px-4"></th>
            </tr></thead>
            <tbody>
              {rows.map(e => (
                <tr key={e.endpoint_id} className="border-b border-[var(--color-line)] last:border-0">
                  <td className="py-2.5 px-4"><div className="text-[var(--color-ink)]">{e.name}</div><div className="mono text-[11px] text-[var(--color-faint)] break-all">{e.url}</div></td>
                  <td className="px-4 mono text-[11px] text-[var(--color-mute)]">{e.events.length ? e.events.join(', ') : 'all'}</td>
                  <td className="px-4 text-[11.5px] text-[var(--color-mute)]">{ago(e.last_delivery_at)}</td>
                  <td className="px-4">{e.is_active
                    ? <span className="mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]">active</span>
                    : <span className="mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-faint)] bg-[var(--color-panel-2)]">revoked</span>}</td>
                  <td className="px-4 text-right whitespace-nowrap">{e.is_active && <>
                    <button onClick={() => test(e.endpoint_id)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline mr-3"><Send size={12} /> Test</button>
                    <button onClick={() => revoke(e.endpoint_id)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-bad)]"><Trash2 size={12} /> Revoke</button></>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {dels.length > 0 && (
        <div>
          <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Recent deliveries</div>
          <Card className="p-0 overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <tbody>
                {dels.slice(0, 12).map(d => (
                  <tr key={d.delivery_id} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="py-2 px-4 text-[12.5px] text-[var(--color-mute)]" title={d.event_type}>{actionLabel(d.event_type)}</td>
                    <td className="px-4 text-[var(--color-faint)]">{d.endpoint_name ?? '—'}</td>
                    <td className="px-4">{d.status === 'delivered'
                      ? <span className="text-[var(--color-good)]">delivered · {d.http_status}</span>
                      : <span className="text-[var(--color-bad)]" title={d.error ?? ''}>failed{d.http_status ? ` · ${d.http_status}` : ''}</span>}</td>
                    <td className="px-4 text-right text-[11px] text-[var(--color-faint)]">{ago(d.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}

      <p className="text-[11.5px] text-[var(--color-faint)]">HTTP push is live. SFTP delivery to a drop server is interface-ready — talk to us if you need it.</p>
    </div>
  )
}

function Overview({ onTab }: { onTab: (t: string) => void }) {
  const q = useQuery({ queryKey: ['control-center'], queryFn: () => api.get<CC>('/v1/admin/control-center') })
  const [editOrg, setEditOrg] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  // deep-link from the "Complete your reporting identity" task (/admin?setup=identity): open the edit
  // form on the missing fields and scroll straight to it, instead of dropping the user on a generic page.
  const identityRef = useRef<HTMLDivElement>(null)
  const didDeepLink = useRef(false)
  useEffect(() => {
    if (didDeepLink.current) return
    const wants = new URLSearchParams(window.location.search).get('setup') === 'identity'
    const o = q.data?.organization
    if (!wants || !o) return
    didDeepLink.current = true
    if (!(o.eori && o.filing_contact_email)) {
      setForm({ legal_name: o.legal_name ?? '', lei: o.lei ?? '', eori: o.eori ?? '',
                filing_contact_email: o.filing_contact_email ?? '', operator_address: o.operator_address ?? '' })
      setEditOrg(true)
    }
    setTimeout(() => identityRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 120)
  }, [q.data])
  if (q.isLoading) return <div className="py-16 text-center text-[var(--color-faint)] text-sm">loading…</div>
  if (q.error || !q.data) return <div className="py-16 text-center text-[var(--color-faint)] text-sm">Could not load.</div>
  const d = q.data
  const org = d.organization
  const pct = Math.round((d.readiness.passed / d.readiness.total) * 100)
  const tone = pct === 100 ? 'var(--color-good)' : pct >= 60 ? 'var(--color-warn)' : 'var(--color-bad)'

  const startEdit = () => { setForm({ legal_name: org.legal_name ?? '', lei: org.lei ?? '', eori: org.eori ?? '', filing_contact_email: org.filing_contact_email ?? '', operator_address: org.operator_address ?? '' }); setEditOrg(true) }
  const saveOrg = async () => {
    setBusy(true)
    try { await api.patch('/v1/admin/organization', form); setEditOrg(false); await q.refetch() } finally { setBusy(false) }
  }
  const F = ({ k, label }: { k: string; label: string }) => (
    <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">{label}</div>
      <input className={inp} value={form[k] ?? ''} onChange={e => setForm({ ...form, [k]: e.target.value })} /></label>
  )

  return (
    <div className="space-y-6">
      {/* readiness — the "is my house in order" signal */}
      <Card className="p-5">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="relative h-14 w-14 shrink-0">
              <svg viewBox="0 0 36 36" className="h-14 w-14 -rotate-90">
                <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--color-line-2)" strokeWidth="3" />
                <circle cx="18" cy="18" r="15.5" fill="none" stroke={tone} strokeWidth="3" strokeLinecap="round"
                  strokeDasharray={`${(pct / 100) * 97.4} 97.4`} />
              </svg>
              <div className="absolute inset-0 grid place-items-center mono text-[12px] font-semibold" style={{ color: tone }}>{pct}%</div>
            </div>
            <div>
              <div className="text-[15px] font-semibold">Reporting readiness</div>
              <div className="text-[12px] text-[var(--color-mute)]">{d.readiness.passed} of {d.readiness.total} checks passing</div>
            </div>
          </div>
        </div>
        <div className="space-y-2">
          {d.readiness.checks.map(c => (
            <div key={c.key} className="flex items-start gap-2.5 text-[13px]">
              {c.ok ? <Check size={16} className="text-[var(--color-good)] mt-px shrink-0" /> : <AlertCircle size={16} className="text-[var(--color-warn)] mt-px shrink-0" />}
              <span className={c.ok ? 'text-[var(--color-mute)]' : 'text-[var(--color-ink)]'}>{c.label}{c.hint && <span className="text-[var(--color-warn)]"> — {c.hint}</span>}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* data health */}
      <div className="grid sm:grid-cols-4 gap-4">
        <Stat big={`${d.data.sites.scored}/${d.data.sites.total}`} label="sites scored" tone={d.data.sites.scored === d.data.sites.total ? 'good' : 'warn'} />
        <Stat big={eur(d.data.sites.value_eur)} label="asset value on the book" />
        <Stat big={`${d.data.plots.eudr_determined}/${d.data.plots.eudr_covered}`} label="EUDR plots determined" tone={d.data.plots.eudr_determined === d.data.plots.eudr_covered ? 'good' : 'warn'} />
        <Stat big={d.data.plots.needs_polygon} label="plots need a polygon" tone={d.data.plots.needs_polygon ? 'warn' : 'good'} />
      </div>

      {/* organization identity (editable — feeds CSRD/EUDR) */}
      <div ref={identityRef} className="scroll-mt-24">
      <Card className="p-5" style={editOrg && !(org.eori && org.filing_contact_email) ? { borderColor: 'var(--color-warn)' } : undefined}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2"><Building2 size={16} className="text-[var(--color-blue)]" /><h3 className="font-semibold">Reporting identity</h3></div>
          {!editOrg && <button onClick={startEdit} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Pencil size={13} /> Edit</button>}
        </div>
        {!editOrg ? (
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2 text-[13px]">
            {[['Name', org.name], ['Legal name', org.legal_name], ['Type', org.type], ['Country', org.country],
              ['LEI', org.lei], ['EORI', org.eori], ['Filing contact', org.filing_contact_email], ['Operator address', org.operator_address]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 border-b border-[var(--color-line)] pb-1.5">
                <span className="text-[var(--color-mute)]">{k}</span>
                <span className={v ? 'text-[var(--color-ink)] text-right' : 'text-[var(--color-warn)]'}>{v || 'not set'}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <RegistryLookup onPick={h => setForm(f => ({ ...f, legal_name: h.legal_name, lei: h.lei,
              operator_address: h.address ?? f.operator_address ?? '' }))} />
            <div className="grid sm:grid-cols-2 gap-3">
              <F k="legal_name" label="Legal name" /><F k="lei" label="LEI" />
              <F k="eori" label="EORI" /><F k="filing_contact_email" label="Filing contact email" />
              <F k="operator_address" label="Operator address" />
            </div>
            <div className="flex gap-3"><Button onClick={saveOrg} disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
              <button onClick={() => setEditOrg(false)} className="text-[13px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Cancel</button></div>
          </div>
        )}
      </Card>
      </div>

      {/* reporting basis — the as-of assumptions every filing is computed on */}
      <ReportingBasis />

      {/* golden-source freshness — is the data under a filing current? */}
      <GoldenSourceFeeds />

      {/* governance + access summary — jump to the relevant tab */}
      <div className="grid sm:grid-cols-3 gap-4">
        <button onClick={() => onTab('Approvals')} className="text-left"><Card className="p-4 hover:border-[var(--color-sky)] transition cursor-pointer h-full">
          <div className="flex items-center gap-2 mb-2"><CheckSquare size={15} className="text-[var(--color-sky)]" /><span className="text-[13px] font-semibold">Approvals</span></div>
          <div className="text-2xl font-semibold" style={{ color: d.governance.pending_approvals ? 'var(--color-warn)' : 'var(--color-ink)' }}>{d.governance.pending_approvals}</div>
          <div className="text-[11px] text-[var(--color-faint)]">pending · {d.governance.second_approver ? '4-eyes ready' : 'no second approver'}</div>
        </Card></button>
        <button onClick={() => onTab('Audit')} className="text-left"><Card className="p-4 hover:border-[var(--color-sky)] transition cursor-pointer h-full">
          <div className="flex items-center gap-2 mb-2"><ScrollText size={15} className="text-[var(--color-sky)]" /><span className="text-[13px] font-semibold">Audit trail</span></div>
          <div className="text-2xl font-semibold">{d.governance.audit_events_30d}</div>
          <div className="text-[11px] text-[var(--color-faint)]">events in the last 30 days</div>
        </Card></button>
        <button onClick={() => onTab('Users')} className="text-left"><Card className="p-4 hover:border-[var(--color-sky)] transition cursor-pointer h-full">
          <div className="flex items-center gap-2 mb-2"><UsersIcon size={15} className="text-[var(--color-sky)]" /><span className="text-[13px] font-semibold">Users</span></div>
          <div className="text-2xl font-semibold">{d.access.active}<span className="text-[var(--color-faint)] text-base">/{d.access.users}</span></div>
          <div className="text-[11px] text-[var(--color-faint)]">active · {d.entitlements.join(', ') || 'no modules'}</div>
        </Card></button>
      </div>
    </div>
  )
}

interface RSettings { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string; is_override: boolean }
const SCENARIOS = [['baseline', 'Baseline (today)'], ['rcp45', 'RCP 4.5 — moderate'], ['rcp85', 'RCP 8.5 — high']]
const HORIZONS = [['current', 'Current'], ['2030', '2030'], ['2040', '2040'], ['2050', '2050']]

function ReportingBasis() {
  const q = useQuery({ queryKey: ['reporting-settings'], queryFn: () => api.get<RSettings>('/v1/admin/reporting-settings') })
  const [edit, setEdit] = useState(false)
  const [f, setF] = useState<Partial<RSettings>>({})
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const d = q.data
  const start = () => { if (d) setF({ scenario: d.scenario, horizon: d.horizon, materiality_threshold: d.materiality_threshold, reporting_period_end: d.reporting_period_end }); setEdit(true); setMsg(null) }
  const save = async () => {
    setBusy(true); setMsg(null)
    try { await api.patch('/v1/admin/reporting-settings', f); setEdit(false); await q.refetch(); setMsg('✓ Saved — every filing now uses this basis.') }
    catch (e) { setMsg((e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not save.') }
    finally { setBusy(false) }
  }
  const sel = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
  const label = (arr: string[][], v?: string) => arr.find(([k]) => k === v)?.[1] ?? v

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2"><ShieldCheck size={16} className="text-[var(--color-blue)]" /><h3 className="font-semibold">Reporting basis</h3></div>
        {!edit && <button onClick={start} className="inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Pencil size={13} /> Edit</button>}
      </div>
      <p className="text-[11.5px] text-[var(--color-faint)] mb-3">The as-of assumptions every CSRD/ESRS filing is computed on. The r²≥0.40 publish gate is a fixed honesty constant — not settable here.</p>
      {q.isLoading || !d ? <div className="text-[13px] text-[var(--color-faint)] py-2">loading…</div> : !edit ? (
        <div className="grid sm:grid-cols-4 gap-x-8 gap-y-2 text-[13px]">
          {[['Reporting period', d.reporting_period_end], ['Scenario', label(SCENARIOS, d.scenario)], ['Horizon', label(HORIZONS, d.horizon)], ['Materiality threshold', `score ≥ ${d.materiality_threshold}`]].map(([k, v]) => (
            <div key={k}><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-0.5 mono">{k}</div><div className="text-[var(--color-ink)]">{v}</div></div>
          ))}
          <div className="sm:col-span-4 text-[11px] text-[var(--color-faint)]">{d.is_override ? 'Custom basis set for this organization.' : 'Using platform defaults.'}</div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">Reporting period end</div>
              <input type="date" className={inp} value={f.reporting_period_end ?? ''} onChange={e => setF({ ...f, reporting_period_end: e.target.value })} /></label>
            <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">Materiality threshold (0–100)</div>
              <input type="number" min={0} max={100} className={inp} value={f.materiality_threshold ?? 40} onChange={e => setF({ ...f, materiality_threshold: Number(e.target.value) })} /></label>
            <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">Scenario</div>
              <select className={sel + ' w-full'} value={f.scenario} onChange={e => setF({ ...f, scenario: e.target.value })}>{SCENARIOS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className="block"><div className="text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono">Time horizon</div>
              <select className={sel + ' w-full'} value={f.horizon} onChange={e => setF({ ...f, horizon: e.target.value })}>{HORIZONS.map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
          </div>
          <div className="flex gap-3 items-center"><Button onClick={save} disabled={busy}>{busy ? 'Saving…' : 'Save basis'}</Button>
            <button onClick={() => setEdit(false)} className="text-[13px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Cancel</button></div>
        </div>
      )}
      {msg && <div className="mt-2 text-[12px]" style={{ color: msg.startsWith('✓') ? 'var(--color-good)' : 'var(--color-warn)' }}>{msg}</div>}
    </Card>
  )
}

interface Feed { key: string; name: string; category: string; cadence_days: number; invalidates_basis: boolean; note: string; last_refresh: string | null; days_since: number | null; status: string; maturity?: string; auto_refresh?: boolean; next_due_days?: number | null; last_by?: string | null; last_status?: string | null }
const FEED_TONE: Record<string, string> = { fresh: 'var(--color-good)', due_soon: 'var(--color-warn)', overdue: 'var(--color-bad)', failed: 'var(--color-bad)', untracked: 'var(--color-faint)' }
// honest state of each ingestion path: green = real & landed; amber = proxy/partial/live-but-not-stored; faint = not yet real
const MATURITY: Record<string, { label: string; tone: string }> = {
  live: { label: 'live', tone: 'var(--color-good)' },
  on_demand: { label: 'on-demand', tone: 'var(--color-warn)' },
  proxy: { label: 'proxy', tone: 'var(--color-warn)' },
  partial: { label: 'partial', tone: 'var(--color-warn)' },
  estimated: { label: 'estimated', tone: 'var(--color-faint)' },
  planned: { label: 'planned', tone: 'var(--color-faint)' },
}

interface RegHit { lei: string; legal_name: string; country?: string; jurisdiction?: string; status?: string; address?: string }
// Auto-fill the reporting identity from GLEIF — the authoritative LEI registry we already ingest. The
// operator searches their entity (name or LEI) and picks it; we fill legal name + LEI + registered address.
function RegistryLookup({ onPick }: { onPick: (h: RegHit) => void }) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<RegHit[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const search = async () => {
    if (q.trim().length < 2) return
    setBusy(true); setErr(null)
    try { const r = await api.get<{ results: RegHit[] }>(`/v1/admin/registry/search?q=${encodeURIComponent(q.trim())}`); setHits(r.results) }
    catch { setErr('Couldn’t reach the LEI registry — try again, or enter the details manually below.'); setHits(null) }
    finally { setBusy(false) }
  }
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3">
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Auto-fill from the global LEI registry (GLEIF)</div>
      <div className="flex gap-2">
        <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && search()}
          placeholder="Search by legal name, or paste a 20-char LEI"
          className="flex-1 bg-[var(--color-bg)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <Button onClick={search} disabled={busy || q.trim().length < 2}>{busy ? 'Searching…' : 'Search'}</Button>
      </div>
      {err && <div className="text-[12px] text-[var(--color-bad)] mt-2">{err}</div>}
      {hits && hits.length === 0 && <div className="text-[12px] text-[var(--color-faint)] mt-2">No match in GLEIF — check the spelling, or enter the details manually below.</div>}
      {hits && hits.length > 0 && (
        <div className="mt-2 flex flex-col gap-1 max-h-56 overflow-y-auto">
          {hits.map(h => (
            <button key={h.lei} onClick={() => onPick(h)} className="text-left rounded-lg border border-[var(--color-line)] px-3 py-2 hover:border-[var(--color-sky)] transition">
              <div className="text-[13px] text-[var(--color-ink)]">{h.legal_name}</div>
              <div className="mono text-[11px] text-[var(--color-faint)] truncate">{h.lei} · {[h.country || h.jurisdiction, h.status, h.address].filter(Boolean).join(' · ')}</div>
            </button>
          ))}
        </div>
      )}
      <div className="mono text-[10px] text-[var(--color-faint)] mt-2">Fills legal name, LEI &amp; registered address from GLEIF. EORI &amp; the filing contact aren’t in GLEIF — add those below.</div>
    </div>
  )
}

// Feeds grouped into a few categories — each a card the operator opens to see the real named sources
// and their live status. Keeps the panel compact while the provenance stays one click away.
const FEED_CATEGORIES: { key: string; label: string; icon: typeof Database; blurb: string }[] = [
  { key: 'hazard', label: 'Climate & hazard', icon: CloudRain, blurb: 'Satellite & agency hazard feeds — heat, drought, flood, fire, storm, seismic.' },
  { key: 'nature', label: 'Nature', icon: Leaf, blurb: 'Forest cover / deforestation for EUDR & ESRS E4.' },
  { key: 'reference', label: 'Reference', icon: Landmark, blurb: 'Entity identity (LEI) & sector reference data.' },
]

function GoldenSourceFeeds() {
  const q = useQuery({ queryKey: ['data-feeds'], queryFn: () => api.get<{ feeds: Feed[] }>('/v1/admin/data-feeds') })
  const [busy, setBusy] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)
  const feeds = q.data?.feeds ?? []
  const refresh = async (k: string) => {
    setBusy(k)
    try { await api.post(`/v1/admin/data-feeds/${k}/refresh`, {}); await q.refetch() } finally { setBusy(null) }
  }
  // worst-status summary for a category card: red if any failed/overdue, amber if due soon, else green.
  const catSummary = (cat: string) => {
    const fs = feeds.filter(f => f.category === cat)
    const failed = fs.filter(f => f.status === 'failed' || f.status === 'overdue').length
    const soon = fs.filter(f => f.status === 'due_soon').length
    const auto = fs.filter(f => f.auto_refresh).length
    const tone = failed ? 'var(--color-bad)' : soon ? 'var(--color-warn)' : 'var(--color-good)'
    const label = failed ? `${failed} need${failed !== 1 ? '' : 's'} attention` : soon ? `${soon} due soon` : auto ? 'all current' : `${fs.length} source${fs.length !== 1 ? 's' : ''}`
    return { n: fs.length, tone, label, auto }
  }

  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-1"><Database size={16} className="text-[var(--color-blue)]" /><h3 className="font-semibold">Golden-source health</h3></div>
      <p className="text-[11.5px] text-[var(--color-faint)] mb-3">
        Your filings run on named satellite &amp; agency feeds that refresh <b>automatically</b> on their own cadence — no action needed.
        Open a category to see each source and its live status; anything stale or failed is flagged and raised before it can reach a filing.
      </p>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)] py-2">loading…</div> : (
        <div className="space-y-2">
          {FEED_CATEGORIES.filter(c => feeds.some(f => f.category === c.key)).map(cat => {
            const s = catSummary(cat.key)
            const isOpen = open === cat.key
            return (
              <div key={cat.key} className="rounded-xl border border-[var(--color-line)] overflow-hidden">
                {/* the category "button" */}
                <button onClick={() => setOpen(isOpen ? null : cat.key)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-[var(--color-bg-2)] transition">
                  <cat.icon size={17} className="text-[var(--color-blue)] shrink-0" />
                  <div className="min-w-0 flex-1 text-left">
                    <div className="text-[13.5px] font-medium text-[var(--color-ink)]">{cat.label} <span className="text-[var(--color-faint)] font-normal">· {s.n}</span></div>
                    <div className="text-[11px] text-[var(--color-faint)] truncate">{cat.blurb}</div>
                  </div>
                  <span className="inline-flex items-center gap-1.5 mono text-[10.5px] uppercase tracking-wide shrink-0" style={{ color: s.tone }}>
                    <span className="h-2 w-2 rounded-full" style={{ background: s.tone }} />{s.label}
                  </span>
                  <ChevronDown size={15} className={`shrink-0 text-[var(--color-faint)] transition-transform ${isOpen ? 'rotate-180' : ''}`} />
                </button>
                {/* the dropdown — the real named sources + status */}
                {isOpen && (
                  <div className="border-t border-[var(--color-line)] bg-[var(--color-bg-2)] px-3 py-2 space-y-1.5">
                    {feeds.filter(f => f.category === cat.key).map(f => {
                      const auto = !!f.auto_refresh
                      const subline = auto
                        ? `auto · every ${f.cadence_days}d${f.last_refresh ? ` · refreshed ${f.days_since}d ago${f.next_due_days != null ? ` · next in ${f.next_due_days}d` : ''}` : ' · awaiting first auto-refresh'}`
                        : (f.maturity === 'on_demand' ? 'fetched per query — nothing to schedule' : f.maturity === 'planned' ? 'adapter not yet wired' : 'derived — not a live feed')
                      const statusLabel = auto ? f.status.replace('_', ' ') : (MATURITY[f.maturity ?? '']?.label ?? '—')
                      const statusTone = auto ? (FEED_TONE[f.status] ?? 'var(--color-faint)') : (MATURITY[f.maturity ?? '']?.tone ?? 'var(--color-faint)')
                      return (
                        <div key={f.key} className="flex items-center gap-3 rounded-lg bg-[var(--color-bg)] border border-[var(--color-line)] px-3 py-2">
                          <span className="h-2 w-2 rounded-full shrink-0" style={{ background: statusTone }} />
                          <div className="min-w-0 flex-1">
                            <div className="text-[13px] text-[var(--color-ink)] truncate">{f.name}
                              {f.maturity && MATURITY[f.maturity] && <span className="mono text-[9px] ml-1.5 px-1 py-0.5 rounded uppercase" style={{ color: MATURITY[f.maturity].tone, background: `color-mix(in oklab, ${MATURITY[f.maturity].tone} 14%, transparent)` }}>{MATURITY[f.maturity].label}</span>}
                              {f.invalidates_basis && <span className="mono text-[9px] ml-1.5 px-1 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)] uppercase">scores</span>}</div>
                            <div className="text-[11px] text-[var(--color-faint)] truncate" title={f.note}>{subline}</div>
                          </div>
                          <span className="mono text-[10px] uppercase tracking-wide shrink-0" style={{ color: statusTone }}>{statusLabel}</span>
                          {auto && <button onClick={() => refresh(f.key)} disabled={busy === f.key} title="Refresh now (override — feeds also refresh automatically)"
                            className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)] disabled:opacity-50 shrink-0">
                            <RefreshCw size={12} className={busy === f.key ? 'animate-spin' : ''} /> {busy === f.key ? '…' : 'Refresh now'}
                          </button>}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

// what each role is FOR — shown at the point of assignment so an admin picks the right one without guessing
const ROLE_INFO: Record<string, { blurb: string; can: string }> = {
  admin:    { blurb: 'Runs the workspace', can: 'Everything — set up the org, manage users & roles, produce and approve filings, see the audit trail.' },
  analyst:  { blurb: 'Does the work', can: 'Build the data & filings and submit them for approval. Cannot approve their own work (4-eyes).' },
  approver: { blurb: 'The second pair of eyes', can: 'Reviews and signs off filings and price claims — the checker in 4-eyes. Cannot be the maker.' },
  viewer:   { blurb: 'Read-only', can: 'Sees the dashboards, risk and reports. Makes no changes and submits nothing.' },
}

function RoleCard({ name, selected, onClick }: { name: string; selected: boolean; onClick: () => void }) {
  const info = ROLE_INFO[name]
  return (
    <button onClick={onClick} title={info?.can}
      className={`text-left rounded-xl border p-3 transition ${selected
        ? 'border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,transparent)]'
        : 'border-[var(--color-line-2)] hover:border-[var(--color-line)]'}`}>
      <div className="flex items-center gap-1.5">
        <span className={`text-[9px] ${selected ? 'text-[var(--color-sky)]' : 'text-[var(--color-faint)]'}`}>{selected ? '●' : '○'}</span>
        <span className="text-[13px] font-medium capitalize text-[var(--color-ink)]">{name}</span>
      </div>
      {info && <>
        <div className="text-[11px] text-[var(--color-sky)] mt-1">{info.blurb}</div>
        <div className="text-[11px] text-[var(--color-faint)] mt-0.5 leading-snug">{info.can}</div>
      </>}
    </button>
  )
}

function Users() {
  const uq = useQuery({ queryKey: ['admin-users'], queryFn: () => api.get<User[]>('/v1/admin/users') })
  const rq = useQuery({ queryKey: ['admin-roles'], queryFn: () => api.get<Role[]>('/v1/admin/roles') })
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role_ids: [] as string[] })
  const [msg, setMsg] = useState<string | null>(null)
  const roles = rq.data ?? []
  const roleId = (name: string) => roles.find(r => r.name === name)?.id

  const create = async () => {
    if (!form.email || !form.full_name || form.password.length < 6) { setMsg('Email, name, and a 6+ char password are required.'); return }
    try { await api.post('/v1/admin/users', form); setForm({ email: '', full_name: '', password: '', role_ids: [] }); setMsg('✓ User created.'); await uq.refetch() }
    catch (e) { setMsg((e as { body?: { detail?: { message?: string } } })?.body?.detail?.message || 'Could not create user.') }
  }
  const toggle = async (u: User) => {
    await api.patch(`/v1/admin/users/${u.id}`, { status: u.status === 'active' ? 'disabled' : 'active' }); await uq.refetch()
  }
  const setRoles = async (u: User, roleName: string) => {
    const current = new Set(u.roles.map(roleId).filter(Boolean) as string[])
    const rid = roleId(roleName); if (!rid) return
    if (current.has(rid)) current.delete(rid); else current.add(rid)
    await api.patch(`/v1/admin/users/${u.id}`, { role_ids: [...current] }); await uq.refetch()
  }

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-3"><UserPlus size={16} className="text-[var(--color-sky)]" /><span className="text-[14px] font-semibold">Add a user</span></div>
        <div className="grid sm:grid-cols-4 gap-3">
          <input className={inp} placeholder="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} />
          <input className={inp} placeholder="full name" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })} />
          <input className={inp} placeholder="temp password (6+)" type="password" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} />
          <div className="flex items-end"><Button onClick={create}>Create user</Button></div>
        </div>
        <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-faint)] mt-4 mb-2">Assign a role — what should this person be able to do?</div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {roles.filter(r => r.name !== 'platform-operator').map(r => {
            const on = form.role_ids.includes(r.id)
            return <RoleCard key={r.id} name={r.name} selected={on}
              onClick={() => setForm({ ...form, role_ids: on ? form.role_ids.filter(x => x !== r.id) : [...form.role_ids, r.id] })} />
          })}
        </div>
        {msg && <div className="mt-3 text-[12.5px] text-[var(--color-mute)]">{msg}</div>}
      </Card>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
            <th className="font-normal py-2.5 px-4">User</th><th className="font-normal px-4">Status</th><th className="font-normal px-4">Roles</th><th className="font-normal px-4"></th>
          </tr></thead>
          <tbody>
            {(uq.data ?? []).map(u => (
              <tr key={u.id} className="border-b border-[var(--color-line)] last:border-0">
                <td className="py-2.5 px-4"><div className="text-[var(--color-ink)]">{u.full_name}</div><div className="text-[11px] text-[var(--color-faint)]">{u.email}</div></td>
                <td className="px-4"><span className={`mono text-[10px] px-2 py-0.5 rounded-full ${u.status === 'active' ? 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]' : 'text-[var(--color-faint)] bg-[color-mix(in_oklab,var(--color-faint)_14%,transparent)]'}`}>{u.status}</span></td>
                <td className="px-4">
                  <div className="flex flex-wrap gap-1.5">
                    {roles.map(r => {
                      const on = u.roles.includes(r.name)
                      return <button key={r.id} onClick={() => setRoles(u, r.name)}
                        className={`text-[10.5px] px-2 py-0.5 rounded-full border ${on ? 'border-[var(--color-blue)] text-[var(--color-blue)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]'}`}>{r.name}</button>
                    })}
                  </div>
                </td>
                <td className="px-4 text-right"><button onClick={() => toggle(u)} className="text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">{u.status === 'active' ? 'Disable' : 'Enable'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function Roles() {
  const rq = useQuery({ queryKey: ['admin-roles'], queryFn: () => api.get<Role[]>('/v1/admin/roles') })
  const pq = useQuery({ queryKey: ['admin-perms'], queryFn: () => api.get<Perm[]>('/v1/admin/permissions') })
  const [busy, setBusy] = useState<string | null>(null)
  const perms = pq.data ?? []

  const toggle = async (role: Role, code: string) => {
    const set = new Set(role.permissions)
    if (set.has(code)) set.delete(code); else set.add(code)
    setBusy(role.id)
    try { await api.patch(`/v1/admin/roles/${role.id}/permissions`, { permission_codes: [...set] }); await rq.refetch() }
    finally { setBusy(null) }
  }

  return (
    <div className="space-y-4">
      {(rq.data ?? []).map(role => (
        <Card key={role.id} className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-[14px] font-semibold capitalize">{role.name}</span>
            {role.is_system && <span className="mono text-[9px] px-2 py-0.5 rounded-full text-[var(--color-faint)] border border-[var(--color-line-2)]">system</span>}
            {busy === role.id && <span className="text-[11px] text-[var(--color-faint)]">saving…</span>}
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
            {perms.map(p => {
              const on = role.permissions.includes(p.code)
              return (
                <button key={p.code} onClick={() => toggle(role, p.code)} title={p.description}
                  className={`text-left text-[11.5px] px-2.5 py-1.5 rounded-lg border transition ${on ? 'border-[var(--color-good)] text-[var(--color-ink)] bg-[color-mix(in_oklab,var(--color-good)_8%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]'}`}>
                  <span className="mono">{on ? '✓ ' : ''}{p.code}</span>
                </button>
              )
            })}
          </div>
        </Card>
      ))}
    </div>
  )
}

function Matrix() {
  const q = useQuery({ queryKey: ['approval-policy'], queryFn: () => api.get<Policy[]>('/v1/admin/approval-policy') })
  const [busy, setBusy] = useState<string | null>(null)
  const set = async (p: Policy, patch: { requires_approval?: boolean; threshold_eur?: number | null }) => {
    setBusy(p.action_key)
    try {
      await api.patch('/v1/admin/approval-policy', {
        action_key: p.action_key, material_fields: p.material_fields,
        requires_approval: patch.requires_approval ?? p.requires_approval,
        threshold_eur: patch.threshold_eur !== undefined ? patch.threshold_eur : p.threshold_eur,
      })
      await q.refetch()
    } finally { setBusy(null) }
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex items-center gap-2">
        <ShieldCheck size={16} className="text-[var(--color-sky)]" />
        <span className="text-[13px] text-[var(--color-mute)]">Which changes require a second approver (4-eyes). Everything is audited regardless. <span className="text-[var(--color-faint)]">Who approves = your team members with the <b>Approver</b> role.</span></span>
      </div>
      {(q.data ?? []).map(p => (
        <div key={p.action_key} className="px-4 py-3 border-b border-[var(--color-line)] last:border-0">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="text-[13.5px] text-[var(--color-ink)]">{p.label}</div>
              <div className="text-[11px] text-[var(--color-faint)] mono">{p.action_key}{p.material_fields.length ? ` · material: ${p.material_fields.join(', ')}` : ''}{p.org_override ? ' · org override' : ' · platform default'}</div>
            </div>
            <button disabled={busy === p.action_key} onClick={() => set(p, { requires_approval: !p.requires_approval })}
              className={`relative w-11 h-6 rounded-full transition ${p.requires_approval ? 'bg-[var(--color-good)]' : 'bg-[var(--color-line-2)]'}`}>
              <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${p.requires_approval ? 'left-[22px]' : 'left-0.5'}`} />
            </button>
            <span className="text-[12px] w-28 text-right" style={{ color: p.requires_approval ? 'var(--color-good)' : 'var(--color-faint)' }}>{p.requires_approval ? '4-eyes required' : 'direct'}</span>
          </div>
          {/* value threshold — for actions that support it (forward-risk decisions): only above the line needs 4-eyes */}
          {p.supports_threshold && p.requires_approval && (
            <div className="flex items-center gap-2 mt-2 pl-1">
              <span className="text-[11.5px] text-[var(--color-mute)]">Only when the exposure is above</span>
              <div className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1">
                <span className="text-[11px] text-[var(--color-faint)]">€</span>
                <input type="number" min={0} defaultValue={p.threshold_eur ?? 0}
                  onBlur={e => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== (p.threshold_eur ?? 0)) set(p, { threshold_eur: v }) }}
                  className="w-28 bg-transparent text-[12px] mono outline-none" />
              </div>
              <span className="text-[11px] text-[var(--color-faint)]">{(p.threshold_eur ?? 0) === 0 ? 'every decision needs 4-eyes' : 'smaller decisions apply directly'}</span>
            </div>
          )}
        </div>
      ))}
    </Card>
  )
}

// ── Decision playbook: what happens automatically when each decision is approved ──────────────────────────
interface PlayRow { action: string; label: string; spin_task?: boolean; assignee_user_id?: string | null; due_days?: number | null; notify?: boolean; flag_disclosure?: boolean; watchlist?: boolean; webhook?: boolean; org_override?: boolean }
interface Member { user_id: string; email: string; name: string }
const AUTO: { key: keyof PlayRow; label: string; hint: string }[] = [
  { key: 'spin_task', label: 'Kanban card', hint: 'create a tracked task on the board' },
  { key: 'notify', label: 'Notify owner', hint: 'email the assigned owner' },
  { key: 'flag_disclosure', label: 'Flag for filing', hint: 'include the exposure in the next climate disclosure' },
  { key: 'watchlist', label: 'Watchlist', hint: 'add to the monitoring watchlist + schedule a re-check' },
  { key: 'webhook', label: 'Webhook', hint: 'emit risk.decision.approved to your registered endpoints' },
]

function DecisionPlaybook() {
  const q = useQuery({ queryKey: ['decision-playbook'], queryFn: () => api.get<{ members: Member[]; playbook: PlayRow[] }>('/v1/admin/decision-playbook') })
  const [busy, setBusy] = useState<string | null>(null)
  const set = async (p: PlayRow, patch: Partial<PlayRow>) => {
    setBusy(p.action)
    try { await api.patch('/v1/admin/decision-playbook', { action: p.action, ...patch }); await q.refetch() }
    finally { setBusy(null) }
  }
  const members = q.data?.members ?? []
  return (
    <Card className="p-0 overflow-hidden mt-4">
      <div className="p-4 border-b border-[var(--color-line)] flex items-center gap-2">
        <ShieldCheck size={16} className="text-[var(--color-sky)]" />
        <span className="text-[13px] text-[var(--color-mute)]">Decision playbook — what runs automatically when a forward-risk decision is <b>approved</b>. Off by default; outward actions still need a person.</span>
      </div>
      {(q.data?.playbook ?? []).map(p => (
        <div key={p.action} className="px-4 py-3 border-b border-[var(--color-line)] last:border-0">
          <div className="flex items-center justify-between gap-3 mb-2">
            <div className="text-[13.5px] text-[var(--color-ink)] font-medium">{p.label} <span className="mono text-[10px] text-[var(--color-faint)] ml-1">{p.org_override ? 'org' : 'default'}</span></div>
            {(p.spin_task || p.watchlist) && (
              <div className="flex items-center gap-2">
                {p.spin_task && (
                  <select value={p.assignee_user_id ?? ''} onChange={e => set(p, { assignee_user_id: e.target.value || null })} disabled={busy === p.action}
                    className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[11.5px] outline-none">
                    <option value="">unassigned</option>
                    {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
                  </select>
                )}
                <div className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line)] px-2 py-1">
                  <input type="number" min={0} defaultValue={p.due_days ?? 0} onBlur={e => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== (p.due_days ?? 0)) set(p, { due_days: v }) }} className="w-12 bg-transparent text-[11.5px] mono outline-none" />
                  <span className="text-[10.5px] text-[var(--color-faint)]">{p.spin_task ? 'days to do' : 'days to re-review'}</span>
                </div>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {AUTO.map(a => {
              const on = !!p[a.key]
              return (
                <button key={a.key} disabled={busy === p.action} title={a.hint} onClick={() => set(p, { [a.key]: !on } as Partial<PlayRow>)}
                  className={`px-2.5 py-1 rounded-lg text-[11.5px] border transition inline-flex items-center gap-1.5 ${on ? 'border-transparent text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}
                  style={on ? { background: 'color-mix(in oklab, var(--color-good) 14%, transparent)' } : undefined}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ background: on ? 'var(--color-good)' : 'var(--color-line-2)' }} />{a.label}
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </Card>
  )
}

interface AppetiteKpi { key: string; label: string; fmt: string; value: number | null; amber: number | null; red: number | null; direction: string | null; status: string | null }
const RAG_C: Record<string, string> = { ok: 'var(--color-good)', amber: '#f0a860', red: '#fb7185' }

function KriAppetite() {
  const [fw, setFw] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['kri-appetite', fw], queryFn: () => api.get<{ supported: boolean; framework?: string; label?: string; frameworks?: { framework: string; label: string }[]; kpis?: AppetiteKpi[]; message?: string }>(`/v1/admin/kri-appetite${fw ? `?framework=${fw}` : ''}`) })
  const [busy, setBusy] = useState<string | null>(null)
  const set = async (k: AppetiteKpi, patch: Record<string, unknown>) => {
    setBusy(k.key)
    try { await api.patch('/v1/admin/kri-appetite', { kri_key: k.key, framework: q.data?.framework, ...patch }); await q.refetch() }
    finally { setBusy(null) }
  }
  const d = q.data
  const fws = d?.frameworks ?? []
  if (d && !d.supported) return <Card className="p-8 mt-4 text-[13px] text-[var(--color-mute)]">{d.message ?? 'No KRI dashboard for this organisation type.'}</Card>
  const kpis = d?.kpis ?? []
  const unit = (f: string) => f === 'pct' ? '%' : f === 'eur' ? '€' : f === 'ha' ? 'ha' : f === 'dec' ? '·' : ''
  return (
    <Card className="p-0 overflow-hidden mt-4">
      <div className="p-4 border-b border-[var(--color-line)] flex items-center gap-2">
        <Gauge size={16} className="text-[var(--color-sky)]" />
        <span className="text-[13px] text-[var(--color-mute)]">Risk-appetite bands on each KRI — a value that crosses <b>warn</b> turns amber, <b>breach</b> turns red on the KRI dashboard. Empty = the indicator is shown but not graded. Direction sets which way is bad.</span>
      </div>
      {fws.length > 1 && (
        <div className="px-4 py-2.5 border-b border-[var(--color-line)] flex flex-wrap gap-1.5">
          {fws.map(f => (
            <button key={f.framework} onClick={() => setFw(f.framework)}
              className={`px-2.5 py-1 rounded-lg text-[11.5px] border transition ${d?.framework === f.framework ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{f.label}</button>
          ))}
        </div>
      )}
      <div className="hidden sm:grid grid-cols-[1.6fr_0.8fr_0.8fr_0.8fr_1fr] gap-3 px-4 py-2 border-b border-[var(--color-line)] mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">
        <span>Indicator</span><span>Now</span><span>Warn (amber)</span><span>Breach (red)</span><span>Direction</span>
      </div>
      {kpis.map(k => {
        const rag = k.status ? RAG_C[k.status] : null
        const vfmt = k.value == null ? '—' : k.fmt === 'pct' ? `${k.value}%` : k.fmt === 'ha' ? `${k.value} ha` : k.fmt === 'dec' ? String(k.value) : k.fmt === 'eur' ? (k.value >= 1e6 ? `€${(k.value / 1e6).toFixed(1)}m` : `€${Math.round(k.value / 1e3)}k`) : Math.round(k.value).toLocaleString('en-GB')
        return (
          <div key={k.key} className="grid grid-cols-2 sm:grid-cols-[1.6fr_0.8fr_0.8fr_0.8fr_1fr] gap-3 px-4 py-3 border-b border-[var(--color-line)] last:border-0 items-center">
            <div className="flex items-center gap-2">
              {k.status && <span className="w-2 h-2 rounded-full shrink-0" style={{ background: rag! }} />}
              <span className="text-[13px] text-[var(--color-ink)]">{k.label}</span>
              <span className="mono text-[9px] text-[var(--color-faint)]">{unit(k.fmt)}</span>
            </div>
            <div className="mono text-[12.5px] tabular-nums" style={rag ? { color: rag } : { color: 'var(--color-mute)' }}>{vfmt}</div>
            <ThreshInput disabled={busy === k.key} defaultValue={k.amber} onCommit={v => set(k, { amber: v })} />
            <ThreshInput disabled={busy === k.key} defaultValue={k.red} onCommit={v => set(k, { red: v })} />
            <select value={k.direction ?? 'higher_worse'} disabled={busy === k.key} onChange={e => set(k, { direction: e.target.value })}
              className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[11.5px] outline-none">
              <option value="higher_worse">higher is worse</option>
              <option value="lower_worse">lower is worse</option>
            </select>
          </div>
        )
      })}
      {kpis.length === 0 && <div className="px-4 py-6 text-[13px] text-[var(--color-faint)]">loading…</div>}
    </Card>
  )
}

function ThreshInput({ defaultValue, onCommit, disabled }: { defaultValue: number | null; onCommit: (v: number | null) => void; disabled: boolean }) {
  return (
    <input type="number" step="any" disabled={disabled} defaultValue={defaultValue ?? ''} placeholder="—"
      onBlur={e => { const raw = e.target.value.trim(); const v = raw === '' ? null : Number(raw); if (v !== defaultValue) onCommit(Number.isNaN(v as number) ? null : v) }}
      className="w-20 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1 text-[11.5px] mono outline-none focus:border-[var(--color-sky)]" />
  )
}
