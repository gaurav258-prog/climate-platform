import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, ChevronRight, ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import { Button, Card, SectionHead } from '../ui'
import { api, apiMessage, apiDetail } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Dialog } from '../Dialog'
import { HEADING, InfoButton, MessageLine, type Message } from '../Details'
import { StatusChip } from '../StatusChip'
import { Ring, SidePanel, num, TONE } from './visuals'
import { fmtDate } from './words'

// The manager's principal adverse impacts statement for one reference period: how far it is answered, section by section,
// and each indicator's impact against the previous period. Every section opens in a side panel, worded as the
// Regulation words it, with the manager's answers for the period; only the items the Regulation leaves to the manager
// are answered there — the rest is computed.

interface Item { id: string; kind: string; label?: string; parent: string | null; binding?: string | null }
interface Section { id: string; title: string; ref: string; items: Item[] }
interface Row { key: string; label: string; value: unknown; unit?: string; prior?: number | null; expl?: string | null; action?: string | null }
interface SummaryRow { d_language: string; d_meets: string[]; d_member_state: string | null; d_text: string }
type Answer = { text?: string; applicable?: boolean; ticked?: boolean; rows?: SummaryRow[] } | null
type Gap = Message & { params?: { section?: string } }
interface Data {
  period_end: string; reference_period: { start: string; end: string; impact_dates: string[] }
  spec: { version: string }; sections: Section[]; computed: Record<string, string>; answers: Record<string, Answer>
  rows: Row[]; gaps: Gap[]; prior_source: Message; ready_to_file: boolean
  historical_comparison: { applies: boolean; periods?: { period_end: string }[]; rows: { period: string }[] }
  legacy_narratives: Record<string, string> | null
}

// the panels, in the statement's order: the sections the manager answers, then Table 1's explanations and actions
const PANELS = [
  { id: 'S1', name: 'Summary' }, { id: 'S4', name: 'Policies' }, { id: 'S5', name: 'Engagement policies' },
  { id: 'S6', name: 'International standards' }, { id: 'T1', name: 'Explanations and actions' },
] as const
const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
const MEETS: Record<string, string> = { home_official: 'An official language of the home country', international_finance: 'Customary in international finance', host_official: 'An official language of a host country' }
const strip = (s?: string) => (s ?? '').replace(/^(\d+\.|\([a-z]\))\s*/, '')
const total = (v: unknown) => (v && typeof v === 'object' && 'total' in (v as object)) ? (v as { total: unknown }).total : v
const figure = (v: unknown) => (typeof v === 'number' ? num(v, 2) : v == null ? '—' : String(v))

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
  const [open, setOpen] = useState<string | null>(null)
  useEffect(() => { setDraft({}) }, [d?.period_end])
  const dirty = Object.keys(draft).length
  const get = (k: string): Answer => (k in draft ? draft[k] : d?.answers[k] ?? null)
  const put = (k: string, v: Answer) => setDraft(x => ({ ...x, [k]: v }))

  const save = async () => {
    if (!d) return
    setBusy(true)
    try {
      const answers = Object.fromEntries(Object.entries(draft).map(([k, v]) =>
        [k, v && (v.text === '' && v.applicable === undefined && v.ticked === undefined && !v.rows) ? null : v]))
      await api.put('/v1/entity/pai-statement/answers', { period_end: d.period_end, answers })
      toast.success(`Saved for ${d.period_end.slice(0, 4)}.`)
      setDraft({})
      qc.invalidateQueries({ queryKey: ['pai-answers'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save.')) }
    finally { setBusy(false) }
  }

  if (q.isLoading) return <Card className="p-5 text-[13px] text-[var(--color-faint)]">Loading the adverse impacts statement…</Card>
  if (!d) return (
    <Card className="p-5">
      <SectionHead icon={FileText} className="mb-2">Principal adverse impacts statement</SectionHead>
      <MessageLine m={{ label: apiMessage(q.error, 'The statement could not be prepared.'), detail: apiDetail(q.error) }} className="text-[13px] text-[var(--color-mute)]" />
    </Card>)

  const gapsOf = (id: string) => d.gaps.filter(g => g.params?.section === id)
  const other = d.gaps.filter(g => !g.params?.section)
  const done = PANELS.filter(p => gapsOf(p.id).length === 0).length
  const year = d.period_end.slice(0, 4)
  const about = {
    title: 'Principal adverse impacts statement', sections: [
      { heading: HEADING.shows, body: `Your statement for 1 January – 31 December ${year}: how far each section is answered, and each indicator's impact against the previous period.` },
      { heading: HEADING.read, body: `Every impact is the average of the impacts on ${d.reference_period.impact_dates.map(fmtDate).join(', ')}. Answers belong to this period only.` },
      { heading: 'Legal basis', body: `Delegated Regulation (EU) 2022/1288, Annex I (Table 1) and Articles 4 to 10.` },
    ],
  }
  const panel = PANELS.find(p => p.id === open)
  const section = d.sections.find(s => s.id === open)

  return (
    <Card className="p-5 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <SectionHead icon={FileText}>Principal adverse impacts statement</SectionHead>
          <InfoButton compact details={about} />
        </div>
        <div className="flex items-center gap-2">
          <select className={`${box} w-auto`} value={d.period_end} onChange={e => setPeriod(e.target.value)} aria-label="Reference period">
            {Array.from(new Set([d.period_end, ...years()])).sort().reverse().map(p => <option key={p} value={p}>{p.slice(0, 4)}</option>)}
          </select>
          {dirty > 0 && <Button onClick={save} disabled={busy}>{busy ? 'Saving…' : `Save ${dirty}`}</Button>}
        </div>
      </div>

      {/* how far it is answered */}
      <div className="flex flex-wrap items-center gap-5">
        <Ring value={(done / PANELS.length) * 100} tone={d.ready_to_file ? TONE.good : TONE.warn}>{done}/{PANELS.length}</Ring>
        <div className="space-y-1.5 min-w-0">
          {d.ready_to_file ? <StatusChip tone="good" label="Ready to file" /> : <StatusChip tone="warn" label={`${d.gaps.length} thing${d.gaps.length === 1 ? '' : 's'} to complete`} />}
          <div className="text-[12px] text-[var(--color-faint)]">Sections complete for {year}</div>
          {other.map((g, i) => <MessageLine key={i} m={g} className="text-[12px] text-[var(--color-warn)]" />)}
        </div>
      </div>

      {/* one tile per section */}
      <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {PANELS.map(p => {
          const n = gapsOf(p.id).length
          return (
            <button key={p.id} type="button" onClick={() => setOpen(p.id)}
              className="text-left rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 hover:border-[var(--color-sky)] transition flex items-center justify-between gap-3">
              <span className="min-w-0">
                <span className="block text-[13px] text-[var(--color-ink)]">{p.name}</span>
                <span className="block mt-1">{n ? <StatusChip tone="warn" label={`${n} to answer`} /> : <StatusChip tone="good" label="Complete" />}</span>
              </span>
              <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />
            </button>)
        })}
        <button type="button" onClick={() => setOpen('S7')}
          className="text-left rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 hover:border-[var(--color-sky)] transition flex items-center justify-between gap-3">
          <span className="min-w-0">
            <span className="block text-[13px] text-[var(--color-ink)]">Historical comparison</span>
            <span className="block mt-1"><StatusChip tone="neutral" label={d.historical_comparison.applies ? `${(d.historical_comparison.periods ?? []).length} earlier period(s)` : 'No earlier period'} /></span>
          </span>
          <ChevronRight size={15} className="text-[var(--color-faint)] shrink-0" />
        </button>
      </div>

      {/* the impacts against the previous period */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[13px] font-medium text-[var(--color-ink)]">Impacts</span>
          <MessageLine m={d.prior_source} className="text-[12px] text-[var(--color-faint)]" />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px] min-w-[520px]">
            <thead><tr className="text-left text-[11px] text-[var(--color-faint)]">
              <th className="py-1.5 pr-3 font-normal">Indicator</th><th className="pr-3 font-normal text-right">{year}</th>
              <th className="pr-3 font-normal text-right">{Number(year) - 1}</th><th className="font-normal w-10" /></tr></thead>
            <tbody>{d.rows.map(r => {
              const now = total(r.value), was = r.prior
              const up = typeof now === 'number' && typeof was === 'number' ? Math.sign(now - was) : null
              return (
                <tr key={r.key} className="border-t border-[var(--color-line)]">
                  <td className="py-2 pr-3 text-[var(--color-mute)]">{r.label}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-[var(--color-ink)]">{figure(now)} <span className="text-[11px] text-[var(--color-faint)]">{r.unit}</span></td>
                  <td className="py-2 pr-3 text-right tabular-nums text-[var(--color-faint)]">{figure(was)}</td>
                  <td className="py-2 text-center">{up == null ? null : up > 0 ? <ArrowUpRight size={14} className="text-[var(--color-warn)] inline" aria-label="Higher than the previous period" />
                    : up < 0 ? <ArrowDownRight size={14} className="text-[var(--color-good)] inline" aria-label="Lower than the previous period" /> : <Minus size={14} className="text-[var(--color-faint)] inline" aria-label="Unchanged" />}</td>
                </tr>)
            })}</tbody>
          </table>
        </div>
      </div>

      {d.legacy_narratives && <Legacy n={d.legacy_narratives} />}

      {open && open !== 'S7' && panel && (
        <SidePanel title={panel.name} wide={open === 'T1'} onClose={() => setOpen(null)}
          about={{ title: panel.name, sections: [{ heading: 'Legal basis', body: open === 'T1' ? 'Delegated Regulation (EU) 2022/1288, Article 6(1) and (2): Table 1, columns Explanation and Actions taken.' : `Delegated Regulation (EU) 2022/1288, ${section?.ref ?? 'Annex I'}.` }] }}>
          <div className="space-y-4">
            {gapsOf(open).length > 0 && (
              <div className="rounded-lg border border-[var(--color-line)] p-3 space-y-1">
                {gapsOf(open).map((g, i) => <MessageLine key={i} m={g} className="text-[12px] text-[var(--color-warn)]" />)}
              </div>)}
            {open === 'T1' ? <TableAnswers d={d} get={get} put={put} /> : section && <SectionForm s={section} d={d} get={get} put={put} />}
            <div className="flex items-center gap-3 pt-2 border-t border-[var(--color-line)]">
              <Button onClick={save} disabled={busy || dirty === 0}>{busy ? 'Saving…' : dirty ? `Save ${dirty}` : 'Saved'}</Button>
              <span className="text-[11.5px] text-[var(--color-faint)]">Answers belong to {year} only.</span>
            </div>
          </div>
        </SidePanel>)}
      {open === 'S7' && <History d={d} onClose={() => setOpen(null)} />}
    </Card>
  )
}

function SectionForm({ s, d, get, put }: { s: Section; d: Data; get: (k: string) => Answer; put: (k: string, v: Answer) => void }) {
  return (
    <div className="space-y-3">
      {s.items.filter(i => i.kind !== 'heading' && i.kind !== 'table_column').map(i => {
        const k = `${s.id}.${i.id}`
        if (i.kind === 'text') return <p key={k} className={`text-[12px] text-[var(--color-faint)] ${i.parent ? 'pl-4' : ''}`}>{i.label}</p>
        if (i.binding?.startsWith('computed')) return (
          <div key={k} className="text-[12.5px]"><div className="text-[var(--color-mute)]">{i.label}</div>
            <div className="mt-0.5 text-[var(--color-ink)]">{k in d.computed ? d.computed[k] : <span className="text-[var(--color-faint)]">Computed when filed</span>}</div></div>)
        if (k === 'S1.d_summary') return <SummaryRows key={k} item={i} value={get(k)} onChange={v => put(k, v)} />
        return <ItemInput key={k} k={k} item={i} value={get(k)} onChange={v => put(k, v)} />
      })}
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
          {item.id === 'a_srd' ? 'Does not apply to us (stated)' : 'We have none (stated)'}
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
              <input className={`${box} w-[70px]`} maxLength={2} placeholder="en" value={r.d_language} onChange={e => set(n, { d_language: e.target.value.toLowerCase() })} aria-label="Language, two letters" />
              {Object.entries(MEETS).map(([m, t]) => (
                <label key={m} className="flex items-center gap-1.5 text-[var(--color-mute)]">
                  <input type="checkbox" checked={r.d_meets.includes(m)} onChange={e => set(n, { d_meets: e.target.checked ? [...r.d_meets, m] : r.d_meets.filter(x => x !== m) })} />{t}</label>))}
              {r.d_meets.includes('host_official') && <input className={`${box} w-[80px]`} maxLength={2} placeholder="DE" value={r.d_member_state ?? ''} onChange={e => set(n, { d_member_state: e.target.value.toUpperCase() })} aria-label="Host country, two letters" />}
              <button type="button" className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-bad)]" onClick={() => onChange({ rows: rows.filter((_, i) => i !== n) })}>Remove</button>
            </div>
            <textarea rows={4} className={box} value={r.d_text} onChange={e => set(n, { d_text: e.target.value })} aria-label="Summary text" />
          </div>))}
        <Button variant="ghost" onClick={add}>Add a language</Button>
      </div>
    </div>
  )
}

// Table 1's last two columns, per indicator: the explanation, and the actions taken and planned with targets
function TableAnswers({ d, get, put }: { d: Data; get: (k: string) => Answer; put: (k: string, v: Answer) => void }) {
  const text = (k: string, col: 'expl' | 'action') => {
    const key = `${k}.${col}`
    const a = get(key)
    return a ? a.text ?? '' : d.rows.find(r => r.key === k)?.[col] ?? ''
  }
  return (
    <div className="space-y-4">
      {d.rows.map(r => (
        <div key={r.key} className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[12.5px] text-[var(--color-ink)]">{r.label}</span>
            <span className="text-[12px] tabular-nums text-[var(--color-mute)] shrink-0">{figure(total(r.value))} {r.unit}</span>
          </div>
          <textarea rows={2} className={box} placeholder="Explanation" value={text(r.key, 'expl')} onChange={e => put(`${r.key}.expl`, { text: e.target.value })} aria-label={`${r.label}: explanation`} />
          <textarea rows={2} className={box} placeholder="Actions taken, and actions planned and targets set for the next period" value={text(r.key, 'action')} onChange={e => put(`${r.key}.action`, { text: e.target.value })} aria-label={`${r.label}: actions`} />
        </div>))}
    </div>
  )
}

function History({ d, onClose }: { d: Data; onClose: () => void }) {
  const s = d.sections.find(x => x.id === 'S7')
  const periods = d.historical_comparison.periods ?? []
  const count = (p: string) => d.historical_comparison.rows.filter(r => r.period === p).length
  return (
    <SidePanel title="Historical comparison" onClose={onClose}
      about={{ title: 'Historical comparison', sections: [{ heading: 'Legal basis', body: `Delegated Regulation (EU) 2022/1288, ${s?.ref ?? 'Article 10'}.` }] }}>
      {periods.length === 0
        ? <MessageLine m={d.prior_source} className="text-[13px] text-[var(--color-mute)]" />
        : <div className="space-y-2">
            {periods.map(p => (
              <div key={p.period_end} className="flex items-center justify-between rounded-lg border border-[var(--color-line)] px-3 py-2 text-[12.5px]">
                <span className="text-[var(--color-ink)]">{p.period_end.slice(0, 4)}</span>
                <span className="text-[var(--color-mute)] tabular-nums">{count(p.period_end)} figures, as reported</span>
              </div>))}
          </div>}
    </SidePanel>
  )
}

function Legacy({ n }: { n: Record<string, string> }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="text-[12px] text-[var(--color-faint)] hover:text-[var(--color-sky)]">Earlier answers not tied to a period</button>
      {open && (
        <Dialog title="Earlier answers not tied to a period" onClose={() => setOpen(false)} className="max-w-xl">
          <div className="space-y-2 text-[12.5px]">{Object.entries(n).map(([k, v]) => (
            <div key={k}><div className="text-[var(--color-mute)] capitalize">{k.replace(/_/g, ' ')}</div><div className="text-[var(--color-ink)]">{v}</div></div>))}</div>
        </Dialog>)}
    </>
  )
}

