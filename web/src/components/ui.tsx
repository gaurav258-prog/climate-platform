import { type ReactNode } from 'react'
import clsx from 'clsx'

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

export function Card({ className, children, style, onClick }: { className?: string; children: ReactNode; style?: React.CSSProperties; onClick?: () => void }) {
  return <div className={clsx('card', className)} style={style} onClick={onClick}>{children}</div>
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <p className="mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-blue)] m-0">{children}</p>
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

export function Stat({ big, label, tone = 'ink' }: { big: ReactNode; label: string; tone?: 'ink' | 'good' | 'warn' | 'bad' }) {
  const c = { ink: 'text-[var(--color-ink)]', good: 'text-[var(--color-good)]', warn: 'text-[var(--color-warn)]', bad: 'text-[var(--color-bad)]' }[tone]
  return (
    <Card className="p-5">
      <div className={clsx('display text-3xl font-semibold leading-none', c)}>{big}</div>
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
    ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:bg-[var(--color-blue)]'
    : 'border border-[var(--color-line-2)] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]'
  return <button onClick={onClick} disabled={disabled} className={clsx(base, v, className)}>{children}</button>
}
