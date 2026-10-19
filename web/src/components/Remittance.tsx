import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileDown, Share2 } from 'lucide-react'
import clsx from 'clsx'
import { api, apiMessage, download } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Button, Card, SectionHead } from '../components/ui'
import { Dialog, CloseButton } from './Dialog'
import { StatusChip } from './StatusChip'
import { HEADING, InfoButton, messageDetails, type Message } from './Details'

// Governed remittance — an evidence pack shared onward to another authority, college or committee (UI standard,
// 2026-10-16). Three surfaces share these types: the issuing supervisor (dialog + list + access log + revoke), the
// supervised entity (where its case file went), and a supervisory body that received one in-product. Each share is a
// line with status chips; its purpose, legal basis, sections and fingerprints open in a pop-up.
export interface Remittance {
  remittance_id: string; regulator_org_id: string; supervised_org_id: string; pack_id: string; pack_version: number; reference: string
  recipient_kind: string; recipient_kind_label: string; recipient_name: string; recipient_org_id: string | null; recipient_org: string | null; recipient_email?: string | null
  purpose: string; legal_basis: { ref: string; act: string; url: string | null; stated: string | null }; sections: string[]; section_labels?: string[]
  content_sha256: string; pdf_sha256: string; watermark: string; expires_at: string; max_downloads: number | null; n_downloads: number
  created_at: string; created_by: string | null; revoked_at: string | null; revoked_by: string | null; revoke_reason: string | null
  status: 'active' | 'expired' | 'revoked' | 'exhausted'; regulator: string; entity: string
}
interface Config { recipient_kinds: Record<string, string>; default_expiry_days: number; max_expiry_days: number; default_max_downloads: number; sections: string[]
  section_labels?: Record<string, string>; bodies_on_tellumen: { org_id: string; name: string }[]; about?: Message }
// A case file's sections in customer words — the same words as the catalogue's case_file_section names, which the
// server prints in the pack and sends with every share (section_labels); tests/unit/test_supervisor_desk.py keeps the
// two identical. This copy serves the pages that read it directly (the bearer-link page, pages/Remit.tsx).
export const SECTION_LABEL: Record<string, string> = { identity: 'Entity identity', supervision: 'Supervision details', submissions: 'Submissions on record',
  plausibility: 'Quick check', lens: 'Full rebuild', projections: 'Projections', exposure: 'Exposure by region', peer_position: 'Peer position',
  engagement: 'Requests and findings', access_trail: 'Access trail', method: 'Method and basis' }
export const STATUS: Record<Remittance['status'], { label: string; color: string }> = {
  active: { label: 'Active', color: 'var(--color-good)' }, expired: { label: 'Expired', color: 'var(--color-faint)' },
  revoked: { label: 'Revoked', color: 'var(--color-bad)' }, exhausted: { label: 'Download limit reached', color: 'var(--color-warn)' } }
const TONE: Record<Remittance['status'], 'good' | 'neutral' | 'bad' | 'warn'> = { active: 'good', expired: 'neutral', revoked: 'bad', exhausted: 'warn' }
const shortDay = (s: string | null | undefined) => s ? new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
const lab = 'block text-[12px] text-[var(--color-mute)]'
const sectionsOf = (r: Remittance) => (r.section_labels ?? r.sections.map(s => SECTION_LABEL[s] ?? 'Other section')).join('; ')
const basisOf = (r: Remittance) => r.legal_basis.url
  ? <a href={r.legal_basis.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">{r.legal_basis.stated ?? r.legal_basis.ref} ↗</a>
  : r.legal_basis.stated ?? r.legal_basis.ref

// ── the remit dialog (supervisor) ───────────────────────────────────────────────────────────────────────────
export function RemitDialog({ orgId, packId, packVersion, onClose }: { orgId: string; packId: string; packVersion: number; onClose: () => void }) {
  const qc = useQueryClient()
  const cfg = useQuery({ queryKey: ['remit-config'], queryFn: () => api.get<Config>('/v1/supervisor/remittance/config') })
  const [kind, setKind] = useState('authority'); const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [body, setBody] = useState('')
  const [purpose, setPurpose] = useState(''); const [basis, setBasis] = useState(''); const [days, setDays] = useState<number | ''>(''); const [max, setMax] = useState<number | ''>('')
  const [sections, setSections] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false); const [done, setDone] = useState<{ reference: string; link: string; expires_at: string } | null>(null)
  const c = cfg.data
  const all = c?.sections ?? []
  const chosen = sections ?? all
  const toggle = (s: string) => setSections(chosen.includes(s) ? chosen.filter(x => x !== s) : [...chosen, s])
  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ reference: string; link: string; expires_at: string }>(`/v1/supervisor/entity/${orgId}/evidence-packs/${packId}/remit`, {
        recipient_kind: kind, recipient_name: name, recipient_email: email || null, recipient_org_id: body || null, purpose, legal_basis: basis || null,
        sections: chosen, expires_in_days: days === '' ? null : days, max_downloads: max === '' ? null : max })
      setDone(r); toast.success(`Shared under ${r.reference}.`)
      await qc.invalidateQueries({ queryKey: ['remittances', orgId] })
    } catch (e) { toast.error(apiMessage(e, 'Could not share the case file.')) } finally { setBusy(false) }
  }
  return (
    <Dialog bare title="Share this case file onward" onClose={onClose} className="w-full max-w-[640px] max-h-[92vh] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl">
      <CloseButton onClick={onClose} className="absolute top-4 right-4" />
      <div className="text-[12px] text-[var(--color-mute)]">Evidence pack, version {packVersion}</div>
      <div className="flex items-center gap-2 mb-4">
        <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">Share this case file onward</h2>
        {c?.about && <InfoButton compact details={messageDetails(c.about)} />}
      </div>
      {done ? (
        <div className="space-y-3">
          <div className="rounded-lg border border-[var(--color-good)]/40 bg-[var(--color-good)]/10 p-4 space-y-2">
            <div className="flex items-center gap-2 flex-wrap"><StatusChip label={`Shared · ${done.reference}`} tone="good" /><span className="text-[12px] text-[var(--color-mute)]">Expires {shortDay(done.expires_at)}</span></div>
            <div className="text-[12px] text-[var(--color-mute)]">The link is shown once.{email ? ` It was e-mailed to ${email}.` : ''}{body ? ' The receiving body also finds it in its workspace.' : ''}</div>
            <div className="flex items-center gap-2">
              <input readOnly value={done.link} aria-label="Link to the shared case file" className={clsx(inp, 'tabular-nums text-[11.5px]')} onFocus={e => e.currentTarget.select()} />
              <Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(done.link); toast.success('Link copied.') }}>Copy</Button>
            </div>
          </div>
          <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid sm:grid-cols-2 gap-3">
            <label className={lab}>Kind of recipient
              <select value={kind} onChange={e => setKind(e.target.value)} className={inp + ' mt-1'}>{Object.entries(c?.recipient_kinds ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
            <label className={lab}>Recipient's name
              <input value={name} onChange={e => setName(e.target.value)} placeholder="For example, the group's college" className={inp + ' mt-1'} /></label>
            <label className={lab}>Recipient's e-mail
              <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Receives the link" className={inp + ' mt-1'} /></label>
            <label className={lab}>Or a supervisory body on Tellumen
              <select value={body} onChange={e => setBody(e.target.value)} className={inp + ' mt-1'}><option value="">None</option>{(c?.bodies_on_tellumen ?? []).map(b => <option key={b.org_id} value={b.org_id}>{b.name}</option>)}</select></label>
          </div>
          <label className={lab}>Purpose
            <input value={purpose} onChange={e => setPurpose(e.target.value)} placeholder="Why the recipient needs it" className={inp + ' mt-1'} /></label>
          <label className={lab}>Legal basis <span className="text-[var(--color-faint)]">· optional; your supervisory powers by default</span>
            <input value={basis} onChange={e => setBasis(e.target.value)} placeholder="The provision you rely on" className={inp + ' mt-1'} /></label>
          <div>
            <div className={lab}>Sections <span className="text-[var(--color-faint)]">· the others print as withheld</span></div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-3 gap-y-1 mt-1">
              {all.map(s => <label key={s} className="flex items-center gap-2 text-[12px] text-[var(--color-ink)]"><input type="checkbox" checked={chosen.includes(s)} onChange={() => toggle(s)} disabled={s === 'identity'} />{c?.section_labels?.[s] ?? SECTION_LABEL[s] ?? 'Other section'}</label>)}
            </div>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className={lab}>Expires after (days)
              <input type="number" min={1} max={c?.max_expiry_days} value={days} onChange={e => setDays(e.target.value === '' ? '' : Number(e.target.value))} placeholder={c ? String(c.default_expiry_days) : ''} className={inp + ' mt-1'} /></label>
            <label className={lab}>Download limit <span className="text-[var(--color-faint)]">· empty for none</span>
              <input type="number" min={1} value={max} onChange={e => setMax(e.target.value === '' ? '' : Number(e.target.value))} placeholder={c ? String(c.default_max_downloads) : ''} className={inp + ' mt-1'} /></label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            <Button onClick={submit} disabled={busy || !name || !purpose || (!email && !body)}>{busy ? 'Sharing…' : 'Share'}</Button>
          </div>
        </div>
      )}
    </Dialog>
  )
}

// ── shares issued on one entity (supervisor) ────────────────────────────────────────────────────────────────
interface Access { at: string; action_label: string | null; outcome: string; outcome_label: string | null; actor: string | null; actor_org: string | null; ip: string | null }
function ShareDetail({ r, onClose }: { r: Remittance; onClose: () => void }) {
  const q = useQuery({ queryKey: ['remittance-log', r.remittance_id], queryFn: () => api.get<{ accesses: Access[] }>(`/v1/supervisor/remittances/${r.remittance_id}/access-log`) })
  const rows = q.data?.accesses ?? []
  const fact = (k: string, v: React.ReactNode) => <div className="contents"><dt className="text-[var(--color-mute)]">{k}</dt><dd className="m-0 min-w-0 text-[var(--color-ink)] break-words">{v}</dd></div>
  return (
    <Dialog title={`${r.reference} · ${r.recipient_name}`} onClose={onClose} className="sm:max-w-2xl">
      <div className="space-y-5">
        <div className="flex flex-wrap gap-2"><StatusChip label={STATUS[r.status].label} tone={TONE[r.status]} /><StatusChip label={r.recipient_kind_label} tone="neutral" /></div>
        <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
          {fact('Purpose', r.purpose)}{fact('Legal basis', basisOf(r))}{fact('Sections', sectionsOf(r))}
          {fact('Issued', `${shortDay(r.created_at)} · ${r.created_by ?? 'your authority'}`)}{fact('Expires', shortDay(r.expires_at))}
          {fact('Downloads', `${r.n_downloads}${r.max_downloads ? ` of ${r.max_downloads}` : ''}`)}
          {r.revoked_at && fact('Revoked', `${shortDay(r.revoked_at)} · ${r.revoked_by ?? 'your authority'}${r.revoke_reason ? ` · ${r.revoke_reason}` : ''}`)}
          {fact('Content fingerprint', <span className="tabular-nums text-[11.5px] break-all">{r.content_sha256}</span>)}
          {fact('Document fingerprint', <span className="tabular-nums text-[11.5px] break-all">{r.pdf_sha256}</span>)}
        </dl>
        <div>
          <div className="text-[12px] text-[var(--color-mute)] mb-1.5">Every view and download</div>
          {q.isLoading ? <div className="text-[12px] text-[var(--color-faint)]">Loading…</div> : rows.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">Not opened yet.</div> : (
            <div className="overflow-x-auto"><table className="data-table w-full text-[12px]"><thead><tr><th>When</th><th>What</th><th>Result</th><th>Who</th></tr></thead>
              <tbody>{rows.map((a, i) => <tr key={i}><td className="tabular-nums whitespace-nowrap">{new Date(a.at).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' })}</td>
                <td>{a.action_label ?? 'Access'}</td><td><StatusChip label={a.outcome_label ?? undefined} tone={a.outcome === 'ok' ? 'good' : 'warn'} /></td>
                <td>{a.actor ? `${a.actor}${a.actor_org ? ` · ${a.actor_org}` : ''}` : 'Holder of the link'}</td></tr>)}</tbody></table></div>)}
        </div>
      </div>
    </Dialog>
  )
}

function Revoke({ r, onDone, onClose }: { r: Remittance; onDone: () => Promise<unknown>; onClose: () => void }) {
  const [why, setWhy] = useState(''); const [busy, setBusy] = useState(false)
  const go = async () => {
    setBusy(true)
    try { await api.post(`/v1/supervisor/remittances/${r.remittance_id}/revoke`, { reason: why || null }); toast.success(`${r.reference} revoked.`); await onDone(); onClose() }
    catch (e) { toast.error(apiMessage(e, 'Could not revoke.')) } finally { setBusy(false) }
  }
  return (
    <Dialog title={`Revoke ${r.reference}?`} onClose={onClose} className="sm:max-w-md">
      <div className="space-y-3">
        <p className="text-[13px] text-[var(--color-mute)] m-0">{r.recipient_name}'s link stops working at once.</p>
        <label className={lab}>Reason <span className="text-[var(--color-faint)]">· optional</span><input value={why} onChange={e => setWhy(e.target.value)} className={inp + ' mt-1'} /></label>
        <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={go} disabled={busy}>Revoke</Button></div>
      </div>
    </Dialog>
  )
}

export function RemittancesIssued({ orgId }: { orgId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const perms = profile?.permissions ?? []
  const can = perms.includes('supervisor.evidence.export'); const canRemit = perms.includes('supervisor.remit')
  const q = useQuery({ queryKey: ['remittances', orgId], enabled: can, queryFn: () => api.get<{ remittances: Remittance[] }>(`/v1/supervisor/entity/${orgId}/remittances`) })
  const [open, setOpen] = useState<Remittance | null>(null)
  const [revoking, setRevoking] = useState<Remittance | null>(null)
  const [all, setAll] = useState(false)
  if (!can) return null
  const rows = q.data?.remittances ?? []
  if (rows.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead icon={Share2} hint="scoped, watermarked, time-limited">Shared onward</SectionHead>
      <div className="overflow-x-auto mt-2">
        <table className="data-table w-full text-[12.5px]">
          <thead><tr><th>Shared with</th><th>Status</th><th>Issued</th><th>Expires</th><th>Downloads</th><th /></tr></thead>
          <tbody>{(all ? rows : rows.slice(0, 5)).map(r => (
            <tr key={r.remittance_id}>
              <td><span className="text-[var(--color-ink)]">{r.recipient_name}</span><span className="block text-[11px] text-[var(--color-faint)]">{r.recipient_kind_label} · {r.reference}</span></td>
              <td><StatusChip label={STATUS[r.status].label} tone={TONE[r.status]} /></td>
              <td className="tabular-nums">{shortDay(r.created_at)}</td>
              <td className="tabular-nums">{shortDay(r.expires_at)}</td>
              <td className="tabular-nums">{r.n_downloads}{r.max_downloads ? ` of ${r.max_downloads}` : ''}</td>
              <td className="whitespace-nowrap text-right"><button type="button" onClick={() => setOpen(r)} className="text-[var(--color-sky)] hover:underline">Details</button>
                {canRemit && r.status === 'active' && <button type="button" onClick={() => setRevoking(r)} className="ml-3 text-[var(--color-bad)] hover:underline">Revoke</button>}</td>
            </tr>))}</tbody>
        </table>
      </div>
      {rows.length > 5 && <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">{all ? 'Show fewer' : `Show all ${rows.length}`}</button>}
      {open && <ShareDetail r={open} onClose={() => setOpen(null)} />}
      {revoking && <Revoke r={revoking} onClose={() => setRevoking(null)} onDone={() => qc.invalidateQueries({ queryKey: ['remittances', orgId] })} />}
    </Card>
  )
}

// ── what the supervised entity sees ─────────────────────────────────────────────────────────────────────────
// Status counts and one line per share; the purpose, legal basis and sections of each share, and what a remittance is,
// open in pop-ups.
export function SharedOnward() {
  const q = useQuery({ queryKey: ['my-remittances'], queryFn: () => api.get<{ remittances: Remittance[]; about: Message }>('/v1/me/supervisors/remittances') })
  const [all, setAll] = useState(false)
  const rows = q.data?.remittances ?? []
  if (rows.length === 0) return null
  const counts = (Object.keys(STATUS) as Remittance['status'][]).map(s => [s, rows.filter(r => r.status === s).length] as const).filter(([, n]) => n > 0)
  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <SectionHead icon={Share2}>Shared onward by your supervisor</SectionHead>
        {q.data?.about && <InfoButton compact details={messageDetails(q.data.about)} />}
        <span className="ml-auto flex flex-wrap gap-1.5">{counts.map(([s, n]) => <StatusChip key={s} label={`${STATUS[s].label} · ${n}`} tone={TONE[s]} />)}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="data-table w-full text-[12.5px]">
          <thead><tr><th>Shared with</th><th>Status</th><th>Issued</th><th>Expires</th><th>Downloads</th><th /></tr></thead>
          <tbody>{(all ? rows : rows.slice(0, 6)).map(r => (
            <tr key={r.remittance_id}>
              <td><span className="text-[var(--color-ink)]">{r.recipient_name}</span><span className="block text-[11px] text-[var(--color-faint)]">{r.recipient_kind_label}</span></td>
              <td><StatusChip label={STATUS[r.status].label} tone={TONE[r.status]} /></td>
              <td className="tabular-nums">{shortDay(r.created_at)}</td>
              <td className="tabular-nums">{shortDay(r.expires_at)}</td>
              <td className="tabular-nums">{r.n_downloads}{r.max_downloads ? ` of ${r.max_downloads}` : ''}</td>
              <td><InfoButton compact details={{ title: r.recipient_name, sections: [
                { heading: 'Reference', body: `${r.reference} · shared by ${r.regulator}` },
                { heading: 'Purpose', body: r.purpose },
                { heading: 'Legal basis', body: basisOf(r) },
                { heading: 'Sections shared', body: sectionsOf(r) },
                ...(r.revoked_at ? [{ heading: 'Revoked', body: shortDay(r.revoked_at) }] : []),
              ] }} /></td>
            </tr>))}</tbody>
        </table>
      </div>
      {rows.length > 6 && <button type="button" onClick={() => setAll(!all)} className="text-[12px] text-[var(--color-sky)] hover:underline">{all ? 'Show fewer' : `Show all ${rows.length}`}</button>}
    </Card>
  )
}

// ── what a supervisory body received in-product ─────────────────────────────────────────────────────────────
export function RemittancesReceived() {
  const q = useQuery({ queryKey: ['remittances-received'], queryFn: () => api.get<{ remittances: Remittance[] }>('/v1/supervisor/remittances/received') })
  const rows = q.data?.remittances ?? []
  if (rows.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead icon={Share2} hint="read-only, from other authorities">Case files shared with you</SectionHead>
      <div className="divide-y divide-[var(--color-line)] mt-2">{rows.map(r => (
        <div key={r.remittance_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
          <span className="text-[var(--color-ink)] mr-auto">{r.entity} <span className="text-[var(--color-faint)]">· from {r.regulator}</span></span>
          <StatusChip label={STATUS[r.status].label} tone={TONE[r.status]} />
          <span className="text-[var(--color-faint)] tabular-nums">until {shortDay(r.expires_at)}</span>
          <InfoButton compact details={{ title: `${r.reference} · ${r.entity}`, sections: [
            { heading: 'Purpose', body: r.purpose }, { heading: 'Legal basis', body: basisOf(r) }, { heading: 'Sections shared', body: sectionsOf(r) },
            { heading: HEADING.limits, body: 'Read-only and watermarked; every download is recorded on the issuing authority’s and the entity’s audit trails.' },
          ] }} />
          {r.status === 'active' && <span className="flex gap-3">
            <button type="button" onClick={() => download(`/v1/supervisor/remittances/received/${r.remittance_id}.pdf`, `remittance-${r.reference}.pdf`)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><FileDown size={13} />PDF</button>
            <button type="button" onClick={() => download(`/v1/supervisor/remittances/received/${r.remittance_id}.json`, `remittance-${r.reference}.json`)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><FileDown size={13} />Data</button></span>}
        </div>))}</div>
      <div className="text-[11.5px] text-[var(--color-faint)] mt-2">These entities are not in your population. <Link to="/supervised" className="text-[var(--color-sky)] hover:underline">Your population →</Link></div>
    </Card>
  )
}
