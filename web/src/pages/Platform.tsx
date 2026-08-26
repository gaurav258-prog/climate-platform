import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, ChevronRight, X, LogIn, LifeBuoy, Send, CheckCircle2, Building2, Users, MapPin, Sprout, Clock, Plus } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Button, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import OperatorTabs from '../components/OperatorTabs'

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
  const [showNew, setShowNew] = useState(false)

  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — platform access only.</Center>
  const d = q.data

  return (
    <div className="fadeup space-y-6">
      <OperatorTabs />
      <div className="flex items-start justify-between gap-4">
        <PageHeader eyebrow="Tellumen · platform operator" title="Tenants"
          lead="Every customer organization on the platform — seats, data footprint, and governance activity. Cross-tenant, read-only; visible only to Tellumen staff." />
        <button onClick={() => setShowNew(true)}
          className="shrink-0 mt-1 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-3.5 py-2 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">
          <Plus size={15} /> Provision tenant
        </button>
      </div>
      {showNew && <CreateTenantModal onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); q.refetch() }} />}

      <HeroBanner
        eyebrow="Tellumen · platform operator"
        title={d.totals.pending_approvals > 0 ? `${d.totals.pending_approvals} approval${d.totals.pending_approvals === 1 ? '' : 's'} waiting across your tenants.` : `${d.totals.tenants} organization${d.totals.tenants === 1 ? '' : 's'} on the platform.`}
        lead="Every customer organization on the platform — seats, data footprint, and governance activity. Cross-tenant, read-only; visible only to Tellumen staff."
        stat={[
          { label: 'Tenants', value: d.totals.tenants, icon: Building2, tone: 'var(--color-sky)' },
          { label: 'Users', value: d.totals.users, icon: Users, tone: 'var(--color-sky)' },
          { label: 'Sites', value: d.totals.sites, icon: MapPin, tone: 'var(--color-sky)' },
          { label: 'Sourcing plots', value: d.totals.plots, icon: Sprout, tone: 'var(--color-sky)' },
          { label: 'Pending approvals', value: d.totals.pending_approvals, icon: Clock, tone: d.totals.pending_approvals ? '#E8853C' : '#4FA46E' },
        ]} />

      <Card className="p-0 overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead><tr className="text-[var(--color-faint)] mono text-[11px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
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

      <SupportQueue />

      {open && <TenantDrawer orgId={open} onClose={() => setOpen(null)} />}
    </div>
  )
}

// ─────────────── Support queue — the "with us" side of the service portal ───────────────
interface SReq {
  id: string; org_id: string; org_name: string | null; category: string; subject: string
  priority: string; status: string; requester_email: string | null; message_count: number
  awaiting_support: boolean; created_at: string | null; first_response_at: string | null; last_activity: string | null
}
interface SMsg { id: string; author_side: 'customer' | 'support'; author_email: string | null; author_name: string | null; body: string; created_at: string | null }

const sPill = (s: string) => s === 'resolved' ? 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]'
  : s === 'in_progress' ? 'text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_14%,transparent)]'
  : 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]'

function SupportQueue() {
  const [status, setStatus] = useState<'open' | 'all'>('open')
  const [sel, setSel] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['ops-support', status], queryFn: () => api.get<{ totals: { open: number; awaiting_support: number }; requests: SReq[] }>(`/v1/ops/support?status=${status === 'open' ? 'open' : 'all'}`) })
  const rows = q.data?.requests ?? []
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <SectionHead icon={LifeBuoy}>Support queue</SectionHead>
        {q.data && <span className="text-[12px] text-[var(--color-mute)]">{q.data.totals.awaiting_support} awaiting a reply · {q.data.totals.open} open</span>}
        <div className="ml-auto flex gap-2">
          {(['open', 'all'] as const).map(f => (
            <button key={f} onClick={() => setStatus(f)} className={`px-3 py-1 rounded-lg text-[12.5px] border transition ${status === f ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{f === 'open' ? 'Open' : 'All'}</button>
          ))}
        </div>
      </div>
      <Card className="p-0 overflow-x-auto">
        {rows.length === 0 ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Nothing {status === 'open' ? 'open' : 'here'}.</div> : (
          <table className="w-full text-[13px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[11px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
              <th className="font-normal py-2.5 px-4">Tenant</th><th className="font-normal px-4">Request</th><th className="font-normal px-4">Type</th>
              <th className="font-normal px-4">Status</th><th className="font-normal px-4 text-right">Msgs</th><th className="font-normal px-4">Last</th><th className="font-normal px-4"></th>
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} onClick={() => setSel(r.id)} className="border-b border-[var(--color-line)] last:border-0 cursor-pointer hover:bg-[var(--color-panel)] transition">
                  <td className="py-2.5 px-4 text-[var(--color-ink)]">{r.org_name}</td>
                  <td className="px-4 text-[var(--color-mute)]">{r.subject}{r.awaiting_support && <span className="ml-2 mono text-[9px] px-1.5 py-0.5 rounded-full uppercase tracking-wide text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]">needs reply</span>}</td>
                  <td className="px-4 text-[var(--color-faint)] capitalize">{r.category}{r.priority !== 'normal' && <span className="ml-1 text-[var(--color-warn)]">· {r.priority}</span>}</td>
                  <td className="px-4"><span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${sPill(r.status)}`}>{r.status.replace('_', ' ')}</span></td>
                  <td className="px-4 text-right mono text-[var(--color-mute)]">{r.message_count}</td>
                  <td className="px-4 text-[11px] text-[var(--color-mute)]">{ago(r.last_activity)}</td>
                  <td className="px-4"><ChevronRight size={15} className="text-[var(--color-faint)]" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      {sel && <SupportDrawer id={sel} onClose={() => setSel(null)} onChanged={() => q.refetch()} />}
    </div>
  )
}

function SupportDrawer({ id, onClose, onChanged }: { id: string; onClose: () => void; onChanged: () => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['ops-support-detail', id], queryFn: () => api.get<{ request: SReq; messages: SMsg[] }>(`/v1/ops/support/${id}`) })
  const [reply, setReply] = useState('')
  const [busy, setBusy] = useState(false)
  const d = q.data
  const send = async (resolve = false) => {
    if (!reply.trim()) { toast.error('Write a reply.'); return }
    setBusy(true)
    try {
      await api.post(`/v1/ops/support/${id}/reply`, { body: reply.trim(), status: resolve ? 'resolved' : undefined })
      setReply(''); await q.refetch(); qc.invalidateQueries({ queryKey: ['ops-support'] }); onChanged()
    } catch { toast.error('Could not send.') } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-40 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-4" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2"><LifeBuoy size={16} className="text-[var(--color-sky)]" /><span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Support · reply as Tellumen</span></div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>
        {!d ? <div className="text-[var(--color-faint)] text-sm">loading…</div> : (<>
          <div>
            <div className="flex items-center gap-2">
              <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${sPill(d.request.status)}`}>{d.request.status.replace('_', ' ')}</span>
              <span className="text-[11px] text-[var(--color-faint)]">{d.request.org_name} · {d.request.requester_email}</span>
            </div>
            <h2 className="text-[17px] font-semibold mt-1.5 leading-snug">{d.request.subject}</h2>
          </div>
          <div className="space-y-3 border-t border-[var(--color-line)] pt-4">
            {d.request.category && d.messages.length === 0 && !d.request.first_response_at && <div className="text-[12.5px] text-[var(--color-faint)]">No messages yet — the customer raised this request. Reply below.</div>}
            {d.messages.map(m => {
              const sup = m.author_side === 'support'
              return (
                <div key={m.id} className={`flex ${sup ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] rounded-xl px-3.5 py-2.5 ${sup ? 'bg-[color-mix(in_oklab,var(--color-sky)_10%,var(--color-bg-2))] border border-[color-mix(in_oklab,var(--color-sky)_28%,var(--color-line))]' : 'bg-[var(--color-panel-2)] border border-[var(--color-line)]'}`}>
                    <div className="flex items-center gap-2 mb-1"><span className={`mono text-[9px] uppercase tracking-wide ${sup ? 'text-[var(--color-sky)]' : 'text-[var(--color-faint)]'}`}>{sup ? 'Tellumen' : (m.author_name || m.author_email || 'Customer')}</span><span className="text-[10px] text-[var(--color-faint)]">{ago(m.created_at)}</span></div>
                    <div className="text-[13px] text-[var(--color-ink)] whitespace-pre-wrap leading-relaxed">{m.body}</div>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="border-t border-[var(--color-line)] pt-4">
            <textarea value={reply} onChange={e => setReply(e.target.value)} rows={4} maxLength={4000} placeholder="Reply to the customer…"
              className="w-full bg-[var(--color-bg-3,var(--color-bg))] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] resize-y" />
            <div className="flex gap-2 mt-2">
              <button disabled={busy || !reply.trim()} onClick={() => send(false)} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium bg-[var(--color-sky)] text-[#0b1206] hover:opacity-90 disabled:opacity-40"><Send size={14} /> Send reply</button>
              <button disabled={busy || !reply.trim()} onClick={() => send(true)} className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[13px] font-medium border border-[var(--color-line-2)] text-[var(--color-good)] hover:border-[var(--color-good)] disabled:opacity-40"><CheckCircle2 size={14} /> Send &amp; resolve</button>
            </div>
          </div>
        </>)}
      </div>
    </div>
  )
}

function TenantDrawer({ orgId, onClose }: { orgId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['ops-tenant', orgId], queryFn: () => api.get<TenantDetail>(`/v1/ops/tenant/${orgId}`) })
  const { viewAsTenant } = useAuth()
  const [busy, setBusy] = useState(false)
  const d = q.data
  const enter = async () => { setBusy(true); try { await viewAsTenant(orgId) } catch { setBusy(false) } }
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
          {d.organization.type !== 'platform' && (
            <div>
              <Button onClick={enter} disabled={busy}><LogIn size={15} /> {busy ? 'Opening…' : 'View as this tenant'}</Button>
              <p className="text-[11px] text-[var(--color-faint)] mt-1.5">Opens their full workspace &amp; cockpit. Recorded in their audit log.</p>
            </div>
          )}
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
// ─────────────── Provision a new client tenant (onboarding step 1) ───────────────
interface Catalog { org_types: string[]; default_entitlements: Record<string, string[]>; offerings: string[] }
interface CreatedTenant { org_id: string; name: string; type: string; entitlements: string[]; admin: { email: string } | null }

function CreateTenantModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const cat = useQuery({ queryKey: ['tenants-catalog'], queryFn: () => api.get<Catalog>('/v1/admin/tenants/catalog') })
  const [f, setF] = useState({ name: '', org_type: 'bank', country: '', legal_name: '', lei: '', filing_contact_email: '', admin_email: '', admin_full_name: '', admin_password: '' })
  const [ent, setEnt] = useState<string[] | null>(null)   // null = use sector defaults
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<CreatedTenant | null>(null)
  const set = (k: string, v: string) => setF(s => ({ ...s, [k]: v }))
  const defaults = cat.data?.default_entitlements?.[f.org_type] ?? []
  const chosen = ent ?? defaults

  const submit = async () => {
    if (!f.name.trim()) { toast.error('A tenant needs a name.'); return }
    if (!f.country.trim()) { toast.error('Country (ISO-2) is required.'); return }
    if (f.admin_email && f.admin_password.length < 6) { toast.error('First-admin password must be at least 6 characters.'); return }
    setBusy(true)
    try {
      const body: Record<string, unknown> = { name: f.name.trim(), org_type: f.org_type, country: f.country || null,
        legal_name: f.legal_name || null, lei: f.lei || null, filing_contact_email: f.filing_contact_email || null,
        entitlements: ent }
      if (f.admin_email) { body.admin_email = f.admin_email; body.admin_full_name = f.admin_full_name || null; body.admin_password = f.admin_password }
      const r = await api.post<CreatedTenant>('/v1/admin/tenants', body)
      setDone(r); toast.success(`Tenant "${r.name}" provisioned`)
    } catch (err) {
      toast.error(err instanceof ApiError ? (err.body as { message?: string })?.message ?? 'Could not provision the tenant.' : 'Could not provision the tenant.')
    } finally { setBusy(false) }
  }

  const Field = ({ label, k, ph, type = 'text' }: { label: string; k: keyof typeof f; ph?: string; type?: string }) => (
    <label className="flex flex-col gap-1">
      <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">{label}</span>
      <input type={type} value={f[k]} placeholder={ph} onChange={e => set(k, e.target.value)}
        className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
    </label>
  )

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[560px]" onClick={e => e.stopPropagation()}>
      <Card className="max-h-[88vh] overflow-y-auto p-5">
        <div className="flex items-center justify-between mb-1">
          <SectionHead icon={Building2}>Provision a new client tenant</SectionHead>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>

        {done ? (
          <div className="mt-3 space-y-3">
            <div className="flex items-center gap-2 text-[var(--color-good)]"><CheckCircle2 size={18} /> <span className="text-[14px] font-medium">{done.name} is live</span></div>
            <div className="text-[13px] text-[var(--color-mute)]">Sector <b className="text-[var(--color-ink)] capitalize">{done.type.replace('_', ' ')}</b> · offerings {done.entitlements.join(', ')} · roles admin/analyst/approver/viewer seeded.</div>
            {done.admin && <div className="rounded-lg border border-[var(--color-line-2)] px-3 py-2 text-[13px]">First admin: <span className="mono text-[var(--color-ink)]">{done.admin.email}</span> — they can log in now and invite the rest of their team.</div>}
            <div className="text-[12px] text-[var(--color-faint)]">Next in onboarding: reporting identity (GLEIF), the client loads their book into the golden source, and governance setup.</div>
            <div className="flex justify-end"><Button onClick={onCreated}>Done</Button></div>
          </div>
        ) : (
          <div className="mt-3 space-y-4">
            <p className="text-[12.5px] text-[var(--color-mute)]">Hybrid onboarding — you stand up the tenant, its identity and a first admin; the client then loads their own book and invites their people.</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Tenant name *" k="name" ph="Meridian Bank" />
              <label className="flex flex-col gap-1">
                <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Sector *</span>
                <select value={f.org_type} onChange={e => { set('org_type', e.target.value); setEnt(null) }}
                  className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)] capitalize">
                  {(cat.data?.org_types ?? ['bank']).map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
                </select>
              </label>
              <Field label="Country (ISO-2) *" k="country" ph="ES" />
              <Field label="Legal name" k="legal_name" ph="Meridian Bank AG" />
              <Field label="LEI" k="lei" ph="529900…" />
              <Field label="Filing contact email" k="filing_contact_email" ph="ir@client.com" />
            </div>

            <div>
              <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Entitlements {ent === null && <span className="text-[var(--color-mute)]">· sector defaults</span>}</div>
              <div className="flex flex-wrap gap-1.5">
                {(cat.data?.offerings ?? []).map(o => {
                  const on = chosen.includes(o)
                  return <button key={o} onClick={() => setEnt((ent ?? defaults).includes(o) ? (ent ?? defaults).filter(x => x !== o) : [...(ent ?? defaults), o])}
                    className={`mono text-[11px] px-2.5 py-1 rounded-md border transition ${on ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]'}`}>{o}</button>
                })}
              </div>
            </div>

            <div className="border-t border-[var(--color-line)] pt-3">
              <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-2">First admin (optional — the client's login)</div>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Email" k="admin_email" ph="admin@client.com" />
                <Field label="Full name" k="admin_full_name" ph="Jane Admin" />
                <Field label="Temp password" k="admin_password" ph="≥ 6 chars" type="password" />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={onClose}>Cancel</Button>
              <Button onClick={submit} disabled={busy}>{busy ? 'Provisioning…' : 'Provision tenant'}</Button>
            </div>
          </div>
        )}
      </Card>
      </div>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[50vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
