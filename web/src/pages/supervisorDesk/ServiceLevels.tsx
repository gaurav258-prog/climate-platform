import { useQuery } from '@tanstack/react-query'
import { Timer } from 'lucide-react'
import { api } from '../../lib/api'
import { Card, SectionHead } from '../../components/ui'
import { HBar } from '../../components/Charts'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { Meter, hrs } from './common'

// Service levels of the engagement, computed only from the times each thread recorded: medians with how many requests
// they rest on, replies on time as a meter, overdue requests by days late, and what is open per entity as bars.
interface Stat { n: number; median: number | null; p90: number | null }
interface Sla { authority: string; n: number; n_open: number; time_to_acknowledge_hours: Stat; time_to_respond_hours: Stat; time_to_close_hours: Stat
  responded_on_time: { n: number; on_time: number; rate: number | null }; awaiting_acknowledgement: { n: number; oldest_days: number | null }
  overdue: { n: number; ageing: Record<string, number>; oldest_days: number | null }
  by_entity: { supervised_org_id: string; label: string; n_open: number; overdue: { n: number } }[] }
interface SlaResp { as_of: string; authorities: Sla[]; ageing_buckets: string[]; note: Message
  definitions: Record<'time_to_acknowledge_hours' | 'time_to_respond_hours' | 'time_to_close_hours' | 'responded_on_time' | 'overdue', Message> }

function Metric({ m, value, sub }: { m: Message; value: string; sub: string }) {
  return (
    <div className="py-2 border-b border-[var(--color-line)] last:border-0">
      <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)]">{m.label}<InfoButton compact details={messageDetails(m)} /></div>
      <div className="flex items-baseline gap-2"><span className="display text-[22px] tabular-nums text-[var(--color-ink)]">{value}</span>
        <span className="text-[11.5px] text-[var(--color-faint)]">{sub}</span></div>
    </div>
  )
}

export function ServiceLevels() {
  const q = useQuery({ queryKey: ['supervisor-sla'], queryFn: () => api.get<SlaResp>('/v1/supervisor/engagement/sla') })
  const d = q.data, a = d?.authorities[0]
  if (!d || !a || a.n === 0) return null
  const df = d.definitions
  const measured = (s: Stat) => `median of ${s.n}`
  const ageing = d.ageing_buckets.map(b => ({ label: `${b} days late`, value: a.overdue.ageing[b] ?? 0, color: 'var(--color-bad)' }))
  const open = a.by_entity.filter(e => e.n_open > 0).slice(0, 7)
  const most = Math.max(1, ...open.map(e => e.n_open))
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={Timer}>Service levels</SectionHead>
        <InfoButton compact details={messageDetails(d.note)} />
        <span className="ml-auto text-[12px] text-[var(--color-faint)]">{a.n} requests · {a.n_open} open</span>
      </div>
      <div className="grid lg:grid-cols-3 gap-6">
        <div>
          <Metric m={df.time_to_acknowledge_hours} value={hrs(a.time_to_acknowledge_hours.median)} sub={measured(a.time_to_acknowledge_hours)} />
          <Metric m={df.time_to_respond_hours} value={hrs(a.time_to_respond_hours.median)} sub={measured(a.time_to_respond_hours)} />
          <div className="py-2">
            <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] mb-1.5">{df.responded_on_time.label}<InfoButton compact details={messageDetails(df.responded_on_time)} /></div>
            <Meter value={a.responded_on_time.on_time} total={a.responded_on_time.n} />
          </div>
        </div>
        <div>
          <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] mb-2">{df.overdue.label} · {a.overdue.n}<InfoButton compact details={messageDetails(df.overdue)} /></div>
          {a.overdue.n ? <HBar data={ageing} format={n => String(n)} height={18} labelWidth="w-28" /> : <div className="text-[12.5px] text-[var(--color-faint)]">Nothing past its due date.</div>}
          {a.awaiting_acknowledgement.n > 0 && <div className="text-[12px] text-[var(--color-mute)] mt-3">Receipt not acknowledged: {a.awaiting_acknowledgement.n}
            {a.awaiting_acknowledgement.oldest_days != null ? ` · oldest ${a.awaiting_acknowledgement.oldest_days} days` : ''}</div>}
        </div>
        <div>
          <div className="text-[12px] text-[var(--color-mute)] mb-2">Open by entity</div>
          <div className="space-y-1.5">{open.map(e => (
            <div key={e.supervised_org_id} className="flex items-center gap-2 text-[11.5px]">
              <span className="w-32 shrink-0 truncate text-right text-[var(--color-mute)]" title={e.label}>{e.label}</span>
              <span className="flex-1 flex h-[14px] rounded overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={`${e.n_open} open, ${e.overdue.n} overdue`}>
                <span style={{ width: `${(e.overdue.n / most) * 100}%`, background: 'var(--color-bad)' }} />
                <span style={{ width: `${((e.n_open - e.overdue.n) / most) * 100}%`, background: 'var(--color-warn)' }} />
              </span>
              <span className="w-6 tabular-nums text-[var(--color-ink)]">{e.n_open}</span>
            </div>))}</div>
          {open.length > 0 && <div className="flex gap-3 mt-2 text-[11px] text-[var(--color-faint)]">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[var(--color-bad)]" />Overdue</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[var(--color-warn)]" />Open, not yet due</span></div>}
        </div>
      </div>
    </Card>
  )
}
