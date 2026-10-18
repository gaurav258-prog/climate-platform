import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight } from 'lucide-react'
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Card } from '../../components/ui'
import MethodGap from '../../components/MethodGap'
import { MessageLine, type Message } from '../../components/Details'
import { scenarioLabel } from '../../lib/labels'
import { balance } from '../../lib/money'
import { CardHead, calcDetails } from './common'
import { SCENARIO_COLOR } from './sectors'

// The forward view's decision signal: the value at or above the organisation's at-risk level today and by 2030, 2050
// and 2100 under one pathway (a line, with the climate models' range as a band), and the assets whose score rises
// most (a slope chart). The method is the server's own (portfolio.forward.*); the screen carries only figures.

interface Point { horizon: string; at_risk_eur: number; at_risk_pct: number; at_risk_band_eur: [number, number]; newly_crossing_eur: number; newly_crossing_count: number }
interface Mover { entity_name: string; current_score: number; future_score: number; delta: number; value_eur: number; horizon: string }
export interface ForwardRisk {
  scenario: string; trajectory: Point[]; movers: Mover[]; runway: string | null; at_risk_threshold?: number
  gap?: string; runway_gap?: string; runway_message?: Message; basis_message?: Message
}

const yearOf = (h: string) => (h === 'current' ? 'Today' : h)

export default function ForwardRiskCard({ d }: { d: ForwardRisk }) {
  if (d.gap) return <MethodGap gap={d.gap} what="Forward risk" />
  const traj = d.trajectory
  const now = traj.find(t => t.horizon === 'current')
  const end = traj[traj.length - 1]
  const color = SCENARIO_COLOR[d.scenario] ?? 'var(--color-sky)'
  const pathway = scenarioLabel(d.scenario)
  const details = calcDetails('Forward risk',
    `The value of your book at or above your at-risk level today, and by 2030, 2050 and 2100 under the ${pathway} pathway, with the assets whose risk rises most.`,
    d.basis_message,
    'The line is the value at risk; the shaded band is its range across the climate models. In the second chart each line is one asset: its score today on the left and in the last year on the right. The flat line is your at-risk level.')
  return (
    <Card className="p-5">
      <CardHead title="Forward risk" hint={pathway} details={details} />
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 mb-4">
        <span className="display text-[26px] leading-none tabular-nums">{now?.at_risk_pct ?? 0}%</span>
        <span className="text-[13px] text-[var(--color-mute)]">of the book at risk today</span>
        {end && end !== now && <>
          <ArrowRight size={15} className="text-[var(--color-faint)] self-center" />
          <span className="display text-[26px] leading-none tabular-nums" style={{ color }}>{end.at_risk_pct}%</span>
          <span className="text-[13px] text-[var(--color-mute)]">by {end.horizon}</span>
        </>}
        {d.runway_message && (
          <span className={`ml-2 text-[12.5px] px-2.5 py-0.5 rounded-full border ${d.runway ? 'border-[var(--color-warn)]/50 text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>
            <MessageLine m={d.runway_message} />
          </span>
        )}
      </div>
      {d.runway_gap && <div className="mb-4"><MethodGap gap={d.runway_gap} what="Act-by year" /></div>}
      <div className="grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Trajectory points={traj} color={color} />
        {d.movers.length > 0 && (
          <div className="min-w-0">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-[12.5px] text-[var(--color-mute)]">Biggest movers by {d.movers[0].horizon}</span>
              <Link to="/decisions" className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline shrink-0">
                Act on these <ArrowRight size={12} />
              </Link>
            </div>
            <Slope movers={d.movers} level={d.at_risk_threshold} color={color} />
          </div>
        )}
      </div>
    </Card>
  )
}

type Row = { label: string; v: number; band: [number, number]; pct: number; newEur: number; newN: number }

function TrajTip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  const r = active ? payload?.[0]?.payload : undefined
  if (!r) return null
  return (
    <div className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-2 text-[12px] shadow-sm">
      <div className="text-[var(--color-mute)] mb-0.5">{r.label}</div>
      <div className="text-[var(--color-ink)] tabular-nums"><b>{balance(r.v)}</b> at risk · {r.pct}% of the book</div>
      {r.band[0] !== r.band[1] && <div className="text-[var(--color-mute)] tabular-nums">Range across models {balance(r.band[0])} – {balance(r.band[1])}</div>}
      {r.newEur > 0 && <div className="text-[var(--color-mute)] tabular-nums">Newly at risk {balance(r.newEur)} · {r.newN} assets</div>}
    </div>
  )
}

// The value at risk by year: one line, the models' range as a band behind it.
function Trajectory({ points, color }: { points: Point[]; color: string }) {
  const rows: Row[] = points.map(p => ({ label: yearOf(p.horizon), v: p.at_risk_eur, band: p.at_risk_band_eur, pct: p.at_risk_pct, newEur: p.newly_crossing_eur, newN: p.newly_crossing_count }))
  const top = Math.max(1, ...rows.flatMap(r => [r.v, r.band[1]]))
  return (
    <div className="min-w-0">
      <div className="text-[12.5px] text-[var(--color-mute)] mb-1">Value at risk</div>
      <div className="h-[210px] -ml-1" role="img" aria-label={rows.map(r => `${r.label}: ${balance(r.v)}`).join(', ')}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 14, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={{ stroke: 'var(--color-line-2)' }} tickLine={false} />
            <YAxis domain={[0, top * 1.08]} tickFormatter={(v: number) => balance(v)} width={62} tick={{ fontSize: 11, fill: 'var(--color-faint)' }} axisLine={false} tickLine={false} />
            <Tooltip content={<TrajTip />} cursor={{ stroke: 'var(--color-line-2)' }} />
            <Area dataKey="band" stroke="none" fill={color} fillOpacity={0.14} isAnimationActive={false} activeDot={false} />
            <Line dataKey="v" stroke={color} strokeWidth={2} isAnimationActive={false}
              dot={{ r: 4, fill: color, stroke: 'var(--color-panel)', strokeWidth: 2 }} activeDot={{ r: 5, fill: color, stroke: 'var(--color-panel)', strokeWidth: 2 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)] mt-1">
        <span className="inline-flex items-center gap-1.5"><span className="w-4 h-[2px] rounded" style={{ background: color }} />Value at risk</span>
        <span className="inline-flex items-center gap-1.5"><span className="w-4 h-2.5 rounded-sm" style={{ background: color, opacity: 0.25 }} />Range across climate models</span>
      </div>
    </div>
  )
}

// A slope chart: each asset's score today (left) and in the last year (right), the at-risk level as a flat line. Labels
// sit right of the lines, pushed apart where they would overlap and tied back to their line by a short leader.
function Slope({ movers, level, color }: { movers: Mover[]; level?: number; color: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [w, setW] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  const H = 220, TOP = 26, BOTTOM = 12, GAP = 30
  const all = [...movers.flatMap(m => [m.current_score, m.future_score]), ...(level != null ? [level] : [])]
  const lo = Math.max(0, Math.floor((Math.min(...all) - 4) / 10) * 10)
  const hi = Math.min(100, Math.ceil((Math.max(...all) + 4) / 10) * 10)
  const y = (s: number) => TOP + ((hi - s) / Math.max(1, hi - lo)) * (H - TOP - BOTTOM)
  const labelW = Math.min(210, Math.max(118, w * 0.44))
  const xL = 14, xR = Math.max(xL + 50, w - labelW - 22)
  // label rows: in the order of their line ends, at least GAP apart, kept inside the chart
  const order = movers.map((m, i) => ({ i, y: y(m.future_score) })).sort((a, b) => a.y - b.y)
  const pos: number[] = []
  order.forEach((o, k) => { pos[k] = k ? Math.max(o.y, pos[k - 1] + GAP) : Math.max(o.y, TOP) })
  const over = (pos[pos.length - 1] ?? 0) - (H - BOTTOM - GAP / 2)
  if (over > 0) for (let k = pos.length - 1; k >= 0; k--) pos[k] = Math.max(TOP - 6, pos[k] - over)
  const labelY: Record<number, number> = Object.fromEntries(order.map((o, k) => [o.i, pos[k]]))
  return (
    <div ref={ref} className="w-full">
      {w > 0 && (
        <svg width={w} height={H} role="img" aria-label={movers.map(m => `${m.entity_name}: ${Math.round(m.current_score)} to ${Math.round(m.future_score)}`).join('; ')}>
          <text x={xL} y={12} fontSize={11} fill="var(--color-faint)">Today</text>
          <text x={xR} y={12} fontSize={11} fill="var(--color-faint)" textAnchor="middle">{movers[0].horizon}</text>
          <line x1={xL} x2={xL} y1={TOP - 6} y2={H - BOTTOM} stroke="var(--color-line)" />
          <line x1={xR} x2={xR} y1={TOP - 6} y2={H - BOTTOM} stroke="var(--color-line)" />
          {level != null && <>
            <line x1={xL} x2={xR} y1={y(level)} y2={y(level)} stroke="var(--color-line-2)" />
            <text x={xL + 4} y={y(level) - 4} fontSize={10.5} fill="var(--color-faint)" stroke="var(--color-panel)" strokeWidth={3} paintOrder="stroke">At-risk level {level}</text>
          </>}
          {movers.map((m, i) => {
            const dim = hover != null && hover !== i
            const y1 = y(m.current_score), y2 = y(m.future_score), ly = labelY[i]
            return (
              <g key={i} opacity={dim ? 0.3 : 1} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: 'default' }}>
                <title>{`${m.entity_name}: ${Math.round(m.current_score)} today → ${Math.round(m.future_score)} by ${m.horizon} · ${balance(m.value_eur)}`}</title>
                <line x1={xL} y1={y1} x2={xR} y2={y2} stroke="transparent" strokeWidth={14} />
                <line x1={xL} y1={y1} x2={xR} y2={y2} stroke={color} strokeWidth={2} strokeLinecap="round" />
                <circle cx={xL} cy={y1} r={4} fill={color} stroke="var(--color-panel)" strokeWidth={2} />
                <circle cx={xR} cy={y2} r={4} fill={color} stroke="var(--color-panel)" strokeWidth={2} />
                <polyline points={`${xR + 6},${y2} ${xR + 12},${y2} ${xR + 18},${ly}`} fill="none" stroke="var(--color-line-2)" />
                <text x={xR + 22} y={ly - 2} fontSize={12} fill="var(--color-ink)">{clip(m.entity_name, labelW)}</text>
                <text x={xR + 22} y={ly + 13} fontSize={11} fill="var(--color-mute)">{`${Math.round(m.current_score)} → ${Math.round(m.future_score)} · ${balance(m.value_eur)}`}</text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

// a name that fits its label column (about 6.3 px a character at 12 px)
const clip = (s: string, width: number) => { const n = Math.floor((width - 24) / 6.3); return s.length > n ? `${s.slice(0, n - 1)}…` : s }
