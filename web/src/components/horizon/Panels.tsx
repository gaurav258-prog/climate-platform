import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Check as Tick, Circle } from 'lucide-react'
import { MessageLine } from '../Details'
import { StatusChip } from '../StatusChip'
import { hazardLabel } from '../../lib/labels'
import { ramp, rgb } from './globe'
import type { Asset, Check, Stop, Task } from './types'

const SEV: Record<string, string> = { action: 'var(--color-sky)', warning: 'var(--color-warn)', info: 'var(--color-blue)', good: 'var(--color-good)' }
const head = 'text-[12px] text-[var(--color-faint)]'

// What needs this person: their roles, then each task in the server's words with its pop-up and the page that acts on it.
export function ActionsPanel({ tasks, roles, raisedPending }: { tasks: Task[]; roles: { key: string; name: string }[]; raisedPending: number }) {
  const nav = useNavigate()
  return (
    <div className="mt-6">
      <div className={head}>Your actions</div>
      <div className="display text-[30px] text-[#F4EFE6] mt-1">{tasks.length ? tasks.length : 'All clear'}</div>
      <div className="flex flex-wrap gap-1.5 mt-3">{roles.map(r => <StatusChip key={r.key} tone="neutral" label={r.name} />)}</div>
      {raisedPending > 0 && <div className="mt-3"><StatusChip tone="warn" label={`${raisedPending} of your requests await approval`} /></div>}
      <div className="flex flex-col gap-2 mt-5">
        {tasks.map(t => (
          <div key={t.key} className="rounded-lg border border-[var(--color-line)] px-3 py-2.5">
            <div className="flex items-start gap-2.5">
              <span className="w-2 h-2 rounded-full shrink-0 mt-1.5" style={{ background: SEV[t.severity] ?? 'var(--color-sky)' }} />
              <MessageLine m={t.message} className="flex-1 min-w-0 text-[14px] text-[var(--color-ink)] leading-snug" />
            </div>
            <div className="flex items-center justify-between gap-2 mt-2 ml-[18px]">
              {t.due ? <span className="inline-flex items-center gap-1"><StatusChip tone={t.bucket === 'overdue' ? 'bad' : 'warn'} label={t.due.label} /></span> : <span />}
              <button onClick={() => nav(t.action.href)} className="text-[12.5px] inline-flex items-center gap-1 whitespace-nowrap hover:underline" style={{ color: SEV[t.severity] ?? 'var(--color-sky)' }}>
                {t.action.label} <ArrowRight size={12} /></button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// The filing-readiness checklist: each check in the server's words; a failing one links to where it is fixed.
export function ReadinessPanel({ passed, total, checks }: { passed: number; total: number; checks: Check[] }) {
  const nav = useNavigate()
  return (
    <div className="mt-6">
      <div className={head}>Filing readiness</div>
      <div className="display text-[30px] text-[#F4EFE6] mt-1">{passed} of {total}</div>
      <div className="flex gap-1 mt-3">{checks.map(c => <span key={c.key} className="h-1.5 flex-1 rounded-full" style={{ background: c.ok ? 'var(--color-good)' : 'var(--color-warn)' }} />)}</div>
      <div className="flex flex-col gap-2 mt-5">
        {checks.map(c => (
          <div key={c.key} className={`flex gap-3 items-start rounded-lg px-3 py-2.5 ${c.ok ? '' : 'border border-[#3a3320] bg-[#171208]'}`}>
            <span className="mt-0.5 shrink-0" style={{ color: c.ok ? 'var(--color-good)' : 'var(--color-warn)' }}>{c.ok ? <Tick size={15} /> : <Circle size={14} />}</span>
            <div className="min-w-0 flex-1">
              <MessageLine m={c.message} className="text-[14px] text-[var(--color-ink)] leading-snug" />
              {!c.ok && c.fix_href && (
                <button onClick={() => nav(c.fix_href!)} className="mt-1.5 text-[12.5px] text-[var(--color-warn)] inline-flex items-center gap-1 hover:underline">{c.fix_label} <ArrowRight size={12} /></button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// A ranked list of the book (or the regions) at the year in view: the ones at risk first when a level is stated.
export function ListPanel({ title, assets, stop, stops, onPick }: {
  title: string; assets: Asset[]; stop: number; stops: Stop[]; onPick: (a: Asset) => void
}) {
  const [all, setAll] = useState(false)
  const ranked = [...assets].sort((x, y) => (y.score[stop] ?? -1) - (x.score[stop] ?? -1))
  const shown = all ? ranked : ranked.slice(0, 10)
  return (
    <div className="mt-6">
      <div className={head}>{title} · {stops[stop].label}</div>
      <div className="display text-[30px] text-[#F4EFE6] mt-1">{assets.length}</div>
      <div className="flex flex-col gap-1.5 mt-4">
        {shown.map(a => {
          const s = a.score[stop], c = ramp(s)
          return (
            <button key={a.id} onClick={() => onPick(a)} className="text-left rounded-lg border border-[var(--color-line)] px-3 py-2 hover:border-[var(--color-sky)]">
              <div className="flex items-center justify-between gap-3">
                <span className="min-w-0 text-[14px] text-[var(--color-ink)] truncate">{a.name}</span>
                <span className="text-[13px] tabular-nums shrink-0" style={{ color: rgb(c) }}>{s == null ? '—' : Math.round(s)}</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-[11.5px] text-[var(--color-faint)] truncate flex-1">{a.region}{a.hazard[stop] ? ` · ${hazardLabel(a.hazard[stop])}` : ''}</span>
                <span className="h-1 w-16 rounded-full bg-[#162133] overflow-hidden shrink-0"><span className="block h-full" style={{ width: `${s ?? 0}%`, background: rgb(c) }} /></span>
              </div>
            </button>
          )
        })}
      </div>
      {ranked.length > 10 && (
        <button onClick={() => setAll(v => !v)} className="mt-3 w-full text-[12.5px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-4 py-2 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
          {all ? 'Show the top ten' : `Show all ${ranked.length}`}</button>
      )}
    </div>
  )
}
