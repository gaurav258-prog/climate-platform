import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, CalendarClock, FileText, KanbanSquare } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'

// Regulatory calendar — filing deadlines and task due-dates on one month grid, with an upcoming list.

interface Ev { date: string; kind: 'obligation' | 'task'; title: string; sub: string; ref_id: string | null; status: string; overdue: boolean; criticality: string | null }
interface Resp { events: Ev[]; upcoming: Ev[]; today: string }

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const DOW = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const kindColor = (e: Ev) => e.overdue ? '#fb7185' : e.kind === 'obligation' ? '#5cc8ff' : e.criticality === 'critical' ? '#fb7185' : e.criticality === 'high' ? '#f0a860' : '#34d399'

export default function Calendar() {
  const q = useQuery({ queryKey: ['reg-calendar'], queryFn: () => api.get<Resp>('/v1/reg-tasks/calendar') })
  const d = q.data
  const [ym, setYm] = useState<{ y: number; m: number }>(() => { const n = new Date(); return { y: n.getFullYear(), m: n.getMonth() } })

  const byDate: Record<string, Ev[]> = {}
  for (const e of d?.events ?? []) (byDate[e.date] ??= []).push(e)

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
      <div>
        <Eyebrow>Workflow · calendar</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Regulatory calendar</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Filing deadlines and task due-dates on one timeline — see the whole runway and what's due next.</p>
      </div>

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
              return (
                <div key={i} className="aspect-square rounded-lg border p-1 flex flex-col" style={{ borderColor: isToday ? 'var(--color-sky)' : 'var(--color-line)', background: isToday ? 'var(--color-panel)' : 'transparent' }}>
                  <div className="text-[10.5px] text-[var(--color-mute)]">{day}</div>
                  <div className="flex flex-wrap gap-0.5 mt-auto">
                    {evs.slice(0, 4).map((e, j) => <span key={j} className="w-1.5 h-1.5 rounded-full" style={{ background: kindColor(e) }} title={e.title} />)}
                  </div>
                </div>
              )
            })}
          </div>
          <div className="flex gap-4 mt-3 mono text-[10px] text-[var(--color-faint)]">
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#5cc8ff' }} /> filing deadline</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#34d399' }} /> task due</span>
            <span className="inline-flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full" style={{ background: '#fb7185' }} /> overdue</span>
          </div>
        </Card>

        {/* upcoming */}
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2">
            <CalendarClock size={15} className="text-[var(--color-sky)]" />
            <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Upcoming</span>
          </div>
          {q.isLoading ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">loading…</div>
            : (d?.upcoming.length ?? 0) === 0 ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">Nothing due in the near term.</div>
            : <div className="divide-y divide-[var(--color-line)]">
                {d!.upcoming.map((e, i) => {
                  const Icon = e.kind === 'obligation' ? FileText : KanbanSquare
                  return (
                    <div key={i} className="px-5 py-3 flex items-center gap-3">
                      <Icon size={14} style={{ color: kindColor(e) }} className="shrink-0" />
                      <div className="min-w-0 flex-1">
                        <div className="text-[13px] text-[var(--color-ink)] truncate">{e.title}</div>
                        <div className="mono text-[10.5px] text-[var(--color-faint)]">{e.sub}</div>
                      </div>
                      <div className="text-right shrink-0">
                        <div className="mono text-[11.5px]" style={{ color: e.overdue ? '#fb7185' : 'var(--color-mute)' }}>{new Date(e.date).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</div>
                        <div className="mono text-[9.5px] text-[var(--color-faint)]">{e.kind}</div>
                      </div>
                    </div>
                  )
                })}
              </div>}
        </Card>
      </div>
    </div>
  )
}
