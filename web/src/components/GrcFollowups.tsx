import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead } from '../components/ui'

const dt = (s: string | null | undefined) => s ? s.slice(0, 16).replace('T', ' ') : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

// ── 1 appetite version history ──────────────────────────────────────────────────────────────────────────────
interface Ver { framework: string; kri_key: string; version: number; amber: number | null; red: number | null; direction: string | null; previous: Record<string, unknown> | null; reason: string | null; created_at: string; changed_by: string | null; approved_by: string | null; approval_request_id: string | null }
export function AppetiteHistory({ framework }: { framework: string | undefined }) {
  const q = useQuery({ queryKey: ['kri-appetite-history', framework], enabled: !!framework, queryFn: () => api.get<{ versions: Ver[] }>(`/v1/admin/kri-appetite/history?framework=${framework}`) })
  const rows = q.data?.versions ?? []
  if (!framework || rows.length === 0) return null
  return (
    <div className="px-4 py-3 border-t border-[var(--color-line)]">
      <div className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Appetite statement · change history</div>
      <div className="divide-y divide-[var(--color-line)]">{rows.slice(0, 12).map(v => (
        <div key={`${v.kri_key}-${v.version}`} className="py-1.5 text-[12px] flex items-center gap-3 flex-wrap">
          <span className="mono text-[10.5px] text-[var(--color-faint)]">{dt(v.created_at)}</span>
          <span className="text-[var(--color-ink)]">{v.kri_key} <span className="mono text-[10px] text-[var(--color-faint)]">v{v.version}</span></span>
          <span className="mono text-[11px]">amber {v.amber ?? '—'} · red {v.red ?? '—'} · {v.direction === 'lower_worse' ? 'lower is worse' : 'higher is worse'}</span>
          {v.previous && <span className="mono text-[10px] text-[var(--color-faint)]">was amber {String((v.previous as { amber?: unknown }).amber ?? '—')} · red {String((v.previous as { red?: unknown }).red ?? '—')}</span>}
          <span className="text-[var(--color-mute)] ml-auto">{v.changed_by ?? '—'}{v.approved_by ? ` · approved by ${v.approved_by}` : ''}{v.reason ? ` · “${v.reason}”` : ''}</span>
        </div>))}</div>
    </div>
  )
}

// ── 3 what applies to me and why ────────────────────────────────────────────────────────────────────────────
interface Check { label: string; attribute: string; result: boolean | null; tier?: string }
interface Mandate { id: string; title: string; act: { name: string; url: string }; article: { ref: string; excerpt?: string }; status: string; tier: { label: string; frequency?: string } | null
  missing: string[]; failed: string[]; checks: Check[]; deliverable: { framework: string | null; label: string | null; channel: string | null; due: string | null }; latest_version: string | null }
interface AppResp { mandates: Mandate[]; summary: { applies: number; cannot_determine: number; not_applicable: number }; note: string; definitions: Record<string, { label: string }> }
const ST: Record<string, { label: string; color: string }> = { applies: { label: 'Applies', color: 'var(--color-good)' }, cannot_determine: { label: 'Cannot determine', color: 'var(--color-warn)' }, not_applicable: { label: 'Not applicable', color: 'var(--color-faint)' } }
export function WhatApplies() {
  const q = useQuery({ queryKey: ['my-mandates'], queryFn: () => api.get<AppResp>('/v1/me/supervisors/mandates') })
  const [open, setOpen] = useState<string | null>(null)
  const d = q.data
  if (!d || d.mandates.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead hint={`${d.summary.applies} apply · ${d.summary.cannot_determine} cannot determine · ${d.summary.not_applicable} not applicable`}>What applies to you, and why</SectionHead>
      <div className="text-[12.5px] text-[var(--color-mute)] mb-3">{d.note}</div>
      <div className="divide-y divide-[var(--color-line)]">{d.mandates.map(m => (
        <div key={m.id} className="py-2.5 text-[12.5px]">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="font-medium" style={{ color: (ST[m.status] ?? ST.not_applicable).color }}>{(ST[m.status] ?? ST.not_applicable).label}</span>
            <span className="text-[var(--color-ink)]">{m.title}</span>
            <a href={m.act.url} target="_blank" rel="noreferrer" className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">{m.article.ref}</a>
            {m.tier && <span className="mono text-[10.5px] text-[var(--color-faint)]">{m.tier.label}{m.tier.frequency ? ` · ${m.tier.frequency}` : ''}</span>}
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">{m.deliverable.label ?? m.deliverable.framework ?? ''}{m.deliverable.channel ? ` · via ${m.deliverable.channel}` : ''}{m.deliverable.due ? ` · due ${m.deliverable.due}` : ''}</span>
            <button onClick={() => setOpen(open === m.id ? null : m.id)} className="text-[var(--color-sky)] hover:underline">{open === m.id ? 'Hide' : 'Why'}</button>
          </div>
          {m.missing.length > 0 && <div className="text-[11.5px] text-[var(--color-warn)] mt-0.5">Cannot determine until you state: {m.missing.map(a => d.definitions[a]?.label ?? a).join(', ')} (Regulatory attributes above).</div>}
          {open === m.id && <ul className="mt-1.5 pl-4 m-0 space-y-0.5 text-[12px]">{m.checks.map((c, i) => (
            <li key={i} style={{ color: c.result === true ? 'var(--color-good)' : c.result === false ? 'var(--color-bad)' : 'var(--color-warn)' }}>{c.result === true ? '✓' : c.result === false ? '✗' : '?'} {c.label}{c.tier ? <span className="text-[var(--color-faint)]"> · {c.tier}</span> : null}</li>))}
            {m.article.excerpt && <li className="text-[var(--color-mute)] list-none -ml-4 mt-1 italic">“{m.article.excerpt.slice(0, 220)}{m.article.excerpt.length > 220 ? '…' : ''}”</li>}</ul>}
        </div>))}</div>
    </Card>
  )
}

// ── 2 what a change touches ─────────────────────────────────────────────────────────────────────────────────
interface Links { framework: string; switches: { key: string; label: string }[]; kris: { key: string; datapoint: string; tier: string }[]; template: { official_form: string | null; form_url: string | null; authority: string | null } | null; mandates: { id: string; title: string; article: string | null }[]; n: number }
interface Impact { changes: (Links & { celex: string; title: string; summary: string | null; effective_date: string | null; status: string; url: string; detected_at: string; touches: Links; task_id: string | null })[]; frameworks: string[]; links: Record<string, Links>; note: string }
function LinkChips({ L }: { L: Links }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-[11px]">
      {L.switches.map(s => <Link key={s.key} to="/admin?tab=Approvals" className="px-2 py-0.5 rounded-full border border-[var(--color-warn)]/50 text-[var(--color-warn)] hover:underline" title="interpretation switch">⚙ {s.label}</Link>)}
      {L.kris.map(k => <Link key={k.key} to="/kri" className={`px-2 py-0.5 rounded-full border ${k.tier === 'core' ? 'border-[var(--color-sky)]/60 text-[var(--color-sky)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'} hover:underline`} title={`KRI · ${k.tier}`}>{k.datapoint}</Link>)}
      {L.template?.official_form && <a href={L.template.form_url ?? '#'} target="_blank" rel="noreferrer" className="px-2 py-0.5 rounded-full border border-[var(--color-good)]/50 text-[var(--color-good)] hover:underline" title="official template">▤ {L.template.official_form}</a>}
      {L.mandates.map(m => <Link key={m.id} to="/reg-changes" className="px-2 py-0.5 rounded-full border border-[var(--color-line-2)] text-[var(--color-ink)]" title="mandate in the registry">§ {m.article ?? m.title}</Link>)}
    </div>
  )
}
export function ChangeImpact() {
  const q = useQuery({ queryKey: ['reg-impact'], queryFn: () => api.get<Impact>('/v1/reg-changes/impact') })
  const d = q.data
  if (!d) return null
  return (
    <Card className="p-5">
      <SectionHead hint="switches · KRI datapoints · template · mandates">What a change touches</SectionHead>
      <div className="text-[12.5px] text-[var(--color-mute)] mb-3">{d.note}</div>
      {d.changes.length > 0 ? (
        <div className="divide-y divide-[var(--color-line)] mb-3">{d.changes.map(c => (
          <div key={c.celex} className="py-2.5">
            <div className="flex items-center gap-3 flex-wrap text-[12.5px]"><span className="mono text-[10.5px] text-[var(--color-faint)]">{c.detected_at}</span><span className="text-[var(--color-ink)]">{c.title}</span>
              <a href={c.url} target="_blank" rel="noreferrer" className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">{c.celex}</a>
              <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">{c.framework}{c.effective_date ? ` · effective ${c.effective_date}` : ''}{c.task_id ? ' · task raised' : ''}</span></div>
            <div className="mt-1.5"><LinkChips L={c.touches} /></div>
          </div>))}</div>
      ) : <div className="text-[12.5px] text-[var(--color-faint)] mb-3">No open detected change to your frameworks. Below is what each framework governs, so you know what a future amendment would touch.</div>}
      <div className="space-y-2.5">{d.frameworks.map(fw => <div key={fw}><div className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1">{fw} · {d.links[fw].n} governed items</div><LinkChips L={d.links[fw]} /></div>)}</div>
    </Card>
  )
}

// ── 4 share the assurance pack with the auditor ─────────────────────────────────────────────────────────────
interface Share { share_id: string; recipient_name: string; recipient_email: string; purpose: string; expires_at: string; max_downloads: number | null; n_downloads: number; status: string; created_at: string; created_by: string | null; accesses: { at: string; action: string; outcome: string; ip: string | null }[] }
export function AssuranceShareDialog({ filingId, label, onClose }: { filingId: string; label: string; onClose: () => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['assurance-shares', filingId], queryFn: () => api.get<{ shares: Share[] }>(`/v1/filings/${filingId}/assurance-shares`) })
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [purpose, setPurpose] = useState(''); const [days, setDays] = useState<number | ''>(''); const [max, setMax] = useState<number | ''>('')
  const [busy, setBusy] = useState(false); const [done, setDone] = useState<{ link: string; expires_at: string } | null>(null)
  const submit = async () => {
    setBusy(true)
    try { const r = await api.post<{ link: string; expires_at: string }>(`/v1/filings/${filingId}/assurance-shares`, { recipient_name: name, recipient_email: email, purpose, expires_in_days: days === '' ? null : days, max_downloads: max === '' ? null : max }); setDone(r); toast.success('Assurance pack shared.'); await qc.invalidateQueries({ queryKey: ['assurance-shares', filingId] }) }
    catch (e) { toast.error((e as Error).message || 'Could not share the pack.') } finally { setBusy(false) }
  }
  const revoke = async (s: Share) => { try { await api.post(`/v1/assurance-shares/${s.share_id}/revoke`); await qc.invalidateQueries({ queryKey: ['assurance-shares', filingId] }) } catch (e) { toast.error((e as Error).message) } }
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-[620px] max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Assurance pack · {label}</div>
        <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)]">Share with the auditor</h2>
        <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-4">The auditor receives a link to the evidence bundle behind this filing: methodology, validation record, four-eyes approvals, provenance, the control register and a hashed manifest. The link expires, counts downloads, can be revoked, and every access is on your audit trail.</p>
        {done ? (
          <div className="rounded-lg border border-[var(--color-good)]/40 bg-[var(--color-good)]/10 p-4 mb-4">
            <div className="text-[12.5px] text-[var(--color-ink)]">Shared · expires {dt(done.expires_at)} · e-mailed to {email}. The link is shown once:</div>
            <div className="mt-2 flex gap-2"><input readOnly value={done.link} className={inp + ' mono text-[11px]'} onFocus={e => e.currentTarget.select()} /><Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(done.link); toast.success('Link copied.') }}>Copy</Button></div>
          </div>
        ) : (
          <div className="space-y-3 mb-4">
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Auditor<input value={name} onChange={e => setName(e.target.value)} className={inp + ' mt-1'} placeholder="Name or firm" /></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">E-mail<input value={email} onChange={e => setEmail(e.target.value)} className={inp + ' mt-1'} /></label>
            </div>
            <label className="block text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Purpose<input value={purpose} onChange={e => setPurpose(e.target.value)} className={inp + ' mt-1'} placeholder="e.g. Limited assurance engagement FY2025" /></label>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Expires in days (default 30)<input type="number" min={1} max={180} value={days} onChange={e => setDays(e.target.value === '' ? '' : Number(e.target.value))} className={inp + ' mt-1'} /></label>
              <label className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)]">Download limit (blank = unlimited)<input type="number" min={1} value={max} onChange={e => setMax(e.target.value === '' ? '' : Number(e.target.value))} className={inp + ' mt-1'} /></label>
            </div>
            <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Close</Button><Button onClick={submit} disabled={busy || !name || !email || !purpose}>{busy ? 'Sharing…' : 'Share'}</Button></div>
          </div>)}
        {(q.data?.shares ?? []).length > 0 && <div>
          <div className="text-[11px] mono uppercase tracking-wide text-[var(--color-faint)] mb-1">Shares of this pack</div>
          <div className="divide-y divide-[var(--color-line)]">{q.data!.shares.map(s => (
            <div key={s.share_id} className="py-1.5 text-[12px] flex items-center gap-3 flex-wrap">
              <span className="text-[var(--color-ink)]">{s.recipient_name}</span><span className="text-[var(--color-mute)]">{s.purpose}</span>
              <span className="mono text-[10.5px]" style={{ color: s.status === 'active' ? 'var(--color-good)' : 'var(--color-faint)' }}>{s.status}</span>
              <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">expires {s.expires_at.slice(0, 10)} · {s.n_downloads}{s.max_downloads ? `/${s.max_downloads}` : ''} downloads · {s.accesses.length} accesses</span>
              {s.status === 'active' && <button onClick={() => revoke(s)} className="text-[var(--color-bad)] hover:underline">Revoke</button>}
            </div>))}</div></div>}
      </div>
    </div>
  )
}
