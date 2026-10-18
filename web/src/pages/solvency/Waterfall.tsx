import type { ReactNode } from 'react'
import { balance } from '../../lib/money'

// A bridge from one figure to another, row by row: a total is a bar from zero, a step floats from the running figure
// to the next one (a reduction in green). Each row's figures come from the server; the chart only lays them out.
export type Step = { label: ReactNode; value: number; total?: boolean; below?: ReactNode }

export default function Waterfall({ steps, label }: { steps: Step[]; label: string }) {
  let run = 0
  const rows = steps.map(s => {
    const from = s.total ? 0 : run
    const to = s.total ? s.value : run + s.value
    run = to
    return { ...s, from, to }
  })
  const max = Math.max(1, ...rows.map(r => Math.max(r.from, r.to)))
  const pct = (v: number) => `${(Math.max(0, v) / max) * 100}%`
  return (
    <div role="img" aria-label={label} className="space-y-2">
      {rows.map((r, i) => {
        const lo = Math.min(r.from, r.to), hi = Math.max(r.from, r.to)
        const tone = r.total ? 'var(--color-sky)' : r.value < 0 ? 'var(--color-good)' : 'var(--color-warn)'
        return (
          <div key={i}>
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className={r.total ? 'text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)]'}>{r.label}</span>
              <span className={`tabular-nums ${r.total ? 'text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)]'}`}>
                {r.total ? balance(r.value) : `${r.value < 0 ? '−' : '+'}${balance(Math.abs(r.value))}`}
              </span>
            </div>
            <div className="h-2.5 mt-1 rounded-full bg-[var(--color-panel-2)] relative overflow-hidden">
              {hi > lo && <div className="absolute inset-y-0 rounded-full" style={{ left: pct(lo), width: `max(3px, ${pct(hi - lo)})`, background: tone }} />}
            </div>
            {r.below && <div className="text-[11.5px] text-[var(--color-faint)] mt-1">{r.below}</div>}
          </div>
        )
      })}
    </div>
  )
}
