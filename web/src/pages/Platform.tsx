import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Globe, ChevronRight, X } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card, Stat } from '../components/ui'

interface Tenant {
  org_id: string; name: string; type: string; country: string; created_at: string | null
  users: number; active_users: number; sites: number; plots: number
  pending_approvals: number; audit_30d: number; last_activity: string | null; entitlements: string[]
}
interface Tenants { totals: { tenants: number; users: number; sites: number; plots: number; pending_approvals: number }; tenants: Tenant[] }
interface TenantDetail {
  organization: { org_id: string; name: string; legal_name: string | null; type: string; country: string; lei: string | null; eori: string | null; filing_contact_email: string | null; created_at: string | null }
  users: { email: string; full_name: string; status: string; last_login_at: string | null; roles: string[] }[]
  entitlements: string[]
  recent_activity: { action: string; email: string | null; created_at: string | null }[]
}

const ago = (iso: string | null) => {
  if (!iso) return 'never'
  const d = (Date.now() - new Date(iso).getTime()) / 86400000
  return d < 1 ? 'today' : d < 2 ? 'yesterday' : `${Math.floor(d)}d ago`
}

export default function Platform() {
  const q = useQuery({ queryKey: ['ops-tenants'], queryFn: () => api.get<Tenants>('/v1/ops/tenants') })
  const [open, setOpen] = useState<string | null>(null)

  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — platform access only.</Center>
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Tellumen · platform operator</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Tenants</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Every customer organization on the platform — seats, data footprint, and governance activity. Cross-tenant, read-only; visible only to Tellumen staff.</p>
      </div>

      <div className="grid sm:grid-cols-5 gap-4">
        <Stat big={d.totals.tenants} label="tenants" />
        <Stat big={d.totals.users} label="users" />
        <Stat big={d.totals.sites} label="sites" />
        <Stat big={d.totals.plots} label="sourcing plots" />
        <Stat big={d.totals.pending_approvals} label="pending approvals" tone={d.totals.pending_approvals ? 'warn' : 'ink'} />
      </div>

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
            <th className="font-normal py-2.5 px-4">Tenant</th><th className="font-normal px-4">Type</th>
            <th className="font-normal px-4 text-right">Users</th><th className="font-normal px-4 text-right">Sites</th>
            <th className="font-normal px-4 text-right">Plots</th><th className="font-normal px-4 text-right">Pending</th>
            <th className="font-normal px-4">Modules</th><th className="font-normal px-4">Last active</th><th className="font-normal px-4"></th>
          </tr></thead>
          <tbody>
            {d.tenants.map(t => (
              <tr key={t.org_id} onClick={() => setOpen(t.org_id)} className="border-b border-[var(--color-line)] last:border-0 cursor-pointer hover:bg-[var(--color-panel)] transition">
                <td className="py-2.5 px-4"><span className="text-[var(--color-ink)]">{t.name}</span> <span className="mono text-[10px] text-[var(--color-faint)]">{t.country}</span></td>
                <td className="px-4 text-[var(--color-mute)] capitalize">{t.type.replace('_', ' ')}</td>
                <td className="px-4 text-right mono text-[var(--color-mute)]">{t.active_users}/{t.users}</td>
                <td className="px-4 text-right mono text-[var(--color-mute)]">{t.sites}</td>
                <td className="px-4 text-right mono text-[var(--color-mute)]">{t.plots}</td>
                <td className="px-4 text-right mono" style={{ color: t.pending_approvals ? 'var(--color-warn)' : 'var(--color-faint)' }}>{t.pending_approvals || '—'}</td>
                <td className="px-4 text-[11px] text-[var(--color-faint)]">{t.entitlements.join(', ') || '—'}</td>
                <td className="px-4 text-[11px] text-[var(--color-mute)]">{ago(t.last_activity)}</td>
                <td className="px-4"><ChevronRight size={15} className="text-[var(--color-faint)]" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {open && <TenantDrawer orgId={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

function TenantDrawer({ orgId, onClose }: { orgId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['ops-tenant', orgId], queryFn: () => api.get<TenantDetail>(`/v1/ops/tenant/${orgId}`) })
  const d = q.data
  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-5" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2"><Globe size={16} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Tenant</span></div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>
        {!d ? <div className="text-[var(--color-faint)] text-sm">loading…</div> : (<>
          <div>
            <h2 className="display text-2xl font-semibold">{d.organization.name}</h2>
            <p className="text-[12px] text-[var(--color-mute)] capitalize">{d.organization.type.replace('_', ' ')} · {d.organization.country}</p>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-[12.5px]">
            {[['Legal name', d.organization.legal_name], ['LEI', d.organization.lei], ['EORI', d.organization.eori], ['Filing contact', d.organization.filing_contact_email]].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3 border-b border-[var(--color-line)] pb-1.5"><span className="text-[var(--color-mute)]">{k}</span><span className={v ? 'text-[var(--color-ink)] text-right' : 'text-[var(--color-faint)]'}>{v || '—'}</span></div>
            ))}
          </div>
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Users ({d.users.length})</div>
            <div className="space-y-1.5">
              {d.users.map(u => (
                <div key={u.email} className="flex items-center justify-between text-[12.5px]">
                  <div><span className="text-[var(--color-ink)]">{u.full_name}</span> <span className="text-[var(--color-faint)] text-[11px]">{u.roles.join(', ')}</span></div>
                  <span className="text-[11px] text-[var(--color-faint)]">{u.last_login_at ? ago(u.last_login_at) : 'never'}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Recent activity</div>
            <div className="space-y-1">
              {d.recent_activity.length === 0 && <div className="text-[12px] text-[var(--color-faint)]">no activity</div>}
              {d.recent_activity.map((a, i) => (
                <div key={i} className="flex items-center justify-between text-[11.5px]">
                  <span className="mono text-[var(--color-mute)]">{a.action}</span>
                  <span className="text-[var(--color-faint)]">{a.email ?? '—'} · {ago(a.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        </>)}
      </div>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[50vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
