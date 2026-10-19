import { useQuery } from '@tanstack/react-query'
import { Globe2 } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { countryName } from '../lib/countries'
import { HEADING, InfoButton, type Details } from './Details'
import { Card, SectionHead } from './ui'

// What happened to the world crop, year by year — CONTEXT only (services/intelligence/world_crop.py). The net figure
// lets one origin's good year offset another's bad one; the losses figure is what the damage-only model is validated
// against. Neither is a forecast, and neither enters volume at risk.

interface Year { year: number; reported_pct: number | null; net_pct: number | null; losses_pct: number | null; coverage_pct: number; origins_used: number; origins_total: number; why_not: string | null }
interface Origin { origin: string; world_share_pct: number; deviation_pct: number; weighted_pct: number }
interface Resp { commodity: string; source: string; data_to_year: number | null; loaded_at: string | null; available: boolean; reason?: string; trend_years_after: number; years: Year[]; origins: { year: number; rows: Origin[] } | null }

const pct = (v: number | null) => v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

// How to read the table, where the figures come from and what they cannot say — one click away (UI standard).
const about = (d: Resp): Details => ({
  title: 'World crop — what happened',
  sections: [
    { heading: HEADING.shows, body: "Each year's world crop against its trend: what the publisher reports, and the deviation of every origin that can be decomposed, weighted by its share of the world crop. Context only — not a forecast, and not part of volume at risk." },
    { heading: HEADING.read, body: "Net lets one origin's good year offset another's bad one; losses only counts the origins below trend — the crop that was lost, the figure the damage model is validated against. Volume at risk counts losses only: a good harvest elsewhere does not save your own plots." },
    { heading: HEADING.sources, body: `${d.source}, to ${d.data_to_year ?? '—'}${d.loaded_at ? ` (loaded ${d.loaded_at})` : ''}.` },
    { heading: HEADING.limits, body: `The deviation is what trend and bearing cycle do not explain — weather, but also pests, policy, new plantings and irrigation; gains especially are not all weather. A year needs ${d.trend_years_after} later years of data before it can be decomposed.` },
  ],
})
const tone = (v: number | null) => v == null ? 'var(--color-faint)' : v < 0 ? 'var(--color-bad)' : v > 0 ? 'var(--color-good)' : 'var(--color-mute)'

export default function WorldCrop({ commodityId }: { commodityId: string }) {
  const q = useQuery({ queryKey: ['world-crop', commodityId], queryFn: () => api.get<Resp>(`/v1/supply/commodity/${commodityId}/world-crop`) })
  const d = q.data
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={Globe2} hint="context, not a forecast">World crop — what happened</SectionHead>
        {d?.available && <InfoButton compact details={about(d)} />}
      </div>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)]">loading…</div>
        : q.error || !d ? <div className="text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the world crop.')}</div>
        : !d.available ? <div className="flex items-center gap-1.5 text-[13px] text-[var(--color-faint)]">No world series for this crop
            {d.reason && <InfoButton compact details={{ title: 'World crop', sections: [{ heading: 'Why', body: d.reason }] }} />}</div>
        : (
        <div className="space-y-4">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
                <th className="font-medium py-1 pr-3">Year</th>
                <th className="font-medium px-2 text-right" title="The world total's change on the year, as the publisher reports it">Reported</th>
                <th className="font-medium px-2 text-right" title="Every decomposable origin's deviation from trend (bearing cycle removed), weighted by its world share — gains offset losses">Net</th>
                <th className="font-medium px-2 text-right" title="The same, counting only the origins below trend — the crop lost">Losses only</th>
                <th className="font-medium px-2 text-right" title="Share of the previous year's world crop held by the origins that could be decomposed">Coverage</th>
              </tr></thead>
              <tbody>
                {d.years.map(y => (
                  <tr key={y.year} className="border-t border-[var(--color-line)]">
                    <td className="py-1.5 pr-3 text-[var(--color-ink)]">{y.year}</td>
                    <td className="px-2 text-right" style={{ color: tone(y.reported_pct) }}>{pct(y.reported_pct)}</td>
                    {y.why_not
                      ? <td colSpan={3} className="px-2 text-right text-[11.5px] text-[var(--color-faint)]">
                          <span className="inline-flex items-center gap-1">Not decomposed
                            <InfoButton compact details={{ title: String(y.year), sections: [{ heading: 'Why', body: y.why_not }] }} /></span></td>
                      : <>
                          <td className="px-2 text-right" style={{ color: tone(y.net_pct) }}>{pct(y.net_pct)}</td>
                          <td className="px-2 text-right" style={{ color: tone(y.losses_pct) }}>{pct(y.losses_pct)}</td>
                          <td className="px-2 text-right text-[var(--color-mute)]">{y.coverage_pct.toFixed(0)}% <span className="text-[var(--color-faint)]">· {y.origins_used}/{y.origins_total}</span></td>
                        </>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {d.origins && d.origins.rows.length > 0 && (
            <div>
              <div className="text-[11.5px] font-medium text-[var(--color-faint)] mb-1.5"
                title="Each origin's deviation from trend, times its share of the world crop">What moved {d.origins.year} most</div>
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-[12px] tabular-nums">
                {d.origins.rows.map(o => (
                  <span key={o.origin} className="text-[var(--color-mute)]">
                    <span className="text-[var(--color-ink)]">{countryName(o.origin)}</span> {pct(o.deviation_pct)} <span className="text-[var(--color-faint)]">of {o.world_share_pct}% share</span>{' '}
                    <span style={{ color: tone(o.weighted_pct) }}>({o.weighted_pct > 0 ? '+' : ''}{o.weighted_pct.toFixed(2)} pts)</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
