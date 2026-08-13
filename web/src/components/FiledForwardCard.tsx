import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, ReferenceDot } from 'recharts'
import { FileClock, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'

// The honest re-base: for a metric that genuinely has filed history (financed emissions), the forward view
// continues from the last value the institution actually FILED — not the model's current-basis figure — so
// reported → projected reads as one line. Metrics with no filed counterpart (physical VaR by pathway) are not
// re-based; this card simply doesn't render for them. Renders nothing when no prior filings exist.

interface P { period: string; value: number; unit: string | null; basis_break: boolean }
interface Proj { period: string; value: number }
interface S {
  datapoint_key: string; label: string; points: P[]; basis_changed: boolean
  projection: Proj[]; proj_method: string | null; proj_reliable: boolean
}

const FEATURED = ['financed_emissions', 'p3_scope3', 'e1_ghg', 'pai_climate']
const compact = (n: number) => {
  const a = Math.abs(n)
  return a >= 1e9 ? `${(n / 1e9).toFixed(2)}bn` : a >= 1e6 ? `${(n / 1e6).toFixed(2)}m`
    : a >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : (a > 0 && a < 10 ? n.toFixed(3).replace(/\.?0+$/, '') : n.toLocaleString())
}

export default function FiledForwardCard() {
  const q = useQuery({ queryKey: ['pf-trends-analytics'], retry: false,
    queryFn: () => api.get<{ series: S[] }>('/v1/prior-filings/trends?horizon_years=3') })
  const series = q.data?.series ?? []
  const s = series.find(x => FEATURED.includes(x.datapoint_key) && x.points.length >= 1)
  if (!s) return null

  const unit = s.points[0].unit && s.points[0].unit !== 'pure' ? ` ${s.points[0].unit}` : ''
  const lastActual = s.points[s.points.length - 1]
  const lastProj = s.projection[s.projection.length - 1]
  const name = s.label.split('—')[0].split('(')[0].trim()

  // one dataset: reported carry `value`, projected years carry `proj`; the last reported point also carries
  // `proj` so the dashed projection starts exactly where the solid reported line ends.
  const data: Record<string, number | string | boolean>[] = [
    ...s.points.map(p => ({ period: p.period, value: p.value, basis_break: p.basis_break })),
    ...s.projection.map(p => ({ period: p.period, proj: p.value })),
  ]
  if (s.projection.length) {
    const anchor = data.find(r => r.period === lastActual.period)
    if (anchor) anchor.proj = lastActual.value
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <FileClock size={15} className="text-[var(--color-blue)] shrink-0" />
          <h3 className="font-semibold text-[15.5px] text-[var(--color-ink)] leading-tight m-0 truncate">{name} — reported &amp; projected</h3>
        </div>
        <Link to="/prior-filings" className="inline-flex items-center gap-1 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline shrink-0">Prior filings <ArrowRight size={11} /></Link>
      </div>
      <div className="p-5">
        {s.points.length < 2 ? (
          <div className="text-[13px] text-[var(--color-mute)]">Last filed <span className="mono text-[var(--color-ink)]">{lastActual.period}: {compact(lastActual.value)}{unit}</span>. Import earlier years in Prior filings to project the forward path from here.</div>
        ) : (
          <>
            <div className="h-[150px] -ml-2">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: 6 }}>
                  <XAxis dataKey="period" tick={{ fontSize: 10.5, fill: 'var(--color-faint)' }} axisLine={{ stroke: 'var(--color-line-2)' }} tickLine={false} />
                  <YAxis tickFormatter={compact} width={50} tick={{ fontSize: 10.5, fill: 'var(--color-faint)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-line-2)', borderRadius: 10, fontSize: 12 }}
                    labelStyle={{ color: 'var(--color-mute)' }}
                    formatter={(v, n) => [`${compact(Number(v))}${unit}`, n === 'proj' ? 'Projected' : 'Reported']} />
                  <Line type="monotone" dataKey="value" name="value" stroke="var(--color-sky)" strokeWidth={2.25} dot={{ r: 2.5, fill: 'var(--color-sky)' }} isAnimationActive={false} />
                  <Line type="monotone" dataKey="proj" name="proj" stroke="var(--color-mute)" strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2, fill: 'var(--color-mute)' }} connectNulls isAnimationActive={false} />
                  {s.points.map((p, i) => p.basis_break && <ReferenceDot key={i} x={p.period} y={p.value} r={4} fill="var(--color-warn)" stroke="var(--color-bg-2)" strokeWidth={2} />)}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-2 text-[12px] text-[var(--color-mute)]">
              Last filed <span className="mono text-[var(--color-ink)]">{lastActual.period}: {compact(lastActual.value)}{unit}</span>
              {lastProj && <> → projected <span className="mono text-[var(--color-ink)]">{lastProj.period}: {compact(lastProj.value)}{unit}</span></>}
              <span className="text-[var(--color-faint)]"> · dashed = projected from your last filed value{s.proj_method ? ` (${s.proj_method})` : ''}{!s.proj_reliable ? ' — indicative; preparation basis changed across the filed years' : ''}.</span>
            </div>
          </>
        )}
      </div>
    </Card>
  )
}
