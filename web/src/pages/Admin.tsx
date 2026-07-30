import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserPlus, ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, Button } from '../components/ui'

interface User { id: string; email: string; full_name: string; status: string; roles: string[]; last_login_at: string | null }
interface Role { id: string; name: string; description: string | null; is_system: boolean; permissions: string[] }
interface Perm { code: string; description: string }
interface Policy { action_key: string; label: string; requires_approval: boolean; material_fields: string[]; org_override: boolean }

const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'

export default function Admin() {
  const { profile } = useAuth()
  const perms = profile?.permissions ?? []
  const tabs = [
    perms.includes('admin.users.manage') && 'Users',
    perms.includes('admin.roles.manage') && 'Roles',
    perms.includes('admin.approval_policy.manage') && 'Approval matrix',
  ].filter(Boolean) as string[]
  const [tab, setTab] = useState(tabs[0] ?? 'Users')

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Governance · administration</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Admin console</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Users, roles &amp; permissions, and the approval matrix that decides which changes need a second approver.</p>
      </div>
      <div className="flex gap-2 flex-wrap">
        {tabs.map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-lg text-[13px] border transition ${tab === t ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{t}</button>
        ))}
      </div>
      {tab === 'Users' && <Users />}
      {tab === 'Roles' && <Roles />}
      {tab === 'Approval matrix' && <Matrix />}
    </div>
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
