import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Scale } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Card, SectionHead } from '../../components/ui'
import { HEADING, InfoButton, MessageLine, type Details, type Message } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { Share, refused, sel } from './parts'
import { savedWords } from './words'

// The choices the rules leave to the institution. Each comes from the server named, with its explanation and — for a
// Pillar 3 statement — the instructions it quotes (services/governance/admin_view.switch_view); the screen shows the
// choice and keeps the rest one click away.

interface Switch { key: string; kind: 'enum' | 'int' | 'float'; default: string | number | null; min: number | null; max: number | null
  name: string; about: Message; options: { value: string | number; label: string }[]; law?: string[]; no_option?: Message }

const ABOUT = {
  title: 'Choices the rules leave to you', sections: [
    { heading: HEADING.shows, body: 'Where a regulation leaves a choice to your institution, you make it here. Each choice is stamped on every report frozen after it, so a reader sees which reading produced each figure.' },
    { heading: HEADING.read, body: 'A choice that drives a money figure has no default: until it is made, that figure is reported as missing, never computed from a guess. Open a choice’s ⓘ for what it decides and the rule behind it.' },
    { heading: HEADING.limits, body: 'Changes are recorded in the audit trail and may wait for a second person, as set in the approval matrix.' },
  ],
}
// a choice's pop-up: what it decides, the rule behind it, what happens when it is not made, the instructions quoted
function details(s: Switch): Details {
  const d = s.about.detail ?? {}
  return { title: s.name, sections: [
    ...(d.what ? [{ heading: 'What it decides', body: d.what }] : []),
    ...(d.why ? [{ heading: 'The rule behind it', body: d.why }] : []),
    ...(d.next ? [{ heading: 'If you do not choose', body: d.next }] : []),
    ...(s.law?.length ? [{ heading: 'The instructions quoted', body: <div className="space-y-2">{s.law.map((q, i) => <p key={i} className="m-0">{q}</p>)}</div> }] : []),
  ] }
}

export default function Methodology() {
  const cat = useQuery({ queryKey: ['calc-catalog'], queryFn: () => api.get<{ interpretation: Switch[] }>('/v1/calc-settings/catalog') })
  const cur = useQuery({ queryKey: ['calc-settings'], queryFn: () => api.get<Record<string, unknown>>('/v1/calc-settings') })
  const [busy, setBusy] = useState<string | null>(null)
  const specs = cat.data?.interpretation ?? []
  const valueOf = (s: Switch) => (cur.data?.[s.key] ?? s.default ?? null) as string | number | null      // null: not chosen
  const save = async (key: string, value: string | number) => {
    setBusy(key)
    try {
      const r = await api.patch<{ status: string }>('/v1/calc-settings', { interpretation: { [key]: value } })
      toast.success(savedWords(r.status, 'Choice saved — new reports use it.'))
      cur.refetch()
    } catch (e) { refused(e, 'The choice could not be saved.') } finally { setBusy(null) }
  }
  const made = specs.filter(s => valueOf(s) != null).length

  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex flex-wrap items-center gap-4">
        <SectionHead icon={Scale} className="gap-1.5">Choices the rules leave to you <InfoButton compact details={ABOUT} /></SectionHead>
        {specs.length > 0 && <div className="ml-auto w-56"><Share n={made} of={specs.length} label="Made" tone={made === specs.length ? 'var(--color-good)' : 'var(--color-warn)'} /></div>}
      </div>
      {specs.length === 0 ? <div className="p-5 text-[13px] text-[var(--color-faint)]">{cat.isLoading ? 'Loading…' : 'No choice applies to your sector.'}</div> : (
        <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
          {specs.map(s => {
            const v = valueOf(s)
            return (
              <li key={s.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
                <div className="min-w-0 flex-1 flex items-center gap-2">
                  <span className="text-[13.5px] text-[var(--color-ink)]">{s.name}</span>
                  <InfoButton compact details={details(s)} />
                  {v == null && !s.no_option && <StatusChip tone="warn" label="Not chosen" />}
                </div>
                {s.no_option ? <MessageLine m={s.no_option} className="text-[12.5px] text-[var(--color-faint)]" />
                  : s.kind === 'enum' || s.options.length > 0 ? (
                    <select value={v == null ? '' : String(v)} disabled={busy === s.key} aria-label={s.name}
                      onChange={e => save(s.key, s.kind === 'int' ? Number(e.target.value) : e.target.value)} className={clsx(sel, 'max-w-[320px]')}>
                      {v == null && <option value="" disabled>Choose…</option>}
                      {s.options.map(o => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
                    </select>
                  ) : (
                    <input type="number" defaultValue={v == null ? undefined : Number(v)} placeholder="Not set" aria-label={s.name}
                      min={s.min ?? undefined} max={s.max ?? undefined} step={s.kind === 'float' ? 0.1 : 1} disabled={busy === s.key}
                      onBlur={e => { const n = Number(e.target.value); if (e.target.value !== '' && n !== Number(v)) save(s.key, n) }}
                      className={clsx(sel, 'w-28 tabular-nums')} />
                  )}
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
