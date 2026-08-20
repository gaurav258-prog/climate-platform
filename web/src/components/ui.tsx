import { type ReactNode, useEffect, useRef, useState } from 'react'
import { Download } from 'lucide-react'
import clsx from 'clsx'

// ── Count-up number — the KPI/stat "hooked" micro-moment. Animates from 0 to the value on mount/change,
// respects prefers-reduced-motion (jumps straight to the value), and renders through a formatter so it works
// for euros, percentages, and plain counts. Skin-agnostic; the motion reads on every skin.
export function CountUp({ value, format = (n) => `${Math.round(n)}`, duration = 900, className }: {
  value: number; format?: (n: number) => string; duration?: number; className?: string
}) {
  const [display, setDisplay] = useState(0)   // start low so the count-up is actually seen on first mount
  const raf = useRef<number | null>(null)
  const from = useRef(0)
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    // no animation when reduced-motion, non-finite, or the tab is hidden (rAF is throttled/paused in
    // background tabs — animating there would leave the number stuck at 0). Land on the value directly.
    if (reduce || !isFinite(value) || (typeof document !== 'undefined' && document.hidden)) {
      setDisplay(value); from.current = value; return
    }
    const start = performance.now(); const a = from.current; const b = value
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)  // ease-out cubic
      setDisplay(a + (b - a) * eased)
      if (p < 1) raf.current = requestAnimationFrame(tick)
      else from.current = b
    }
    raf.current = requestAnimationFrame(tick)
    // safety net: guarantee we land on the exact value even if rAF stalls (backgrounded mid-animation).
    const safety = window.setTimeout(() => { setDisplay(b); from.current = b }, duration + 150)
    return () => { if (raf.current) cancelAnimationFrame(raf.current); clearTimeout(safety) }
  }, [value, duration])
  return <span className={className}>{format(display)}</span>
}

// Count-up for an ALREADY-formatted KPI string ("€648.1m", "70%", "1,240"). Parses the single leading number,
// animates it, and re-assembles with the original prefix/suffix/precision — so any KPI grid gets the count-up
// moment with no numeric plumbing. Falls back to the plain string for anything it can't cleanly parse
// (fractions like "129/145", ranges, status text), so it's always safe to drop in.
export function CountUpText({ children, className, duration }: { children: string; className?: string; duration?: number }) {
  const text = String(children ?? '')
  const m = /^(\D*)(\d[\d,]*(?:\.\d+)?)(.*)$/.exec(text.trim())
  if (!m || m[3].includes('/')) return <span className={className}>{text}</span>
  const [, pre, numStr, suf] = m
  const decimals = numStr.includes('.') ? numStr.split('.')[1].length : 0
  const hadComma = numStr.includes(',')
  const value = parseFloat(numStr.replace(/,/g, ''))
  if (!isFinite(value)) return <span className={className}>{text}</span>
  const fmt = (n: number) => pre + (hadComma
    ? n.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
    : n.toFixed(decimals)) + suf
  return <CountUp value={value} format={fmt} duration={duration} className={className} />
}

// The one consistent "export what I'm looking at" control — wired to lib/export downloadCsv on every view,
// so extract-to-your-own-tool is a standard affordance across all sectors, not an ad-hoc per-page button.
export function ExportButton({ onExport, label = 'CSV', className }: { onExport: () => void; label?: string; className?: string }) {
  return (
    <button onClick={onExport} title="Download this view as CSV"
      className={clsx('inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition', className)}>
      <Download size={13} /> {label}
    </button>
  )
}

export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden style={{ display: 'block' }}>
      <defs>
        <linearGradient id="tm-h" x1="24" y1="4" x2="24" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1560c4" /><stop offset="1" stopColor="#06152e" />
        </linearGradient>
        <radialGradient id="tm-l" cx="24" cy="22" r="15" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#fff" /><stop offset="0.35" stopColor="#9fd4ff" />
          <stop offset="0.7" stopColor="#3aa0ff" stopOpacity="0.35" /><stop offset="1" stopColor="#3aa0ff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <polygon points="44,24 34,41.3 14,41.3 4,24 14,6.7 34,6.7" fill="url(#tm-h)" stroke="#6cb8ff" strokeWidth="3" strokeLinejoin="round" />
      <circle cx="24" cy="22" r="12" fill="url(#tm-l)" />
      <circle cx="24" cy="21" r="4.6" fill="#f2f9ff" />
    </svg>
  )
}

// `lift` opts a card into the hover-lift micro-interaction (used for clickable/drillable cards). The transform
// lives only during :hover (see skins.css) so it never leaves a retained transform that would trap fixed drawers.
export function Card({ className, children, style, onClick, lift }: { className?: string; children: ReactNode; style?: React.CSSProperties; onClick?: () => void; lift?: boolean }) {
  return <div className={clsx('card', lift && 'lift', className)} style={style} onClick={onClick}>{children}</div>
}

// The page's flow-stage hue tints the eyebrow (Shell sets --stage per route), so a page's header echoes
// its nav stage. Falls back to the neutral blue where --stage isn't set (e.g. login, standalone screens).
export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mono text-[11px] uppercase tracking-[0.2em] m-0" style={{ color: 'var(--stage, var(--color-blue))' }}>{children}</p>
}

// The three oversight lenses over the same book. Each surface declares which lens it is, so the
// Control / Governance / Insight frame is legible to users:
//   Control    — "did we get it right?"     blocks a filing until every check clears   (Control Tower)
//   Governance — "is risk in appetite?"     thresholds, status & trend, escalates      (KRI)
//   Insight    — "why · what-if?"           drivers, lineage & scenarios, explains     (Analytics)
const LENS = {
  control: { name: 'Control', q: 'did we get it right?' },
  governance: { name: 'Governance', q: 'is risk in appetite?' },
  insight: { name: 'Insight', q: 'why · what-if?' },
} as const

export function Lens({ kind, className }: { kind: keyof typeof LENS; className?: string }) {
  const l = LENS[kind]
  return (
    <span
      title="Tellumen's three oversight lenses — Control (did we get it right?) · Governance (is risk in appetite?) · Insight (why & what-if?)"
      className={clsx('inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1 whitespace-nowrap', className)}>
      <span className="mono text-[9.5px] uppercase tracking-[0.14em] font-semibold text-[var(--color-sky)]">{l.name}</span>
      <span className="text-[11px] text-[var(--color-faint)]">{l.q}</span>
    </span>
  )
}

// The one readable section/card heading used across the platform — a blue icon + a bold ~16px title,
// with an optional muted descriptor after a "·". Replaces the old tiny 10.5px mono-uppercase header bars,
// which were hard to read and identify. Chart axis/column micro-labels stay small — those are captions.
export function SectionHead({ icon: Icon, hint, children, className }: {
  icon?: React.ComponentType<{ size?: number; className?: string }>
  hint?: ReactNode; children: ReactNode; className?: string
}) {
  return (
    <div className={clsx('flex items-center gap-2 min-w-0 flex-wrap', className)}>
      {Icon && <Icon size={16} className="text-[var(--color-blue)] shrink-0" />}
      <h3 className="font-semibold text-[15.5px] text-[var(--color-ink)] leading-tight m-0">{children}</h3>
      {hint && <span className="text-[13px] text-[var(--color-mute)] hidden sm:inline">· {hint}</span>}
    </div>
  )
}

export function Stat({ big, label, tone = 'ink' }: { big: ReactNode; label: string; tone?: 'ink' | 'good' | 'warn' | 'bad' }) {
  const c = { ink: 'text-[var(--color-ink)]', good: 'text-[var(--color-good)]', warn: 'text-[var(--color-warn)]', bad: 'text-[var(--color-bad)]' }[tone]
  return (
    <Card className="p-5">
      <div className={clsx('display text-3xl font-semibold leading-none tabular-nums', c)}>
        {typeof big === 'string' ? <CountUpText>{big}</CountUpText> : big}
      </div>
      <div className="text-xs text-[var(--color-mute)] mt-2">{label}</div>
    </Card>
  )
}

const STATUS: Record<string, { label: string; cls: string }> = {
  deforestation_free: { label: 'Deforestation-free', cls: 'text-[var(--color-good)] bg-[color-mix(in_oklab,var(--color-good)_14%,transparent)]' },
  non_compliant: { label: 'Non-compliant', cls: 'text-[var(--color-bad)] bg-[color-mix(in_oklab,var(--color-bad)_14%,transparent)]' },
  geolocation_incomplete: { label: 'Needs polygon', cls: 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]' },
  insufficient: { label: 'Insufficient', cls: 'text-[var(--color-slate)] bg-[color-mix(in_oklab,var(--color-slate)_16%,transparent)]' },
  not_covered: { label: 'Not EUDR', cls: 'text-[var(--color-faint)] bg-[color-mix(in_oklab,var(--color-faint)_16%,transparent)]' },
  not_determined: { label: 'Not checked', cls: 'text-[var(--color-faint)] bg-[color-mix(in_oklab,var(--color-faint)_14%,transparent)]' },
}

export function StatusPill({ status }: { status: string | null | undefined }) {
  const s = STATUS[status || 'not_determined'] ?? STATUS.not_determined
  return <span className={clsx('mono text-[10.5px] font-medium px-2.5 py-1 rounded-full whitespace-nowrap', s.cls)}>{s.label}</span>
}

export function Button({ children, onClick, variant = 'primary', disabled, className }: {
  children: ReactNode; onClick?: () => void; variant?: 'primary' | 'ghost'; disabled?: boolean; className?: string
}) {
  const base = 'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition disabled:opacity-50 disabled:cursor-not-allowed'
  const v = variant === 'primary'
    ? 'btn-accent bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:bg-[var(--color-blue)]'
    : 'border border-[var(--color-line-2)] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]'
  return <button onClick={onClick} disabled={disabled} className={clsx(base, v, className)}>{children}</button>
}
