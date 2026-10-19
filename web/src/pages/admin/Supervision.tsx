import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, UserPlus, Users as UsersIcon, X } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { Button, Card, SectionHead } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { Field, inp, refused, sel } from './parts'

// A supervisory authority's own set-up: its profile (customer class and expectations), the entities it supervises and
// who works which. Shown to a supervisory body only; every code arrives named (sector, role, capacity, scenario).

type Option = { value: string; label: string }
interface Metric { id: string; label: string; unit: string; watch_above?: number; act_above?: number; watch_below?: number }
interface Profile { config: { profile_id: string; label: string; default_scenario: string; default_horizon: string; sectors: Record<string, { label: string; metrics: Metric[] }> }
  overrides: { thresholds?: Record<string, Record<string, Record<string, number>>>; reference_prefix?: string | null; signatory_title?: string | null }
  available_profiles: Record<string, string>; options: { scenario: Option[]; horizon: Option[] } }

const PROFILE = {
  title: 'Supervision profile', sections: [
    { heading: HEADING.shows, body: 'Your customer class — the sectors you supervise, the reports they file and the expectations you hold them to — and the defaults your analyses open on.' },
    { heading: HEADING.read, body: 'A level left empty uses the profile’s own. Letter references read prefix, year, kind and number; the signatory title is printed on every letter.' },
  ],
}
const LEVELS: [keyof Metric, string][] = [['watch_above', 'Watch above'], ['act_above', 'Act above'], ['watch_below', 'Watch below']]

export function SupervisionProfile() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const isReg = profile?.org?.type === 'regulator'
  const q = useQuery({ queryKey: ['supervision-profile'], enabled: isReg, queryFn: () => api.get<Profile>('/v1/supervisor/profile') })
  const [busy, setBusy] = useState(false)
  if (!isReg || !q.data) return null
  const d = q.data
  const save = async (body: Record<string, unknown>) => {
    setBusy(true)
    try { await api.put('/v1/supervisor/profile', body); await qc.invalidateQueries({ queryKey: ['supervision-profile'] }); await qc.invalidateQueries({ queryKey: ['supervisor-benchmark'] }) }
    catch (e) { refused(e, 'The profile could not be saved.') } finally { setBusy(false) }
  }
  const setLevel = (sector: string, metric: string, key: string, raw: string) => {
    const t = JSON.parse(JSON.stringify(d.overrides.thresholds ?? {}))
    t[sector] = t[sector] ?? {}; t[sector][metric] = t[sector][metric] ?? {}
    if (raw === '') delete t[sector][metric][key]; else t[sector][metric][key] = Number(raw)
    return save({ thresholds: t })
  }
  return (
    <Card className="p-5 space-y-4">
      <SectionHead icon={Landmark} className="gap-1.5">Supervision profile <InfoButton compact details={PROFILE} /></SectionHead>
      <div className="grid sm:grid-cols-3 gap-3">
        <Field label="Profile">
          <select value={d.config.profile_id} disabled={busy} onChange={e => save({ profile: e.target.value })} className={clsx(sel, 'w-full py-2')}>
            {Object.entries(d.available_profiles).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
        </Field>
        <Field label="Default scenario">
          <select value={d.config.default_scenario} disabled={busy} onChange={e => save({ default_scenario: e.target.value })} className={clsx(sel, 'w-full py-2')}>
            {d.options.scenario.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Default horizon">
          <select value={d.config.default_horizon} disabled={busy} onChange={e => save({ default_horizon: e.target.value })} className={clsx(sel, 'w-full py-2')}>
            {d.options.horizon.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </Field>
        <Field label="Letter reference prefix">
          <input defaultValue={d.overrides.reference_prefix ?? ''} maxLength={8} disabled={busy} className={clsx(inp, 'uppercase')}
            onBlur={e => e.target.value !== (d.overrides.reference_prefix ?? '') && save({ reference_prefix: e.target.value })} />
        </Field>
        <Field label="Signatory title" className="sm:col-span-2">
          <input defaultValue={d.overrides.signatory_title ?? ''} disabled={busy} className={inp}
            onBlur={e => e.target.value !== (d.overrides.signatory_title ?? '') && save({ signatory_title: e.target.value })} />
        </Field>
      </div>
      {Object.entries(d.config.sectors).map(([sec, s]) => (
        <section key={sec}>
          <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">{s.label}</h4>
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
            {s.metrics.filter(m => LEVELS.some(([k]) => m[k] != null)).map(m => (
              <li key={m.id} className="py-2 flex flex-wrap items-center justify-between gap-3 text-[12.5px]">
                <span className="text-[var(--color-ink)]">{m.label}</span>
                <span className="flex flex-wrap items-center gap-2 text-[11.5px] text-[var(--color-faint)]">
                  {LEVELS.filter(([k]) => m[k] != null).map(([k, label]) => (
                    <label key={k} className="inline-flex items-center gap-1.5">{label}
                      <input className={clsx(sel, 'w-20 text-right tabular-nums')} defaultValue={m[k] as number} disabled={busy}
                        onBlur={e => Number(e.target.value) !== m[k] && setLevel(sec, m.id, k, e.target.value)} />
                    </label>
                  ))}
                  <span>{m.unit === 'pct' ? '%' : 'EUR'}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </Card>
  )
}

// ── the entities this authority supervises ───────────────────────────────────────────────────────────────────
interface ScopeRow { supervision_id: string; org_id: string; name: string; country: string | null; lei: string | null; jurisdiction: string | null
  created_at: string | null; acknowledged_at: string | null; site_access: boolean }
interface ScopeResp { profile_label: string; sectors: string[]; sector_labels: string[]; in_profile: ScopeRow[]; out_of_profile: ScopeRow[]
  candidates: { org_id: string; name: string; type: string; type_label: string | null; country: string | null }[] }
const POPULATION = {
  title: 'Supervised population', sections: [
    { heading: HEADING.shows, body: 'The entities your authority supervises, whether each has acknowledged it, and whether it granted access to its individual sites.' },
    { heading: HEADING.read, body: 'Only an entity in a sector your profile covers can be added. An entity not on the platform gets a minimal account: its contact activates it by e-mail and sees only the supervisory portal.' },
  ],
}

export function SupervisionScope() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const can = profile?.org?.type === 'regulator' && (profile?.permissions ?? []).includes('supervisor.scope.manage')
  const [search, setSearch] = useState('')
  const q = useQuery({ queryKey: ['supervision-scope', search], enabled: !!can, queryFn: () => api.get<ScopeResp>(`/v1/supervisor/scope${search ? `?q=${encodeURIComponent(search)}` : ''}`) })
  const [jur, setJur] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)
  const [contacts, setContacts] = useState<ScopeRow | null>(null)
  if (!can || !q.data) return null
  const d = q.data
  const refresh = () => Promise.all(['supervision-scope', 'supervisor-workflow', 'supervision-assignments'].map(k => qc.invalidateQueries({ queryKey: [k] })))
  const add = async (org_id: string) => {
    setBusy(true)
    try { await api.post('/v1/supervisor/scope', { supervised_org_id: org_id, jurisdiction: jur[org_id] || null }); toast.success('Added to your population; the entity has been told.'); await refresh() }
    catch (e) { refused(e, 'The entity could not be added.') } finally { setBusy(false) }
  }
  const end = async (r: ScopeRow) => {
    if (!window.confirm(`End supervision of ${r.name}? Its assignments end with it.`)) return
    setBusy(true)
    try { await api.del(`/v1/supervisor/scope/${r.supervision_id}`); await refresh() } catch (e) { refused(e, 'Supervision could not be ended.') } finally { setBusy(false) }
  }
  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SectionHead icon={UsersIcon} className="gap-1.5">Supervised population <InfoButton compact details={POPULATION} /></SectionHead>
        <span className="text-[12.5px] text-[var(--color-mute)]">{d.profile_label}</span>
        <div className="flex flex-wrap gap-1.5">{d.sector_labels.map(s => <span key={s} className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{s}</span>)}</div>
        <Button variant="ghost" className="ml-auto" onClick={() => setAdding(true)}><UserPlus size={14} /> Add an entity not on the platform</Button>
      </div>
      {d.out_of_profile.length > 0 && (
        <div className="rounded-lg border border-[var(--color-warn)]/40 bg-[var(--color-warn)]/10 px-3 py-2 text-[12.5px] text-[var(--color-ink)]">
          <div>Outside your profile, so not counted in your population — switch profile or end their supervision:</div>
          <div className="mt-1.5 flex flex-wrap gap-2">{d.out_of_profile.map(r => (
            <span key={r.supervision_id} className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-panel)] px-2 py-0.5">{r.name}
              <button disabled={busy} onClick={() => end(r)} aria-label={`End supervision of ${r.name}`} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]"><X size={12} /></button></span>
          ))}</div>
        </div>
      )}
      <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
        {d.in_profile.length === 0 && <li className="py-2 text-[12.5px] text-[var(--color-faint)]">No entity yet — add one below.</li>}
        {d.in_profile.map(r => (
          <li key={r.supervision_id} className="py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12.5px]">
            <span className="min-w-[200px]"><span className="text-[var(--color-ink)]">{r.name}</span>
              <span className="text-[11.5px] text-[var(--color-faint)] ml-2">{[r.country, r.jurisdiction].filter(Boolean).join(' · ')}</span></span>
            <StatusChip tone={r.acknowledged_at ? 'good' : 'warn'} label={r.acknowledged_at ? 'Acknowledged' : 'Awaiting acknowledgement'} />
            <StatusChip tone={r.site_access ? 'good' : 'neutral'} label={r.site_access ? 'Sites granted' : 'Regional only'} />
            {r.created_at && <span className="text-[11.5px] text-[var(--color-faint)]">since {r.created_at.slice(0, 10)}</span>}
            <span className="ml-auto flex items-center gap-3">
              <button onClick={() => setContacts(r)} className="text-[12px] text-[var(--color-sky)] hover:underline">Contacts</button>
              <button disabled={busy} onClick={() => end(r)} className="text-[12px] text-[var(--color-faint)] hover:text-[var(--color-bad)]">End supervision</button>
            </span>
          </li>
        ))}
      </ul>
      <div>
        <div className="text-[12.5px] text-[var(--color-ink)] mb-1.5">Add an entity already on the platform</div>
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search by name or identifier" aria-label="Search entities" className={clsx(inp, 'max-w-sm mb-2')} />
        <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
          {d.candidates.length === 0 && <li className="py-2 text-[12.5px] text-[var(--color-faint)]">No further entities in your sectors{search ? ' match this search' : ''}.</li>}
          {d.candidates.map(c => (
            <li key={c.org_id} className="py-2 flex flex-wrap items-center gap-3 text-[12.5px]">
              <span className="min-w-[200px]"><span className="text-[var(--color-ink)]">{c.name}</span>
                <span className="text-[11.5px] text-[var(--color-faint)] ml-2">{[c.type_label, c.country].filter(Boolean).join(' · ')}</span></span>
              <input value={jur[c.org_id] ?? ''} onChange={e => setJur(j => ({ ...j, [c.org_id]: e.target.value }))} placeholder="Jurisdiction" aria-label={`Jurisdiction of ${c.name}`} className={clsx(sel, 'w-40')} />
              <Button variant="ghost" disabled={busy} onClick={() => add(c.org_id)}>Add to population</Button>
            </li>
          ))}
        </ul>
      </div>
      {adding && <AddRespondent sectors={d.sectors} labels={d.sector_labels} onClose={() => setAdding(false)} onDone={async () => { setAdding(false); await refresh() }} />}
      {contacts && <Contacts row={contacts} onClose={() => setContacts(null)} />}
    </Card>
  )
}

function AddRespondent({ sectors, labels, onClose, onDone }: { sectors: string[]; labels: string[]; onClose: () => void; onDone: () => Promise<unknown> }) {
  const [f, setF] = useState({ name: '', org_type: sectors[0] ?? '', country: '', jurisdiction: '', lei: '', contact_email: '', contact_name: '' })
  const [busy, setBusy] = useState(false)
  const add = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ name: string; invite: { email: string } }>('/v1/supervisor/scope/respondent', { ...f, jurisdiction: f.jurisdiction || null, lei: f.lei || null, contact_name: f.contact_name || null })
      toast.success(`${r.name} added; an activation link was sent to ${r.invite.email}.`); await onDone()
    } catch (e) { refused(e, 'The entity could not be added.') } finally { setBusy(false) }
  }
  return (
    <Dialog title="Add an entity not on the platform" onClose={onClose} className="max-w-2xl">
      <div className="space-y-4">
        <p className="m-0 text-[12.5px] text-[var(--color-mute)]">The entity gets a minimal, audited account: its contact activates it by e-mail and sees only the supervisory portal.</p>
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="Entity name"><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} className={inp} /></Field>
          <Field label="Sector"><select value={f.org_type} onChange={e => setF({ ...f, org_type: e.target.value })} className={inp}>{sectors.map((s, i) => <option key={s} value={s}>{labels[i]}</option>)}</select></Field>
          <Field label="Country, two letters"><input value={f.country} onChange={e => setF({ ...f, country: e.target.value.toUpperCase() })} maxLength={2} className={inp} /></Field>
          <Field label="Jurisdiction"><input value={f.jurisdiction} onChange={e => setF({ ...f, jurisdiction: e.target.value })} className={inp} /></Field>
          <Field label="Legal entity identifier"><input value={f.lei} onChange={e => setF({ ...f, lei: e.target.value })} className={inp} /></Field>
          <div />
          <Field label="Contact e-mail"><input value={f.contact_email} onChange={e => setF({ ...f, contact_email: e.target.value })} className={inp} /></Field>
          <Field label="Contact name"><input value={f.contact_name} onChange={e => setF({ ...f, contact_name: e.target.value })} className={inp} /></Field>
        </div>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !f.name || !f.country || !f.contact_email} onClick={add}>{busy ? 'Adding…' : 'Add and invite'}</Button>
        </div>
      </div>
    </Dialog>
  )
}

function Contacts({ row, onClose }: { row: ScopeRow; onClose: () => void }) {
  const q = useQuery({ queryKey: ['entity-contacts', row.supervision_id], queryFn: () => api.get<{ contacts: { email: string; full_name: string | null; status: string; last_login_at: string | null }[] }>(`/v1/supervisor/scope/${row.supervision_id}/contacts`) })
  const [email, setEmail] = useState(''); const [name, setName] = useState(''); const [busy, setBusy] = useState(false)
  const invite = async () => {
    setBusy(true)
    try { await api.post(`/v1/supervisor/scope/${row.supervision_id}/invite`, { email, full_name: name || null }); toast.success(`Activation link sent to ${email}.`); setEmail(''); setName(''); await q.refetch() }
    catch (e) { refused(e, 'The invitation could not be sent.') } finally { setBusy(false) }
  }
  const people = q.data?.contacts ?? []
  return (
    <Dialog title={`People at ${row.name}`} onClose={onClose}>
      <div className="space-y-4">
        {people.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No one invited yet.</div> : (
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
            {people.map(c => (
              <li key={c.email} className="py-2 flex items-center justify-between gap-3 text-[12.5px]">
                <span><span className="text-[var(--color-ink)]">{c.full_name ?? c.email}</span><span className="block text-[11.5px] text-[var(--color-faint)]">{c.email}</span></span>
                <StatusChip value={c.status} tone={c.status === 'active' ? 'good' : 'warn'} label={c.status === 'active' ? 'Active' : 'Invited'} />
              </li>
            ))}
          </ul>
        )}
        <div className="grid sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <Field label="E-mail"><input value={email} onChange={e => setEmail(e.target.value)} className={inp} /></Field>
          <Field label="Name"><input value={name} onChange={e => setName(e.target.value)} className={inp} /></Field>
          <Button variant="ghost" disabled={busy || !email} onClick={invite}>Invite</Button>
        </div>
      </div>
    </Dialog>
  )
}

// ── who works which entity ───────────────────────────────────────────────────────────────────────────────────
interface Assign { entities: { org_id: string; name: string; jurisdiction: string | null }[]
  people: { user_id: string; full_name: string; status: string; roles: string[]; scope: 'assigned' | 'population' }[]
  assignments: { assignment_id: string; supervised_org_id: string; user_id: string; full_name: string; capacity_label: string }[]
  roles: Record<string, { label: string; scope: string }> }
const TEAM = {
  title: 'Who works which entity', sections: [
    { heading: HEADING.shows, body: 'Your team and the entities each person works.' },
    { heading: HEADING.read, body: 'A person whose role works a case list sees only the entities assigned to them; a person in a horizontal role sees the whole population.' },
  ],
}

export function SupervisionAssignments() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const can = profile?.org?.type === 'regulator' && (profile?.permissions ?? []).includes('supervisor.assignments.manage')
  const q = useQuery({ queryKey: ['supervision-assignments'], enabled: !!can, queryFn: () => api.get<Assign>('/v1/supervisor/assignments') })
  const [pick, setPick] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  if (!can || !q.data) return null
  const d = q.data
  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: ['supervision-assignments'] }), qc.invalidateQueries({ queryKey: ['supervisor-workflow'] })])
  const add = async (org: string) => {
    const uid = pick[org]; if (!uid) return
    setBusy(true)
    try { await api.put('/v1/supervisor/assignments', { supervised_org_id: org, user_id: uid, capacity: 'lead' }); setPick(p => ({ ...p, [org]: '' })); await refresh() }
    catch (e) { refused(e, 'The person could not be assigned.') } finally { setBusy(false) }
  }
  const end = async (id: string) => { setBusy(true); try { await api.del(`/v1/supervisor/assignments/${id}`); await refresh() } catch (e) { refused(e, 'The assignment could not be ended.') } finally { setBusy(false) } }
  const active = d.people.filter(p => p.status === 'active')
  return (
    <Card className="p-5 space-y-4">
      <SectionHead icon={UsersIcon} className="gap-1.5">Who works which entity <InfoButton compact details={TEAM} /></SectionHead>
      <div className="flex flex-wrap gap-2">
        {d.people.map(p => (
          <span key={p.user_id} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line)] px-2.5 py-1 text-[12px]">
            <span className="text-[var(--color-ink)]">{p.full_name}</span>
            <span className="text-[11px] text-[var(--color-faint)]">{p.roles.map(r => d.roles[r]?.label).filter(Boolean).join(' · ') || 'No role'}</span>
            <StatusChip tone={p.scope === 'population' ? 'good' : 'warn'} label={p.scope === 'population' ? 'Whole population' : 'Assigned only'} />
          </span>
        ))}
      </div>
      <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
        {d.entities.map(e => {
          const mine = d.assignments.filter(a => a.supervised_org_id === e.org_id)
          const free = active.filter(p => !mine.some(a => a.user_id === p.user_id))
          return (
            <li key={e.org_id} className="py-2 flex flex-wrap items-center gap-3 text-[12.5px]">
              <span className="min-w-[200px] text-[var(--color-ink)]">{e.name}{e.jurisdiction && <span className="text-[11.5px] text-[var(--color-faint)] ml-2">{e.jurisdiction}</span>}</span>
              <span className="flex flex-wrap gap-1.5">
                {mine.length === 0 && <StatusChip tone="warn" label="Nobody assigned" />}
                {mine.map(a => (
                  <span key={a.assignment_id} className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-panel-2)] px-2 py-0.5">
                    {a.full_name}<span className="text-[11px] text-[var(--color-faint)]">{a.capacity_label}</span>
                    <button disabled={busy} onClick={() => end(a.assignment_id)} aria-label={`End ${a.full_name}'s assignment`} className="text-[var(--color-faint)] hover:text-[var(--color-bad)]"><X size={12} /></button>
                  </span>
                ))}
              </span>
              <span className="ml-auto flex items-center gap-2">
                <select value={pick[e.org_id] ?? ''} onChange={ev => setPick(p => ({ ...p, [e.org_id]: ev.target.value }))} disabled={busy} aria-label={`Assign a person to ${e.name}`} className={sel}>
                  <option value="">Assign a person…</option>
                  {free.map(p => <option key={p.user_id} value={p.user_id}>{p.full_name}</option>)}
                </select>
                <Button variant="ghost" disabled={busy || !pick[e.org_id]} onClick={() => add(e.org_id)}>Assign</Button>
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
