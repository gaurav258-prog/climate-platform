import { useQuery } from '@tanstack/react-query'
import { Timer, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'

// Detection lag — how long each KRI sat in breach before anyone acted on it. Every figure here is a pure
// timestamp fact from the breach-episode ledger (onset when first observed out of appetite → acknowledged
// when a remediation task was raised → cleared when back in appetite), never an estimate. Answers the board's
// "how long did each breach take to surface?" directly. Hidden until there's at least one recorded episode.

interface Episode {
  kri_key: string; label: string; severity: string; open: boolean; acknowledged: boolean
  days_in_breach: number; response_lag_days: number | null
}
interface Resp {
  episodes: Episode[]
  summary: { n_episodes: number; n_open: number; n_unacknowledged: number; median_response_lag_days: number | null; worst_open_unacknowledged_days: number | null }
}

const dur = (n: number | null) => n == null ? '—' : n < 1 ? `${Math.round(n * 24)}h` : `${n < 10 ? n.toFixed(1) : Math.round(n)}d`

function Stat({ label, value, tone = 'ink' }: { label: string; value: string; tone?: 'ink' | 'good' | 'bad' | 'warn' }) {
  const c = { ink: 'var(--color-ink)', good: 'var(--color-good)', bad: 'var(--color-bad)', warn: 'var(--color-warn)' }[tone]
  return (
    <div>
      <div className="display text-[22px] leading-none tabular-nums" style={{ color: c }}>{value}</div>
      <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">{label}</div>
    </div>
  )
}

export default function DetectionLag({ framework }: { framework: string }) {
  const q = useQuery({
    queryKey: ['kri-detection-lag', framework],
    queryFn: () => api.get<Resp>(`/v1/reg-tasks/kri/detection-lag?framework=${framework}`),
    enabled: !!framework,
  })
  const d = q.data
  if (!d || d.summary.n_episodes === 0) return null
  const s = d.summary
  const open = d.episodes.filter(e => e.open).sort((a, b) => b.days_in_breach - a.days_in_breach)

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Timer size={15} className="text-[var(--color-blue)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">Detection lag</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· how long a breach sits before it's actioned</span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
        <Stat label="Open breaches" value={String(s.n_open)} />
        <Stat label="Unacknowledged" value={String(s.n_unacknowledged)} tone={s.n_unacknowledged ? 'bad' : 'good'} />
        <Stat label="Worst open" value={dur(s.worst_open_unacknowledged_days)} tone={(s.worst_open_unacknowledged_days ?? 0) >= 7 ? 'warn' : 'ink'} />
        <Stat label="Median response" value={dur(s.median_response_lag_days)} />
      </div>
      {open.length > 0 && (
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {open.slice(0, 6).map(e => (
            <div key={e.kri_key} className="flex items-center gap-3 py-2 text-[12.5px]">
              <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: e.severity === 'red' ? 'var(--color-bad)' : 'var(--color-warn)' }} />
              <span className="flex-1 min-w-0 truncate text-[var(--color-ink)]">{e.label}</span>
              <span className="mono text-[11px] text-[var(--color-mute)] shrink-0">{dur(e.days_in_breach)} in breach</span>
              {e.acknowledged
                ? <span className="mono text-[10px] inline-flex items-center gap-1 shrink-0" style={{ color: 'var(--color-good)' }}><CheckCircle2 size={11} /> actioned{e.response_lag_days != null ? ` · ${dur(e.response_lag_days)}` : ''}</span>
                : <span className="mono text-[10px] inline-flex items-center gap-1 shrink-0" style={{ color: 'var(--color-bad)' }}><AlertTriangle size={11} /> not actioned</span>}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
