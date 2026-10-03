import { useQuery } from '@tanstack/react-query'
import { Globe2 } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { Card, SectionHead } from './ui'

// What happened to the world crop, year by year — CONTEXT only (services/intelligence/world_crop.py). The net figure
// lets one origin's good year offset another's bad one; the losses figure is what the damage-only model is validated
// against. Neither is a forecast, and neither enters volume at risk.

interface Year { year: number; reported_pct: number | null; net_pct: number | null; losses_pct: number | null; coverage_pct: number; origins_used: number; origins_total: number; why_not: string | null }
interface Origin { origin: string; world_share_pct: number; deviation_pct: number; weighted_pct: number }
interface Resp { commodity: string; source: string; data_to_year: number | null; loaded_at: string | null; available: boolean; reason?: string; trend_years_after: number; years: Year[]; origins: { year: number; rows: Origin[] } | null }

const pct = (v: number | null) => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`
const tone = (v: number | null) => v == null ? 'var(--color-faint)' : v < 0 ? 'var(--color-bad)' : v > 0 ? 'var(--color-good)' : 'var(--color-mute)'

export default function WorldCrop({ commodityId }: { commodityId: string }) {
  const q = useQuery({ queryKey: ['world-crop', commodityId], queryFn: () => api.get<Resp>(`/v1/supply/commodity/${commodityId}/world-crop`) })
  const d = q.data
  return (
    <Card className="p-5">
      <SectionHead icon={Globe2} hint="context — not a forecast, not part of volume at risk" className="mb-3">World crop — what happened</SectionHead>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)]">loading…</div>
        : q.error || !d ? <div className="text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the world crop.')}</div>
        : !d.available ? <div className="text-[13px] text-[var(--color-faint)]">{d.reason}</div>
        : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left">
                <th className="font-normal py-1 pr-3">Year</th>
                <th className="font-normal px-2 text-right" title="The world total's change on the year, as FAOSTAT reports it">Reported</th>
                <th className="font-normal px-2 text-right" title="Every decomposable origin's deviation from trend (bearing cycle removed), weighted by its world share — gains offset losses">Net</th>
                <th className="font-normal px-2 text-right" title="The same, counting only the origins below trend — the crop lost">Losses only</th>
                <th className="font-normal px-2 text-right" title="Share of the previous year's world crop held by the origins that could be decomposed">Coverage</th>
              </tr></thead>
              <tbody>
                {d.years.map(y => (
                  <tr key={y.year} className="border-t border-[var(--color-line)]">
                    <td className="py-1.5 pr-3 mono text-[var(--color-ink)]">{y.year}</td>
                    <td className="px-2 text-right mono" style={{ color: tone(y.reported_pct) }}>{pct(y.reported_pct)}</td>
                    {y.why_not
                      ? <td colSpan={3} className="px-2 text-right text-[11px] text-[var(--color-faint)]">{y.why_not}</td>
                      : <>
                          <td className="px-2 text-right mono" style={{ color: tone(y.net_pct) }}>{pct(y.net_pct)}</td>
                          <td className="px-2 text-right mono" style={{ color: tone(y.losses_pct) }}>{pct(y.losses_pct)}</td>
                          <td className="px-2 text-right mono text-[var(--color-mute)]">{y.coverage_pct.toFixed(0)}% <span className="text-[var(--color-faint)]">· {y.origins_used}/{y.origins_total}</span></td>
                        </>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {d.origins && d.origins.rows.length > 0 && (
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5">What moved {d.origins.year} most · deviation from trend × world share</div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
                {d.origins.rows.map(o => (
                  <span key={o.origin} className="text-[var(--color-mute)]">
                    <span className="mono text-[var(--color-ink)]">{o.origin}</span> {pct(o.deviation_pct)} <span className="text-[var(--color-faint)]">of {o.world_share_pct}% share</span>{' '}
                    <span className="mono" style={{ color: tone(o.weighted_pct) }}>({o.weighted_pct > 0 ? '+' : ''}{o.weighted_pct.toFixed(2)} pts)</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className="text-[11px] text-[var(--color-faint)] space-y-1 max-w-[80ch]">
            <p><b className="text-[var(--color-mute)]">Net</b> lets one origin's good year offset another's bad one; <b className="text-[var(--color-mute)]">losses only</b> is the crop that was lost — the figure our damage model is validated against. Volume at risk counts losses only: a good harvest elsewhere does not save your own plots.</p>
            <p>The deviation is what trend and bearing cycle do not explain — weather, but also pests, policy, new plantings and irrigation; gains especially are not all weather. A year needs {d.trend_years_after} later years of data before it can be decomposed. Source: {d.source}, to {d.data_to_year}{d.loaded_at ? ` (loaded ${d.loaded_at})` : ''}.</p>
          </div>
        </div>
      )}
    </Card>
  )
}
