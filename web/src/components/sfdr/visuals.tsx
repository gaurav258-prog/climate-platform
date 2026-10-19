import type { ReactNode } from 'react'
import { Drawer } from '../Drawer'
import { CloseButton } from '../Dialog'
import { InfoButton, type Details } from '../Details'

// Small visuals the fund, SFDR and ESRS screens share (UI standard, 2026-10-16: figures and visuals on the main screen,
// the words one click away): a meter, a ring, a stacked bar with its legend, and the side panel a template opens in.

export const TONE = {
  good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', sky: 'var(--color-sky)',
  slate: 'var(--color-slate)', faint: 'var(--color-faint)',
} as const

export const pct = (n?: number | null, d = 0) => (n == null ? '—' : `${Number(n).toLocaleString('en-GB', { maximumFractionDigits: d })}%`)
export const num = (n?: number | null, d = 0) => (n == null ? '—' : Number(n).toLocaleString('en-GB', { maximumFractionDigits: d }))

// a share as a filled bar (0–100), with the figure beside it — a percentage, or a score out of 100 (score)
export function Meter({ value, tone = TONE.sky, label, width = 'w-24', score, bare }: { value: number | null | undefined; tone?: string; label?: string; width?: string; score?: boolean; bare?: boolean }) {
  const v = value == null ? 0 : Math.max(0, Math.min(100, value))
  return (
    <span className="inline-flex items-center gap-2" aria-label={label}>
      <span className={`${width} h-1.5 rounded-full overflow-hidden`} style={{ background: 'var(--color-panel-2)' }}>
        <span className="block h-full rounded-full" style={{ width: `${v}%`, background: value == null ? 'transparent' : tone }} />
      </span>
      {!bare && <span className="tabular-nums text-[11.5px] text-[var(--color-mute)] w-10 text-right">{score ? (value == null ? '—' : Math.round(value)) : pct(value)}</span>}
    </span>
  )
}

// a share as a ring with what it counts in the middle
export function Ring({ value, tone = TONE.good, size = 64, children }: { value: number; tone?: string; size?: number; children?: ReactNode }) {
  const r = (size - 8) / 2, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value))
  return (
    <span className="relative inline-grid place-items-center shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-panel-2)" strokeWidth={6} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={tone} strokeWidth={6} strokeLinecap="round"
          strokeDasharray={`${(v / 100) * c} ${c}`} />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[12.5px] font-semibold tabular-nums text-[var(--color-ink)]">{children ?? pct(v)}</span>
    </span>
  )
}

// counts as one stacked bar, each part named in the legend under it
export type Part = { n: number; tone: string; label: string }
export function Stack({ parts, legend = true }: { parts: Part[]; legend?: boolean }) {
  const total = parts.reduce((a, p) => a + p.n, 0)
  return (
    <div className="min-w-0">
      <div className="flex h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-panel-2)' }}>
        {total > 0 && parts.filter(p => p.n > 0).map(p => <span key={p.label} style={{ width: `${(p.n / total) * 100}%`, background: p.tone }} />)}
      </div>
      {legend && (
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
          {parts.filter(p => p.n > 0).map(p => (
            <span key={p.label} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]">
              <span className="w-2 h-2 rounded-full" style={{ background: p.tone }} />{p.n} {p.label}
            </span>))}
        </div>)}
    </div>
  )
}

// the side panel a template, a list or a form opens in: its name, an ⓘ, and its body
export function SidePanel({ title, about, onClose, children, wide }: { title: string; about?: Details; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <Drawer label={title} onClose={onClose} backdropClassName="bg-black/50"
      className={`w-full ${wide ? 'max-w-4xl' : 'max-w-2xl'} h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] shadow-2xl`}>
      <div className="sticky top-0 z-10 flex items-center justify-between gap-3 px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
        <div className="flex items-center gap-2 min-w-0">
          <h2 className="font-semibold text-[16px] text-[var(--color-ink)] m-0 truncate">{title}</h2>
          {about && <InfoButton compact details={about} />}
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="p-6">{children}</div>
    </Drawer>
  )
}
