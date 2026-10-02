import { useState } from 'react'
import { Button } from '../ui'
import type { Comparatives, CmpRow } from './types'

// Comparative information (ESRS 1 chapter 7.1) for every figure of the statement: the previous period's figure — as the
// undertaking attests it, else as reported — and what the version's text asks where it is revised, absent or relieved.

const fmt = (v: unknown): string => typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 4 })
  : v && typeof v === 'object' ? Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k}: ${fmt(x)}`).join('; ') : v == null ? '—' : String(v)
const STATUS: Record<string, { t: string; c: string }> = {
  comparative: { t: 'comparative', c: 'var(--color-good)' }, revised: { t: 'revised — explained', c: 'var(--color-good)' },
  relief: { t: 'not required', c: 'var(--color-faint)' }, impracticable: { t: 'impracticable — stated', c: 'var(--color-faint)' },
  missing: { t: 'no comparative', c: 'var(--color-bad)' }, reason_missing: { t: 'reasons needed', c: 'var(--color-bad)' },
  state_significance: { t: 'significant?', c: 'var(--color-warn)' },
}
const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus:border-[var(--color-sky)]'

export default function EsrsComparatives({ c, v2026, onAnswer }: { c: Comparatives; v2026: boolean; onAnswer: (id: string, value: any) => Promise<void> }) {
  const open = c.rows.filter(r => !['comparative', 'relief'].includes(r.status))
  return (
    <div className="px-5 py-4 space-y-3 text-[12.5px]">
      <p className="text-[var(--color-mute)]">
        Previous period ending {c.previous_period_end} · reported: {c.reported.source ?? 'no statement held for it'}
        {c.reliefs.all ? ` · not required this year: ${c.reliefs.all}` : ''}
        {c.needs.length ? ` · state ${c.needs.join(', ')} to know whether a first-year relief applies` : ''}
      </p>
      {c.rows.length === 0 && <p className="text-[var(--color-faint)]">No figure of the statement is stated yet.</p>}
      {c.rows.length > 0 && <div className="overflow-x-auto">
        <table className="w-full min-w-[760px]">
          <thead><tr className="text-left mono text-[10px] uppercase text-[var(--color-faint)]">
            <th className="py-1 pr-3">Figure</th><th className="pr-3">This period</th><th className="pr-3">Previous period</th><th className="pr-3">As reported</th><th>Status</th></tr></thead>
          <tbody>{c.rows.map(r => {
            const s = STATUS[r.status] ?? { t: r.status, c: 'var(--color-mute)' }
            return (
              <tr key={`${r.item}-${r.concept}`} className="border-t border-[var(--color-line)] align-top">
                <td className="py-1.5 pr-3"><span className="mono text-[11px]">{r.item}</span> <span className="text-[var(--color-faint)]">{r.concept}</span></td>
                <td className="py-1.5 pr-3 mono tabular-nums">{fmt(r.current)}</td>
                <td className="py-1.5 pr-3 mono tabular-nums">{fmt(r.comparative)}{r.difference != null && <span className="text-[var(--color-warn)]"> (Δ {fmt(r.difference)})</span>}</td>
                <td className="py-1.5 pr-3 mono tabular-nums">{fmt(r.reported)}</td>
                <td className="py-1.5" style={{ color: s.c }}>{s.t}{r.relief ? <div className="text-[10.5px] text-[var(--color-faint)]">{r.relief}</div> : null}</td>
              </tr>)
          })}</tbody>
        </table>
      </div>}
      {open.length > 0 && <div className="space-y-3">{open.map(r => <Answer key={`${r.item}-${r.concept}`} r={r} v2026={v2026} onAnswer={onAnswer} />)}</div>}
      {v2026 && c.reported.source == null && <TopicFirstTime c={c} onAnswer={onAnswer} />}
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
    <div className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
      <div className="text-[var(--color-mute)]"><span className="mono text-[11px]">{r.item}</span> · {r.concept}</div>
      {revised ? <>
        <p className="text-[11.5px] text-[var(--color-faint)]">The previous period's figure differs from the one reported (difference {fmt(r.difference)}). {v2026
          ? 'Where it differs significantly, give the reasons for the change (2026 ESRS 1 §87(a)).' : 'Give the reasons for the revision (2023 ESRS 1 §84(b)).'}</p>
        {v2026 && <div className="flex gap-4 text-[12px]">
          <label className="flex items-center gap-1.5"><input type="radio" checked={sig === true} onChange={() => setSig(true)} /> Differs significantly</label>
          <label className="flex items-center gap-1.5"><input type="radio" checked={sig === false} onChange={() => setSig(false)} /> Not significantly</label></div>}
        {(!v2026 || sig) && <textarea rows={2} className={box} placeholder="Reasons for the revision" value={reason} onChange={e => setReason(e.target.value)} />}
        <Button onClick={() => onAnswer(id, { ...(v2026 ? { significant: sig } : {}), ...(reason.trim() ? { reason } : {}) })}
          disabled={v2026 ? sig === undefined || (sig && !reason.trim()) : !reason.trim()}>Save</Button>
      </> : <>
        <p className="text-[11.5px] text-[var(--color-faint)]">No comparative is stated or reported. State the previous period's figure under "Figures you state", or disclose that it is impracticable to provide (ESRS 1 §85).</p>
        <textarea rows={2} className={box} placeholder="Why the comparative is impracticable" value={imp} onChange={e => setImp(e.target.value)} />
        <Button onClick={() => onAnswer(id, { impracticable: imp })} disabled={!imp.trim()}>Save</Button>
      </>}
    </div>
  )
}

function TopicFirstTime({ c, onAnswer }: { c: Comparatives; onAnswer: (id: string, value: any) => Promise<void> }) {
  const stds = Array.from(new Set(c.rows.map(r => r.standard)))
  if (!stds.length) return null
  return (
    <div className="text-[12px] text-[var(--color-mute)] space-y-1">
      <div>No previous statement is held. A topic reported for the first time needs no comparative information (2026 ESRS 1 §87(b)):</div>
      <div className="flex gap-4">{stds.map(s => (
        <label key={s} className="flex items-center gap-1.5">
          <input type="checkbox" checked={!!c.topics_first_time[`topic.${s}`]} onChange={e => onAnswer(`topic.${s}`, e.target.checked ? { first_time: true } : null)} />
          ESRS {s} is reported for the first time</label>))}</div>
    </div>
  )
}
