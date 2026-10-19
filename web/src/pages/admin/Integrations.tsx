import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, ExternalLink, KeyRound, Link2, Plug, Send, Trash2, Webhook } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { webhookTestOutcome } from '../../lib/webhookTest'
import { Button, Card, SectionHead } from '../../components/ui'
import { Dialog } from '../../components/Dialog'
import { HEADING, InfoButton } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import DropFolders from '../../components/DropFolders'
import { CopyRow, Field, ShownOnce, ago, inp, refused, sel } from './parts'

// Connections to the organisation's own systems: tokens that let a system send data in, the addresses it calls (the
// server's own, never typed here), the events sent to its systems, and the systems of record a figure opens in.

interface Token { token_id: string; name: string; token_prefix: string; is_active: boolean; created_by_email: string | null; last_used_at: string | null }
interface Connection { check: string; books: { label: string; url: string }[] }

const TOKENS = {
  title: 'Connect your systems', sections: [
    { heading: HEADING.shows, body: 'Tokens that let your own systems send data straight into your workspace — the third way in beside typing it and uploading a template.' },
    { heading: HEADING.read, body: 'A token acts as your organisation. Rows it sends pass the same checks as an upload: a clean batch is imported, a batch that fails a check waits for a second person, and every refused row comes back with its reason.' },
    { heading: HEADING.limits, body: 'Keep a token in your system’s secret store and revoke it at once if it leaks. The full guide to sending data is in Documentation.' },
  ],
}

export default function Integrations() {
  const { profile } = useAuth()
  return (
    <div className="space-y-5">
      <Tokens />
      <DropFolders sector={profile?.org?.type ?? ''} />
      <Webhooks />
      <SourceSystems />
    </div>
  )
}

function Tokens() {
  const q = useQuery({ queryKey: ['ingest-tokens'], queryFn: () => api.get<Token[]>('/v1/ingest/tokens') })
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<{ name: string; raw: string } | null>(null)
  const [connect, setConnect] = useState(false)
  const [showRevoked, setShowRevoked] = useState(false)
  const all = q.data ?? []
  const revoked = all.filter(t => !t.is_active).length
  const rows = showRevoked ? all : all.filter(t => t.is_active)
  const create = async () => {
    setBusy(true)
    try { const r = await api.post<{ raw_token: string; name: string }>('/v1/ingest/tokens', { name: name.trim() }); setShown({ name: r.name, raw: r.raw_token }); setName(''); q.refetch() }
    catch (e) { refused(e, 'The token could not be created.') } finally { setBusy(false) }
  }
  const revoke = async (t: Token) => {
    if (!confirm(`Revoke “${t.name}”? Any system using it stops at once.`)) return
    try { await api.del(`/v1/ingest/tokens/${t.token_id}`); q.refetch() } catch (e) { refused(e, 'The token could not be revoked.') }
  }
  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SectionHead icon={Plug} className="gap-1.5">Connect your systems <InfoButton compact details={TOKENS} /></SectionHead>
        <span className="text-[12.5px] text-[var(--color-mute)] tabular-nums">{all.length - revoked} active</span>
        {revoked > 0 && <button onClick={() => setShowRevoked(v => !v)} aria-pressed={showRevoked} className="text-[12.5px] text-[var(--color-sky)] hover:underline">{showRevoked ? 'Hide revoked' : `Show ${revoked} revoked`}</button>}
        <Button variant="ghost" className="ml-auto" onClick={() => setConnect(true)}><Link2 size={14} /> Connection details</Button>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="New token" className="flex-1 min-w-[220px]"><input value={name} onChange={e => setName(e.target.value)} placeholder="A name, such as Core banking nightly" maxLength={80} className={inp} /></Field>
        <Button onClick={create} disabled={busy || name.trim().length < 2}><KeyRound size={15} /> {busy ? 'Creating…' : 'Create token'}</Button>
      </div>
      {shown && <ShownOnce title={`Copy the token “${shown.name}” now — it is shown only once.`} value={shown.raw} />}
      {rows.length > 0 && (
        <div className="overflow-x-auto -mx-5">
          <table className="data-table w-full text-[13px]">
            <thead><tr><th>Name</th><th>Starts with</th><th>Created by</th><th>Last used</th><th>Status</th><th></th></tr></thead>
            <tbody>{rows.map(t => (
              <tr key={t.token_id}>
                <td className="text-[var(--color-ink)]">{t.name}</td>
                <td className="mono text-[11.5px] text-[var(--color-mute)]">{t.token_prefix}…</td>
                <td className="text-[12px] text-[var(--color-mute)]">{t.created_by_email ?? '—'}</td>
                <td className="text-[12px] text-[var(--color-mute)]">{ago(t.last_used_at)}</td>
                <td><StatusChip tone={t.is_active ? 'good' : 'neutral'} label={t.is_active ? 'Active' : 'Revoked'} /></td>
                <td className="text-right">{t.is_active && <button onClick={() => revoke(t)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-bad)]"><Trash2 size={13} /> Revoke</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {connect && <ConnectionDialog onClose={() => setConnect(false)} />}
    </Card>
  )
}

function ConnectionDialog({ onClose }: { onClose: () => void }) {
  const q = useQuery({ queryKey: ['ingest-connection'], queryFn: () => api.get<Connection>('/v1/ingest/connection') })
  return (
    <Dialog title="Connection details" onClose={onClose} className="max-w-xl">
      {!q.data ? <div className="text-[13px] text-[var(--color-faint)]">Loading…</div> : (
        <div className="space-y-4 text-[13px] text-[var(--color-mute)]">
          <p className="m-0">Your system sends its token in the request’s authorisation header, as a bearer token.</p>
          <CopyRow label="1 · Check the token" value={q.data.check} />
          {q.data.books.map((b, i) => <CopyRow key={b.url} label={`${i + 2} · Send your ${b.label}`} value={b.url} />)}
          <p className="m-0">Send the rows as a list, in the template’s fields or in your own with a saved mapping. <a href="/docs" className="text-[var(--color-sky)] hover:underline">The full guide is in Documentation.</a></p>
        </div>
      )}
    </Dialog>
  )
}

// ── events sent to the organisation's own systems ────────────────────────────────────────────────────────────
interface EventType { type: string; label: string; name: string }
interface Endpoint { endpoint_id: string; name: string; url: string; events: string[]; event_names: string[]; is_active: boolean; last_delivery_at: string | null }
interface Delivery { delivery_id: string; event_type: string; event_name: string | null; status: string; http_status: number | null; endpoint_name: string | null; created_at: string | null }
const WEBHOOKS = {
  title: 'Notify your systems', sections: [
    { heading: HEADING.shows, body: 'Addresses of your governance, reporting or data systems that are told the moment something happens in your workspace, and the recent deliveries.' },
    { heading: HEADING.read, body: 'Each event is sent as a signed message; your system checks the signature with the secret shown once when the address is added. Choose the events to send, or none to send them all, and send a test to check the address.' },
    { heading: HEADING.limits, body: 'Delivery of files to your own file-transfer server is prepared and switched on on request: raise a request in Support.' },
  ],
}

function Webhooks() {
  const cat = useQuery({ queryKey: ['wh-events'], queryFn: () => api.get<{ events: EventType[] }>('/v1/webhooks/events') })
  const eps = useQuery({ queryKey: ['wh-endpoints'], queryFn: () => api.get<Endpoint[]>('/v1/webhooks') })
  const del = useQuery({ queryKey: ['wh-deliveries'], queryFn: () => api.get<Delivery[]>('/v1/webhooks/deliveries') })
  const [f, setF] = useState({ url: '', name: '', events: [] as string[] })
  const [busy, setBusy] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const create = async () => {
    setBusy(true)
    try { const r = await api.post<{ secret: string }>('/v1/webhooks', { url: f.url.trim(), name: f.name.trim(), events: f.events }); setSecret(r.secret); setF({ url: '', name: '', events: [] }); eps.refetch() }
    catch (e) { refused(e, 'The address could not be added.') } finally { setBusy(false) }
  }
  const revoke = async (e: Endpoint) => {
    if (!confirm(`Stop sending events to “${e.name}”?`)) return
    try { await api.del(`/v1/webhooks/${e.endpoint_id}`); eps.refetch() } catch (x) { refused(x, 'The address could not be revoked.') }
  }
  const test = async (e: Endpoint) => {
    try { const r = await api.post<{ status: string; http_status: number | null }>(`/v1/webhooks/${e.endpoint_id}/test`); const o = webhookTestOutcome(r); if (o.ok) toast.success(o.text); else toast.error(o.text); del.refetch(); eps.refetch() }
    catch (x) { refused(x, 'The test could not be sent.') }
  }
  const rows = eps.data ?? [], dels = (del.data ?? []).slice(0, 12)
  const delivered = dels.filter(d => d.status === 'delivered').length
  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SectionHead icon={Webhook} className="gap-1.5">Notify your systems <InfoButton compact details={WEBHOOKS} /></SectionHead>
        {dels.length > 0 && <span className="ml-auto text-[12.5px] text-[var(--color-mute)] tabular-nums">{delivered} of {dels.length} recent deliveries arrived</span>}
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        <Field label="Address"><input value={f.url} onChange={e => setF({ ...f, url: e.target.value })} placeholder="https://your-system.example.com/events" className={inp} /></Field>
        <Field label="Name"><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="A name, such as Governance listener" maxLength={80} className={inp} /></Field>
      </div>
      <div>
        <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Events — none chosen sends them all</div>
        <div className="flex flex-wrap gap-2">
          {(cat.data?.events ?? []).map(ev => {
            const on = f.events.includes(ev.type)
            return (
              <button key={ev.type} title={ev.label} aria-pressed={on} onClick={() => setF({ ...f, events: on ? f.events.filter(x => x !== ev.type) : [...f.events, ev.type] })}
                className={clsx('inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[12px] border transition', on ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>
                {on && <Check size={12} />}{ev.name}
              </button>
            )
          })}
        </div>
      </div>
      <Button onClick={create} disabled={busy || !f.url.trim() || f.name.trim().length < 2}><Webhook size={15} /> {busy ? 'Adding…' : 'Add address'}</Button>
      {secret && <ShownOnce title="Copy the signing secret now — it is shown only once." value={secret} />}
      {rows.length > 0 && (
        <div className="overflow-x-auto -mx-5">
          <table className="data-table w-full text-[13px]">
            <thead><tr><th>Address</th><th>Events</th><th>Last sent</th><th>Status</th><th></th></tr></thead>
            <tbody>{rows.map(e => (
              <tr key={e.endpoint_id}>
                <td><div className="text-[var(--color-ink)]">{e.name}</div><div className="text-[11.5px] text-[var(--color-faint)] break-all">{e.url}</div></td>
                <td className="text-[12px] text-[var(--color-mute)]">{e.event_names.length ? e.event_names.join(' · ') : 'All events'}</td>
                <td className="text-[12px] text-[var(--color-mute)]">{ago(e.last_delivery_at)}</td>
                <td><StatusChip tone={e.is_active ? 'good' : 'neutral'} label={e.is_active ? 'Active' : 'Revoked'} /></td>
                <td className="text-right whitespace-nowrap">{e.is_active && <>
                  <button onClick={() => test(e)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline mr-3"><Send size={12} /> Test</button>
                  <button onClick={() => revoke(e)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-bad)]"><Trash2 size={12} /> Revoke</button></>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {dels.length > 0 && (
        <div>
          <div className="text-[12.5px] text-[var(--color-ink)] mb-2">Recent deliveries</div>
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)] text-[12.5px]">
            {dels.map(d => (
              <li key={d.delivery_id} className="flex flex-wrap items-center gap-3 py-2">
                <span className="text-[var(--color-mute)]">{d.event_name ?? 'Another event'}</span>
                <span className="text-[var(--color-faint)]">{d.endpoint_name ?? '—'}</span>
                <StatusChip tone={d.status === 'delivered' ? 'good' : 'bad'} label={d.status === 'delivered' ? 'Arrived' : 'Did not arrive'} />
                {d.http_status != null && <span className="text-[11.5px] text-[var(--color-faint)] tabular-nums">answer {d.http_status}</span>}
                <span className="ml-auto text-[11.5px] text-[var(--color-faint)]">{ago(d.created_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

// ── systems of record a figure opens in ──────────────────────────────────────────────────────────────────────
interface System { key: string; name: string; kind: string; kind_label: string; deep_link_template: string; active: boolean }
const SOURCES = {
  title: 'Open a figure in your own system', sections: [
    { heading: HEADING.shows, body: 'Your systems of record — general ledger, core banking, loan origination, warehouse, mapping — so a person can open the record behind a figure in that system, from the asset’s panel.' },
    { heading: HEADING.read, body: 'Only the link is kept, never the record itself; the record opens under your own system’s sign-in. Write the link with {id} where the record’s number goes.' },
  ],
}

function SourceSystems() {
  const q = useQuery({ queryKey: ['source-systems'], queryFn: () => api.get<{ systems: System[]; kinds: { value: string; label: string }[] }>('/v1/source-systems') })
  const [f, setF] = useState({ key: '', name: '', kind: 'core_banking', deep_link_template: '' })
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try { await api.post('/v1/source-systems', f); toast.success(`${f.name} registered.`); setF({ key: '', name: '', kind: 'core_banking', deep_link_template: '' }); q.refetch() }
    catch (e) { refused(e, 'The system could not be registered.') } finally { setBusy(false) }
  }
  const systems = q.data?.systems ?? []
  return (
    <Card className="p-5 space-y-4">
      <SectionHead icon={ExternalLink} className="gap-1.5">Open a figure in your own system <InfoButton compact details={SOURCES} /></SectionHead>
      {systems.length > 0 && (
        <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)] border-y border-[var(--color-line)]">
          {systems.map(s => (
            <li key={s.key} className="flex flex-wrap items-center gap-3 py-2.5 text-[12.5px]">
              <span className="font-medium text-[var(--color-ink)]">{s.name}</span>
              <span className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{s.kind_label}</span>
              <span className="flex-1 min-w-0 text-[11.5px] text-[var(--color-faint)] truncate">{s.deep_link_template}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="grid sm:grid-cols-2 gap-3 max-w-3xl">
        <Field label="Name"><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Such as Finacle core banking" className={inp} /></Field>
        <Field label="Short name, letters and digits"><input value={f.key} onChange={e => setF({ ...f, key: e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '') })} className={inp} /></Field>
        <Field label="Kind">
          <select value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })} className={clsx(sel, 'w-full py-2')}>{(q.data?.kinds ?? []).map(k => <option key={k.value} value={k.value}>{k.label}</option>)}</select>
        </Field>
        <Field label="Link to a record"><input value={f.deep_link_template} onChange={e => setF({ ...f, deep_link_template: e.target.value })} placeholder="https://ledger.example.com/account/{id}" className={inp} /></Field>
      </div>
      <Button onClick={submit} disabled={busy || !f.key || !f.name || !f.deep_link_template}>{busy ? 'Registering…' : 'Register system'}</Button>
    </Card>
  )
}
