import { type ReactNode, useState } from 'react'
import { AlertCircle, Check, Copy } from 'lucide-react'
import clsx from 'clsx'
import { apiDetail, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { InfoButton, messageDetails, type Message } from '../../components/Details'

// Small pieces the control center's tabs share. Every explanation the server sends is a catalogue message
// (core/messages.py): its label is the line on screen, its detail opens from ⓘ.

export const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]'
export const sel = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]'

// how long ago, in words ('today', '3 days ago', 'never')
export function ago(iso: string | null | undefined): string {
  if (!iso) return 'never'
  const d = (Date.now() - new Date(iso).getTime()) / 86400000
  return d < 1 ? 'today' : d < 2 ? 'yesterday' : `${Math.floor(d)} days ago`
}

// a refused request: its catalogue label on screen (the detail is in the server's answer for a pop-up)
export const refused = (e: unknown, fallback: string) => toast.error(apiDetail(e)?.what ?? apiMessage(e, fallback))

// a card's own ⓘ for a catalogue message (its label is the card's title, so only the button shows)
export function About({ m }: { m: Message | null | undefined }) {
  return m ? <InfoButton compact details={messageDetails(m)} /> : null
}

// an on/off switch — a real button, so it is reachable by keyboard and read as a switch
export function Toggle({ on, onChange, disabled, label }: { on: boolean; onChange: () => void; disabled?: boolean; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={onChange}
      className={clsx('relative w-11 h-6 rounded-full transition shrink-0 disabled:opacity-50', on ? 'bg-[var(--color-good)]' : 'bg-[var(--color-line-2)]')}>
      <span className={clsx('absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all', on ? 'left-[22px]' : 'left-0.5')} />
    </button>
  )
}

// a value to copy (an address, an identifier) — shown as a read-only field with a copy button
export function CopyRow({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false)
  const copy = () => { navigator.clipboard?.writeText(value); setDone(true); setTimeout(() => setDone(false), 1500) }
  return (
    <label className="block">
      <span className="text-[12px] text-[var(--color-mute)]">{label}</span>
      <span className="mt-1 flex items-center gap-2">
        <input readOnly value={value} aria-label={label} className="flex-1 min-w-0 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 mono text-[11.5px] text-[var(--color-mute)]" />
        <button type="button" onClick={copy} aria-label={`Copy ${label}`} className="shrink-0 text-[var(--color-sky)] hover:text-[var(--color-blue)]">
          {done ? <Check size={15} /> : <Copy size={15} />}
        </button>
      </span>
    </label>
  )
}

// a secret shown once (a token, a signing secret): copy it now, it never shows again
export function ShownOnce({ title, value, children }: { title: string; value: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_8%,transparent)] p-3.5">
      <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-sky)] mb-2"><AlertCircle size={14} /> {title}</div>
      <CopyRow value={value} label="Secret" />
      {children}
    </div>
  )
}

// a labelled field in a form
export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx('block', className)}>
      <span className="text-[12px] text-[var(--color-mute)]">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

// a share of a whole as a thin bar with its count — the quick visual of 'n of m'
export function Share({ n, of, tone = 'var(--color-sky)', label }: { n: number; of: number; tone?: string; label: string }) {
  const pct = of > 0 ? Math.min(100, (100 * n) / of) : 0
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px] mb-1">
        <span className="text-[var(--color-mute)]">{label}</span>
        <span className="tabular-nums text-[var(--color-ink)]">{n} <span className="text-[var(--color-faint)]">of {of}</span></span>
      </div>
      <div className="h-1.5 rounded-full bg-[var(--color-panel-2)] overflow-hidden" role="img" aria-label={`${label}: ${n} of ${of}`}>
        <span className="block h-full rounded-full" style={{ width: `${pct}%`, background: tone }} />
      </div>
    </div>
  )
}
