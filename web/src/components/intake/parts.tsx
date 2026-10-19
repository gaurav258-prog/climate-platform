import type { ReactNode } from 'react'
import { CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'
import { ApiError } from '../../lib/api'
import { InfoButton, messageDetails, type Message } from '../Details'

// Small pieces the data-intake and lineage screens share (UI standard, 2026-10-16): a server message with its
// explanation one click away, a check row with its outcome icon, and a segmented bar for "how many of what".

export const TONE = { good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', neutral: 'var(--color-slate)', faint: 'var(--color-faint)', info: 'var(--color-sky)' } as const
export type Tone = keyof typeof TONE

// The catalogue message of a refused request — the server's {error: {message, detail, msg}} — or the fallback words.
export function errMessage(e: unknown, fallback: string): Message {
  const b = e instanceof ApiError ? (e.body as { error?: { message?: string; detail?: Message['detail']; msg?: Message } | string } | null) : null
  const er = b && typeof b === 'object' ? b.error : null
  if (er && typeof er === 'object') return er.msg ?? { label: er.message ?? fallback, detail: er.detail ?? null }
  return { label: fallback }
}

// A message as a line: its label, ⓘ for the explanation.
export function Said({ m, tone, className }: { m: Message; tone?: Tone; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 min-w-0 ${className ?? ''}`} style={tone ? { color: TONE[tone] } : undefined}>
      <span className="min-w-0">{m.label}</span>
      <InfoButton compact details={messageDetails(m)} />
    </span>
  )
}

// One check: an outcome icon, its message, and anything under it.
export function CheckLine({ ok, warn, m, children }: { ok: boolean; warn?: boolean; m: Message; children?: ReactNode }) {
  const Icon = ok ? CheckCircle2 : warn ? AlertTriangle : XCircle
  return (
    <div className="flex items-start gap-2 text-[12.5px]">
      <Icon size={14} className="mt-0.5 shrink-0" style={{ color: ok ? TONE.good : warn ? TONE.warn : TONE.bad }} />
      <div className="min-w-0 flex-1">
        <Said m={m} className={ok ? 'text-[var(--color-mute)]' : 'text-[var(--color-ink)]'} />
        {children}
      </div>
    </div>
  )
}

// A segmented bar: each part's share of the whole, its colour and its name (the legend under it).
export function Segments({ parts, total, legend = true, height = 'h-2' }: {
  parts: { n: number; tone: Tone; label: string }[]; total?: number; legend?: boolean; height?: string
}) {
  const shown = parts.filter(p => p.n > 0)
  const sum = total ?? shown.reduce((a, p) => a + p.n, 0)
  return (
    <div className="space-y-1.5">
      <div className={`flex ${height} rounded-full overflow-hidden bg-[var(--color-line)]`} role="img"
        aria-label={shown.map(p => `${p.n} ${p.label}`).join(', ')}>
        {shown.map(p => <div key={p.label} title={`${p.n.toLocaleString('en-GB')} ${p.label}`}
          style={{ width: `${(100 * p.n) / Math.max(1, sum)}%`, background: TONE[p.tone] }} />)}
      </div>
      {legend && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)]">
          {shown.map(p => <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: TONE[p.tone] }} />{p.n.toLocaleString('en-GB')} {p.label}</span>)}
        </div>)}
    </div>
  )
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString('en-GB')} ${n === 1 ? one : many}`
export const day = (s: string | null | undefined) => s ? s.slice(0, 10) : '—'
