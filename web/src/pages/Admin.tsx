import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserPlus, ShieldCheck, Check, AlertCircle, Building2, CheckSquare, ScrollText, Users as UsersIcon, Pencil, Database, RefreshCw } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, Button, Stat } from '../components/ui'
import Approvals from './Approvals'
import Audit from './Audit'

interface User { id: string; email: string; full_name: string; status: string; roles: string[]; last_login_at: string | null }
interface Role { id: string; name: string; description: string | null; is_system: boolean; permissions: string[] }
interface Perm { code: string; description: string }
interface Policy { action_key: string; label: string; requires_approval: boolean; material_fields: string[]; org_override: boolean }
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
  const tabs = [
    perms.includes('admin.users.manage') && 'Overview',
    perms.includes('approvals.view') && 'Approvals',
    perms.includes('admin.audit.view') && 'Audit',
    perms.includes('admin.users.manage') && 'Users',
    perms.includes('admin.roles.manage') && 'Roles',
    perms.includes('admin.approval_policy.manage') && 'Approval matrix',
  ].filter(Boolean) as string[]
  const [tab, setTab] = useState(tabs[0] ?? 'Overview')

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Governance · control center</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Control center</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Is your organization set up correctly and your data complete enough to trust the numbers? Reporting identity, data readiness, users, roles, and the approval matrix — in one place.</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-[13px] border transition ${tab === t ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{t}</button>
        ))}
      </div>
      {tab === 'Overview' && <Overview onTab={setTab} />}
      {tab === 'Approvals' && <Approvals embedded />}
      {tab === 'Audit' && <Audit embedded />}
      {tab === 'Users' && <Users />}
      {tab === 'Roles' && <Roles />}
      {tab === 'Approval matrix' && <Matrix />}
    </div>
  )
}

function Overview({ onTab }: { onTab: (t: string) => void }) {
  const q = useQuery({ queryKey: ['control-center'], queryFn: () => api.get<CC>('/v1/admin/control-center') })
  const [editOrg, setEditOrg] = useState(false)
  const [form, setForm] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
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
      <Card className="p-5">
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

interface Feed { key: string; name: string; category: string; cadence_days: number; invalidates_basis: boolean; note: string; last_refresh: string | null; days_since: number | null; status: string }
const FEED_TONE: Record<string, string> = { fresh: 'var(--color-good)', due_soon: 'var(--color-warn)', overdue: 'var(--color-bad)', untracked: 'var(--color-faint)' }

function GoldenSourceFeeds() {
  const q = useQuery({ queryKey: ['data-feeds'], queryFn: () => api.get<{ feeds: Feed[] }>('/v1/admin/data-feeds') })
  const [busy, setBusy] = useState<string | null>(null)
  const feeds = q.data?.feeds ?? []
  const refresh = async (k: string) => {
    setBusy(k)
    try { await api.post(`/v1/admin/data-feeds/${k}/refresh`, {}); await q.refetch() } finally { setBusy(null) }
  }
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-1"><Database size={16} className="text-[var(--color-blue)]" /><h3 className="font-semibold">Golden-source freshness</h3></div>
      <p className="text-[11.5px] text-[var(--color-faint)] mb-3">When each satellite/agency &amp; reference feed under your filings was last refreshed. Feeds that <b>invalidate a live basis</b> re-score on refresh; a frozen snapshot never moves — a refresh produces a new version.</p>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)] py-2">loading…</div> : (
        <div className="space-y-1.5">
          {feeds.map(f => (
            <div key={f.key} className="flex items-center gap-3 border border-[var(--color-line)] rounded-lg px-3 py-2">
              <span className="h-2 w-2 rounded-full shrink-0" style={{ background: FEED_TONE[f.status] ?? 'var(--color-faint)' }} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] text-[var(--color-ink)] truncate">{f.name}
                  {f.invalidates_basis && <span className="mono text-[9px] ml-1.5 px-1 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)] uppercase">scores</span>}</div>
                <div className="text-[11px] text-[var(--color-faint)]">{f.category} · every {f.cadence_days}d · {f.last_refresh ? `refreshed ${f.days_since}d ago` : 'no refresh recorded'}</div>
              </div>
              <span className="mono text-[10px] uppercase tracking-wide" style={{ color: FEED_TONE[f.status] }}>{f.status.replace('_', ' ')}</span>
              <button onClick={() => refresh(f.key)} disabled={busy === f.key}
                className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)] disabled:opacity-50">
                <RefreshCw size={12} className={busy === f.key ? 'animate-spin' : ''} /> {busy === f.key ? '…' : 'Record refresh'}
              </button>
            </div>
          ))}
        </div>
      )}
    </Card>
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
        <div className="flex flex-wrap gap-2 mt-3">
          {roles.map(r => {
            const on = form.role_ids.includes(r.id)
            return <button key={r.id} onClick={() => setForm({ ...form, role_ids: on ? form.role_ids.filter(x => x !== r.id) : [...form.role_ids, r.id] })}
              className={`text-[11.5px] px-2.5 py-1 rounded-full border ${on ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>{r.name}</button>
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
  const set = async (p: Policy, requires: boolean) => {
    setBusy(p.action_key)
    try { await api.patch('/v1/admin/approval-policy', { action_key: p.action_key, requires_approval: requires, material_fields: p.material_fields }); await q.refetch() }
    finally { setBusy(null) }
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex items-center gap-2">
        <ShieldCheck size={16} className="text-[var(--color-sky)]" />
        <span className="text-[13px] text-[var(--color-mute)]">Which changes require a second approver (4-eyes). Everything is audited regardless.</span>
      </div>
      {(q.data ?? []).map(p => (
        <div key={p.action_key} className="flex items-center gap-4 px-4 py-3 border-b border-[var(--color-line)] last:border-0">
          <div className="flex-1">
            <div className="text-[13.5px] text-[var(--color-ink)]">{p.label}</div>
            <div className="text-[11px] text-[var(--color-faint)] mono">{p.action_key}{p.material_fields.length ? ` · material: ${p.material_fields.join(', ')}` : ''}{p.org_override ? ' · org override' : ' · platform default'}</div>
          </div>
          <button disabled={busy === p.action_key} onClick={() => set(p, !p.requires_approval)}
            className={`relative w-11 h-6 rounded-full transition ${p.requires_approval ? 'bg-[var(--color-good)]' : 'bg-[var(--color-line-2)]'}`}>
            <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${p.requires_approval ? 'left-[22px]' : 'left-0.5'}`} />
          </button>
          <span className="text-[12px] w-28 text-right" style={{ color: p.requires_approval ? 'var(--color-good)' : 'var(--color-faint)' }}>{p.requires_approval ? '4-eyes required' : 'direct'}</span>
        </div>
      ))}
    </Card>
  )
}
