import { useState } from 'react'
import { History } from 'lucide-react'
import { Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, messageDetails, type Message } from '../../components/Details'
import { basisText, cellName, pct, type Named } from './checks'
import { VERDICT, type Verdict } from './RangeCell'

// The entity's filed template across the years on file, as a slope chart: one line per cell from year to year, the
// cells that moved most in colour, the whole template's share in bold. Under each year, that year's quick-check results.
export interface Trend {
  periods: { period_label: string; share_pct: number | null; basis: { scenario: string; horizon: string; stated: boolean }; tier1_counts: Record<Verdict, number> | null }[]
  cells: (Named & { key: string; share_pct: Record<string, number | null>; change_pp: number | null; moved: boolean })[]
  labels: string[]; change_pp: number | null; n_moved: number; move_pp: number; note: Message
}

const W = 640, H = 260, L = 40, R = 48, T = 14, B = 14
const pts = (n: number) => (i: number) => n < 2 ? L + (W - L - R) / 2 : L + (i * (W - L - R)) / (n - 1)
const yOf = (v: number) => T + (1 - v / 100) * (H - T - B)
const change = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(v)} pts`

export function AcrossYears({ t }: { t: Trend }) {
  const [hover, setHover] = useState<string | null>(null)
  const x = pts(t.labels.length)
  const line = (shares: (number | null)[]) => shares.map((v, i) => v == null ? null : `${x(i)},${yOf(v)}`).filter(Boolean).join(' ')
  const whole = t.periods.map(p => p.share_pct)
  const moved = t.cells.filter(c => c.change_pp != null).slice(0, 6)
  const hovered = t.cells.find(c => c.key === hover)
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
        <SectionHead icon={History}>Across years</SectionHead>
        <InfoButton compact details={{ title: 'Across years', sections: [
          ...messageDetails(t.note).sections,
          { heading: HEADING.read, body: `Each thin line is one cell’s filed share from year to year; the cells that moved more than ${t.move_pp} percentage points are in colour. The bold line is the whole template. Under each year, that year’s quick-check results.` },
        ] }} />
        {t.change_pp != null && <span className="ml-auto flex flex-wrap gap-1.5">
          <StatusChip tone={Math.abs(t.change_pp) > t.move_pp ? 'warn' : 'neutral'} label={`Whole template ${change(t.change_pp)}`} />
          <StatusChip tone={t.n_moved ? 'warn' : 'neutral'} label={`${t.n_moved} cells moved more than ${t.move_pp} pts`} />
        </span>}
      </div>
      {t.labels.length < 2 ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">One year on file: no trend yet.</div> : (
        <div className="grid gap-6 lg:grid-cols-[3fr_1fr] items-start">
          <div className="min-w-0">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label="Filed share of each cell, year by year">
              {[0, 25, 50, 75, 100].map(v => <g key={v}>
                <line x1={L} x2={W - R} y1={yOf(v)} y2={yOf(v)} stroke="var(--color-line)" strokeDasharray="3 3" />
                <text x={L - 6} y={yOf(v) + 4} textAnchor="end" fontSize="11" fill="var(--color-faint)">{v}%</text>
              </g>)}
              {t.labels.map((_, i) => <line key={i} x1={x(i)} x2={x(i)} y1={T} y2={H - B} stroke="var(--color-line-2)" />)}
              {t.cells.map(c => {
                const on = hover === c.key
                return <polyline key={c.key} points={line(t.labels.map(l => c.share_pct[l] ?? null))} fill="none"
                  stroke={c.moved ? 'var(--color-warn)' : 'var(--color-slate)'} strokeWidth={on ? 3 : c.moved ? 1.8 : 1}
                  strokeOpacity={hover && !on ? 0.15 : c.moved ? 0.9 : 0.35} onMouseEnter={() => setHover(c.key)} onMouseLeave={() => setHover(null)}>
                  <title>{`${cellName(c)}: ${t.labels.map(l => pct(c.share_pct[l])).join(' → ')}`}</title>
                </polyline>
              })}
              <polyline points={line(whole)} fill="none" stroke="var(--color-sky)" strokeWidth={3.5} />
              {whole.map((v, i) => v == null ? null : <g key={i}>
                <circle cx={x(i)} cy={yOf(v)} r={4.5} fill="var(--color-sky)" />
                <text x={x(i) + (i === whole.length - 1 ? 8 : -8)} y={yOf(v) + 4} textAnchor={i === whole.length - 1 ? 'start' : 'end'} fontSize="12" fontWeight="600" fill="var(--color-ink)">{v}%</text>
              </g>)}
            </svg>
            <div className="grid gap-3 mt-2" style={{ gridTemplateColumns: `repeat(${t.periods.length}, minmax(0, 1fr))` }}>
              {t.periods.map((p, i) => <Year key={p.period_label} p={p} align={i === 0 ? 'start' : i === t.periods.length - 1 ? 'end' : 'center'} />)}
            </div>
          </div>
          <div className="space-y-1.5 min-w-0">
            <div className="text-[12px] text-[var(--color-mute)] mb-1 truncate">{hovered ? cellName(hovered) : 'Moved most'}</div>
            {(hovered ? [hovered] : moved).map(c => (
              <div key={c.key} onMouseEnter={() => setHover(c.key)} onMouseLeave={() => setHover(null)}
                className="flex items-center justify-between gap-2 text-[12px]">
                <span className="truncate min-w-0 text-[var(--color-ink)]" title={cellName(c)}>{cellName(c)}</span>
                {c.change_pp != null && <StatusChip tone={c.moved ? 'warn' : 'neutral'} label={change(c.change_pp)} />}
              </div>))}
          </div>
        </div>)}
    </Card>
  )
}

function Year({ p, align }: { p: Trend['periods'][number]; align: 'start' | 'center' | 'end' }) {
  const c = p.tier1_counts
  const total = c ? Object.values(c).reduce((a, n) => a + n, 0) : 0
  const order: Verdict[] = ['plausible', 'above_band', 'below_band', 'no_reference']
  return (
    <div className={`flex flex-col gap-1 ${align === 'end' ? 'items-end text-right' : align === 'center' ? 'items-center text-center' : 'items-start'}`}>
      <div className="text-[12.5px] font-medium text-[var(--color-ink)]">{p.period_label}</div>
      <div className="text-[11px] text-[var(--color-faint)]">{p.basis.stated ? basisText(p.basis.scenario, p.basis.horizon) : 'No basis stated'}</div>
      {c && total > 0 ? (
        <div className="flex h-2 w-32 gap-[2px] rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img"
          aria-label={order.map(v => `${c[v]} ${VERDICT[v].label.toLowerCase()}`).join(', ')}>
          {order.filter(v => c[v]).map(v => <div key={v} title={`${VERDICT[v].label} ${c[v]}`} style={{ width: `${(c[v] / total) * 100}%`, background: VERDICT[v].color }} />)}
        </div>) : <div className="text-[11px] text-[var(--color-faint)]">Not checked</div>}
    </div>
  )
}
