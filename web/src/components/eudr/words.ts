import { useMutation } from '@tanstack/react-query'
import { MESSAGE_HEADING, type DetailSection, type Message } from '../Details'
import { apiDetail, apiMessage } from '../../lib/api'
import { statusLabel } from '../../lib/hazards'
import { toast } from '../../lib/toast'
import type { Check } from './types'

// The EUDR journey's shared words and helpers: the colours a state reads in, a statement's status in words, a check's
// explanation for its pop-up, and a refused request as a catalogue message.

export const TONE = { good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', info: 'var(--color-sky)', none: 'var(--color-faint)', slate: 'var(--color-slate)' }
export const OUTCOME_TONE: Record<string, string> = { no_loss_detected: TONE.good, loss_after_cutoff: TONE.warn, not_assessable: TONE.slate, unread: TONE.none }

// a statement's or declaration's status: its chip colour and words (the last stage is the number the system assigns)
export const STATEMENT_TONE: Record<string, 'good' | 'warn' | 'bad' | 'neutral'> = {
  draft: 'neutral', returned: 'warn', in_review: 'warn', approved: 'good', attested: 'good', submitted: 'good', accepted: 'good',
  rejected: 'bad', withdrawn: 'neutral', superseded: 'neutral',
}
export const statementWord = (s: string, last = 'Reference received') => s === 'accepted' ? last : statusLabel(s)

const SEVERITY_EFFECT = {
  blocking: 'Blocking: it must be cleared before this can be prepared.',
  warning: 'To review: it does not block; you decide, and the approver sees it.',
  info: 'For information only.',
}

// A check's pop-up: what it means, why, what to do, its legal basis and its effect.
export function checkDetails(c: Check): DetailSection[] {
  const d = c.msg.detail ?? {}
  return [
    ...(['what', 'why', 'next'] as const).filter(k => d[k]).map(k => ({ heading: MESSAGE_HEADING[k], body: d[k] })),
    ...(c.ref ? [{ heading: 'Legal basis', body: `EU Deforestation Regulation (EU) 2023/1115, ${c.ref}` }] : []),
    ...(c.passed ? [] : [{ heading: 'Effect', body: SEVERITY_EFFECT[c.severity] }]),
  ]
}

// A message's detail as pop-up sections.
export const messageSections = (m: Message): DetailSection[] =>
  (['what', 'why', 'next'] as const).filter(k => m.detail?.[k]).map(k => ({ heading: MESSAGE_HEADING[k], body: m.detail![k] }))

// The worst open check among those whose rule is one of these (or one of them per plot / party): a tile's state.
export function worst(checks: Check[], ...rules: string[]): 'bad' | 'warn' | 'good' {
  const mine = checks.filter(c => !c.passed && rules.some(r => c.rule === r || c.rule.startsWith(`${r}:`) || c.rule.startsWith(`${r}_`)))
  return mine.some(c => c.severity === 'blocking') ? 'bad' : mine.some(c => c.severity === 'warning') ? 'warn' : 'good'
}

// A refused request in the catalogue's words (core/errors.py): its label, its explanation behind the ⓘ.
export type Refusal = Message | null
export const refusal = (e: unknown, fallback: string): Message => ({ label: apiMessage(e, fallback), detail: apiDetail(e) })

// A form's request: a toast when it is done; a refusal stays in the form (Form's `error`).
export function useSend<T>(fn: () => Promise<T>, done: string, onDone: () => void) {
  return useMutation({ mutationFn: fn, onSuccess: () => { toast.success(done); onDone() } })
}

export const linkBtn = 'text-[12px] text-[var(--color-sky)] hover:underline'
