import { useState, useEffect, useCallback } from 'react'
import { Users, KeyRound, ScrollText, CheckSquare, SlidersHorizontal, Plus, Loader2, Check, X, ChevronDown, ChevronUp } from 'lucide-react'
import {
  fetchAdminUsers, createAdminUser, patchAdminUser,
  fetchRoles, fetchPermissions, setRolePermissions,
  fetchAudit, fetchApprovals, decideApproval, fetchSubmission,
  fetchCalcSettings, updateCalcSettings,
} from '../../api/client'
import { industryForOrg } from '../../data/catalog'
import { DisclosureSummary } from '../bank/Reports'

const TABS = [
  { id: 'users',         label: 'Users',                icon: Users,      perm: 'admin.users.manage' },
  { id: 'roles',         label: 'Roles & permissions',  icon: KeyRound,   perm: 'admin.roles.manage' },
  { id: 'calc-settings', label: 'Calculation methods',  icon: SlidersHorizontal, perm: 'admin.roles.manage' },
  { id: 'audit',         label: 'Audit trail',          icon: ScrollText, perm: 'admin.audit.view' },
  { id: 'approvals',     label: 'Approvals',            icon: CheckSquare, perm: 'approvals.view', altPerm: 'approvals.decide' },
]

export default function AdminPage({ auth }) {
  const perms = new Set(auth?.permissions || [])
  const tabs = TABS.filter(t => perms.has(t.perm) || (t.altPerm && perms.has(t.altPerm)))
  const [tab, setTab] = useState(tabs[0]?.id || 'users')

  return (
    <div className="flex h-full overflow-hidden bg-[#f5f5f7]">
      <aside className="w-60 shrink-0 border-r border-gray-200 bg-white p-3">
        <p className="px-3 pb-2 pt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-gray-400">Admin</p>
        {tabs.map(t => {
          const on = tab === t.id, Icon = t.icon
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] transition ${
                on ? 'bg-[#0071e3]/10 font-medium text-[#0071e3]' : 'text-gray-600 hover:bg-gray-100'}`}>
              <Icon size={15} strokeWidth={1.8} /> {t.label}
            </button>
          )
        })}
      </aside>
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-8 py-8">
          {tab === 'users'         && <UsersTab />}
          {tab === 'roles'         && <RolesTab />}
          {tab === 'calc-settings' && <CalcSettingsTab auth={auth} />}
          {tab === 'audit'         && <AuditTab />}
          {tab === 'approvals'     && <ApprovalsTab auth={auth} />}
        </div>
      </div>
    </div>
  )
}

function Title({ children, sub }) {
  return <div className="mb-5"><h1 className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">{children}</h1>
    {sub && <p className="mt-1 text-[14px] text-gray-500">{sub}</p>}</div>
}

// ── Users ──────────────────────────────────────────────────────────────
function UsersTab() {
  const [users, setUsers] = useState(null)
  const [roles, setRoles] = useState([])
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ email: '', full_name: '', password: '', role_ids: [] })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    fetchAdminUsers().then(setUsers).catch(() => setUsers([]))
    fetchRoles().then(setRoles).catch(() => setRoles([]))
  }, [])
  useEffect(() => { load() }, [load])

  async function add(e) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      await createAdminUser(form)
      setForm({ email: '', full_name: '', password: '', role_ids: [] }); setAdding(false); load()
    } catch (e) { setErr(e.message || 'Could not create user.') }
    finally { setBusy(false) }
  }
  async function toggleStatus(u) {
    await patchAdminUser(u.id, { status: u.status === 'active' ? 'disabled' : 'active' })
    load()
  }
  const toggleRole = (id) => setForm(f => ({
    ...f, role_ids: f.role_ids.includes(id) ? f.role_ids.filter(x => x !== id) : [...f.role_ids, id],
  }))

  return (
    <div>
      <div className="flex items-center justify-between">
        <Title sub="Manage who can access your organization's workspace.">Users</Title>
        <button onClick={() => setAdding(v => !v)}
          className="flex items-center gap-1.5 rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white hover:brightness-110">
          <Plus size={15} /> Add user
        </button>
      </div>

      {adding && (
        <form onSubmit={add} className="mb-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <input required placeholder="Email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })}
              className="rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]" />
            <input required placeholder="Full name" value={form.full_name} onChange={e => setForm({ ...form, full_name: e.target.value })}
              className="rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]" />
            <input required type="password" placeholder="Temp password (min 6)" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })}
              className="rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]" />
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {roles.map(r => (
              <button type="button" key={r.id} onClick={() => toggleRole(r.id)}
                className={`rounded-full border px-3 py-1 text-[12px] capitalize transition ${
                  form.role_ids.includes(r.id) ? 'border-[#0071e3] bg-[#0071e3]/10 text-[#0071e3]' : 'border-gray-200 text-gray-600'}`}>
                {r.name}
              </button>
            ))}
          </div>
          {err && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{err}</p>}
          <div className="mt-4 flex gap-2">
            <button type="submit" disabled={busy}
              className="rounded-full bg-[#0071e3] px-4 py-2 text-[13px] font-medium text-white disabled:opacity-50">
              {busy ? 'Creating…' : 'Create user'}
            </button>
            <button type="button" onClick={() => setAdding(false)} className="rounded-full border border-gray-200 px-4 py-2 text-[13px]">Cancel</button>
          </div>
        </form>
      )}

      <div className="overflow-hidden rounded-2xl border border-gray-200/70 bg-white shadow-sm">
        <table className="w-full text-[13px]">
          <thead><tr className="border-b border-gray-100 text-left text-gray-400">
            <th className="px-4 py-2.5 font-medium">User</th><th className="px-4 py-2.5 font-medium">Roles</th>
            <th className="px-4 py-2.5 font-medium">Last login</th><th className="px-4 py-2.5 font-medium">Status</th>
            <th className="px-4 py-2.5 font-medium"></th>
          </tr></thead>
          <tbody>
            {(users || []).map(u => (
              <tr key={u.id} className="border-b border-gray-50 last:border-0">
                <td className="px-4 py-3"><div className="font-medium text-[#1d1d1f]">{u.full_name}</div><div className="text-[12px] text-gray-400">{u.email}</div></td>
                <td className="px-4 py-3 capitalize text-gray-600">{u.roles.join(', ') || '—'}</td>
                <td className="px-4 py-3 text-gray-500">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'never'}</td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${u.status === 'active' ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'}`}>{u.status}</span>
                </td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => toggleStatus(u)} className="text-[12px] font-medium text-[#0071e3] hover:underline">
                    {u.status === 'active' ? 'Disable' : 'Enable'}
                  </button>
                </td>
              </tr>
            ))}
            {users === null && <tr><td colSpan={5} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Roles & permission matrix ──────────────────────────────────────────
function RolesTab() {
  const [roles, setRoles] = useState(null)
  const [perms, setPerms] = useState([])
  const [saving, setSaving] = useState(null)

  const load = useCallback(() => {
    fetchRoles().then(setRoles).catch(() => setRoles([]))
    fetchPermissions().then(setPerms).catch(() => setPerms([]))
  }, [])
  useEffect(() => { load() }, [load])

  async function toggle(role, code) {
    const has = role.permissions.includes(code)
    const next = has ? role.permissions.filter(c => c !== code) : [...role.permissions, code]
    setSaving(`${role.id}:${code}`)
    // optimistic
    setRoles(rs => rs.map(r => r.id === role.id ? { ...r, permissions: next } : r))
    try { await setRolePermissions(role.id, next) }
    catch { load() }           // revert from server on failure
    finally { setSaving(null) }
  }

  if (roles === null) return <div><Title>Roles & permissions</Title><p className="text-gray-400">Loading…</p></div>
  return (
    <div>
      <Title sub="Toggle a cell to grant or revoke a permission for a role. Changes save immediately and are audited.">Roles & permissions</Title>
      <div className="overflow-x-auto rounded-2xl border border-gray-200/70 bg-white shadow-sm">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b border-gray-100 text-left">
              <th className="px-4 py-3 font-medium text-gray-400">Permission</th>
              {roles.map(r => <th key={r.id} className="px-3 py-3 text-center font-medium capitalize text-[#1d1d1f]">{r.name}</th>)}
            </tr>
          </thead>
          <tbody>
            {perms.map(p => (
              <tr key={p.code} className="border-b border-gray-50 last:border-0">
                <td className="px-4 py-2.5"><div className="font-medium text-[#1d1d1f]">{p.code}</div><div className="text-[11px] text-gray-400">{p.description}</div></td>
                {roles.map(r => {
                  const on = r.permissions.includes(p.code)
                  const key = `${r.id}:${p.code}`
                  return (
                    <td key={r.id} className="px-3 py-2.5 text-center">
                      <button onClick={() => toggle(r, p.code)} disabled={saving === key}
                        className={`inline-flex h-6 w-6 items-center justify-center rounded-md border transition ${
                          on ? 'border-[#0071e3] bg-[#0071e3] text-white' : 'border-gray-200 bg-white text-transparent hover:border-gray-300'}`}>
                        {saving === key ? <Loader2 size={13} className="animate-spin text-gray-400" /> : <Check size={14} />}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Calc settings (per-org calculation-method triggers) ────────────────
const SEVERITY_OPTIONS = [
  { value: 'universal', label: 'Universal', detail: 'One discount schedule (0/5/15/30% by Low/Moderate/High/Very High) applied to every hazard alike.' },
  { value: 'peril_specific', label: 'Peril-specific', detail: 'A separate, harsher schedule for structural perils (seismic/volcanic up to 45%) vs. milder ones (drought/heat 10–15%).' },
]
const VAR_METHOD_OPTIONS = [
  { value: 'haircut', label: 'Risk-bucket haircut', detail: 'Deterministic: the same discount schedule banking and real estate use, applied to position value.' },
  { value: 'monte_carlo', label: 'Monte Carlo VaR', detail: 'Simulates a distribution around the disclosed haircut and reports an uncertainty band, not a single number.' },
]
const RETURN_PERIOD_OPTIONS = [
  { value: 'fixed', label: 'Fixed tiers', detail: 'One return-period ladder (200/50/20/10yr by L/M/H/VH) for every hazard.' },
  { value: 'peril_specific', label: 'Peril-specific tiers', detail: 'Longer return periods for rare structural perils (seismic/volcanic up to 1000yr), shorter for frequent weather perils.' },
]

function SettingCard({ title, sub, options, value, onChange, disabled }) {
  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
      <h3 className="text-[14px] font-semibold text-[#1d1d1f]">{title}</h3>
      <p className="mt-0.5 text-[12px] text-gray-500">{sub}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {options.map(o => (
          <button key={o.value} type="button" disabled={disabled} onClick={() => onChange(o.value)}
            className={`rounded-xl border p-3 text-left transition disabled:cursor-not-allowed disabled:opacity-50 ${
              value === o.value ? 'border-[#0071e3] bg-[#0071e3]/[0.06]' : 'border-gray-200 hover:border-gray-300'}`}>
            <div className="flex items-center gap-2">
              <span className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                value === o.value ? 'border-[#0071e3] bg-[#0071e3]' : 'border-gray-300'}`}>
                {value === o.value && <Check size={11} className="text-white" strokeWidth={3} />}
              </span>
              <span className="text-[13px] font-medium text-[#1d1d1f]">{o.label}</span>
            </div>
            <p className="mt-1.5 pl-6 text-[12px] leading-snug text-gray-500">{o.detail}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

function CalcSettingsTab({ auth }) {
  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(null)
  const [err, setErr] = useState(null)
  const industry = industryForOrg(auth?.org)

  const load = useCallback(() => { fetchCalcSettings().then(setSettings).catch(() => setSettings(null)) }, [])
  useEffect(() => { load() }, [load])

  async function change(field, value) {
    setSaving(field); setErr(null)
    const prev = settings
    setSettings(s => ({ ...s, [field]: value }))   // optimistic
    try { setSettings(await updateCalcSettings({ [field]: value })) }
    catch (e) { setSettings(prev); setErr(e.message || 'Could not save.') }
    finally { setSaving(null) }
  }

  if (settings === null) return <div><Title>Calculation methods</Title><p className="text-gray-400">Loading…</p></div>
  return (
    <div>
      <Title sub="Every org gets today's default behaviour until you opt into an alternative. Changes apply to every workspace, disclosure and report immediately, and are audited.">
        Calculation methods
      </Title>
      {err && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{err}</p>}
      <div className="space-y-4">
        <SettingCard title="Climate-severity discount model"
          sub="Used everywhere a hazard score is converted into a value discount: banking's collateral haircut, real estate's climate-adjusted value, asset management's climate VaR."
          options={SEVERITY_OPTIONS} value={settings.severity_model} disabled={saving === 'severity_model'}
          onChange={v => change('severity_model', v)} />
        {industry === 'assetmgmt' && (
          <SettingCard title="Portfolio climate-VaR method" sub="Asset management only — how portfolio-level climate Value-at-Risk is computed."
            options={VAR_METHOD_OPTIONS} value={settings.assetmgmt_var_method} disabled={saving === 'assetmgmt_var_method'}
            onChange={v => change('assetmgmt_var_method', v)} />
        )}
        {industry === 'insurance' && (
          <SettingCard title="Return-period model" sub="Insurance only — how a risk bucket maps to an annual occurrence probability for loss-curve pricing."
            options={RETURN_PERIOD_OPTIONS} value={settings.insurance_return_period_model} disabled={saving === 'insurance_return_period_model'}
            onChange={v => change('insurance_return_period_model', v)} />
        )}
      </div>
    </div>
  )
}

// ── Audit ──────────────────────────────────────────────────────────────
function AuditTab() {
  const [rows, setRows] = useState(null)
  useEffect(() => { fetchAudit({ limit: 100 }).then(setRows).catch(() => setRows([])) }, [])
  return (
    <div>
      <Title sub="Every login and mutation, newest first — actor, action and target.">Audit trail</Title>
      <div className="overflow-hidden rounded-2xl border border-gray-200/70 bg-white shadow-sm">
        <table className="w-full text-[13px]">
          <thead><tr className="border-b border-gray-100 text-left text-gray-400">
            <th className="px-4 py-2.5 font-medium">When</th><th className="px-4 py-2.5 font-medium">Actor</th>
            <th className="px-4 py-2.5 font-medium">Action</th><th className="px-4 py-2.5 font-medium">Target</th>
          </tr></thead>
          <tbody>
            {(rows || []).map(r => (
              <tr key={r.id} className="border-b border-gray-50 last:border-0">
                <td className="px-4 py-2.5 text-gray-500">{r.created_at ? new Date(r.created_at).toLocaleString() : ''}</td>
                <td className="px-4 py-2.5 text-gray-700">{r.actor_email || '—'}</td>
                <td className="px-4 py-2.5"><code className="rounded bg-gray-100 px-1.5 py-0.5 text-[12px] text-[#1d1d1f]">{r.action}</code></td>
                <td className="px-4 py-2.5 text-gray-500">{r.target_type ? `${r.target_type}` : '—'}</td>
              </tr>
            ))}
            {rows === null && <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">Loading…</td></tr>}
            {rows && rows.length === 0 && <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-400">No audit entries yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Approvals (4-eyes) ──────────────────────────────────────────────────
const mn = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

function ApprovalsTab({ auth }) {
  const [rows, setRows] = useState(null)
  const [busy, setBusy] = useState(null)
  const [expanded, setExpanded] = useState(null)   // request id whose snapshot is shown
  const [snapshot, setSnapshot] = useState(null)    // { loading } | { data } for the expanded row
  const canDecide = new Set(auth?.permissions || []).has('approvals.decide')

  const load = useCallback(() => { fetchApprovals().then(setRows).catch(() => setRows([])) }, [])
  useEffect(() => { load() }, [load])

  async function decide(id, decision) {
    setBusy(id)
    try { await decideApproval(id, decision, decision === 'approved' ? 'Reviewed and approved' : 'Rejected') }
    catch (e) { alert(e.message) }
    finally { setBusy(null); load() }
  }

  async function toggleSnapshot(r) {
    if (expanded === r.id) { setExpanded(null); return }
    setExpanded(r.id)
    setSnapshot({ loading: true })
    try {
      const full = await fetchSubmission(r.payload.submission_id)
      setSnapshot({ data: full })
    } catch (e) {
      setSnapshot(null)
    }
  }

  const badge = { pending: 'bg-amber-50 text-amber-700', approved: 'bg-emerald-50 text-emerald-700', rejected: 'bg-red-50 text-red-700' }
  return (
    <div>
      <Title sub="Four-eyes: a request must be approved by someone other than its maker.">Approvals</Title>
      {rows === null && <p className="text-gray-400">Loading…</p>}
      {rows && rows.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-8 text-center text-[14px] text-gray-400">No approval requests.</div>
      )}
      <div className="space-y-3">
        {(rows || []).map(r => {
          const isSubmission = r.request_type === 'submission.release'
          return (
          <div key={r.id} className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-[14px] font-semibold text-[#1d1d1f]">{r.title || r.request_type}</h3>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge[r.status]}`}>{r.status}</span>
                </div>
                <p className="mt-0.5 text-[12px] text-gray-400">
                  <code className="text-gray-500">{r.request_type}</code> · maker {r.maker_email}
                  {r.checker_email && ` · checker ${r.checker_email}`}
                  {r.created_at && ` · ${new Date(r.created_at).toLocaleString()}`}
                </p>
                {isSubmission && (
                  <p className="mt-1.5 text-[12px] text-gray-600">
                    <span className="font-medium">{r.payload.period_label}</span> · {r.payload.framework} ·
                    value at risk <span className="font-medium text-[#c2410c]">{mn(r.payload.value_at_risk_eur)}</span> ·
                    {' '}{r.payload.n_assets} assets
                  </p>
                )}
                {isSubmission && (
                  <button onClick={() => toggleSnapshot(r)}
                    className="mt-1.5 flex items-center gap-1 text-[12px] font-medium text-[#0071e3] hover:underline">
                    {expanded === r.id ? <><ChevronUp size={13} /> Hide full snapshot</> : <><ChevronDown size={13} /> View full snapshot</>}
                  </button>
                )}
              </div>
              {r.status === 'pending' && canDecide && (
                r.is_own ? (
                  <span className="shrink-0 rounded-full bg-gray-100 px-3 py-1.5 text-[12px] text-gray-400">Your request — needs another approver</span>
                ) : (
                  <div className="flex shrink-0 gap-2">
                    <button onClick={() => decide(r.id, 'approved')} disabled={busy === r.id}
                      className="flex items-center gap-1 rounded-full bg-emerald-600 px-3 py-1.5 text-[12px] font-medium text-white hover:brightness-110 disabled:opacity-50">
                      <Check size={13} /> Approve
                    </button>
                    <button onClick={() => decide(r.id, 'rejected')} disabled={busy === r.id}
                      className="flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1.5 text-[12px] font-medium text-gray-600 hover:border-red-300 hover:text-red-600 disabled:opacity-50">
                      <X size={13} /> Reject
                    </button>
                  </div>
                )
              )}
            </div>
            {isSubmission && expanded === r.id && (
              <div className="mt-4 border-t border-gray-100 pt-4">
                {snapshot?.loading && <p className="text-gray-400">Loading snapshot…</p>}
                {snapshot?.data && <DisclosureSummary d={snapshot.data.snapshot} />}
                {!snapshot && <p className="text-gray-400">Could not load snapshot.</p>}
              </div>
            )}
          </div>
        )})}
      </div>
    </div>
  )
}
