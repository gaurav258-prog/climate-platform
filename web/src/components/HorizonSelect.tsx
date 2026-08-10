import { useState } from 'react'

// User-selectable projection horizon. The engine is MODELLED at anchor years (2025 'current', 2030, 2050,
// 2100); a year in between is interpolated server-side and flagged here as "interp" so it's never mistaken
// for an independently modelled node. Emits the API `horizon` token: 'current' or a calendar year string.
const NOW = 2025
export const HZ_ANCHORS = new Set(['current', '2030', '2050', '2100'])
const PRESETS: { token: string; label: string }[] = [
  { token: 'current', label: 'Now' },
  { token: String(NOW + 1), label: '+1y' },
  { token: String(NOW + 3), label: '+3y' },
  { token: '2030', label: '2030' },
  { token: '2050', label: '2050' },
  { token: '2100', label: '2100' },
]
export const DEFAULT_HORIZON = String(NOW + 3)   // operational surfaces open near-term (+3y)

export function isInterpolated(token: string): boolean {
  return !HZ_ANCHORS.has(token)
}
export function horizonLabel(token: string): string {
  if (token === 'current') return 'Now'
  const p = PRESETS.find(x => x.token === token)
  if (p) return p.label
  const y = parseInt(token, 10)
  return Number.isFinite(y) ? (y > NOW ? `+${y - NOW}y` : String(y)) : token
}

export default function HorizonSelect({ value, onChange, className = '' }: {
  value: string; onChange: (token: string) => void; className?: string
}) {
  const [custom, setCustom] = useState(false)
  const known = value === 'current' || PRESETS.some(p => p.token === value)
  const interp = isInterpolated(value)
  return (
    <div className={`inline-flex items-center gap-2 ${className}`}>
      <span className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">Horizon</span>
      {!custom ? (
        <select
          value={known ? value : '__custom__'}
          onChange={e => { const v = e.target.value; if (v === '__custom__') { setCustom(true) } else onChange(v) }}
          className="rounded-md border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]">
          {PRESETS.map(p => <option key={p.token} value={p.token}>{p.label}{p.token !== 'current' && !HZ_ANCHORS.has(p.token) ? ` · ${NOW + (parseInt(p.token) - NOW)}` : ''}</option>)}
          {!known && <option value={value}>{horizonLabel(value)} · {value}</option>}
          <option value="__custom__">Custom year…</option>
        </select>
      ) : (
        <input autoFocus type="number" min={NOW} max={2100} defaultValue={parseInt(value) || NOW + 3}
          onKeyDown={e => { if (e.key === 'Enter') { onChange(String((e.target as HTMLInputElement).value)); setCustom(false) } }}
          onBlur={e => { const v = e.target.value; if (v) onChange(String(v)); setCustom(false) }}
          placeholder="year"
          className="w-20 rounded-md border border-[var(--color-sky)] bg-[var(--color-panel)] px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none" />
      )}
      {interp && <span className="mono text-[8.5px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 12%, transparent)' }} title="Interpolated between modelled anchor years (2025 / 2030 / 2050 / 2100) — not an independently modelled node.">interp</span>}
    </div>
  )
}
