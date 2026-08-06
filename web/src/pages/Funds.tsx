import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Pencil, BadgeCheck, AlertTriangle } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { Eyebrow, Card, Button } from '../components/ui'

// The asset-manager's SFDR front door: the manager's filing identity (LEI / legal name / contact — required
// before any statement can be filed) and the fund list, each fund drilling to its full climate report + the
// SFDR PAI statement. Everything reads the golden source; nothing is invented.

interface Fund {
  fund_id: string; name: string; fund_type: string; sfdr_classification: string | null; parent_fund_id: string | null
  total_value_eur: number; positions: number; physical_score: number | null; transition_score: number | null; waci: number | null
}
interface Narratives { policies?: string; actions?: string; engagement?: string; standards?: string }
interface Profile { name?: string; legal_name?: string; lei?: string; filing_contact_email?: string; country?: string; sfdr_narratives?: Narratives | null; error?: string }
const NARR: { key: keyof Narratives; label: string; hint: string }[] = [
  { key: 'policies', label: 'Policies', hint: 'How principal adverse impacts are identified & prioritised' },
  { key: 'actions', label: 'Actions', hint: 'Actions taken / planned this period to mitigate the PAIs' },
  { key: 'engagement', label: 'Engagement', hint: 'Engagement policy with investee companies' },
  { key: 'standards', label: 'Standards', hint: 'Adherence to responsible-business conduct codes (UNGC / OECD)' },
]

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const scoreCol = (s?: number | null) => s == null ? 'var(--color-faint)' : s < 28 ? '#34d399' : s < 50 ? '#e8b24c' : s < 75 ? '#f0a860' : '#fb7185'

const SFDR: Record<string, { label: string; c: string }> = {
  article_9: { label: 'Art. 9', c: '#34d399' }, article_8: { label: 'Art. 8', c: '#5cc8ff' }, article_6: { label: 'Art. 6', c: '#94a3b8' },
}
export function SfdrBadge({ c }: { c: string | null }) {
  const s = SFDR[c ?? ''] ?? { label: c ?? '—', c: '#94a3b8' }
  return <span className="mono text-[10px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap" style={{ color: s.c, background: `${s.c}22` }}>SFDR {s.label}</span>
}

export default function Funds() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['funds'], queryFn: () => api.get<{ funds: Fund[] }>('/v1/funds') })
  const funds = q.data?.funds ?? []

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Asset management · SFDR (Sustainable Finance Disclosure Regulation)</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Funds</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Each fund's physical &amp; transition climate risk and its SFDR Principal-Adverse-Impact statement — assembled from your holdings against the golden source, ready to file.</p>
      </div>

      <FilingIdentity />
      <SfdrNarratives />

      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)] mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Your funds</div>
        {q.isLoading ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</div>
          : funds.length === 0 ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">No funds yet.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {funds.map(f => (
                <button key={f.fund_id} onClick={() => nav(`/funds/${f.fund_id}`)}
                  className="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-[var(--color-bg-2)] transition">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[14px] text-[var(--color-ink)] truncate">{f.name}</span>
                      <SfdrBadge c={f.sfdr_classification} />
                    </div>
                    <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">{eur(f.total_value_eur)} · {f.positions} position{f.positions === 1 ? '' : 's'}{f.parent_fund_id ? ' · look-through vehicle' : ''}</div>
                  </div>
                  <ScorePill label="physical" v={f.physical_score} />
                  <ScorePill label="transition" v={f.transition_score} />
                  <div className="text-right w-24 shrink-0">
                    <div className="mono text-[12.5px] tabular-nums text-[var(--color-mute)]">{f.waci != null ? Math.round(f.waci).toLocaleString('en-GB') : '—'}</div>
                    <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">WACI</div>
                  </div>
                  <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />
                </button>
              ))}
            </div>}
      </Card>
    </div>
  )
}

function ScorePill({ label, v }: { label: string; v: number | null }) {
  return (
    <div className="text-right w-20 shrink-0">
      <div className="mono text-[12.5px] tabular-nums" style={{ color: scoreCol(v) }}>{v == null ? '—' : `${Math.round(v)}/100`}</div>
      <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">{label}</div>
    </div>
  )
}

function FilingIdentity() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['manager-profile'], queryFn: () => api.get<Profile>('/v1/manager/filing-profile') })
  const p = q.data
  const [edit, setEdit] = useState(false)
  const [lei, setLei] = useState(''); const [legal, setLegal] = useState(''); const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)
  const open = () => { setLei(p?.lei ?? ''); setLegal(p?.legal_name ?? ''); setEmail(p?.filing_contact_email ?? ''); setErr(null); setEdit(true) }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.put<{ error?: string; detail?: string }>('/v1/manager/filing-profile', { lei: lei.trim(), legal_name: legal.trim() || undefined, filing_contact_email: email.trim() || undefined })
      if (r.error) { setErr(r.detail || r.error); return }
      qc.invalidateQueries({ queryKey: ['manager-profile'] }); setEdit(false)
    } catch (e) { setErr(e instanceof ApiError ? (typeof e.body === 'object' && e.body && 'detail' in e.body ? String((e.body as { detail: unknown }).detail) : e.message) : 'Could not save.') }
    finally { setBusy(false) }
  }

  const hasLei = !!p?.lei
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Filing identity · the manager on every SFDR statement</div>
          {!edit ? (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px]">
              <span className="inline-flex items-center gap-1.5">{hasLei ? <BadgeCheck size={14} className="text-[var(--color-good)]" /> : <AlertTriangle size={14} className="text-[var(--color-warn)]" />}<b className="text-[var(--color-ink)]">{p?.legal_name || p?.name || '—'}</b></span>
              <span className="text-[var(--color-mute)]">LEI <span className="mono">{p?.lei || '— (required to file)'}</span></span>
              {p?.filing_contact_email && <span className="text-[var(--color-mute)]">{p.filing_contact_email}</span>}
              {p?.country && <span className="text-[var(--color-faint)] mono">{p.country}</span>}
            </div>
          ) : (
            <div className="space-y-2 mt-1">
              {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
              <div className="flex flex-wrap gap-2">
                <input value={lei} onChange={e => setLei(e.target.value)} placeholder="LEI (20 chars, validated vs GLEIF)" className="w-72 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] mono outline-none focus:border-[var(--color-sky)]" />
                <input value={legal} onChange={e => setLegal(e.target.value)} placeholder="Legal name (optional — GLEIF fills it)" className="w-72 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
                <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Filing contact email" className="w-56 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]" />
              </div>
            </div>
          )}
        </div>
        {!edit
          ? <Button variant="ghost" onClick={open}><Pencil size={13} /> {hasLei ? 'Edit' : 'Set identity'}</Button>
          : <div className="flex gap-2 shrink-0"><Button variant="primary" onClick={save} disabled={busy || lei.trim().length !== 20}>Save</Button><Button variant="ghost" onClick={() => setEdit(false)}>Cancel</Button></div>}
      </div>
    </Card>
  )
}

// The manager's SFDR narrative sections — one set, applied to every fund's Annex I statement, and REQUIRED
// before a fund can be filed. Saved through the filing-profile (which re-validates the LEI vs GLEIF), so the
// manager identity must be set first.
function SfdrNarratives() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['manager-profile'], queryFn: () => api.get<Profile>('/v1/manager/filing-profile') })
  const p = q.data
  const [edit, setEdit] = useState(false)
  const [form, setForm] = useState<Narratives>({})
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)
  if (!p) return null
  const cur = p.sfdr_narratives ?? {}
  const filled = NARR.filter(n => (cur[n.key] ?? '').trim()).length
  const open = () => { setForm({ ...cur }); setErr(null); setEdit(true) }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.put<{ error?: string; detail?: string }>('/v1/manager/filing-profile', { lei: p.lei, narratives: form })
      if (r.error) { setErr(r.detail || r.error); return }
      qc.invalidateQueries({ queryKey: ['manager-profile'] }); qc.invalidateQueries({ queryKey: ['fund-sfdr'] }); setEdit(false)
    } catch (e) { setErr(e instanceof ApiError ? e.message : 'Could not save.') }
    finally { setBusy(false) }
  }
  const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)] resize-none'
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4 mb-1">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">SFDR narratives · required on every statement <span className="ml-1.5" style={{ color: filled === NARR.length ? 'var(--color-good)' : 'var(--color-warn)' }}>{filled}/{NARR.length} complete</span></div>
        {!p.lei ? <span className="mono text-[10.5px] text-[var(--color-warn)]">set the filing identity first</span>
          : !edit ? <Button variant="ghost" onClick={open}><Pencil size={13} /> Edit</Button>
          : <div className="flex gap-2 shrink-0"><Button variant="primary" onClick={save} disabled={busy}>Save</Button><Button variant="ghost" onClick={() => setEdit(false)}>Cancel</Button></div>}
      </div>
      {err && <div className="text-[12px] text-[var(--color-bad)] mb-2">{err}</div>}
      {!edit ? (
        <div className="grid sm:grid-cols-2 gap-x-6 gap-y-2 mt-2">
          {NARR.map(n => (
            <div key={n.key} className="text-[12px]">
              <span className="text-[var(--color-mute)]">{n.label}: </span>
              <span className={(cur[n.key] ?? '').trim() ? 'text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}>{(cur[n.key] ?? '').trim() || 'not set — required to file'}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2.5 mt-2">
          {NARR.map(n => (
            <label key={n.key} className="block">
              <span className="text-[12px] text-[var(--color-mute)]">{n.label} <span className="text-[var(--color-faint)]">— {n.hint}</span></span>
              <textarea value={form[n.key] ?? ''} onChange={e => setForm(f => ({ ...f, [n.key]: e.target.value }))} rows={2} className={`${box} mt-1`} />
            </label>
          ))}
        </div>
      )}
    </Card>
  )
}
