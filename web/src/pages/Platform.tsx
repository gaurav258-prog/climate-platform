import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, CheckCircle2, ChevronRight, Clock, Globe, LifeBuoy, LogIn, MapPin, Plus, Send, Sprout, Users } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { pressable } from '../lib/pressable'
import { actionLabel } from '../lib/actionLabels'
import { Button, Card, HeroBanner, PageHeader, SectionHead } from '../components/ui'
import OperatorTabs from '../components/OperatorTabs'
import { CloseButton, Dialog } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { HEADING, InfoButton } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { Field, Share, ago, inp, refused } from './admin/parts'

// Tellumen's platform-operator view, to the UI standard (2026-10-16): every customer workspace at a glance, the support
// queue, and provisioning. Cross-workspace and read-only; the server names every code (services/governance/admin_view).

interface Tenant {
  org_id: string; name: string; type: string; type_label: string | null; country: string; users: number; active_users: number
  sites: number; plots: number; pending_approvals: number; last_activity: string | null; offerings: { key: string; label: string }[]
}
interface Tenants { totals: { tenants: number; users: number; sites: number; plots: number; pending_approvals: number }; tenants: Tenant[] }
interface TenantDetail {
  organization: { org_id: string; name: string; legal_name: string | null; type: string; type_label: string | null; country: string; lei: string | null; eori: string | null; filing_contact_email: string | null }
  users: { email: string; full_name: string; status: string; last_login_at: string | null; role_labels: string[] }[]
  offerings: { key: string; label: string }[]
  recent_activity: { action: string; email: string | null; created_at: string | null }[]
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Each customer organisation on the platform: its people, its book, the approvals waiting and when it was last active; the support requests from every customer; and provisioning a new workspace.' },
  { heading: HEADING.limits, body: 'Visible to Tellumen’s platform operators only. Reading across workspaces changes nothing in them; opening a workspace as its customer is recorded in that customer’s own audit trail.' },
]
const SECTOR_TONE = ['var(--color-sky)', 'var(--color-good)', 'var(--color-warn)', 'var(--color-blue)', 'var(--color-slate)', 'var(--color-bad)', 'var(--color-faint)']

export default function Platform() {
  const q = useQuery({ queryKey: ['ops-tenants'], queryFn: () => api.get<Tenants>('/v1/ops/tenants') })
  const [open, setOpen] = useState<string | null>(null)
  const [showNew, setShowNew] = useState(false)
  if (q.isLoading) return <Center>Loading…</Center>
  if (q.error || !q.data) return <Center>The workspaces could not be loaded — this view is for platform operators.</Center>
  const d = q.data
  const bySector = [...d.tenants.reduce((m, t) => m.set(t.type_label ?? 'Other', (m.get(t.type_label ?? 'Other') ?? 0) + 1), new Map<string, number>()).entries()].sort((a, b) => b[1] - a[1])

  return (
    <div className="fadeup space-y-6">
      <OperatorTabs />
      <PageHeader eyebrow="Tellumen · platform operator" title="Customer workspaces" lead="Every customer on the platform, and their requests." about={ABOUT}
        actions={<Button onClick={() => setShowNew(true)}><Plus size={15} /> Provision a workspace</Button>} />
      {showNew && <CreateTenant onClose={() => setShowNew(false)} onCreated={() => { setShowNew(false); q.refetch() }} />}

      <HeroBanner eyebrow="Platform"
        title={d.totals.pending_approvals > 0 ? `${d.totals.pending_approvals} approvals waiting across your customers.` : `${d.totals.tenants} organisations on the platform.`}
        stat={[
          { label: 'Workspaces', value: d.totals.tenants, icon: Building2, tone: 'var(--color-sky)' },
          { label: 'People', value: d.totals.users, icon: Users, tone: 'var(--color-sky)' },
          { label: 'Sites', value: d.totals.sites, icon: MapPin, tone: 'var(--color-sky)' },
          { label: 'Sourcing plots', value: d.totals.plots, icon: Sprout, tone: 'var(--color-sky)' },
          { label: 'Approvals waiting', value: d.totals.pending_approvals, icon: Clock, tone: d.totals.pending_approvals ? 'var(--color-warn)' : 'var(--color-good)' },
        ]} />

      <Card className="p-4">
        <div className="text-[12.5px] text-[var(--color-mute)] mb-2">Workspaces by sector</div>
        <div className="flex h-2.5 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={bySector.map(([k, n]) => `${k} ${n}`).join(', ')}>
          {bySector.map(([k, n], i) => <span key={k} style={{ width: `${(100 * n) / d.tenants.length}%`, background: SECTOR_TONE[i % SECTOR_TONE.length], opacity: 0.85 }} />)}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[12px]">
          {bySector.map(([k, n], i) => <span key={k} className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: SECTOR_TONE[i % SECTOR_TONE.length] }} />{k} <b className="text-[var(--color-ink)] tabular-nums">{n}</b></span>)}
        </div>
      </Card>

      <Card className="p-0 overflow-x-auto">
        <table className="data-table w-full text-[13px]">
          <thead><tr><th>Workspace</th><th>Sector</th><th className="min-w-[140px]">People</th><th className="text-right">Sites</th><th className="text-right">Plots</th>
            <th className="text-right">Waiting</th><th>Modules</th><th>Last active</th><th></th></tr></thead>
          <tbody>
            {d.tenants.map(t => (
              <tr key={t.org_id} {...pressable(() => setOpen(t.org_id), { row: true })} className="cursor-pointer hover:bg-[var(--color-panel)]">
                <td><span className="text-[var(--color-ink)]">{t.name}</span> <span className="text-[11px] text-[var(--color-faint)]">{t.country}</span></td>
                <td className="text-[var(--color-mute)]">{t.type_label}</td>
                <td><Share n={t.active_users} of={t.users} label="Active" tone="var(--color-good)" /></td>
                <td className="text-right tabular-nums text-[var(--color-mute)]">{t.sites}</td>
                <td className="text-right tabular-nums text-[var(--color-mute)]">{t.plots}</td>
                <td className="text-right tabular-nums" style={{ color: t.pending_approvals ? 'var(--color-warn)' : 'var(--color-faint)' }}>{t.pending_approvals || '—'}</td>
                <td><div className="flex flex-wrap gap-1">{t.offerings.map(o => <span key={o.key} className="text-[11px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)] whitespace-nowrap">{o.label}</span>)}</div></td>
                <td className="text-[12px] text-[var(--color-mute)] whitespace-nowrap">{ago(t.last_activity)}</td>
                <td><ChevronRight size={15} className="text-[var(--color-faint)]" /></td>
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

// ── the support queue — every customer's requests ────────────────────────────────────────────────────────────
interface SReq {
  id: string; org_name: string | null; subject: string; category_label: string; priority: string; priority_label: string
  status: string; status_label: string; requester_email: string | null; message_count: number; awaiting_support: boolean
  first_response_at: string | null; last_activity: string | null
}
interface SMsg { id: string; author_side: 'customer' | 'support'; author_email: string | null; author_name: string | null; body: string; created_at: string | null }
const STATUS_TONE: Record<string, 'good' | 'warn' | 'neutral'> = { resolved: 'good', in_progress: 'neutral', open: 'warn' }
const SUPPORT = {
  title: 'Support requests', sections: [
    { heading: HEADING.shows, body: 'Every customer’s requests, with those waiting for Tellumen’s reply first.' },
    { heading: HEADING.read, body: 'A reply is written into the customer’s thread and recorded in their audit trail. A first reply moves an open request to in progress.' },
  ],
}

function SupportQueue() {
  const [status, setStatus] = useState<'open' | 'all'>('open')
  const [sel, setSel] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['ops-support', status], queryFn: () => api.get<{ totals: { open: number; awaiting_support: number }; requests: SReq[] }>(`/v1/ops/support?status=${status}`) })
  const rows = q.data?.requests ?? []
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        <SectionHead icon={LifeBuoy} className="gap-1.5">Support requests <InfoButton compact details={SUPPORT} /></SectionHead>
        {q.data && <>
          <StatusChip tone={q.data.totals.awaiting_support ? 'warn' : 'good'} label={`${q.data.totals.awaiting_support} waiting for a reply`} />
          <StatusChip tone="neutral" label={`${q.data.totals.open} open`} />
        </>}
        <div className="ml-auto flex gap-2">
          {(['open', 'all'] as const).map(f => (
            <button key={f} onClick={() => setStatus(f)} aria-pressed={status === f}
              className={clsx('px-3 py-1 rounded-lg text-[12.5px] border transition', status === f ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{f === 'open' ? 'Open' : 'All'}</button>
          ))}
        </div>
      </div>
      <Card className="p-0 overflow-x-auto">
        {rows.length === 0 ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Nothing {status === 'open' ? 'open' : 'here'}.</div> : (
          <table className="data-table w-full text-[13px]">
            <thead><tr><th>Customer</th><th>Request</th><th>Kind</th><th>Status</th><th className="text-right">Messages</th><th>Last</th><th></th></tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} {...pressable(() => setSel(r.id), { row: true })} className="cursor-pointer hover:bg-[var(--color-panel)]">
                  <td className="text-[var(--color-ink)]">{r.org_name}</td>
                  <td className="text-[var(--color-mute)]">{r.subject}{r.awaiting_support && <StatusChip className="ml-2" tone="warn" label="Needs a reply" />}</td>
                  <td className="text-[var(--color-faint)]">{r.category_label}{r.priority !== 'normal' && <span className="ml-1 text-[var(--color-warn)]">· {r.priority_label}</span>}</td>
                  <td><StatusChip tone={STATUS_TONE[r.status] ?? 'neutral'} label={r.status_label} /></td>
                  <td className="text-right tabular-nums text-[var(--color-mute)]">{r.message_count}</td>
                  <td className="text-[12px] text-[var(--color-mute)] whitespace-nowrap">{ago(r.last_activity)}</td>
                  <td><ChevronRight size={15} className="text-[var(--color-faint)]" /></td>
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
    setBusy(true)
    try {
      await api.post(`/v1/ops/support/${id}/reply`, { body: reply.trim(), status: resolve ? 'resolved' : undefined })
      setReply(''); await q.refetch(); qc.invalidateQueries({ queryKey: ['ops-support'] }); onChanged()
    } catch (e) { refused(e, 'The reply could not be sent.') } finally { setBusy(false) }
  }
  return (
    <Drawer label="Support request" onClose={onClose} overlayClassName="z-40" className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-4">
      <div className="flex items-center justify-between"><SectionHead icon={LifeBuoy}>Reply as Tellumen</SectionHead><CloseButton onClick={onClose} /></div>
      {!d ? <div className="text-[var(--color-faint)] text-sm">Loading…</div> : (<>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusChip tone={STATUS_TONE[d.request.status] ?? 'neutral'} label={d.request.status_label} />
            <span className="text-[12px] text-[var(--color-faint)]">{[d.request.org_name, d.request.requester_email].filter(Boolean).join(' · ')}</span>
          </div>
          <h2 className="text-[17px] font-semibold mt-1.5 leading-snug">{d.request.subject}</h2>
        </div>
        <div className="space-y-3 border-t border-[var(--color-line)] pt-4">
          {d.messages.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No messages yet — reply below.</div>}
          {d.messages.map(m => {
            const ours = m.author_side === 'support'
            return (
              <div key={m.id} className={clsx('flex', ours ? 'justify-end' : 'justify-start')}>
                <div className={clsx('max-w-[85%] rounded-xl px-3.5 py-2.5 border', ours ? 'bg-[color-mix(in_oklab,var(--color-sky)_10%,var(--color-bg-2))] border-[color-mix(in_oklab,var(--color-sky)_28%,var(--color-line))]' : 'bg-[var(--color-panel-2)] border-[var(--color-line)]')}>
                  <div className="flex items-center gap-2 mb-1 text-[11.5px]"><span className={ours ? 'text-[var(--color-sky)]' : 'text-[var(--color-faint)]'}>{ours ? 'Tellumen' : (m.author_name || m.author_email || 'Customer')}</span><span className="text-[var(--color-faint)]">{ago(m.created_at)}</span></div>
                  <div className="text-[13px] text-[var(--color-ink)] whitespace-pre-wrap leading-relaxed">{m.body}</div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="border-t border-[var(--color-line)] pt-4">
          <textarea value={reply} onChange={e => setReply(e.target.value)} rows={4} maxLength={4000} placeholder="Reply to the customer…" aria-label="Reply" className={clsx(inp, 'resize-y')} />
          <div className="flex gap-2 mt-2">
            <Button disabled={busy || !reply.trim()} onClick={() => send(false)}><Send size={14} /> Send reply</Button>
            <Button variant="ghost" disabled={busy || !reply.trim()} onClick={() => send(true)}><CheckCircle2 size={14} /> Send and resolve</Button>
          </div>
        </div>
      </>)}
    </Drawer>
  )
}

function TenantDrawer({ orgId, onClose }: { orgId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['ops-tenant', orgId], queryFn: () => api.get<TenantDetail>(`/v1/ops/tenant/${orgId}`) })
  const { viewAsTenant } = useAuth()
  const [busy, setBusy] = useState(false)
  const d = q.data
  const enter = async () => { setBusy(true); try { await viewAsTenant(orgId) } catch (e) { refused(e, 'The workspace could not be opened.'); setBusy(false) } }
  const VIEW_AS = { title: 'View as this customer', sections: [
    { heading: HEADING.shows, body: 'Opens the customer’s full workspace as one of its active people would see it.' },
    { heading: HEADING.limits, body: 'Recorded in the customer’s own audit trail, so they can see that Tellumen opened it.' },
  ] }
  return (
    <Drawer label="Workspace" onClose={onClose} overlayClassName="z-40" className="w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6 space-y-5">
      <div className="flex items-center justify-between"><SectionHead icon={Globe}>Workspace</SectionHead><CloseButton onClick={onClose} /></div>
      {!d ? <div className="text-[var(--color-faint)] text-sm">Loading…</div> : (<>
        <div>
          <h2 className="display text-2xl font-semibold m-0">{d.organization.name}</h2>
          <p className="text-[12.5px] text-[var(--color-mute)] m-0 mt-1">{[d.organization.type_label, d.organization.country].filter(Boolean).join(' · ')}</p>
          <div className="flex flex-wrap gap-1.5 mt-2">{d.offerings.map(o => <span key={o.key} className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{o.label}</span>)}</div>
        </div>
        {d.organization.type !== 'platform' && (
          <div className="flex items-center gap-2">
            <Button onClick={enter} disabled={busy}><LogIn size={15} /> {busy ? 'Opening…' : 'View as this customer'}</Button>
            <InfoButton compact details={VIEW_AS} />
          </div>
        )}
        <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[12.5px] m-0">
          {([['Legal name', d.organization.legal_name], ['Legal entity identifier', d.organization.lei], ['Customs number', d.organization.eori], ['Filing contact', d.organization.filing_contact_email]] as [string, string | null][]).map(([k, v]) => (
            <div key={k} className="contents"><dt className="text-[var(--color-mute)]">{k}</dt><dd className="m-0 text-right truncate">{v ? <span className="text-[var(--color-ink)]">{v}</span> : <span className="text-[var(--color-faint)]">—</span>}</dd></div>
          ))}
        </dl>
        <section>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-2">People · {d.users.length}</h4>
          <ul className="m-0 p-0 list-none space-y-1.5">
            {d.users.map(u => (
              <li key={u.email} className="flex items-center justify-between gap-3 text-[12.5px]">
                <span className="min-w-0"><span className="text-[var(--color-ink)]">{u.full_name}</span> <span className="text-[var(--color-faint)] text-[11.5px]">{u.role_labels.join(', ')}</span></span>
                <span className="text-[11.5px] text-[var(--color-faint)] whitespace-nowrap">{ago(u.last_login_at)}</span>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-2">Recent activity</h4>
          {d.recent_activity.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">No activity yet.</div> : (
            <ul className="m-0 p-0 list-none space-y-1">
              {d.recent_activity.map((a, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="text-[var(--color-mute)]">{actionLabel(a.action)}</span>
                  <span className="text-[var(--color-faint)] truncate">{[a.email, ago(a.created_at)].filter(Boolean).join(' · ')}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </>)}
    </Drawer>
  )
}

// ── provision a new workspace (onboarding step one) ──────────────────────────────────────────────────────────
interface Catalog { org_types: string[]; default_entitlements: Record<string, string[]>; offerings: string[]; sector_names: Record<string, string>; offering_names: Record<string, string> }
interface Created { org_id: string; name: string; type_label: string; offerings: { key: string; label: string }[]; role_labels: string[]; admin: { email: string } | null }

function CreateTenant({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const cat = useQuery({ queryKey: ['tenants-catalog'], queryFn: () => api.get<Catalog>('/v1/admin/tenants/catalog') })
  const [f, setF] = useState({ name: '', org_type: 'bank', country: '', legal_name: '', lei: '', filing_contact_email: '', admin_email: '', admin_full_name: '', admin_password: '' })
  const [ent, setEnt] = useState<string[] | null>(null)      // null: the sector's usual modules
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<Created | null>(null)
  const set = (k: keyof typeof f, v: string) => setF(s => ({ ...s, [k]: v }))
  const defaults = cat.data?.default_entitlements?.[f.org_type] ?? []
  const chosen = ent ?? defaults
  const ready = f.name.trim() && f.country.trim().length === 2 && (!f.admin_email || f.admin_password.length >= 6)
  const submit = async () => {
    setBusy(true)
    try {
      const body: Record<string, unknown> = { name: f.name.trim(), org_type: f.org_type, country: f.country, legal_name: f.legal_name || null,
        lei: f.lei || null, filing_contact_email: f.filing_contact_email || null, entitlements: ent }
      if (f.admin_email) Object.assign(body, { admin_email: f.admin_email, admin_full_name: f.admin_full_name || null, admin_password: f.admin_password })
      const r = await api.post<Created>('/v1/admin/tenants', body)
      setDone(r); toast.success(`${r.name} is live.`)
    } catch (e) { refused(e, 'The workspace could not be provisioned.') } finally { setBusy(false) }
  }
  const NEXT = { title: 'Provisioning', sections: [
    { heading: HEADING.shows, body: 'You set up the workspace, its identity and a first administrator; the customer then loads their own book and invites their people.' },
    { heading: HEADING.read, body: 'The modules start from the sector’s usual set; change them if the contract differs.' },
  ] }
  return (
    <Dialog title="Provision a workspace" onClose={onClose} className="max-w-[600px]">
      {done ? (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[var(--color-good)]"><CheckCircle2 size={18} /> <span className="text-[14px] font-medium">{done.name} is live</span></div>
          <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[12.5px] m-0">
            <dt className="text-[var(--color-mute)]">Sector</dt><dd className="m-0 text-[var(--color-ink)]">{done.type_label}</dd>
            <dt className="text-[var(--color-mute)]">Modules</dt><dd className="m-0 flex flex-wrap gap-1">{done.offerings.map(o => <span key={o.key} className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{o.label}</span>)}</dd>
            <dt className="text-[var(--color-mute)]">Roles created</dt><dd className="m-0 text-[var(--color-ink)]">{done.role_labels.join(', ')}</dd>
            {done.admin && <><dt className="text-[var(--color-mute)]">First administrator</dt><dd className="m-0 text-[var(--color-ink)]">{done.admin.email}</dd></>}
          </dl>
          <p className="m-0 text-[12.5px] text-[var(--color-mute)]">Next for the customer: confirm their reporting identity, load their book and set up their approvals.</p>
          <div className="flex justify-end"><Button onClick={onCreated}>Done</Button></div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-mute)]">A workspace, its identity and a first administrator. <InfoButton compact details={NEXT} /></div>
          <div className="grid sm:grid-cols-2 gap-3">
            <Field label="Name"><input value={f.name} onChange={e => set('name', e.target.value)} className={inp} /></Field>
            <Field label="Sector">
              <select value={f.org_type} onChange={e => { set('org_type', e.target.value); setEnt(null) }} className={inp}>
                {(cat.data?.org_types ?? []).map(t => <option key={t} value={t}>{cat.data?.sector_names[t]}</option>)}
              </select>
            </Field>
            <Field label="Country, two letters"><input value={f.country} onChange={e => set('country', e.target.value.toUpperCase())} maxLength={2} className={inp} /></Field>
            <Field label="Legal name"><input value={f.legal_name} onChange={e => set('legal_name', e.target.value)} className={inp} /></Field>
            <Field label="Legal entity identifier"><input value={f.lei} onChange={e => set('lei', e.target.value)} className={inp} /></Field>
            <Field label="Filing contact e-mail"><input value={f.filing_contact_email} onChange={e => set('filing_contact_email', e.target.value)} className={inp} /></Field>
          </div>
          <div>
            <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Modules{ent === null && <span className="text-[var(--color-faint)]"> · the sector’s usual set</span>}</div>
            <div className="flex flex-wrap gap-1.5">
              {(cat.data?.offerings ?? []).map(o => {
                const on = chosen.includes(o)
                return <button key={o} aria-pressed={on} onClick={() => setEnt(on ? chosen.filter(x => x !== o) : [...chosen, o])}
                  className={clsx('text-[12px] px-2.5 py-1 rounded-md border transition', on ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]')}>{cat.data?.offering_names[o]}</button>
              })}
            </div>
          </div>
          <div className="border-t border-[var(--color-line)] pt-3">
            <div className="text-[12.5px] text-[var(--color-ink)] mb-2">First administrator — optional, the customer’s own sign-in</div>
            <div className="grid sm:grid-cols-3 gap-3">
              <Field label="E-mail"><input value={f.admin_email} onChange={e => set('admin_email', e.target.value)} className={inp} /></Field>
              <Field label="Full name"><input value={f.admin_full_name} onChange={e => set('admin_full_name', e.target.value)} className={inp} /></Field>
              <Field label="Temporary password"><input type="password" autoComplete="new-password" value={f.admin_password} onChange={e => set('admin_password', e.target.value)} className={inp} /></Field>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={busy || !ready}>{busy ? 'Provisioning…' : 'Provision workspace'}</Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[50vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
