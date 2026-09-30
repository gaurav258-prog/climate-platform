import { useState } from 'react'
import { Button } from '../ui'
import type { Item, Section, Datapoint } from './types'

// One ESRS standard of the statement, item by item in the regulation's order: the printed wording, each figure with
// its lane (computed by the platform, stated by the undertaking, derived) and previous-period figure, the undertaking's
// answers — and, for any item it does not report, the omission and its reason (not material, the item's printed
// condition does not apply, or a named phase-in).

type Answer = (standard: string, id: string, value: any) => Promise<void>

const REASONS = [
  { k: 'not_material', label: 'not material' },
  { k: 'condition_not_applicable', label: 'its condition does not apply' },
  { k: 'phase_in', label: 'phase-in' },
] as const
const LANE: Record<string, string> = { computed: 'computed', derived: 'derived', provided: 'you state it', same_as: 'reported elsewhere' }
const HORIZON: Record<string, string> = { short: 'short term', medium: 'medium term', long: 'long term' }
const input = 'block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]'

function fmt(v: any): string {
  if (v == null) return '—'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 6 })
  if (Array.isArray(v)) return v.map(fmt).join(', ')
  if (typeof v === 'object') return Object.entries(v).map(([k, x]) => `${k}: ${fmt(x)}`).join(' · ')
  return String(v)
}

function Figure({ d }: { d: Datapoint }) {
  const gap = d.status === 'gap' || d.status === 'missing'
  const unit = d.currency ?? (d.unit && !['count', 'boolean'].includes(d.unit) ? d.unit : '')
  const value = d.by_horizon
    ? Object.entries(d.by_horizon).map(([h, x]) => `${HORIZON[h] ?? h}: ${fmt(x)}`).join(' · ')
    : fmt(d.value)
  return (
    <div className="flex items-baseline gap-2 text-[11.5px] flex-wrap">
      <span className="mono text-[10.5px] text-[var(--color-faint)]">{d.key}</span>
      {gap
        ? <span className="text-[var(--color-warn)]">{d.gap ?? (d.lane === 'provided' ? 'not stated yet — state it under “Figures you state”' : 'not available')}</span>
        : <span className="tabular-nums text-[var(--color-ink)]">{value}{unit ? ` ${unit}` : ''}</span>}
      <span className="mono text-[10px] text-[var(--color-faint)]">{LANE[d.lane]}</span>
      {d.previous != null && <span className="text-[10.5px] text-[var(--color-faint)]">previous period {fmt(d.previous)}</span>}
    </div>
  )
}

function Editor({ it, phaseIns, onSave, onCancel }: {
  it: Item; phaseIns: { id: string; ref: string }[]; onSave: (v: any) => Promise<void>; onCancel: () => void
}) {
  const a = it.answer ?? {}
  const answerable = it.kind === 'question' || it.kind === 'choice' || (it.kind === 'field' && !!it.narrative)
  const [mode, setMode] = useState<'answer' | 'omit'>(it.status === 'omitted' || !answerable ? 'omit' : 'answer')
  const [text, setText] = useState<string>(a.text ?? '')
  const [yes, setYes] = useState<boolean | null>(typeof a.ticked === 'boolean' ? a.ticked : null)
  const [reason, setReason] = useState<string>(it.omission?.reason ?? 'not_material')
  const [statement, setStatement] = useState<string>(it.omission?.statement ?? '')
  const [phase, setPhase] = useState<string>(it.omission?.phase_in ?? '')
  const [busy, setBusy] = useState(false)
  const build = () => {
    if (mode === 'omit') return { omitted: { reason, ...(reason === 'phase_in' ? { phase_in: phase } : { statement }) } }
    if (it.kind === 'choice') return { ticked: yes }
    return { text }
  }
  const save = async () => { setBusy(true); try { await onSave(build()) } finally { setBusy(false) } }
  return (
    <div className="mt-2 space-y-2 max-w-xl">
      {answerable && (
        <div className="flex gap-3 text-[11.5px]">
          <label className="flex items-center gap-1"><input type="radio" checked={mode === 'answer'} onChange={() => setMode('answer')} /> report it</label>
          <label className="flex items-center gap-1"><input type="radio" checked={mode === 'omit'} onChange={() => setMode('omit')} /> omit it, with the reason</label>
        </div>
      )}
      {mode === 'answer' && it.kind === 'choice' && (
        <div className="flex gap-3 text-[12px]">
          <label className="flex items-center gap-1"><input type="radio" checked={yes === true} onChange={() => setYes(true)} /> yes</label>
          <label className="flex items-center gap-1"><input type="radio" checked={yes === false} onChange={() => setYes(false)} /> no</label>
        </div>
      )}
      {mode === 'answer' && it.kind !== 'choice' && answerable && (
        <textarea rows={it.kind === 'field' ? 2 : 4} value={text} onChange={e => setText(e.target.value)} className={input}
          placeholder={it.kind === 'field' ? 'the narrative this item asks for beside its figures' : 'answer'} />
      )}
      {mode === 'omit' && <>
        <select aria-label="Reason for omitting" value={reason} onChange={e => setReason(e.target.value)} className={input}>
          {REASONS.filter(r => r.k !== 'condition_not_applicable' || it.conditional).map(r => <option key={r.k} value={r.k}>{r.label}</option>)}
        </select>
        {reason === 'condition_not_applicable' && <div className="text-[10.5px] text-[var(--color-faint)]">Condition: {it.conditional}</div>}
        {reason === 'phase_in'
          ? <select aria-label="Phase-in" value={phase} onChange={e => setPhase(e.target.value)} className={input}>
              <option value="">choose the phase-in used…</option>
              {phaseIns.map(p => <option key={p.id} value={p.id}>{p.id} — {p.ref}</option>)}
            </select>
          : <textarea rows={2} value={statement} onChange={e => setStatement(e.target.value)} className={input} placeholder="say why" />}
      </>}
      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={save} disabled={busy}>Save</Button>
        {(it.answer || it.status === 'omitted') && <button onClick={() => onSave(null)} className="mono text-[11px] text-[var(--color-bad)] hover:underline">clear</button>}
        <button onClick={onCancel} className="mono text-[11px] text-[var(--color-mute)] hover:underline">cancel</button>
      </div>
    </div>
  )
}

const STATUS: Record<string, { c: string; label: string }> = {
  filled: { c: 'var(--color-good)', label: 'reported' },
  omitted: { c: 'var(--color-mute)', label: 'omitted' },
  missing: { c: 'var(--color-warn)', label: 'to do' },
}

export default function EsrsItems({ section, phaseIns, onAnswer, filter }: {
  section: Section; phaseIns: { id: string; ref: string }[]; onAnswer?: Answer; filter: 'all' | 'todo'
}) {
  const [editing, setEditing] = useState<string | null>(null)
  const topicOmitted = section.topic?.material === false
  const shown = section.items.filter(i => filter === 'all' || i.kind === 'heading' || i.status === 'missing')
  return (
    <div className="divide-y divide-[var(--color-line)]">
      {topicOmitted && <div className="px-5 py-3 text-[12px] text-[var(--color-mute)]">This topic is assessed not material: its items are omitted{section.topic?.explanation ? ` — ${section.topic.explanation}` : ''}.</div>}
      {shown.map(it => {
        if (it.kind === 'heading') return <div key={it.id} className="px-5 py-2.5 text-[13px] font-medium text-[var(--color-good)]">{it.label}</div>
        if (it.status === 'printed') return <div key={it.id} className="px-5 py-1.5 text-[11.5px] text-[var(--color-mute)]">{it.label}</div>
        const s = STATUS[it.status]
        const canEdit = onAnswer && !topicOmitted && editing !== it.id
        return (
          <div key={it.id} className="px-5 py-2.5">
            <div className="flex items-start justify-between gap-3">
              <div className="text-[12.5px] text-[var(--color-ink)] max-w-[78%]">
                <span className="mono text-[10.5px] text-[var(--color-faint)] mr-1.5">{it.note}</span>{it.label}
                {it.obligation === 'may' && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">voluntary</span>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className="mono text-[10px]" style={{ color: s.c }}>{s.label}</span>
                {canEdit && <button onClick={() => setEditing(it.id)} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">
                  {it.status === 'missing' ? (it.kind === 'field' && !it.narrative ? 'omit' : 'answer') : 'edit'}</button>}
              </div>
            </div>
            {it.datapoints && it.datapoints.length > 0 && <div className="mt-1 space-y-0.5">{it.datapoints.map(d => <Figure key={d.key} d={d} />)}</div>}
            {it.answer?.text && <div className="text-[12px] text-[var(--color-mute)] mt-1 whitespace-pre-wrap">{it.answer.text}</div>}
            {typeof it.answer?.ticked === 'boolean' && <div className="text-[12px] text-[var(--color-mute)] mt-1">{it.answer.ticked ? 'Yes' : 'No'}</div>}
            {it.status === 'omitted' && it.omission && !topicOmitted && (
              <div className="text-[11px] text-[var(--color-faint)] mt-1">Omitted — {REASONS.find(r => r.k === it.omission!.reason)?.label}
                {it.omission.phase_in ? ` (${it.omission.phase_in})` : ''}{it.omission.statement ? `: ${it.omission.statement}` : ''}</div>
            )}
            {editing === it.id && onAnswer && (
              <Editor it={it} phaseIns={phaseIns} onCancel={() => setEditing(null)}
                onSave={async v => { await onAnswer(section.standard, it.id, v); setEditing(null) }} />
            )}
          </div>
        )
      })}
    </div>
  )
}

export function Materiality({ sections, onAnswer }: { sections: Section[]; onAnswer: Answer }) {
  const [draft, setDraft] = useState<Record<string, { material: boolean | null; explanation: string }>>(
    Object.fromEntries(sections.map(s => [s.standard, { material: s.topic?.material ?? null, explanation: s.topic?.explanation ?? '' }])))
  const [busy, setBusy] = useState<string | null>(null)
  const save = async (t: string) => {
    const d = draft[t]
    if (d.material === null) return
    setBusy(t)
    try { await onAnswer('materiality', t, { material: d.material, ...(d.explanation.trim() ? { explanation: d.explanation.trim() } : {}) }) }
    finally { setBusy(null) }
  }
  return (
    <div className="grid gap-3 sm:grid-cols-3 p-5">
      {sections.map(s => {
        const d = draft[s.standard]
        const set = (p: Partial<typeof d>) => setDraft(x => ({ ...x, [s.standard]: { ...x[s.standard], ...p } }))
        return (
          <div key={s.standard} className="rounded border border-[var(--color-line)] p-3 space-y-2">
            <div className="text-[12.5px] font-medium text-[var(--color-ink)]">{s.title}</div>
            <div className="flex gap-3 text-[12px]">
              <label className="flex items-center gap-1"><input type="radio" checked={d.material === true} onChange={() => set({ material: true })} /> material</label>
              <label className="flex items-center gap-1"><input type="radio" checked={d.material === false} onChange={() => set({ material: false })} /> not material</label>
            </div>
            <textarea rows={2} value={d.explanation} onChange={e => set({ explanation: e.target.value })} className={input}
              placeholder={s.standard === 'E1' && d.material === false ? 'a detailed explanation is required for climate change' : 'basis of the assessment (optional)'} />
            <div className="flex items-center justify-between">
              <span className="mono text-[10px] text-[var(--color-faint)]">{s.topic == null ? 'not stated' : s.topic.material ? 'stated: material' : 'stated: not material'}</span>
              <Button variant="ghost" onClick={() => save(s.standard)} disabled={busy !== null || d.material === null}>Save</Button>
            </div>
          </div>
        )
      })}
    </div>
  )
}
