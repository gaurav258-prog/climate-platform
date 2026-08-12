import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { FileClock, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'

// A slim reference that ties the forward view back to what the organisation actually filed: it shows the
// most recent confirmed filed figure (financed emissions where present) and links to Prior filings, where
// the projection continues from that value. Renders nothing when no prior filings are on file.

interface P { period: string; value: number; unit: string | null }
interface S { datapoint_key: string; label: string; points: P[] }

const fmt = (n: number, u: string | null) => {
  const a = Math.abs(n)
  const s = a >= 1e9 ? `${(n / 1e9).toFixed(2)}bn` : a >= 1e6 ? `${(n / 1e6).toFixed(2)}m`
    : a >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : (a > 0 && a < 10 ? n.toFixed(3).replace(/\.?0+$/, '') : n.toLocaleString())
  return `${s}${u && u !== 'pure' ? ` ${u}` : ''}`
}

const FEATURED = ['financed_emissions', 'p3_scope3', 'e1_ghg', 'pai_climate']

export default function ReportedHistoryRef() {
  const q = useQuery({ queryKey: ['pf-trends-ref'], retry: false,
    queryFn: () => api.get<{ series: S[] }>('/v1/prior-filings/trends?horizon_years=1') })
  const series = q.data?.series ?? []
  if (!series.length) return null

  const year = Math.max(...series.flatMap(s => s.points.map(p => parseInt(p.period, 10) || 0)))
  const feat = series.find(s => FEATURED.includes(s.datapoint_key)) ?? series[0]
  const last = feat.points[feat.points.length - 1]
  const name = feat.label.split('—')[0].split('(')[0].trim()

  return (
    <Link to="/prior-filings"
      className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-3 py-1.5 text-[12px] hover:border-[var(--color-sky)] transition">
      <FileClock size={13} className="text-[var(--color-blue)] shrink-0" />
      <span className="text-[var(--color-mute)]">Anchored to your last filing ({year}) — {name}: <span className="text-[var(--color-ink)] mono tabular-nums">{fmt(last.value, last.unit)}</span></span>
      <ArrowRight size={12} className="text-[var(--color-sky)] shrink-0" />
    </Link>
  )
}
