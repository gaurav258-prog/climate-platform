import { useMemo, useState } from 'react'
import { CalendarClock } from 'lucide-react'
import clsx from 'clsx'
import { Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton } from '../../components/Details'
import { day, daysBetween } from './common'
import { useCalendar, type DueRequest } from './data'

// The runway: every report due and every open request from the supervisor on one time axis, today marked. A date on
// the axis filters the list below; a request opens its thread.

const DONE = new Set(['submitted', 'accepted'])
const FREQUENCY: Record<string, string> = { annual: 'Annual', semiannual: 'Half-yearly', quarterly: 'Quarterly', monthly: 'Monthly', one_off: 'One-off' }
const ROW = 'py-2 grid grid-cols-[6.5rem_minmax(0,1fr)_auto] items-center gap-3 text-[12.5px]'
const TONE = { bad: 'var(--color-bad)', good: 'var(--color-good)', open: 'var(--color-sky)' }

type Mark = { date: string; n: number; tone: keyof typeof TONE; requests: DueRequest[] }
function marks<T>(items: T[], date: (t: T) => string, tone: (ts: T[]) => keyof typeof TONE, requests: (ts: T[]) => DueRequest[]): Mark[] {
  const by = new Map<string, T[]>()
  for (const it of items) by.set(date(it), [...(by.get(date(it)) ?? []), it])
  return [...by.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([d, ts]) => ({ date: d, n: ts.length, tone: tone(ts), requests: requests(ts) }))
}

// Dates close together on the axis alternate up and down so neither dot hides the other.
function placed(ms: Mark[], at: (d: string) => number): (Mark & { dy: number })[] {
  let last = -1, up = false
  return ms.map(m => { const f = at(m.date); up = f - last < 0.025 ? !up : false; last = f; return { ...m, dy: up ? -8 : 0 } })
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Each report your organisation owes, on the date it is due, and each open request from your supervisor, on the date your reply is due. The line marks today.' },
  { heading: HEADING.read, body: 'Red: overdue. Green: delivered. Blue: still to come. A number in a dot counts the items due that day. Choose a date to list only what is due then; choose a request to open it.' },
  { heading: HEADING.sources, body: 'Your filing calendar, including the deadlines your supervisor has published, and your supervisor’s requests.' },
]

export function Deadlines({ requests, onRequest }: { requests: DueRequest[]; onRequest: (id: string) => void }) {
  const cal = useCalendar()
  const [pick, setPick] = useState<string | null>(null)
  const [all, setAll] = useState(false)
  const due = useMemo(() => (cal.data?.events ?? []).filter(e => e.kind === 'obligation').sort((a, b) => a.date.localeCompare(b.date)), [cal.data])
  const open = requests.filter(r => r.status !== 'closed' && r.due_date)
  if (!cal.data || (due.length === 0 && open.length === 0)) return null
  const today = cal.data.today
  const dates = [...due.map(e => e.date), ...open.map(r => r.due_date!), today].sort()
  const span = Math.max(30, daysBetween(dates[0], dates[dates.length - 1]))
  const pad = Math.max(10, Math.round(span * 0.06))
  const start = new Date(Date.parse(dates[0]) - pad * 86400000).toISOString().slice(0, 10)
  const total = span + 2 * pad
  const at = (d: string) => daysBetween(start, d) / total
  const x = (d: string) => `${at(d) * 100}%`
  const reports = marks(due, e => e.date, es => es.some(e => e.overdue) ? 'bad' : es.every(e => DONE.has(e.status ?? '')) ? 'good' : 'open', () => [])
  const asks = marks(open, r => r.due_date!, rs => rs.some(r => r.overdue) ? 'bad' : 'open', rs => rs)
  const todo = [...due].sort((a, b) => Number(DONE.has(a.status ?? '')) - Number(DONE.has(b.status ?? '')) || a.date.localeCompare(b.date))
  const shown = pick ? due.filter(e => e.date === pick) : all ? todo : todo.slice(0, 6)
  const asked = pick ? open.filter(r => r.due_date === pick) : []
  return (
    <Card className="p-5 space-y-4">
      <div className="flex items-center gap-2">
        <SectionHead icon={CalendarClock}>Deadlines</SectionHead>
        <InfoButton compact details={{ title: 'Deadlines', sections: ABOUT }} />
        {pick && <button onClick={() => setPick(null)} className="ml-auto text-[12px] text-[var(--color-sky)] hover:underline">Show all dates</button>}
      </div>
      <div className="relative pl-24">
        {[{ label: 'Reports due', ms: reports }, { label: 'Requests due', ms: asks }].map(lane => (
          <div key={lane.label} className="relative h-9 border-b border-[var(--color-line)]">
            <span className="absolute -left-24 top-1/2 -translate-y-1/2 text-[11.5px] text-[var(--color-mute)]">{lane.label}</span>
            {placed(lane.ms, at).map(m => (
              <button key={m.date} type="button" onClick={() => m.requests.length === 1 ? onRequest(m.requests[0].request_id) : setPick(pick === m.date ? null : m.date)}
                aria-label={`${m.n} due ${day(m.date)}`} title={`${m.n} due ${day(m.date)}`}
                className={clsx('absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full grid place-items-center text-[10px] font-semibold text-[var(--color-bg)] transition',
                  pick === m.date ? 'ring-2 ring-[var(--color-ink)]' : 'hover:scale-110')}
                style={{ left: x(m.date), marginTop: m.dy, width: m.n > 1 ? 20 : 13, height: m.n > 1 ? 20 : 13, background: TONE[m.tone] }}>
                {m.n > 1 ? m.n : ''}
              </button>
            ))}
          </div>
        ))}
        <div className="absolute top-0 bottom-5 w-px bg-[var(--color-ink)] opacity-60" style={{ left: `calc(6rem + (100% - 6rem) * ${daysBetween(start, today) / total})` }} />
        <div className="relative h-5">
          {ticks(start, total).filter(t => Math.abs(at(t.date) - at(today)) > 0.05).map(t => <span key={t.date} className="absolute top-1 -translate-x-1/2 text-[10.5px] text-[var(--color-faint)] whitespace-nowrap" style={{ left: x(t.date) }}>{t.label}</span>)}
          <span className="absolute top-1 -translate-x-1/2 text-[10.5px] font-medium text-[var(--color-ink)]" style={{ left: x(today) }}>Today</span>
        </div>
      </div>
      {shown.length + asked.length > 0 && (
        <div className="divide-y divide-[var(--color-line)]">
          {asked.map(r => (
            <button key={r.request_id} type="button" onClick={() => onRequest(r.request_id)} className={clsx(ROW, 'w-full text-left group')}>
              <span className="tabular-nums" style={{ color: r.overdue ? 'var(--color-bad)' : 'var(--color-mute)' }}>{day(r.due_date)}</span>
              <span className="min-w-0 text-[var(--color-ink)] group-hover:text-[var(--color-sky)]">{r.title}</span>
              <span className="flex flex-wrap justify-end gap-1.5"><StatusChip label={r.kind_label} tone="neutral" />{r.overdue && <StatusChip value="overdue" />}</span>
            </button>
          ))}
          {shown.map((e, i) => (
            <div key={i} className={ROW}>
              <span className="tabular-nums" style={{ color: e.overdue ? 'var(--color-bad)' : 'var(--color-mute)' }}>{day(e.date)}</span>
              <span className="min-w-0">
                <span className="text-[var(--color-ink)]">{e.title}</span>
                <span className="block text-[11.5px] text-[var(--color-faint)]">{[e.period, FREQUENCY[e.frequency ?? ''], e.entity].filter(Boolean).join(' · ')}</span>
              </span>
              <span className="flex flex-wrap justify-end gap-1.5">
                {e.set_by && <StatusChip label="Supervisor’s deadline" tone="neutral" />}
                <StatusChip value={e.status ?? 'not_started'} />
                {e.overdue && <StatusChip value="overdue" />}
              </span>
            </div>
          ))}
        </div>
      )}
      {!pick && due.length > 6 && <button type="button" onClick={() => setAll(!all)} className="text-[12px] text-[var(--color-sky)] hover:underline">{all ? 'Show fewer' : `Show all ${due.length} reports`}</button>}
    </Card>
  )
}

// Month labels along the axis, at most about eight.
function ticks(start: string, total: number): { date: string; label: string }[] {
  const s = new Date(`${start}T00:00:00`)
  const out: { date: string; label: string }[] = []
  const months = Math.ceil(total / 30)
  const step = Math.max(1, Math.ceil(months / 8))
  for (let m = 1; m <= months; m += step) {
    const d = new Date(s.getFullYear(), s.getMonth() + m, 1)
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
    if (daysBetween(start, iso) < total) out.push({ date: iso, label: d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' }) })
  }
  return out
}
