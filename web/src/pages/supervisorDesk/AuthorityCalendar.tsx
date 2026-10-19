import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, ChevronRight } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, messageDetails, type Message } from '../../components/Details'
import { Failed, Loading, Meter, day, field } from './common'

// The calendar by authority: which deliverables the population owes to which authority, by when, and how many entities
// have filed. Per authority a year strip (a dot per deliverable, today marked) over one line per deliverable; its
// channel and the act's rule one click away, the entities one click further.
interface Ev { date: string | null; title: string; mandate_id: string; mandate_title: string; status: string; status_label: string | null; overdue: boolean
  frequency_label: string | null; channel_label: string | null; due_rule: string | null; n_applicable: number; n_filed: number; n_cannot: number
  entities: { org_id: string; name: string; filed: boolean }[]; authority?: string }
interface Group { authority: string; events: Ev[]; n_deliverables: number; n_applicable: number; n_filed: number; n_overdue: number; next_due: string | null }
interface CalResp { period_label: string; today: string; authorities: Group[]; undated: Ev[]; note: Message }

const tone = (e: Ev) => e.n_applicable && e.n_filed >= e.n_applicable ? 'var(--color-good)' : e.overdue ? 'var(--color-bad)' : 'var(--color-warn)'
const ms = (s: string) => Date.parse(`${s.slice(0, 10)}T00:00:00`)

function YearStrip({ events, today }: { events: Ev[]; today: string }) {
  const dated = events.filter(e => e.date)
  if (!dated.length) return null
  const lo = Math.min(...dated.map(e => ms(e.date!)), ms(today)), hi = Math.max(...dated.map(e => ms(e.date!)), ms(today))
  const pad = Math.max(86400000 * 20, (hi - lo) * 0.08)
  const x = (t: number) => `${((t - (lo - pad)) / (hi - lo + 2 * pad)) * 100}%`
  return (
    <div className="relative h-10 my-2" role="img" aria-label="Due dates on a time line, today marked">
      <div className="absolute left-0 right-0 top-1/2 h-px bg-[var(--color-line-2)]" />
      <div className="absolute top-1 bottom-1 w-px bg-[var(--color-sky)]" style={{ left: x(ms(today)) }} title={`Today · ${day(today)}`} />
      <span className="absolute -top-1 text-[10px] text-[var(--color-sky)] -translate-x-1/2" style={{ left: x(ms(today)) }}>today</span>
      {dated.map(e => <span key={e.mandate_id} title={`${e.title} · ${day(e.date)}`} className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 border-[var(--color-bg)]"
        style={{ left: x(ms(e.date!)), background: tone(e) }} />)}
    </div>
  )
}

function details(e: Ev) {
  return { title: e.mandate_title, sections: [
    { heading: 'Channel', body: `${e.channel_label ?? '—'}${e.frequency_label ? ` · ${e.frequency_label}` : ''}` },
    ...(e.due_rule ? [{ heading: "The act's rule", body: e.due_rule }] : []),
    ...(e.n_cannot ? [{ heading: HEADING.limits, body: `Applicability cannot yet be determined for ${e.n_cannot} ${e.n_cannot === 1 ? 'entity' : 'entities'}: a regulatory attribute is missing.` }] : []),
  ] }
}

function Row({ e, period }: { e: Ev; period: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="py-2.5">
      <div className="flex items-center gap-3 flex-wrap text-[12.5px]">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-2 min-w-0 mr-auto text-left group">
          <ChevronRight size={13} className={clsx('text-[var(--color-faint)] transition-transform', open && 'rotate-90')} />
          <span className="w-24 shrink-0 tabular-nums" style={{ color: e.overdue ? 'var(--color-bad)' : 'var(--color-ink)' }}>{day(e.date)}</span>
          <span className="text-[var(--color-ink)] group-hover:text-[var(--color-sky)]">{e.title}</span>
        </button>
        <Meter value={e.n_filed} total={e.n_applicable} label={`${e.n_filed} of ${e.n_applicable} applicable entities filed`} late={e.overdue} />
        {e.overdue ? <StatusChip value="past_due" label="Past due" /> : <StatusChip value={e.status} label={e.status_label ?? undefined} />}
        <InfoButton compact details={details(e)} />
      </div>
      {open && <div className="flex flex-wrap gap-1.5 mt-2 pl-[8.5rem]">{e.entities.length === 0
        ? <span className="text-[12px] text-[var(--color-faint)]">No entity in your population to which this applies for {period}.</span>
        : e.entities.map(x => <Link key={x.org_id} to={`/supervised/${x.org_id}`}><StatusChip label={x.name} tone={x.filed ? 'good' : 'neutral'} /></Link>)}</div>}
    </div>
  )
}

export function AuthorityCalendar() {
  const years = [1, 2, 3].map(i => `FY${new Date().getFullYear() - i + 1}`)
  const [period, setPeriod] = useState(years[1])
  const q = useQuery({ queryKey: ['supervisor-authority-calendar', period], queryFn: () => api.get<CalResp>(`/v1/supervisor/obligations/calendar?period_label=${period}`) })
  const d = q.data
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <select aria-label="Financial year" value={period} onChange={e => setPeriod(e.target.value)} className={field}>{years.map(y => <option key={y} value={y}>{y}</option>)}</select>
        {d && <InfoButton label="How the calendar is built" details={messageDetails(d.note)} />}
      </div>
      {q.isLoading ? <Loading what="the calendar" /> : !d ? <Failed what="the calendar" /> : (<>
        {d.authorities.map(g => (
          <Card key={g.authority} className="p-5">
            <div className="flex flex-wrap items-center gap-2">
              <SectionHead icon={CalendarDays}>{g.authority}</SectionHead>
              <span className="ml-auto flex flex-wrap items-center gap-2">
                <Meter value={g.n_filed} total={g.n_applicable} label={`${g.n_filed} of ${g.n_applicable} entity filings received`} late={g.n_overdue > 0} />
                {g.n_overdue > 0 && <StatusChip label={`${g.n_overdue} past due`} tone="bad" />}
                {g.next_due && <StatusChip label={`Next due ${day(g.next_due)}`} tone="neutral" />}
              </span>
            </div>
            <YearStrip events={g.events} today={d.today} />
            <div className="divide-y divide-[var(--color-line)]">{g.events.map(e => <Row key={e.mandate_id} e={e} period={d.period_label} />)}</div>
          </Card>))}
        {d.authorities.length === 0 && <Card className="p-5 text-[13px] text-[var(--color-faint)]">No dated deliverable for {d.period_label} in your profile.</Card>}
        {d.undated.length > 0 && <Card className="p-5">
          <SectionHead hint="no calendar date">Due on an event</SectionHead>
          <div className="divide-y divide-[var(--color-line)] mt-2">{d.undated.map(e => (
            <div key={e.mandate_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
              <span className="text-[var(--color-ink)] mr-auto">{e.title}<span className="text-[var(--color-faint)]"> · {e.authority}</span></span>
              <span className="text-[var(--color-mute)]">{e.n_applicable} {e.n_applicable === 1 ? 'entity' : 'entities'}</span>
              <InfoButton compact details={details(e)} />
            </div>))}</div>
        </Card>}
      </>)}
    </div>
  )
}
