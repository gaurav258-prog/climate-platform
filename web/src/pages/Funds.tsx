import { useState } from 'react'
import EetPanel from '../components/EetPanel'
import PaiStatement from '../components/sfdr/PaiStatement'
import { money } from '../lib/money'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, Pencil, BadgeCheck, Plus, Briefcase, Landmark } from 'lucide-react'
import { api, apiMessage, apiDetail } from '../lib/api'
import { Card, Button, SectionHead, PageHeader, StatGrid } from '../components/ui'
import { HEADING, MessageLine } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { ARTICLE, FUND_TYPE, scoreTone } from '../components/sfdr/words'
import { Meter } from '../components/sfdr/visuals'

// The asset manager's SFDR front door: the manager's filing identity, its principal adverse impacts statement, the
// funds (each drilling to its climate report and adverse-impact figures) and the European ESG Template.

interface Fund {
  fund_id: string; name: string; fund_type: string; sfdr_classification: string | null; parent_fund_id: string | null
  total_value_eur: number; base?: Base | null; positions: number; physical_score: number | null; transition_score: number | null; waci: number | null
}
interface Profile { name?: string; legal_name?: string; lei?: string; filing_contact_email?: string; country?: string }
interface Base { currency: string; as_of: string; available?: boolean; total_value?: number }
type Problem = { label: string; detail: ReturnType<typeof apiDetail> } | null

const eur = (n?: number | null) => money(n, 'EUR')
// a fund's value in its own base currency (holdings are held in euro; converted at the holdings date)
const fundValue = (eurValue: number, b?: Base | null) =>
  b && b.currency !== 'EUR' && b.available !== false && b.total_value != null ? money(b.total_value, b.currency) : eur(eurValue)

export function SfdrBadge({ c }: { c: string | null }) {
  const a = ARTICLE[c ?? '']
  return a ? <StatusChip label={a.label} tone={c === 'article_9' ? 'good' : 'neutral'} />
    : <StatusChip label="Not classified" tone="warn" />
}

export default function Funds() {
  const nav = useNavigate()
  const q = useQuery({ queryKey: ['funds'], queryFn: () => api.get<{ funds: Fund[] }>('/v1/funds') })
  const funds = q.data?.funds ?? []
  const [adding, setAdding] = useState(false)
  const total = funds.reduce((a, f) => a + (f.total_value_eur || 0), 0)
  const weighted = (k: 'physical_score' | 'transition_score') => {
    const w = funds.filter(f => f[k] != null && f.total_value_eur > 0)
    const v = w.reduce((a, f) => a + f.total_value_eur, 0)
    return v ? w.reduce((a, f) => a + (f[k] as number) * f.total_value_eur, 0) / v : null
  }
  const phys = weighted('physical_score'), trans = weighted('transition_score')

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Asset management" title="Funds"
        lead="Your funds' climate risk and adverse-impact disclosures."
        about={[
          { heading: HEADING.shows, body: 'Each fund\'s physical and transition climate risk, the principal adverse impacts statement you publish as a manager under the Sustainable Finance Disclosure Regulation (SFDR), and the European ESG Template you send distributors.' },
          { heading: HEADING.sources, body: 'Your holdings, matched to their issuers by ISIN; the issuers\' locations scored for physical risk; the figures investees report, or you add in the holdings upload.' },
        ]} />

      {funds.length > 0 && (
        <StatGrid cols={4} items={[
          { label: 'Funds', value: funds.length },
          { label: 'Value held', value: eur(total) },
          { label: 'Physical risk', value: phys == null ? '—' : `${Math.round(phys)}/100`, accent: phys == null ? undefined : scoreTone(phys), sub: 'Weighted by value' },
          { label: 'Transition risk', value: trans == null ? '—' : `${Math.round(trans)}/100`, accent: trans == null ? undefined : scoreTone(trans), sub: trans == null ? 'Not scored yet' : 'Weighted by value' },
        ]} />)}

      <FilingIdentity />
      <PaiStatement />

      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
          <SectionHead icon={Briefcase} className="mb-0">Your funds</SectionHead>
          {!adding && <Button variant="ghost" onClick={() => setAdding(true)}><Plus size={13} /> New fund</Button>}
        </div>
        {adding && <NewFund funds={funds} onDone={id => { setAdding(false); if (id) nav(`/funds/${id}`) }} />}
        {q.isLoading ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">Loading…</div>
          : funds.length === 0 ? <div className="p-10 text-center text-[var(--color-faint)] text-sm">No funds yet.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              <div className="hidden md:grid grid-cols-[1fr_8.5rem_8.5rem_6rem_1rem] gap-4 px-5 py-2 text-[11px] text-[var(--color-faint)]">
                <span>Fund</span><span>Physical risk</span><span>Transition risk</span><span className="text-right">Carbon intensity</span><span />
              </div>
              {funds.map(f => (
                <button key={f.fund_id} onClick={() => nav(`/funds/${f.fund_id}`)}
                  className="w-full text-left px-5 py-3.5 grid grid-cols-1 md:grid-cols-[1fr_8.5rem_8.5rem_6rem_1rem] gap-x-4 gap-y-2 items-center hover:bg-[var(--color-bg-2)] transition">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-[14px] text-[var(--color-ink)] truncate">{f.name}</span>
                      <SfdrBadge c={f.sfdr_classification} />
                    </div>
                    <div className="text-[12px] text-[var(--color-faint)] mt-0.5">{fundValue(f.total_value_eur, f.base)} · {f.positions} holding{f.positions === 1 ? '' : 's'}{f.parent_fund_id ? ' · held through another fund' : ''}</div>
                  </div>
                  <Score v={f.physical_score} label="Physical risk" />
                  <Score v={f.transition_score} label="Transition risk" />
                  <div className="md:text-right text-[13px] tabular-nums text-[var(--color-mute)]" title="Tonnes of CO₂e per million euro of revenue, weighted by value">
                    {f.waci != null ? Math.round(f.waci).toLocaleString('en-GB') : '—'}<span className="text-[11px] text-[var(--color-faint)]"> t/€m</span>
                  </div>
                  <ChevronRight size={15} className="text-[var(--color-faint)] hidden md:block" />
                </button>
              ))}
            </div>}
      </Card>

      <EetPanel />
    </div>
  )
}

function Score({ v, label }: { v: number | null; label: string }) {
  return (
    <span className="inline-flex items-center gap-2" aria-label={label}>
      <span className="md:hidden text-[11px] text-[var(--color-faint)] w-24">{label}</span>
      <Meter value={v} tone={scoreTone(v)} width="w-16" score />
    </span>
  )
}

function FilingIdentity() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['manager-profile'], queryFn: () => api.get<Profile>('/v1/manager/filing-profile') })
  const p = q.data
  const [edit, setEdit] = useState(false)
  const [lei, setLei] = useState(''); const [legal, setLegal] = useState(''); const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Problem>(null)
  const open = () => { setLei(p?.lei ?? ''); setLegal(p?.legal_name ?? ''); setEmail(p?.filing_contact_email ?? ''); setErr(null); setEdit(true) }
  const save = async () => {
    setBusy(true); setErr(null)
    try {
      await api.put('/v1/manager/filing-profile', { lei: lei.trim(), legal_name: legal.trim() || undefined, filing_contact_email: email.trim() || undefined })
      qc.invalidateQueries({ queryKey: ['manager-profile'] }); qc.invalidateQueries({ queryKey: ['pai-answers'] }); setEdit(false)
    } catch (e) { setErr({ label: apiMessage(e, 'Could not save.'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]'

  return (
    <Card className="p-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <SectionHead icon={Landmark} hint="the manager named on every statement" className="mb-2">Filing identity</SectionHead>
          {!edit ? (
            <div className="flex flex-wrap items-center gap-2 text-[13px]">
              <b className="text-[var(--color-ink)] font-medium">{p?.legal_name || p?.name || '—'}</b>
              {p?.lei ? <StatusChip tone="good" label={`LEI ${p.lei}`} /> : <StatusChip tone="warn" label="LEI required" />}
              {p?.lei && <BadgeCheck size={14} className="text-[var(--color-good)]" aria-label="Checked against the LEI register" />}
              {p?.filing_contact_email ? <span className="text-[var(--color-mute)]">{p.filing_contact_email}</span> : <StatusChip tone="warn" label="Contact required" />}
            </div>
          ) : (
            <div className="space-y-2 mt-1">
              {err && <MessageLine m={err} className="text-[12px] text-[var(--color-bad)]" />}
              <div className="flex flex-wrap gap-2">
                <input value={lei} onChange={e => setLei(e.target.value)} placeholder="LEI — 20 letters and digits" aria-label="LEI" className={`${field} w-64`} />
                <input value={legal} onChange={e => setLegal(e.target.value)} placeholder="Legal name (the register can fill it)" aria-label="Legal name" className={`${field} w-72`} />
                <input value={email} onChange={e => setEmail(e.target.value)} placeholder="Filing contact e-mail" aria-label="Filing contact e-mail" className={`${field} w-56`} />
              </div>
            </div>
          )}
        </div>
        {!edit
          ? <Button variant="ghost" onClick={open}><Pencil size={13} /> {p?.lei ? 'Edit' : 'Set identity'}</Button>
          : <div className="flex gap-2 shrink-0"><Button variant="primary" onClick={save} disabled={busy || lei.trim().length !== 20}>Save</Button><Button variant="ghost" onClick={() => setEdit(false)}>Cancel</Button></div>}
      </div>
    </Card>
  )
}

// a fund as the manager states it — the SFDR category and the base currency are the manager's statements, never defaulted
function NewFund({ funds, onDone }: { funds: Fund[]; onDone: (fundId: string | null) => void }) {
  const qc = useQueryClient()
  const [f, setF] = useState({ name: '', fund_type: 'fund', sfdr_classification: '', base_currency: '', parent_fund_id: '', lei: '' })
  const [busy, setBusy] = useState(false); const [err, setErr] = useState<Problem>(null)
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
    } catch (e) { setErr({ label: apiMessage(e, 'Could not create the fund.'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]'
  const label = 'block text-[11.5px] text-[var(--color-mute)] mb-1'
  return (
    <div className="px-5 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] space-y-3">
      {err && <MessageLine m={err} className="text-[12px] text-[var(--color-bad)]" />}
      <div className="flex flex-wrap gap-3 items-end">
        <label><span className={label}>Name</span><input value={f.name} onChange={set('name')} className={`${field} w-72`} /></label>
        <label><span className={label}>Type</span>
          <select value={f.fund_type} onChange={set('fund_type')} className={field}>{Object.entries(FUND_TYPE).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>
        <label><span className={label}>SFDR category</span>
          <select value={f.sfdr_classification} onChange={set('sfdr_classification')} className={field}>
            <option value="">Choose…</option>{Object.entries(ARTICLE).map(([v, a]) => <option key={v} value={v}>{a.long}</option>)}</select></label>
        <label><span className={label}>Base currency</span><input value={f.base_currency} onChange={set('base_currency')} placeholder="For example EUR" maxLength={3} className={`${field} w-32 uppercase`} /></label>
        {sub && <label><span className={label}>Part of fund</span>
          <select value={f.parent_fund_id} onChange={set('parent_fund_id')} className={field}>
            <option value="">Choose…</option>{funds.map(x => <option key={x.fund_id} value={x.fund_id}>{x.name}</option>)}</select></label>}
        <label><span className={label}>Fund LEI (optional)</span><input value={f.lei} onChange={set('lei')} placeholder="Checked against the register" maxLength={20} className={`${field} w-56`} /></label>
      </div>
      <div className="flex gap-2">
        <Button variant="primary" onClick={save} disabled={busy || !ready}>Create fund</Button>
        <Button variant="ghost" onClick={() => onDone(null)}>Cancel</Button>
      </div>
    </div>
  )
}
