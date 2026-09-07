// The supervisory process, one entity at a time: five steps derived from what the platform holds, never ticked
// by hand. Filled = done, half = partly, empty = not yet, dashed = planned surface. Used on the Population table
// (compact) and at the top of the entity file (with details).
export interface Step { key: string; label: string; done: boolean; partial?: boolean; planned?: boolean; detail?: string }

export default function StageStrip({ steps, compact = false }: { steps: Step[]; compact?: boolean }) {
  return (
    <div className={`flex items-center ${compact ? 'gap-1' : 'gap-2 flex-wrap'}`} aria-label="Supervisory process">
      {steps.map((s, i) => {
        const color = s.done ? 'var(--color-good)' : s.partial ? 'var(--color-warn)' : s.planned ? 'var(--color-faint)' : 'var(--color-line)'
        return (
          <div key={s.key} className={`flex items-center ${compact ? '' : 'gap-2'}`} title={`${i + 1}. ${s.label}${s.detail ? ' — ' + s.detail : ''}`}>
            <span className="inline-flex items-center justify-center rounded-full shrink-0 mono"
              style={{ width: compact ? 18 : 26, height: compact ? 18 : 26, fontSize: compact ? 9.5 : 11.5,
                       background: s.done ? color : 'transparent', color: s.done ? '#fff' : color,
                       border: `${s.planned ? '1.5px dashed' : '1.5px solid'} ${color}`,
                       boxShadow: s.partial ? `inset 0 0 0 4px ${color}33` : undefined }}>{i + 1}</span>
            {!compact && (
              <div className="min-w-0 mr-3">
                <div className="text-[12px] leading-tight" style={{ color: s.done || s.partial ? 'var(--color-ink)' : 'var(--color-faint)' }}>{s.label}{s.planned ? <span className="mono text-[9px] uppercase ml-1 text-[var(--color-faint)]">planned</span> : null}</div>
                {s.detail && <div className="mono text-[10px] text-[var(--color-faint)] leading-tight">{s.detail}</div>}
              </div>)}
            {i < steps.length - 1 && <span className={`h-px ${compact ? 'w-2' : 'w-5'} shrink-0`} style={{ background: s.done ? 'var(--color-good)' : 'var(--color-line)' }} />}
          </div>)
      })}
    </div>
  )
}
