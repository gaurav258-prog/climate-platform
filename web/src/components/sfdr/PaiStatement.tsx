import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight } from 'lucide-react'
import { Button, Card, SectionHead } from '../ui'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'

// The manager's principal adverse impacts statement for one reference period (Delegated Regulation (EU) 2022/1288,
// Annex I): every item each section must contain, worded as Articles 5 to 10 word it, with the manager's answer for the
// period; Table 1's explanation and actions per row beside the impact and the previous period's reported figure. Only
// the items the Regulation leaves to the manager are editable; the rest is computed and shown.

interface Item { id: string; kind: string; label?: string; note?: string; parent: string | null; binding?: string | null }
interface Section { id: string; title: string; ref: string; items: Item[] }
interface Row { key: string; label: string; value: unknown; unit?: string; prior?: number | null; expl?: string | null; action?: string | null }
interface SummaryRow { d_language: string; d_meets: string[]; d_member_state: string | null; d_text: string }
type Answer = { text?: string; applicable?: boolean; ticked?: boolean; rows?: SummaryRow[] } | null
interface Data {
  period_end: string; reference_period: { start: string; end: string; impact_dates: string[] }
  spec: { version: string }; sections: Section[]; computed: Record<string, string>; answers: Record<string, Answer>
  rows: Row[]; prior_period: { period_end: string; source: string } | null
  historical_comparison: { applies: boolean; rows: { period: string; indicator: string; impact: number | string; source: string }[] }
  missing: string[]; ready_to_file: boolean; legacy_narratives: Record<string, string> | null
}

const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
const MEETS: Record<string, string> = { home_official: 'Official language of the home Member State', international_finance: 'Customary in international finance', host_official: 'Official language of a host Member State' }
const strip = (s?: string) => (s ?? '').replace(/^(\d+\.|\([a-z]\))\s*/, '')
const fmt = (v: unknown) => typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : v == null ? '—' : String(v)
const total = (v: unknown) => (v && typeof v === 'object' && 'total' in (v as object)) ? (v as { total: unknown }).total : v

function years(): string[] {
  const y = new Date().getFullYear()
  return [y - 1, y - 2, y - 3, y - 4].map(n => `${n}-12-31`)
}

export default function PaiStatement() {
  const qc = useQueryClient()
  const [period, setPeriod] = useState<string | null>(null)
  const q = useQuery({
    queryKey: ['pai-answers', period],
    queryFn: () => api.get<Data>(`/v1/entity/pai-statement/answers${period ? `?period_end=${period}` : ''}`),
    retry: false,
  })
  const d = q.data
  const [draft, setDraft] = useState<Record<string, Answer>>({})
  const [busy, setBusy] = useState(false)
  const [showMissing, setShowMissing] = useState(false)
  useEffect(() => { setDraft({}) }, [d?.period_end])
  const dirty = Object.keys(draft).length
  const get = (k: string): Answer => (k in draft ? draft[k] : d?.answers[k] ?? null)
  const put = (k: string, v: Answer) => setDraft(x => ({ ...x, [k]: v }))
  const rowAns = (k: string, col: 'expl' | 'action') => {
    const key = `${k}.${col}`
    if (key in draft) return draft[key]?.text ?? ''
    return d?.rows.find(r => r.key === k)?.[col] ?? ''
  }

  const save = async () => {
    if (!d) return
    setBusy(true)
    try {
      const answers = Object.fromEntries(Object.entries(draft).map(([k, v]) =>
        [k, v && (v.text === '' && v.applicable === undefined && v.ticked === undefined && !v.rows) ? null : v]))
      await api.put('/v1/entity/pai-statement/answers', { period_end: d.period_end, answers })
      toast.success('Saved for ' + d.period_end.slice(0, 4) + '.')
      setDraft({})
      qc.invalidateQueries({ queryKey: ['pai-answers'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save.')) }
    finally { setBusy(false) }
  }

  if (q.isLoading) return <Card className="p-5 text-[13px] text-[var(--color-faint)]">Loading the principal adverse impacts statement…</Card>
  if (!d) return <Card className="p-5 text-[13px] text-[var(--color-mute)]">{apiMessage(q.error, 'The statement could not be prepared.')}</Card>

  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <SectionHead hint={`Delegated Regulation (EU) 2022/1288 · Annex I · spec ${d.spec.version}`}>Principal adverse impacts statement</SectionHead>
          <p className="text-[12px] text-[var(--color-mute)] mt-1 max-w-[70ch]">
            Covers {d.reference_period.start} – {d.reference_period.end}. Every impact is the average of the impacts on {d.reference_period.impact_dates.join(', ')} (Article 6(3)). Answers below belong to this period only.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select className={`${box} w-auto`} value={d.period_end} onChange={e => setPeriod(e.target.value)} aria-label="Reference period">
            {Array.from(new Set([d.period_end, ...years()])).sort().reverse().map(p => <option key={p} value={p}>{p.slice(0, 4)}</option>)}
          </select>
          <Button onClick={save} disabled={busy || dirty === 0}>{busy ? 'Saving…' : dirty ? `Save ${dirty}` : 'Saved'}</Button>
        </div>
      </div>

      <button type="button" onClick={() => setShowMissing(s => !s)} className="flex items-center gap-2 text-[12.5px]">
        {d.ready_to_file ? <CheckCircle2 size={15} className="text-[var(--color-good)]" /> : <AlertTriangle size={15} className="text-[var(--color-warn)]" />}
        <span className={d.ready_to_file ? 'text-[var(--color-good)]' : 'text-[var(--color-warn)]'}>
          {d.ready_to_file ? 'Everything the Regulation requires is answered.' : `${d.missing.length} thing(s) the Regulation still requires`}
        </span>
        {!d.ready_to_file && (showMissing ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
      </button>
      {showMissing && !d.ready_to_file && (
        <ul className="text-[12px] text-[var(--color-mute)] space-y-1 pl-6 list-disc">{d.missing.map(m => <li key={m}>{m}</li>)}</ul>)}

      {d.sections.filter(s => s.id !== 'S7').map(s => (
        <SectionForm key={s.id} s={s} d={d} get={get} put={put} />
      ))}

      <div>
        <SectionHead className="mb-1">Table 1 — explanation and actions, per indicator</SectionHead>
        <p className="text-[12px] text-[var(--color-mute)] mb-2">
          Impact [year n-1]: {d.prior_period ? `as reported for ${d.prior_period.period_end} (${d.prior_period.source})` : 'no statement was reported for the previous period'}.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] min-w-[860px]">
            <thead><tr className="text-left text-[var(--color-faint)] mono text-[10px] uppercase">
              <th className="py-1.5 pr-3 w-[26%]">Indicator</th><th className="pr-3">Impact {d.period_end.slice(0, 4)}</th><th className="pr-3">Impact {Number(d.period_end.slice(0, 4)) - 1}</th>
              <th className="pr-3 w-[27%]">Explanation</th><th className="w-[27%]">Actions taken, and actions planned and targets set for the next reference period</th></tr></thead>
            <tbody>{d.rows.map(r => (
              <tr key={r.key} className="border-t border-[var(--color-line)] align-top">
                <td className="py-2 pr-3">{r.label}</td>
                <td className="py-2 pr-3 mono tabular-nums">{fmt(total(r.value))} <span className="text-[var(--color-faint)]">{r.unit}</span></td>
                <td className="py-2 pr-3 mono tabular-nums">{fmt(r.prior)}</td>
                <td className="py-2 pr-3"><textarea rows={2} className={box} value={rowAns(r.key, 'expl')} onChange={e => put(`${r.key}.expl`, { text: e.target.value })} aria-label={`${r.label} — explanation`} /></td>
                <td className="py-2"><textarea rows={2} className={box} value={rowAns(r.key, 'action')} onChange={e => put(`${r.key}.action`, { text: e.target.value })} aria-label={`${r.label} — actions`} /></td>
              </tr>))}</tbody>
          </table>
        </div>
      </div>

      <History d={d} />
      {d.legacy_narratives && <Legacy n={d.legacy_narratives} />}
    </Card>
  )
}

function SectionForm({ s, d, get, put }: { s: Section; d: Data; get: (k: string) => Answer; put: (k: string, v: Answer) => void }) {
  return (
    <div className="border-t border-[var(--color-line)] pt-4">
      <SectionHead hint={s.ref} className="mb-2">{s.title}</SectionHead>
      <div className="space-y-3">
        {s.items.filter(i => i.kind !== 'heading' && i.kind !== 'table_column').map(i => {
          const k = `${s.id}.${i.id}`
          if (i.kind === 'text') return <p key={k} className={`text-[12px] text-[var(--color-faint)] ${i.parent ? 'pl-4' : ''}`}>{i.label}</p>
          if (i.binding?.startsWith('computed')) return (
            <div key={k} className="text-[12.5px]"><div className="text-[var(--color-mute)]">{i.label}</div>
              <div className="mt-0.5">{k in d.computed ? d.computed[k] : <span className="text-[var(--color-faint)]">computed when filed</span>}</div></div>)
          if (k === 'S1.d_summary') return <SummaryRows key={k} item={i} value={get(k)} onChange={v => put(k, v)} />
          return <ItemInput key={k} k={k} item={i} value={get(k)} onChange={v => put(k, v)} />
        })}
      </div>
    </div>
  )
}

function ItemInput({ k, item, value, onChange }: { k: string; item: Item; value: Answer; onChange: (v: Answer) => void }) {
  const optional = item.binding === 'input:where_applicable'
  const label = <span className="text-[12.5px] text-[var(--color-mute)]">{strip(item.label)}</span>
  if (item.kind === 'choice') return (
    <div className={item.parent ? 'pl-4' : ''}>{label}
      <div className="flex gap-4 mt-1 text-[12.5px]">
        <label className="flex items-center gap-1.5"><input type="radio" name={k} checked={value?.ticked === true} onChange={() => onChange({ ticked: true, text: value?.text ?? '' })} /> Used</label>
        <label className="flex items-center gap-1.5"><input type="radio" name={k} checked={value?.ticked === false} onChange={() => onChange({ ticked: false })} /> Not used</label>
      </div>
      {value?.ticked && <textarea rows={2} className={`${box} mt-1`} placeholder="Name and provider of the scenario, and when it was designed" value={value.text ?? ''} onChange={e => onChange({ ticked: true, text: e.target.value })} />}
    </div>)
  return (
    <label className={`block ${item.parent ? 'pl-4' : ''}`}>{label}
      {optional && (
        <span className="flex items-center gap-1.5 text-[12px] text-[var(--color-faint)] mt-1">
          <input type="checkbox" checked={value?.applicable === false} onChange={e => onChange(e.target.checked ? { applicable: false } : { text: '' })} />
          {item.id === 'a_srd' ? 'Not applicable to us (stated)' : 'We have none (stated)'}
        </span>)}
      {value?.applicable !== false && (item.binding === 'input:date'
        ? <input type="date" className={`${box} mt-1 max-w-[200px]`} value={value?.text ?? ''} onChange={e => onChange({ text: e.target.value })} />
        : <textarea rows={item.binding === 'input:text' && !item.parent ? 3 : 2} className={`${box} mt-1`} value={value?.text ?? ''} onChange={e => onChange({ text: e.target.value })} />)}
    </label>
  )
}

function SummaryRows({ item, value, onChange }: { item: Item; value: Answer; onChange: (v: Answer) => void }) {
  const rows = value?.rows ?? []
  const set = (n: number, patch: Partial<SummaryRow>) => onChange({ rows: rows.map((r, i) => i === n ? { ...r, ...patch } : r) })
  const add = () => onChange({ rows: [...rows, { d_language: '', d_meets: [], d_member_state: null, d_text: '' }] })
  return (
    <div>
      <div className="text-[12.5px] text-[var(--color-mute)]">{strip(item.label)} — one text per language</div>
      <div className="space-y-3 mt-2">
        {rows.map((r, n) => (
          <div key={n} className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
            <div className="flex flex-wrap gap-3 items-center text-[12px]">
              <input className={`${box} w-[70px]`} maxLength={2} placeholder="en" value={r.d_language} onChange={e => set(n, { d_language: e.target.value.toLowerCase() })} aria-label="Language (ISO 639-1)" />
              {Object.entries(MEETS).map(([m, t]) => (
                <label key={m} className="flex items-center gap-1.5 text-[var(--color-mute)]">
                  <input type="checkbox" checked={r.d_meets.includes(m)} onChange={e => set(n, { d_meets: e.target.checked ? [...r.d_meets, m] : r.d_meets.filter(x => x !== m) })} />{t}</label>))}
              {r.d_meets.includes('host_official') && <input className={`${box} w-[80px]`} maxLength={2} placeholder="DE" value={r.d_member_state ?? ''} onChange={e => set(n, { d_member_state: e.target.value.toUpperCase() })} aria-label="Host Member State" />}
              <button type="button" className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-bad)]" onClick={() => onChange({ rows: rows.filter((_, i) => i !== n) })}>Remove</button>
            </div>
            <textarea rows={4} className={box} value={r.d_text} onChange={e => set(n, { d_text: e.target.value })} aria-label="Summary text" />
          </div>))}
        <Button variant="ghost" onClick={add}>Add a language</Button>
      </div>
    </div>
  )
}

function History({ d }: { d: Data }) {
  const s = d.sections.find(x => x.id === 'S7')
  const byPeriod = useMemo(() => {
    const m = new Map<string, number>()
    d.historical_comparison.rows.forEach(r => m.set(r.period, (m.get(r.period) ?? 0) + 1))
    return [...m.entries()]
  }, [d])
  return (
    <div className="border-t border-[var(--color-line)] pt-4">
      <SectionHead hint={s?.ref} className="mb-1">{s?.title ?? 'Historical comparison'}</SectionHead>
      <p className="text-[12px] text-[var(--color-mute)]">
        {d.historical_comparison.applies
          ? `Compared with ${byPeriod.map(([p, n]) => `${p} (${n} figures)`).join(', ')} — as reported, printed with the statement.`
          : 'Not applicable: no earlier statement was reported on. Upload one under Prior filings, stating whom it is for and its period end, to compare with it.'}
      </p>
    </div>
  )
}

function Legacy({ n }: { n: Record<string, string> }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border-t border-[var(--color-line)] pt-3">
      <button type="button" onClick={() => setOpen(o => !o)} className="flex items-center gap-1.5 text-[12px] text-[var(--color-faint)]">
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Earlier answers not tied to any period (for reference — not filed)
      </button>
      {open && <div className="mt-2 space-y-1.5 text-[12px]">{Object.entries(n).map(([k, v]) => (
        <div key={k}><span className="text-[var(--color-mute)] capitalize">{k.replace('_', ' ')}: </span>{v}</div>))}</div>}
    </div>
  )
}
