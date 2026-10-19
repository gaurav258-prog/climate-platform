import { useState } from 'react'
import { Button } from '../ui'
import { HEADING, MessageLine, InfoButton, messageDetails } from '../Details'
import { StatusChip } from '../StatusChip'
import { SidePanel, Stack, TONE } from '../sfdr/visuals'
import { fmtDate } from '../sfdr/words'
import { CMP } from './words'
import type { Comparatives, CmpRow } from './types'

// Comparative information for every figure of the statement: the previous period's figure — as the undertaking attests
// it, else as reported — and, where a figure is revised, absent or relieved, what the version's text asks. The figures
// on the main screen; the undertaking's statements on them in a side panel.

const fmt = (v: unknown): string => typeof v === 'number' ? v.toLocaleString('en-GB', { maximumFractionDigits: 4 })
  : v && typeof v === 'object' ? Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${fmt(x)}`).join('; ') : v == null ? '—' : String(v)
const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:border-[var(--color-sky)]'
const TONES = { good: TONE.good, warn: TONE.warn, bad: TONE.bad, neutral: TONE.faint } as const

export default function EsrsComparatives({ c, v2026, onAnswer }: { c: Comparatives; v2026: boolean; onAnswer: (id: string, value: any) => Promise<void> }) {
  const [open, setOpen] = useState(false)
  const todo = c.rows.filter(r => !['comparative', 'relief', 'revised', 'impracticable'].includes(r.status))
  const count = (k: string) => c.rows.filter(r => r.status === k).length
  const firstTime = v2026 && c.reported.source == null && c.rows.length > 0
  return (
    <div className="px-5 py-4 space-y-4 text-[12.5px]">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <StatusChip tone="neutral" label={`Previous period ending ${fmtDate(c.previous_period_end)}`} />
        {c.reported.source_msg && <MessageLine m={c.reported.source_msg} className="text-[12px] text-[var(--color-mute)]" />}
        {c.reliefs.all_msg && <MessageLine m={c.reliefs.all_msg} className="text-[12px] text-[var(--color-good)]" />}
        {c.needs_msg && <MessageLine m={c.needs_msg} className="text-[12px] text-[var(--color-warn)]" />}
      </div>
      {c.rows.length === 0 ? <p className="text-[var(--color-faint)]">No figure of the statement is stated yet.</p> : <>
        <Stack parts={(['comparative', 'revised', 'relief', 'impracticable', 'state_significance', 'reason_missing', 'missing'] as const)
          .map(k => ({ n: count(k), tone: TONES[CMP[k].tone], label: CMP[k].label.toLowerCase() }))} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead><tr className="text-left text-[11px] text-[var(--color-faint)]">
              <th className="py-1 pr-3 font-normal">Figure</th><th className="pr-3 font-normal text-right">This period</th><th className="pr-3 font-normal text-right">Previous period</th>
              <th className="pr-3 font-normal text-right">As reported</th><th className="font-normal">Status</th></tr></thead>
            <tbody>{c.rows.map(r => {
              const s = CMP[r.status] ?? { label: 'Recorded', tone: 'neutral' as const }
              return (
                <tr key={`${r.item}-${r.concept}`} className="border-t border-[var(--color-line)] align-top">
                  <td className="py-1.5 pr-3 text-[var(--color-mute)]">{r.label ?? 'A figure'}</td>
                  <td className="py-1.5 pr-3 tabular-nums text-right text-[var(--color-ink)]">{fmt(r.current)}</td>
                  <td className="py-1.5 pr-3 tabular-nums text-right">{fmt(r.comparative)}{r.difference != null && <span className="text-[var(--color-warn)]"> (Δ {fmt(r.difference)})</span>}</td>
                  <td className="py-1.5 pr-3 tabular-nums text-right text-[var(--color-faint)]">{fmt(r.reported)}</td>
                  <td className="py-1.5"><span className="inline-flex items-center gap-1"><StatusChip tone={s.tone} label={s.label} />
                    {r.relief_msg && <InfoButton compact details={messageDetails(r.relief_msg)} />}</span></td>
                </tr>)
            })}</tbody>
          </table>
        </div>
      </>}
      {(todo.length > 0 || firstTime) && <Button variant="ghost" onClick={() => setOpen(true)}>{todo.length ? `Complete ${todo.length} comparative${todo.length === 1 ? '' : 's'}` : 'Topics reported for the first time'}</Button>}
      {open && (
        <SidePanel title="Comparative information" onClose={() => setOpen(false)}
          about={{ title: 'Comparative information', sections: [
            { heading: HEADING.read, body: 'Each figure is shown beside the previous period\'s. Where a previous figure is revised, say why; where none can be given, say that it is impracticable.' },
            { heading: 'Legal basis', body: 'ESRS 1, chapter 7.1: paragraphs 83 to 85 (2023), 87 (2026); first-year reliefs in paragraphs 136 (2023) and 124 (2026).' }] }}>
          <div className="space-y-3">
            {todo.map(r => <Answer key={`${r.item}-${r.concept}`} r={r} v2026={v2026} onAnswer={onAnswer} />)}
            {firstTime && <TopicFirstTime c={c} onAnswer={onAnswer} />}
          </div>
        </SidePanel>)}
    </div>
  )
}

function Answer({ r, v2026, onAnswer }: { r: CmpRow; v2026: boolean; onAnswer: (id: string, value: any) => Promise<void> }) {
  const a = r.answer ?? {}
  const [reason, setReason] = useState<string>(a.reason ?? '')
  const [imp, setImp] = useState<string>(a.impracticable ?? '')
  const [sig, setSig] = useState<boolean | undefined>(a.significant)
  const id = `cmp.${r.concept}`
  const revised = r.difference != null
  return (
    <div className="rounded-lg border border-[var(--color-line)] p-3 space-y-2 text-[12.5px]">
      <div className="text-[var(--color-ink)]">{r.label ?? 'A figure'}</div>
      {revised ? <>
        <p className="text-[12px] text-[var(--color-mute)]">The previous period's figure differs from the one reported (difference {fmt(r.difference)}). {v2026
          ? 'Where it differs significantly, give the reasons for the change.' : 'Give the reasons for the revision.'}</p>
        {v2026 && <div className="flex gap-4 text-[12px]">
          <label className="flex items-center gap-1.5"><input type="radio" checked={sig === true} onChange={() => setSig(true)} /> Differs significantly</label>
          <label className="flex items-center gap-1.5"><input type="radio" checked={sig === false} onChange={() => setSig(false)} /> Not significantly</label></div>}
        {(!v2026 || sig) && <textarea rows={2} className={box} placeholder="Reasons for the revision" value={reason} onChange={e => setReason(e.target.value)} />}
        <Button onClick={() => onAnswer(id, { ...(v2026 ? { significant: sig } : {}), ...(reason.trim() ? { reason } : {}) })}
          disabled={v2026 ? sig === undefined || (sig && !reason.trim()) : !reason.trim()}>Save</Button>
      </> : <>
        <p className="text-[12px] text-[var(--color-mute)]">No comparative is stated or reported. State the previous period's figure under Figures you state, or say why it is impracticable to provide.</p>
        <textarea rows={2} className={box} placeholder="Why the comparative is impracticable" value={imp} onChange={e => setImp(e.target.value)} />
        <Button onClick={() => onAnswer(id, { impracticable: imp })} disabled={!imp.trim()}>Save</Button>
      </>}
    </div>
  )
}

function TopicFirstTime({ c, onAnswer }: { c: Comparatives; onAnswer: (id: string, value: any) => Promise<void> }) {
  const stds = Array.from(new Set(c.rows.map(r => r.standard)))
  return (
    <div className="rounded-lg border border-[var(--color-line)] p-3 text-[12.5px] text-[var(--color-mute)] space-y-2">
      <div>No previous statement is held. A topic reported for the first time needs no comparative information.</div>
      <div className="flex flex-wrap gap-4">{stds.map(s => (
        <label key={s} className="flex items-center gap-1.5">
          <input type="checkbox" checked={!!c.topics_first_time[`topic.${s}`]} onChange={e => onAnswer(`topic.${s}`, e.target.checked ? { first_time: true } : null)} />
          {s} is reported for the first time</label>))}</div>
    </div>
  )
}
