import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronLeft, ChevronRight, CalendarClock, FileText, KanbanSquare, GitBranch, ChevronRight as Chev } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, SectionHead, PageHeader } from '../components/ui'
import { filingLink, taskLink } from '../lib/links'

// Regulatory calendar — filing deadlines and task due-dates on one month grid, with an upcoming list.

interface Ev { date: string; kind: 'obligation' | 'task' | 'reg_change'; title: string; sub: string; ref_id: string | null; status: string; overdue: boolean; criticality: string | null }
interface Resp { events: Ev[]; upcoming: Ev[]; today: string }

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const DOW = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const kindColor = (e: Ev) => e.overdue ? '#fb7185' : e.kind === 'obligation' ? '#5cc8ff' : e.kind === 'reg_change' ? '#a78bfa' : e.criticality === 'critical' ? '#fb7185' : e.criticality === 'high' ? '#f0a860' : '#34d399'

export default function Calendar() {
  const q = useQuery({ queryKey: ['reg-calendar'], queryFn: () => api.get<Resp>('/v1/reg-tasks/calendar') })
  const d = q.data
  const nav = useNavigate()
  const { profile } = useAuth()
  const [ym, setYm] = useState<{ y: number; m: number }>(() => { const n = new Date(); return { y: n.getFullYear(), m: n.getMonth() } })
  const [selDate, setSelDate] = useState<string | null>(null)

  const byDate: Record<string, Ev[]> = {}
  for (const e of d?.events ?? []) (byDate[e.date] ??= []).push(e)

  // where an event drills to: an obligation → its filing (or the filings page to prepare); a task → the board
  const target = (e: Ev): string | null =>
    e.kind === 'reg_change' ? '/reg-changes'
      : e.kind === 'task' ? (e.ref_id ? taskLink(e.ref_id) : '/tasks')
        : (e.ref_id ? filingLink(profile?.org?.type, e.ref_id) : (profile?.org?.type === 'manufacturer' ? '/filings' : '/compliance'))
  const go = (e: Ev) => { const t = target(e); if (t) nav(t) }

  // build the month grid (Mon-first)
  const firstOfMonth = new Date(ym.y, ym.m, 1)
  const startDow = (firstOfMonth.getDay() + 6) % 7   // Mon=0
  const daysInMonth = new Date(ym.y, ym.m + 1, 0).getDate()
  const cells: (number | null)[] = [...Array(startDow).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)]
  while (cells.length % 7 !== 0) cells.push(null)
  const iso = (day: number) => `${ym.y}-${String(ym.m + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  const shift = (n: number) => setYm(({ y, m }) => { const nm = m + n; return { y: y + Math.floor(nm / 12), m: ((nm % 12) + 12) % 12 } })

  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Workflow · calendar" title="Regulatory calendar"
        lead="Filing deadlines, task due-dates and upcoming rule changes on one timeline — see the whole runway and what's due next." />

      <div className="grid lg:grid-cols-[1.6fr_1fr] gap-5">
        {/* month grid */}
        <Card className="p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="display text-lg">{MONTHS[ym.m]} {ym.y}</div>
            <div className="flex gap-1">
              <button onClick={() => shift(-1)} className="text-[var(--color-faint)] hover:text-[var(--color-ink)] p-1"><ChevronLeft size={16} /></button>
              <button onClick={() => shift(1)} className="text-[var(--color-faint)] hover:text-[var(--color-ink)] p-1"><ChevronRight size={16} /></button>
            </div>
          </div>
          <div className="grid grid-cols-7 gap-1 mono text-[10px] text-[var(--color-faint)] mb-1">
            {DOW.map(x => <div key={x} className="text-center py-1">{x}</div>)}
          </div>
          <div className="grid grid-cols-7 gap-1">
            {cells.map((day, i) => {
              if (day === null) return <div key={i} />
              const key = iso(day)
              const evs = byDate[key] ?? []
              const isToday = key === d?.today
              const isSel = key === selDate
              return (
                <button key={i} onClick={() => setSelDate(evs.length ? key : null)} disabled={!evs.length}
                  className={`aspect-square rounded-lg border p-1 flex flex-col text-left ${evs.length ? 'hover:border-[var(--color-sky)] cursor-pointer' : 'cursor-default'}`}
                  style={{ borderColor: isSel ? 'var(--color-sky)' : isToday ? 'var(--color-sky)' : 'var(--color-line)', background: isSel ? 'var(--color-panel-2)' : isToday ? 'var(--color-panel)' : 'transparent' }}>
                  <div className="text-[10.5px] text-[var(--color-mute)]">{day}</div>
                  <div className="flex flex-wrap gap-0.5 mt-auto">
                    {evs.slice(0, 4).map((e, j) => <span key={j} className="w-1.5 h-1.5 rounded-full" style={{ background: kindColor(e) }} title={e.title} />)}
                  </div>
                </button>
              )
            })}
          </div>
          <div className="flex gap-4 mt-3 mono text-[10px] text-[var(--color-faint)]">
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#5cc8ff' }} /> filing deadline</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#34d399' }} /> task due</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#a78bfa' }} /> rule change takes effect</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#fb7185' }} /> overdue</span>
          </div>
        </Card>

        {/* side panel — the selected day's events, or the upcoming list. Every row drills through. */}
        {(() => {
          const list = selDate ? (byDate[selDate] ?? []) : (d?.upcoming ?? [])
          const heading = selDate ? `On ${new Date(selDate).toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' })}` : 'Upcoming'
          return (
            <Card className="p-0 overflow-hidden self-start">
              <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><CalendarClock size={15} className="text-[var(--color-sky)]" /><SectionHead>{heading}</SectionHead></div>
                {selDate && <button onClick={() => setSelDate(null)} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">upcoming ↑</button>}
              </div>
              {q.isLoading ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">loading…</div>
                : list.length === 0 ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">{selDate ? 'Nothing on this day.' : 'Nothing due in the near term.'}</div>
                : <div className="divide-y divide-[var(--color-line)]">
                    {list.map((e, i) => {
                      const Icon = e.kind === 'obligation' ? FileText : e.kind === 'reg_change' ? GitBranch : KanbanSquare
                      return (
                        <button key={i} onClick={() => go(e)} className="w-full text-left px-5 py-3 flex items-center gap-3 hover:bg-[var(--color-panel)] transition">
                          <Icon size={14} style={{ color: kindColor(e) }} className="shrink-0" />
                          <div className="min-w-0 flex-1">
                            <div className="text-[13px] text-[var(--color-ink)] truncate">{e.title}</div>
                            <div className="mono text-[10.5px] text-[var(--color-faint)]">{e.sub}</div>
                          </div>
                          <div className="text-right shrink-0">
                            <div className="mono text-[11.5px]" style={{ color: e.overdue ? '#fb7185' : 'var(--color-mute)' }}>{new Date(e.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</div>
                            <div className="mono text-[9.5px] text-[var(--color-faint)]">{e.kind}</div>
                          </div>
                          <Chev size={14} className="text-[var(--color-faint)] shrink-0" />
                        </button>
                      )
                    })}
                  </div>}
            </Card>
          )
        })()}
      </div>
    </div>
  )
}
