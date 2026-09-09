import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Button, Card, SectionHead } from '../components/ui'

// Governed remittance — an evidence pack shared onward to another authority, college or committee.
// Three surfaces share these types: the issuing supervisor (dialog + list + access log + revoke), the supervised
// entity (where its case file went), and a supervisory body that received one in-product.
export interface Remittance {
  remittance_id: string; regulator_org_id: string; supervised_org_id: string; pack_id: string; pack_version: number; reference: string
  recipient_kind: string; recipient_kind_label: string; recipient_name: string; recipient_org_id: string | null; recipient_org: string | null; recipient_email?: string | null
  purpose: string; legal_basis: { ref: string; act: string; url: string | null; stated: string | null }; sections: string[]
  content_sha256: string; pdf_sha256: string; watermark: string; expires_at: string; max_downloads: number | null; n_downloads: number
  created_at: string; created_by: string | null; revoked_at: string | null; revoked_by: string | null; revoke_reason: string | null
  status: 'active' | 'expired' | 'revoked' | 'exhausted'; regulator: string; entity: string
}
interface Config { recipient_kinds: Record<string, string>; default_expiry_days: number; max_expiry_days: number; default_max_downloads: number; sections: string[]
  bodies_on_tellumen: { org_id: string; name: string }[]; notice: string }
export const SECTION_LABEL: Record<string, string> = { identity: 'Entity identity', supervision: 'Supervision details', submissions: 'Submissions on record', plausibility: 'Tier 1 plausibility',
  lens: 'Tier 2 independent lens', projections: 'Projections', exposure: 'Exposure (regional)', peer_position: 'Peer position', engagement: 'Requests and findings', access_trail: 'Access trail', method: 'Method and basis' }
export const STATUS: Record<Remittance['status'], { label: string; color: string }> = {
  active: { label: 'Active', color: 'var(--color-good)' }, expired: { label: 'Expired', color: 'var(--color-faint)' },
  revoked: { label: 'Revoked', color: 'var(--color-bad)' }, exhausted: { label: 'Download limit reached', color: 'var(--color-warn)' } }
const dt = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

// ── the remit dialog (supervisor) ───────────────────────────────────────────────────────────────────────────
export function RemitDialog({ orgId, packId, packVersion, onClose }: { orgId: string; packId: string; packVersion: number; onClose: () => void }) {
  const qc = useQueryClient()
  const cfg = useQuery({ queryKey: ['remit-config'], queryFn: () => api.get<Config>('/v1/supervisor/remittance/config') })
  const [kind, setKind] = useState('authority'); const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [body, setBody] = useState('')
  const [purpose, setPurpose] = useState(''); const [basis, setBasis] = useState(''); const [days, setDays] = useState<number | ''>(''); const [max, setMax] = useState<number | ''>('')
  const [sections, setSections] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false); const [done, setDone] = useState<{ reference: string; link: string; expires_at: string; pdf_sha256: string } | null>(null)
  const c = cfg.data
  const all = c?.sections ?? []
  const chosen = sections ?? all
  const toggle = (s: string) => setSections(chosen.includes(s) ? chosen.filter(x => x !== s) : [...chosen, s])
  const submit = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ reference: string; link: string; expires_at: string; pdf_sha256: string }>(`/v1/supervisor/entity/${orgId}/evidence-packs/${packId}/remit`, {
        recipient_kind: kind, recipient_name: name, recipient_email: email || null, recipient_org_id: body || null, purpose, legal_basis: basis || null,
        sections: chosen, expires_in_days: days === '' ? null : days, max_downloads: max === '' ? null : max })
      setDone(r); toast.success(`Remitted under ${r.reference}.`)
      await qc.invalidateQueries({ queryKey: ['remittances', orgId] })
    } catch (e) { toast.error((e as Error).message || 'Could not remit the pack.') } finally { setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[640px] max-h-[92vh] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Governed remittance · evidence pack v{packVersion}</div>
        <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">Remit this case file onward</h2>
        <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-4">{c?.notice ?? 'The recipient gets a scoped, watermarked, time-limited copy under a link that you can revoke; every access is logged and the entity sees the remittance on its audit trail.'}</p>
        {done ? (
          <div className="space-y-3">
            <div className="rounded-lg border border-[var(--color-good)]/40 bg-[var(--color-good)]/10 p-4">
              <div className="text-[13px] font-medium text-[var(--color-ink)]">Issued · <span className="mono">{done.reference}</span></div>
              <div className="text-[12px] text-[var(--color-mute)] mt-1">Expires {dt(done.expires_at)} · document hash <span className="mono text-[10.5px]">{done.pdf_sha256.slice(0, 16)}…</span></div>
              <div className="text-[11.5px] text-[var(--color-mute)] mt-3">The link below is shown once. {email ? `It has been e-mailed to ${email}.` : ''}{body ? ' The receiving body also sees it under Remittances received.' : ''}</div>
              <div className="mt-2 flex items-center gap-2">
                <input readOnly value={done.link} className={inp + ' mono text-[11px]'} onFocus={e => e.currentTarget.select()} />
                <Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(done.link); toast.success('Link copied.') }}>Copy</Button>
              </div>
            </div>
            <div className="flex justify-end"><Button onClick={onClose}>Done</Button></div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Recipient kind
                <select value={kind} onChange={e => setKind(e.target.value)} className={inp + ' mt-1'}>{Object.entries(c?.recipient_kinds ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Recipient name
                <input value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Supervisory college · Group X" className={inp + ' mt-1'} /></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Recipient e-mail
                <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Receives the link" className={inp + ' mt-1'} /></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Or a supervisory body on Tellumen
                <select value={body} onChange={e => setBody(e.target.value)} className={inp + ' mt-1'}><option value="">— none —</option>{(c?.bodies_on_tellumen ?? []).map(b => <option key={b.org_id} value={b.org_id}>{b.name}</option>)}</select></label>
            </div>
            <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Purpose
              <input value={purpose} onChange={e => setPurpose(e.target.value)} placeholder="Why this recipient needs the case file" className={inp + ' mt-1'} /></label>
            <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Legal basis (optional; the sector's supervisory powers are cited by default)
              <input value={basis} onChange={e => setBasis(e.target.value)} placeholder="e.g. Art. 116 CRD — college of supervisors" className={inp + ' mt-1'} /></label>
            <div>
              <div className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1">Sections included <span className="normal-case tracking-normal">— the rest print as withheld</span></div>
              <div className="grid grid-cols-3 gap-x-3 gap-y-1">
                {all.map(s => <label key={s} className="flex items-center gap-2 text-[12px] text-[var(--color-ink)]"><input type="checkbox" checked={chosen.includes(s)} onChange={() => toggle(s)} disabled={s === 'identity'} />{SECTION_LABEL[s] ?? s}</label>)}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Expires in days (default {c?.default_expiry_days ?? 30}, at most {c?.max_expiry_days ?? 180})
                <input type="number" min={1} max={c?.max_expiry_days ?? 180} value={days} onChange={e => setDays(e.target.value === '' ? '' : Number(e.target.value))} className={inp + ' mt-1'} /></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Download limit (blank = unlimited)
                <input type="number" min={1} value={max} onChange={e => setMax(e.target.value === '' ? '' : Number(e.target.value))} placeholder={String(c?.default_max_downloads ?? 5)} className={inp + ' mt-1'} /></label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="ghost" onClick={onClose}>Cancel</Button>
              <Button onClick={submit} disabled={busy || !name || !purpose || (!email && !body)}>{busy ? 'Issuing…' : 'Issue remittance'}</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── remittances issued on one entity (supervisor) ───────────────────────────────────────────────────────────
interface Access { at: string; action: string; outcome: string; ip: string | null; user_agent: string | null; actor: string | null; actor_org: string | null }
function AccessLog({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['remittance-log', id], queryFn: () => api.get<{ accesses: Access[] }>(`/v1/supervisor/remittances/${id}/access-log`) })
  const rows = q.data?.accesses ?? []
  if (q.isLoading) return <div className="text-[11.5px] text-[var(--color-faint)] py-1">loading the access log…</div>
  if (rows.length === 0) return <div className="text-[11.5px] text-[var(--color-faint)] py-1">Not opened yet.</div>
  return (
    <div className="overflow-x-auto"><table className="data-table text-[11.5px]"><thead><tr><th>When</th><th>Action</th><th>Outcome</th><th>Who</th><th>From</th></tr></thead>
      <tbody>{rows.map((a, i) => <tr key={i}><td className="mono">{dt(a.at)}</td><td>{a.action.replace('_', ' ')}</td><td style={{ color: a.outcome === 'ok' ? 'var(--color-good)' : 'var(--color-warn)' }}>{a.outcome}</td>
        <td>{a.actor ? `${a.actor}${a.actor_org ? ` · ${a.actor_org}` : ''}` : 'link holder'}</td><td className="mono text-[10.5px] text-[var(--color-faint)]">{a.ip ?? '—'}</td></tr>)}</tbody></table></div>
  )
}
export function RemittancesIssued({ orgId }: { orgId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const perms = profile?.permissions ?? []
  const can = perms.includes('supervisor.evidence.export'); const canRemit = perms.includes('supervisor.remit')
  const q = useQuery({ queryKey: ['remittances', orgId], enabled: can, queryFn: () => api.get<{ remittances: Remittance[] }>(`/v1/supervisor/entity/${orgId}/remittances`) })
  const [open, setOpen] = useState<string | null>(null)
  if (!can) return null
  const rows = q.data?.remittances ?? []
  if (rows.length === 0) return null
  const revoke = async (r: Remittance) => {
    const reason = window.prompt(`Revoke ${r.reference} to ${r.recipient_name}? The link stops working at once. Reason (optional):`)
    if (reason === null) return
    try { await api.post(`/v1/supervisor/remittances/${r.remittance_id}/revoke`, { reason }); toast.success(`${r.reference} revoked.`); await qc.invalidateQueries({ queryKey: ['remittances', orgId] }) }
    catch (e) { toast.error((e as Error).message || 'Could not revoke.') }
  }
  return (
    <Card className="p-5">
      <div className="text-[13px] font-medium text-[var(--color-ink)]">Remittances</div>
      <div className="text-[11.5px] text-[var(--color-mute)] mb-2">Case files on this entity shared onward under a governed share. Each is scoped, watermarked and time-limited; you can revoke it at any time, and every view and download is logged here and on the entity's audit trail.</div>
      <div className="divide-y divide-[var(--color-line)]">{rows.map(r => (
        <div key={r.remittance_id} className="py-2 text-[12.5px]">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="mono text-[11px] text-[var(--color-ink)]">{r.reference}</span>
            <span className="text-[var(--color-ink)]">{r.recipient_name} <span className="text-[var(--color-faint)]">· {r.recipient_kind_label}{r.recipient_org ? ' · on Tellumen' : ''}</span></span>
            <span className="text-[var(--color-mute)]">{r.purpose}</span>
            <span className="mono text-[10.5px]" style={{ color: STATUS[r.status].color }}>{STATUS[r.status].label}</span>
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">pack v{r.pack_version} · {r.sections.length}/{Object.keys(SECTION_LABEL).length} sections · expires {r.expires_at.slice(0, 10)} · {r.n_downloads}{r.max_downloads ? `/${r.max_downloads}` : ''} downloads</span>
            <button onClick={() => setOpen(open === r.remittance_id ? null : r.remittance_id)} className="text-[var(--color-sky)] hover:underline">{open === r.remittance_id ? 'Hide log' : 'Access log'}</button>
            {canRemit && r.status === 'active' && <button onClick={() => revoke(r)} className="text-[var(--color-bad)] hover:underline">Revoke</button>}
          </div>
          {r.revoked_at && <div className="mono text-[10.5px] text-[var(--color-bad)] mt-0.5">revoked {dt(r.revoked_at)} by {r.revoked_by ?? '—'}{r.revoke_reason ? ` · ${r.revoke_reason}` : ''}</div>}
          {open === r.remittance_id && <div className="mt-2 pl-2 border-l-2 border-[var(--color-line)]">
            <div className="mono text-[10.5px] text-[var(--color-faint)] mb-1">legal basis {r.legal_basis.stated ?? r.legal_basis.ref} · content {r.content_sha256.slice(0, 12)}… · document {r.pdf_sha256.slice(0, 12)}… · issued {dt(r.created_at)} by {r.created_by ?? '—'}</div>
            <AccessLog id={r.remittance_id} /></div>}
        </div>))}</div>
    </Card>
  )
}

// ── what the supervised entity sees ─────────────────────────────────────────────────────────────────────────
export function SharedOnward() {
  const q = useQuery({ queryKey: ['my-remittances'], queryFn: () => api.get<{ remittances: Remittance[]; note: string }>('/v1/me/supervisors/remittances') })
  const rows = q.data?.remittances ?? []
  if (rows.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead hint="every remittance of your case file · also on your audit trail">Shared onward by your supervisors</SectionHead>
      <div className="text-[12.5px] text-[var(--color-mute)] mb-3">{q.data?.note}</div>
      <div className="divide-y divide-[var(--color-line)]">{rows.map(r => (
        <div key={r.remittance_id} className="py-2 text-[12.5px]">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="mono text-[11px] text-[var(--color-ink)]">{r.reference}</span>
            <span className="text-[var(--color-ink)]">{r.regulator} → {r.recipient_name} <span className="text-[var(--color-faint)]">· {r.recipient_kind_label}</span></span>
            <span className="mono text-[10.5px]" style={{ color: STATUS[r.status].color }}>{STATUS[r.status].label}</span>
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">issued {r.created_at.slice(0, 10)} · expires {r.expires_at.slice(0, 10)} · {r.n_downloads} download{r.n_downloads === 1 ? '' : 's'}</span>
          </div>
          <div className="text-[11.5px] text-[var(--color-mute)] mt-0.5">Purpose: {r.purpose} · Legal basis: {r.legal_basis.stated ?? r.legal_basis.ref} · Sections: {r.sections.map(s => SECTION_LABEL[s] ?? s).join(', ')}</div>
        </div>))}</div>
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
      <div className="text-[13px] font-medium text-[var(--color-ink)]">Remittances received</div>
      <div className="text-[11.5px] text-[var(--color-mute)] mb-2">Case files other authorities have shared with this body. Each is scoped to the sections listed, watermarked, and open until its expiry or revocation; every download is logged on the issuing authority's and the entity's audit trails.</div>
      <div className="divide-y divide-[var(--color-line)]">{rows.map(r => (
        <div key={r.remittance_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
          <span className="mono text-[11px] text-[var(--color-ink)]">{r.reference}</span>
          <span className="text-[var(--color-ink)]">{r.entity} <span className="text-[var(--color-faint)]">· from {r.regulator}</span></span>
          <span className="text-[var(--color-mute)]">{r.purpose}</span>
          <span className="mono text-[10.5px]" style={{ color: STATUS[r.status].color }}>{STATUS[r.status].label}</span>
          <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">{r.sections.map(s => SECTION_LABEL[s] ?? s).join(', ')} · expires {r.expires_at.slice(0, 10)}</span>
          {r.status === 'active' && <span className="flex gap-3">
            <button onClick={() => download(`/v1/supervisor/remittances/received/${r.remittance_id}.pdf`, `remittance-${r.reference}.pdf`)} className="text-[var(--color-sky)] hover:underline">PDF ↓</button>
            <button onClick={() => download(`/v1/supervisor/remittances/received/${r.remittance_id}.json`, `remittance-${r.reference}.json`)} className="text-[var(--color-sky)] hover:underline">JSON ↓</button></span>}
        </div>))}</div>
      <div className="text-[11px] text-[var(--color-faint)] mt-2">A remittance is read-only: the entity is not in your population. <Link to="/supervised" className="text-[var(--color-sky)] hover:underline">Your population →</Link></div>
    </Card>
  )
}
