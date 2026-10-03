import { useState } from 'react'
import EetPanel from '../components/EetPanel'
import PaiStatement from '../components/sfdr/PaiStatement'
import { money } from '../lib/money'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Pencil, BadgeCheck, AlertTriangle, Plus } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { Card, Button, SectionHead, PageHeader } from '../components/ui'

// The asset-manager's SFDR front door: the manager's filing identity (LEI / legal name / contact — required
// before any statement can be filed) and the fund list, each fund drilling to its full climate report + the
// SFDR PAI statement. Everything reads the golden source; nothing is invented.

interface Fund {
  fund_id: string; name: string; fund_type: string; sfdr_classification: string | null; parent_fund_id: string | null
  total_value_eur: number; base?: Base | null; positions: number; physical_score: number | null; transition_score: number | null; waci: number | null
}
interface Profile { name?: string; legal_name?: string; lei?: string; filing_contact_email?: string; country?: string }

interface Base { currency: string; as_of: string; available?: boolean; reason?: string; total_value?: number; physical_value_at_risk?: number | null; transition_value_at_risk?: number | null }
const eur = (n?: number | null) => money(n, 'EUR')
// a fund's value in its own base currency (holdings are held in EUR; converted at the holdings date)
const fundValue = (eurValue: number, b?: Base | null) =>
  b && b.currency !== 'EUR' && b.available !== false && b.total_value != null ? `${money(b.total_value, b.currency)} (${eur(eurValue)})` : eur(eurValue)
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
  const [adding, setAdding] = useState(false)

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Asset management · SFDR (Sustainable Finance Disclosure Regulation)" title="Funds"
        lead="Each fund's physical & transition climate risk and its SFDR Principal-Adverse-Impact statement — assembled from your holdings against the golden source, ready to file." />

      <FilingIdentity />
      <PaiStatement />

      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
          <SectionHead className="mb-0">Your funds</SectionHead>
          {!adding && <Button variant="ghost" onClick={() => setAdding(true)}><Plus size={13} /> New fund</Button>}
        </div>
        {adding && <NewFund funds={funds} onDone={id => { setAdding(false); if (id) nav(`/funds/${id}`) }} />}
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
                    <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">{fundValue(f.total_value_eur, f.base)} · {f.positions} position{f.positions === 1 ? '' : 's'}{f.parent_fund_id ? ' · look-through vehicle' : ''}</div>
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

      <EetPanel />
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
      await api.put('/v1/manager/filing-profile', { lei: lei.trim(), legal_name: legal.trim() || undefined, filing_contact_email: email.trim() || undefined })
      qc.invalidateQueries({ queryKey: ['manager-profile'] }); setEdit(false)
    } catch (e) { setErr(apiMessage(e, 'Could not save.')) }
    finally { setBusy(false) }
  }

  const hasLei = !!p?.lei
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <SectionHead hint="the manager on every SFDR statement" className="mb-2">Filing identity</SectionHead>
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

// a fund as the manager states it — the SFDR article and the base currency are the manager's statements, never defaulted
const FUND_TYPES: [string, string][] = [['fund', 'Fund'], ['sub_portfolio', 'Sub-portfolio'], ['mandate', 'Mandate'], ['fund_of_funds', 'Fund of funds']]
const ARTICLES: [string, string][] = [['article_6', 'Article 6'], ['article_8', 'Article 8 — promotes E/S characteristics'], ['article_9', 'Article 9 — sustainable investment objective']]

function NewFund({ funds, onDone }: { funds: Fund[]; onDone: (fundId: string | null) => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({ name: '', fund_type: 'fund', sfdr_classification: '', base_currency: '', parent_fund_id: '', lei: '' })
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<string | null>(null)
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const sub = f.fund_type === 'sub_portfolio'
  const ready = f.name.trim().length >= 2 && !!f.sfdr_classification && f.base_currency.trim().length === 3 && (!sub || !!f.parent_fund_id)
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api.post<{ fund_id: string }>('/v1/funds', {
        name: f.name.trim(), fund_type: f.fund_type, sfdr_classification: f.sfdr_classification,
        base_currency: f.base_currency.trim().toUpperCase(), parent_fund_id: sub ? f.parent_fund_id : undefined,
        lei: f.lei.trim() || undefined })
      qc.invalidateQueries({ queryKey: ['funds'] }); onDone(r.fund_id)
    } catch (e) { setErr(apiMessage(e, 'Could not create the fund.')) }
    finally { setBusy(false) }
  }
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]'
  const label = 'block text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1 mono'
  return (
    <div className="px-5 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] space-y-3">
      {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
      <div className="flex flex-wrap gap-3 items-end">
        <label><span className={label}>Name</span><input value={f.name} onChange={set('name')} className={`${field} w-72`} /></label>
        <label><span className={label}>Type</span>
          <select value={f.fund_type} onChange={set('fund_type')} className={field}>{FUND_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label><span className={label}>SFDR article</span>
          <select value={f.sfdr_classification} onChange={set('sfdr_classification')} className={field}>
            <option value="">Choose…</option>{ARTICLES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label><span className={label}>Base currency</span><input value={f.base_currency} onChange={set('base_currency')} placeholder="ISO 4217, e.g. EUR" maxLength={3} className={`${field} w-36 mono uppercase`} /></label>
        {sub && <label><span className={label}>Part of fund</span>
          <select value={f.parent_fund_id} onChange={set('parent_fund_id')} className={field}>
            <option value="">Choose…</option>{funds.map(x => <option key={x.fund_id} value={x.fund_id}>{x.name}</option>)}</select></label>}
        <label><span className={label}>Fund LEI (optional)</span><input value={f.lei} onChange={set('lei')} placeholder="validated vs GLEIF" maxLength={20} className={`${field} w-56 mono`} /></label>
      </div>
      <div className="flex gap-2">
        <Button variant="primary" onClick={save} disabled={busy || !ready}>Create fund</Button>
        <Button variant="ghost" onClick={() => onDone(null)}>Cancel</Button>
      </div>
    </div>
  )
}
