import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { UserPlus, Users as UsersIcon, KeyRound, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { pressable } from '../../lib/pressable'
import { Button, Card, SectionHead, StatGrid } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { Field, ago, inp, refused } from './parts'

// People and roles. Every name comes from the server (names.role, names.admin.permission and .permission_area); a
// permission's code never reaches the screen — its name does, with what it allows one hover away.

interface User { id: string; email: string; full_name: string; status: string; status_label: string; roles: string[]; last_login_at: string | null }
interface Role { id: string; name: string; label: string; is_system: boolean; permissions: string[] }
interface Perm { code: string; name: string; area: string; description: string | null }

// what each of the platform's roles is for — shown where a role is chosen
const ROLE_FOR: Record<string, string> = {
  admin: 'Runs the workspace: sets up the organisation, people and roles; prepares and approves filings; sees the audit trail.',
  analyst: 'Does the work: builds the data and filings and sends them for approval. Never approves their own work.',
  approver: 'The second person: reviews and approves filings and changes. Never approves a change they made.',
  viewer: 'Reads the dashboards, risk and reports. Changes nothing and sends nothing.',
  auditor: 'Reads the reports and the audit trail, for an internal or external audit. Changes nothing.',
}
const PEOPLE = {
  title: 'People', sections: [
    { heading: HEADING.shows, body: 'Everyone who can sign in to your workspace, whether they are active, when they last signed in and the roles that decide what each may do.' },
    { heading: HEADING.read, body: 'A person may hold several roles; click a role to give it or take it away. Approving a change always needs a second person: no one approves their own.' },
  ],
}
const ROLES = {
  title: 'Roles', sections: [
    { heading: HEADING.shows, body: 'What each role may do, by area: the darker a cell, the more of that area’s permissions the role holds.' },
    { heading: HEADING.read, body: 'Open a role to switch its permissions on or off; the change applies to everyone holding the role and is recorded in the audit trail. Hold the pointer over a permission to read what it allows.' },
  ],
}

export function Users() {
  const uq = useQuery({ queryKey: ['admin-users'], queryFn: () => api.get<User[]>('/v1/admin/users') })
  const rq = useQuery({ queryKey: ['admin-roles'], queryFn: () => api.get<Role[]>('/v1/admin/roles') })
  const [adding, setAdding] = useState(false)
  const users = uq.data ?? [], roles = (rq.data ?? []).filter(r => r.name !== 'platform-operator')
  const roleId = (name: string) => roles.find(r => r.name === name)?.id
  const toggleStatus = async (u: User) => {
    try { await api.patch(`/v1/admin/users/${u.id}`, { status: u.status === 'active' ? 'disabled' : 'active' }); await uq.refetch() }
    catch (e) { refused(e, 'The change could not be saved.') }
  }
  const toggleRole = async (u: User, name: string) => {
    const ids = new Set(u.roles.map(roleId).filter(Boolean) as string[])
    const rid = roleId(name); if (!rid) return
    if (ids.has(rid)) ids.delete(rid); else ids.add(rid)
    try { await api.patch(`/v1/admin/users/${u.id}`, { role_ids: [...ids] }); await uq.refetch() }
    catch (e) { refused(e, 'The change could not be saved.') }
  }
  const active = users.filter(u => u.status === 'active').length
  const holders = (name: string) => users.filter(u => u.status === 'active' && u.roles.includes(name)).length

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <SectionHead icon={UsersIcon} className="gap-1.5">People <InfoButton compact details={PEOPLE} /></SectionHead>
        <Button className="ml-auto" onClick={() => setAdding(true)}><UserPlus size={15} /> Add a person</Button>
      </div>
      <StatGrid cols={4} items={[
        { label: 'Active', value: `${active} of ${users.length}`, accent: 'var(--color-good)' },
        ...roles.filter(r => ['admin', 'approver', 'analyst'].includes(r.name)).map(r => ({
          label: r.label, value: holders(r.name), accent: r.name === 'approver' && holders(r.name) < 1 ? 'var(--color-warn)' : undefined })),
      ]} />
      <Card className="p-0 overflow-x-auto">
        <table className="data-table w-full text-[13px]">
          <thead><tr><th>Person</th><th>Status</th><th>Roles</th><th>Last signed in</th><th></th></tr></thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td><div className="text-[var(--color-ink)]">{u.full_name}</div><div className="text-[11.5px] text-[var(--color-faint)]">{u.email}</div></td>
                <td><StatusChip value={u.status} label={u.status_label} tone={u.status === 'active' ? 'good' : 'neutral'} /></td>
                <td>
                  <div className="flex flex-wrap gap-1.5">
                    {roles.map(r => {
                      const on = u.roles.includes(r.name)
                      return <button key={r.id} onClick={() => toggleRole(u, r.name)} aria-pressed={on}
                        className={clsx('text-[11.5px] px-2 py-0.5 rounded-full border transition', on ? 'border-[var(--color-blue)] text-[var(--color-blue)] bg-[color-mix(in_oklab,var(--color-blue)_10%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)] hover:text-[var(--color-ink)]')}>{r.label}</button>
                    })}
                  </div>
                </td>
                <td className="text-[12px] text-[var(--color-mute)] whitespace-nowrap">{ago(u.last_login_at)}</td>
                <td className="text-right"><button onClick={() => toggleStatus(u)} className="text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">{u.status === 'active' ? 'Disable' : 'Enable'}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {adding && <AddPerson roles={roles} onClose={() => setAdding(false)} onDone={() => { setAdding(false); uq.refetch() }} />}
    </div>
  )
}

function AddPerson({ roles, onClose, onDone }: { roles: Role[]; onClose: () => void; onDone: () => void }) {
  const [f, setF] = useState({ email: '', full_name: '', password: '', role_ids: [] as string[] })
  const [busy, setBusy] = useState(false)
  const ready = f.email.includes('@') && f.full_name.trim() && f.password.length >= 6
  const create = async () => {
    setBusy(true)
    try { await api.post('/v1/admin/users', f); toast.success(`${f.email} can sign in now with the temporary password.`); onDone() }
    catch (e) { refused(e, 'The person could not be added.') } finally { setBusy(false) }
  }
  return (
    <Dialog title="Add a person" onClose={onClose} className="max-w-2xl">
      <div className="space-y-4">
        <div className="grid sm:grid-cols-3 gap-3">
          <Field label="E-mail"><input className={inp} type="email" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} /></Field>
          <Field label="Full name"><input className={inp} value={f.full_name} onChange={e => setF({ ...f, full_name: e.target.value })} /></Field>
          <Field label="Temporary password"><input className={inp} type="password" autoComplete="new-password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} /></Field>
        </div>
        <div>
          <div className="text-[12.5px] text-[var(--color-ink)] mb-2">What should this person be able to do?</div>
          <div className="grid sm:grid-cols-2 gap-2.5">
            {roles.map(r => {
              const on = f.role_ids.includes(r.id)
              return (
                <button key={r.id} aria-pressed={on} onClick={() => setF({ ...f, role_ids: on ? f.role_ids.filter(x => x !== r.id) : [...f.role_ids, r.id] })}
                  className={clsx('text-left rounded-xl border p-3 transition', on ? 'border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,transparent)]' : 'border-[var(--color-line-2)] hover:border-[var(--color-line)]')}>
                  <div className="text-[13px] font-medium text-[var(--color-ink)]">{r.label}</div>
                  {ROLE_FOR[r.name] && <div className="text-[11.5px] text-[var(--color-faint)] mt-0.5 leading-snug">{ROLE_FOR[r.name]}</div>}
                </button>
              )
            })}
          </div>
        </div>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button onClick={create} disabled={busy || !ready}>{busy ? 'Adding…' : 'Add person'}</Button>
        </div>
      </div>
    </Dialog>
  )
}

export function Roles() {
  const rq = useQuery({ queryKey: ['admin-roles'], queryFn: () => api.get<Role[]>('/v1/admin/roles') })
  const pq = useQuery({ queryKey: ['admin-perms'], queryFn: () => api.get<Perm[]>('/v1/admin/permissions') })
  const [open, setOpen] = useState<string | null>(null)
  const roles = rq.data ?? [], perms = pq.data ?? []
  const areas = [...new Set(perms.map(p => p.area))]
  const role = roles.find(r => r.id === open)
  return (
    <div className="space-y-4">
      <SectionHead icon={KeyRound} className="gap-1.5">Roles <InfoButton compact details={ROLES} /></SectionHead>
      <Card className="p-0 overflow-x-auto">
        <table className="data-table w-full text-[12.5px]">
          <thead><tr><th>Role</th>{areas.map(a => <th key={a} className="text-center whitespace-nowrap">{a}</th>)}<th></th></tr></thead>
          <tbody>
            {roles.map(r => (
              <tr key={r.id} {...pressable(() => setOpen(r.id), { row: true })} className="cursor-pointer hover:bg-[var(--color-panel)]">
                <td className="whitespace-nowrap"><span className="text-[var(--color-ink)]">{r.label}</span>{r.is_system && <span className="ml-2 text-[11px] text-[var(--color-faint)]">System</span>}</td>
                {areas.map(a => {
                  const all = perms.filter(p => p.area === a), held = all.filter(p => r.permissions.includes(p.code)).length
                  return (
                    <td key={a} className="text-center">
                      <span className="inline-grid place-items-center w-9 h-6 rounded-md text-[11px] tabular-nums" title={`${held} of ${all.length}`}
                        style={{ background: `color-mix(in oklab, var(--color-sky) ${all.length ? Math.round(70 * held / all.length) : 0}%, var(--color-panel-2))`, color: held ? 'var(--color-ink)' : 'var(--color-faint)' }}>{held}</span>
                    </td>
                  )
                })}
                <td className="text-right"><ChevronRight size={14} className="text-[var(--color-faint)] inline" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      {role && <RoleDrawer role={role} perms={perms} areas={areas} onClose={() => setOpen(null)} onSaved={() => rq.refetch()} />}
    </div>
  )
}

function RoleDrawer({ role, perms, areas, onClose, onSaved }: { role: Role; perms: Perm[]; areas: string[]; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false)
  const toggle = async (code: string) => {
    const set = new Set(role.permissions)
    if (set.has(code)) set.delete(code); else set.add(code)
    setBusy(true)
    try { await api.patch(`/v1/admin/roles/${role.id}/permissions`, { permission_codes: [...set] }); onSaved() }
    catch (e) { refused(e, 'The role could not be changed.') } finally { setBusy(false) }
  }
  return (
    <Drawer label={role.label} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-5">
      <div className="flex items-center justify-between"><SectionHead>{role.label}</SectionHead><CloseButton onClick={onClose} /></div>
      {areas.map(a => (
        <section key={a}>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-2">{a}</h4>
          <div className="grid sm:grid-cols-2 gap-1.5">
            {perms.filter(p => p.area === a).map(p => {
              const on = role.permissions.includes(p.code)
              return (
                <button key={p.code} disabled={busy} onClick={() => toggle(p.code)} title={p.description ?? undefined} aria-pressed={on}
                  className={clsx('text-left text-[12.5px] px-2.5 py-1.5 rounded-lg border transition disabled:opacity-60', on ? 'border-[var(--color-good)] text-[var(--color-ink)] bg-[color-mix(in_oklab,var(--color-good)_8%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)] hover:text-[var(--color-ink)]')}>
                  {on ? '✓ ' : ''}{p.name}
                </button>
              )
            })}
          </div>
        </section>
      ))}
    </Drawer>
  )
}
