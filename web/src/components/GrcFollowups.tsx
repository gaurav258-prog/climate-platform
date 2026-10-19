import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, History, Network, Send } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../lib/api'
import { frameworkLabel } from '../lib/hazards'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead } from '../components/ui'
import { HEADING, InfoButton, MessageLine, type Message, type DetailSection } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog, CloseButton } from './Dialog'
import { version } from './filing/words'

const dt = (s: string | null | undefined) => s ? new Date(s).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
const day = (s: string | null | undefined) => s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—'
const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

// ── 1 the appetite statement's change history ───────────────────────────────────────────────────────────────
interface Ver { kri_key: string; version: number; amber: number | null; red: number | null; direction: string | null; previous: { amber?: number | null; red?: number | null } | null; reason: string | null; created_at: string; changed_by: string | null; approved_by: string | null }
const band = (a?: number | null, r?: number | null) => `amber ${a ?? '—'} · red ${r ?? '—'}`

export function AppetiteHistory({ framework }: { framework: string | undefined }) {
  const q = useQuery({ queryKey: ['kri-appetite-history', framework], enabled: !!framework, queryFn: () => api.get<{ versions: Ver[] }>(`/v1/admin/kri-appetite/history?framework=${framework}`) })
  // the indicators' names, from the appetite bands of the same framework
  const names = useQuery({ queryKey: ['kri-appetite-names', framework], enabled: !!framework,
    queryFn: () => api.get<{ kpis?: { key: string; label: string }[] }>(`/v1/admin/kri-appetite?framework=${framework}`) })
  const name: Record<string, string> = Object.fromEntries((names.data?.kpis ?? []).map(k => [k.key, k.label]))
  const rows = q.data?.versions ?? []
  if (!framework || rows.length === 0) return null
  return (
    <div className="px-4 py-3 border-t border-[var(--color-line)]">
      <div className="flex items-center gap-1.5 mb-1.5">
        <SectionHead icon={History}>Appetite changes</SectionHead>
        <InfoButton compact details={{ title: 'Appetite changes', sections: [
          { heading: HEADING.shows, body: "Every change to an indicator's amber and red bands: when, the bands before and after, who made it and who approved it." },
          { heading: HEADING.read, body: 'Select the ⓘ on a change for the reason given.' }] }} />
      </div>
      <div className="divide-y divide-[var(--color-line)]">{rows.slice(0, 12).map(v => (
        <div key={`${v.kri_key}-${v.version}`} className="py-1.5 text-[12.5px] flex items-center gap-3 flex-wrap">
          <span className="text-[11.5px] text-[var(--color-faint)] w-36 shrink-0">{dt(v.created_at)}</span>
          <span className="text-[var(--color-ink)]">{name[v.kri_key] ?? 'An indicator no longer graded'}</span>
          <StatusChip tone="neutral" label={version(v.version)} />
          <span className="tabular-nums text-[12px] text-[var(--color-mute)] inline-flex items-center gap-1.5">
            {v.previous && <><span className="text-[var(--color-faint)]">{band(v.previous.amber, v.previous.red)}</span><ArrowRight size={11} /></>}
            <span className="text-[var(--color-ink)]">{band(v.amber, v.red)}</span>
          </span>
          <span className="text-[11.5px] text-[var(--color-faint)]">{v.direction === 'lower_worse' ? 'Lower is worse' : 'Higher is worse'}</span>
          <span className="text-[var(--color-mute)] ml-auto inline-flex items-center gap-1.5">{v.changed_by ?? '—'}{v.approved_by ? ` · approved by ${v.approved_by}` : ''}
            {v.reason && <InfoButton compact details={{ title: 'Why the bands changed', sections: [{ heading: 'Reason', body: v.reason }] }} />}</span>
        </div>))}</div>
    </div>
  )
}

// ── 2 what a regulatory change touches ──────────────────────────────────────────────────────────────────────
interface Links { framework: string; switches: { key: string; label: string }[]; kris: { key: string; datapoint: string; tier: string }[]; template: { official_form: string | null; form_url: string | null } | null; mandates: { id: string; title: string; article: string | null }[]; n: number }
interface Impact { changes: { celex: string; title: string; effective_date: string | null; url: string; detected_at: string; framework: string; touches: Links; task_id: string | null }[]; frameworks: string[]; links: Record<string, Links> }
const KINDS = [{ k: 'switches', label: 'Interpretations', color: 'var(--color-warn)' }, { k: 'kris', label: 'Indicators', color: 'var(--color-sky)' },
  { k: 'template', label: 'Template', color: 'var(--color-good)' }, { k: 'mandates', label: 'Mandates', color: 'var(--color-viz, #a78bfa)' }] as const
const count = (L: Links, k: typeof KINDS[number]['k']) => k === 'template' ? (L.template?.official_form ? 1 : 0) : L[k].length

// everything one framework's change can touch, for its pop-up
function touched(L: Links): DetailSection[] {
  return [
    ...(L.switches.length ? [{ heading: 'Interpretations', body: <ul className="space-y-0.5">{L.switches.map(s => <li key={s.key}>{s.label}</li>)}</ul> }] : []),
    ...(L.kris.length ? [{ heading: 'Indicators', body: <ul className="space-y-0.5">{L.kris.map(k => <li key={k.key}>{k.datapoint}{k.tier === 'core' ? ' (core)' : ''}</li>)}</ul> }] : []),
    ...(L.template?.official_form ? [{ heading: 'Official template', body: L.template.form_url ? <a href={L.template.form_url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">{L.template.official_form}</a> : L.template.official_form }] : []),
    ...(L.mandates.length ? [{ heading: 'Mandates', body: <ul className="space-y-0.5">{L.mandates.map(m => <li key={m.id}>{m.title}{m.article ? ` (${m.article})` : ''}</li>)}</ul> }] : []),
  ]
}

// A framework's governed items as one bar, coloured by kind.
function TouchBar({ L }: { L: Links }) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <div className="flex h-2 w-40 rounded-full overflow-hidden bg-[var(--color-line)]" role="img"
        aria-label={KINDS.map(x => `${count(L, x.k)} ${x.label.toLowerCase()}`).join(', ')}>
        {KINDS.map(x => count(L, x.k) > 0 && <div key={x.k} style={{ width: `${(100 * count(L, x.k)) / Math.max(1, L.n)}%`, background: x.color }} />)}
      </div>
      {KINDS.filter(x => count(L, x.k) > 0).map(x => <span key={x.k} className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)]"><span className="w-2 h-2 rounded-full" style={{ background: x.color }} />{count(L, x.k)} {x.label.toLowerCase()}</span>)}
    </div>
  )
}

export function ChangeImpact() {
  const q = useQuery({ queryKey: ['reg-impact'], queryFn: () => api.get<Impact>('/v1/reg-changes/impact') })
  const d = q.data
  if (!d) return null
  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-1.5">
        <SectionHead icon={Network}>What a change touches</SectionHead>
        <InfoButton compact details={{ title: 'What a change touches', sections: [
          { heading: HEADING.shows, body: 'For each detected change to a report you file, what it may change here: the interpretations you state, the indicators and figures that feed it, the official template, and the mandates that cite it.' },
          { heading: HEADING.sources, body: "Your configuration: an item is listed when it declares the report the change amends. Nothing is inferred from the change's text." }] }} />
      </div>
      {d.changes.length > 0 ? (
        <div className="divide-y divide-[var(--color-line)]">{d.changes.map(c => (
          <div key={c.celex} className="py-2.5 space-y-1.5">
            <div className="flex items-center gap-2 flex-wrap text-[12.5px]">
              <span className="text-[11.5px] text-[var(--color-faint)]">{day(c.detected_at)}</span>
              <span className="text-[var(--color-ink)]">{c.title}</span>
              <StatusChip tone="neutral" label={frameworkLabel(c.framework)} />
              {c.effective_date && <StatusChip tone="warn" label={`Effective ${day(c.effective_date)}`} />}
              {c.task_id && <Link to="/tasks" className="text-[12px] text-[var(--color-sky)] hover:underline">Task raised</Link>}
              <a href={c.url} target="_blank" rel="noreferrer" className="text-[12px] text-[var(--color-sky)] hover:underline ml-auto">Official text</a>
            </div>
            <div className="flex items-center gap-1.5"><TouchBar L={c.touches} /><InfoButton compact details={{ title: c.title, sections: touched(c.touches) }} /></div>
          </div>))}</div>
      ) : <div className="text-[12.5px] text-[var(--color-faint)] flex items-center gap-1.5">No open change detected to your reports
          <InfoButton compact details={{ title: 'No open change', sections: [{ heading: HEADING.read, body: 'Below is what each report governs here, so you know what a future amendment would touch.' }] }} /></div>}
      <div className="space-y-2 pt-1">{d.frameworks.map(fw => (
        <div key={fw} className="flex items-center gap-3 flex-wrap">
          <span className="text-[12.5px] text-[var(--color-ink)] w-56 shrink-0 truncate">{frameworkLabel(fw)}</span>
          <TouchBar L={d.links[fw]} />
          <InfoButton compact details={{ title: frameworkLabel(fw), sections: touched(d.links[fw]) }} />
        </div>))}</div>
    </Card>
  )
}

// ── 3 share the assurance pack with the auditor ─────────────────────────────────────────────────────────────
interface Share { share_id: string; recipient_name: string; purpose: string; expires_at: string; max_downloads: number | null; n_downloads: number; status: string; accesses: unknown[] }
export function AssuranceShareDialog({ filingId, label, onClose }: { filingId: string; label: string; onClose: () => void }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['assurance-shares', filingId], queryFn: () => api.get<{ shares: Share[] }>(`/v1/filings/${filingId}/assurance-shares`) })
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [purpose, setPurpose] = useState(''); const [days, setDays] = useState<number | ''>(''); const [max, setMax] = useState<number | ''>('')
  const [busy, setBusy] = useState(false); const [done, setDone] = useState<{ link: string; expires_at: string } | null>(null)
  const [err, setErr] = useState<Message | null>(null)
  const submit = async () => {
    setBusy(true); setErr(null)
    try { const r = await api.post<{ link: string; expires_at: string }>(`/v1/filings/${filingId}/assurance-shares`, { recipient_name: name, recipient_email: email, purpose, expires_in_days: days === '' ? null : days, max_downloads: max === '' ? null : max }); setDone(r); toast.success('Assurance pack shared.'); await qc.invalidateQueries({ queryKey: ['assurance-shares', filingId] }) }
    catch (e) { setErr({ label: apiMessage(e, 'Could not share the pack'), detail: apiDetail(e) }) } finally { setBusy(false) }
  }
  const revoke = async (s: Share) => {
    try { await api.post(`/v1/assurance-shares/${s.share_id}/revoke`); await qc.invalidateQueries({ queryKey: ['assurance-shares', filingId] }) }
    catch (e) { toast.error(apiMessage(e, 'Could not revoke the share.')) }
  }
  const field = 'text-[12px] text-[var(--color-mute)]'
  return (
    <Dialog bare title="Share with the auditor" onClose={onClose} className="w-full max-w-[620px] max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-bg)] p-6 shadow-2xl">
      <CloseButton onClick={onClose} className="absolute top-4 right-4" />
      <div className="text-[12px] text-[var(--color-blue)] mb-1">Assurance pack · {label}</div>
      <h2 className="display text-lg font-semibold m-0 text-[var(--color-ink)] flex items-center gap-2"><Send size={16} /> Share with the auditor
        <InfoButton compact details={{ title: 'Sharing the assurance pack', sections: [
          { heading: HEADING.shows, body: 'The auditor receives a link to the evidence behind this filing: the method, the validation record, the four-eyes approvals, where each figure came from, the control register and a list of every file with its fingerprint.' },
          { heading: 'Limits', body: 'The link expires, counts downloads and can be revoked; every access is on your audit trail.' }] }} /></h2>
      <div className="mt-4" />
      {done ? (
        <div className="rounded-lg border border-[var(--color-good)]/40 bg-[var(--color-good)]/10 p-4 mb-4">
          <div className="text-[12.5px] text-[var(--color-ink)]">Shared · expires {dt(done.expires_at)} · e-mailed to {email}. The link is shown once:</div>
          <div className="mt-2 flex gap-2"><input readOnly value={done.link} aria-label="Share link" className={inp + ' text-[11.5px]'} onFocus={e => e.currentTarget.select()} /><Button variant="ghost" onClick={() => { navigator.clipboard?.writeText(done.link); toast.success('Link copied.') }}>Copy</Button></div>
        </div>
      ) : (
        <div className="space-y-3 mb-4">
          {err && <MessageLine m={err} className="text-[12.5px] text-[var(--color-bad)]" />}
          <div className="grid grid-cols-2 gap-3">
            <label className={field}>Auditor<input value={name} onChange={e => setName(e.target.value)} className={inp + ' mt-1'} placeholder="Name or firm" /></label>
            <label className={field}>E-mail<input value={email} onChange={e => setEmail(e.target.value)} className={inp + ' mt-1'} /></label>
          </div>
          <label className={`block ${field}`}>Purpose<input value={purpose} onChange={e => setPurpose(e.target.value)} className={inp + ' mt-1'} placeholder="For example limited assurance engagement FY2025" /></label>
          <div className="grid grid-cols-2 gap-3">
            <label className={field}>Expires after (days)<input type="number" min={1} max={180} value={days} placeholder="30" onChange={e => setDays(e.target.value === '' ? '' : Number(e.target.value))} className={inp + ' mt-1'} /></label>
            <label className={field}>Download limit<input type="number" min={1} value={max} placeholder="No limit" onChange={e => setMax(e.target.value === '' ? '' : Number(e.target.value))} className={inp + ' mt-1'} /></label>
          </div>
          <div className="flex justify-end gap-2"><Button variant="ghost" onClick={onClose}>Close</Button><Button onClick={submit} disabled={busy || !name || !email || !purpose}>{busy ? 'Sharing…' : 'Share'}</Button></div>
        </div>)}
      {(q.data?.shares ?? []).length > 0 && <div>
        <div className="text-[12px] font-medium text-[var(--color-mute)] mb-1">Shares of this pack</div>
        <div className="divide-y divide-[var(--color-line)]">{q.data!.shares.map(s => (
          <div key={s.share_id} className="py-1.5 text-[12.5px] flex items-center gap-3 flex-wrap">
            <span className="text-[var(--color-ink)]">{s.recipient_name}</span><span className="text-[var(--color-mute)] truncate max-w-[180px]">{s.purpose}</span>
            <StatusChip value={s.status} />
            <span className="text-[11.5px] text-[var(--color-faint)] ml-auto">Expires {day(s.expires_at)} · {s.n_downloads}{s.max_downloads ? ` of ${s.max_downloads}` : ''} downloads · {s.accesses.length} accesses</span>
            {s.status === 'active' && <button onClick={() => revoke(s)} className="text-[12px] text-[var(--color-bad)] hover:underline">Revoke</button>}
          </div>))}</div></div>}
    </Dialog>
  )
}
