// Small, dependency-free, theme-aware SVG charts for the cockpit. No external libraries (CSP-safe).

interface Bar { label: string; value: number; color?: string; sub?: string }

// Horizontal bar chart — bars scaled to the max value. Good for "exposure by hazard".
export function HBar({ data, format, height = 22 }: { data: Bar[]; format: (n: number) => string; height?: number }) {
  const max = Math.max(1, ...data.map(d => Math.abs(d.value)))
  return (
    <div className="space-y-1.5">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="w-32 shrink-0 text-[11.5px] text-[var(--color-mute)] truncate text-right">{d.label}</div>
          <div className="flex-1 relative rounded" style={{ height, background: 'var(--color-panel-2)' }}>
            <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.max(2, (Math.abs(d.value) / max) * 100)}%`, background: d.color ?? 'var(--color-sky)', opacity: 0.85 }} />
            <div className="absolute inset-0 flex items-center px-2 text-[10.5px] mono" style={{ color: 'var(--color-ink)' }}>{format(d.value)}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// Diverging bars around a zero centre-line — good for period-over-period deltas (red up-risk / green down).
export function DivergingBars({ data, format }: { data: Bar[]; format: (n: number) => string }) {
  const max = Math.max(1, ...data.map(d => Math.abs(d.value)))
  return (
    <div className="space-y-1.5">
      {data.map((d, i) => {
        const pct = (Math.abs(d.value) / max) * 50
        const pos = d.value >= 0
        return (
          <div key={i} className="flex items-center gap-2">
            <div className="w-28 shrink-0 text-[11px] text-[var(--color-mute)] truncate text-right">{d.label}</div>
            <div className="flex-1 relative h-4">
              <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--color-line-2)]" />
              <div className="absolute inset-y-0 rounded-sm" style={{
                [pos ? 'left' : 'right']: '50%', width: `${Math.max(1, pct)}%`,
                background: pos ? '#fb7185' : '#34d399', opacity: 0.85,
              } as React.CSSProperties} />
            </div>
            <div className="w-20 text-right mono text-[10.5px]" style={{ color: d.value > 0 ? '#fb7185' : d.value < 0 ? '#34d399' : 'var(--color-faint)' }}>
              {d.value > 0 ? '+' : ''}{format(d.value)}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// A pair of stacked bars comparing prior vs now (for a headline reconciliation).
export function PairBars({ prior, now, format, labels = ['prior', 'now'] }: { prior: number; now: number; format: (n: number) => string; labels?: [string, string] }) {
  const max = Math.max(1, prior, now)
  const row = (v: number, lbl: string, tone: string) => (
    <div className="flex items-center gap-2">
      <div className="w-12 text-[10.5px] mono text-[var(--color-faint)] text-right">{lbl}</div>
      <div className="flex-1 h-4 rounded bg-[var(--color-panel-2)] relative">
        <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.max(2, (v / max) * 100)}%`, background: tone, opacity: 0.8 }} />
      </div>
      <div className="w-20 text-right mono text-[10.5px] text-[var(--color-mute)]">{format(v)}</div>
    </div>
  )
  return <div className="space-y-1.5">{row(prior, labels[0], 'var(--color-faint)')}{row(now, labels[1], 'var(--color-sky)')}</div>
}
