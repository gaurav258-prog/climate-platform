import { useQuery } from '@tanstack/react-query'
import { Telescope } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { countryName } from '../lib/countries'
import { hazardLabel } from '../lib/hazards'
import { HEADING, InfoButton } from './Details'
import { Card, SectionHead } from './ui'

// Supply outlook (E164) — the seasons the yield record does not hold yet, read only through PUBLISHED calibrations
// (services/outlook): a loss range where the calibration passed the downside gate, a gain range where it passed the four
// upside rules, otherwise held with the reason. Own origins first, then the alternatives. Context only — never part of
// volume at risk, COGS-at-risk, KRIs or filings.

interface Season { year: number; score: number; reads: 'loss' | 'gain' | 'held'; range_pct?: [number, number, number]; capped?: boolean; why?: string }
interface Origin {
  origin: string; own: boolean; driver: string; recipe: string; yield_source: string; last_reported_year: number | null; r2_oos: number
  downside_pass: boolean; upside_pass: boolean; seasons: Season[]; in_progress: { year: number; months_observed: number; months: number } | null; weather_through: string | null
}
interface Resp { commodity: string; origins: Origin[]; own_without_calibration: string[]; basis: string }

const pct = (v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`

function Chip({ ok, yes, no }: { ok: boolean; yes: string; no: string }) {
  return <span className="text-[10.5px] font-medium border rounded px-1.5 py-0.5 whitespace-nowrap"
    style={{ color: ok ? 'var(--color-good)' : 'var(--color-faint)', borderColor: ok ? 'var(--color-good)' : 'var(--color-line-2)' }}>{ok ? yes : no}</span>
}

function SeasonCell({ s }: { s: Season }) {
  if (s.reads === 'held') return (
    <span className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-faint)]">{s.year}: held
      {s.why && <InfoButton compact details={{ title: `${s.year}: held`, sections: [{ heading: 'Why', body: s.why }] }} />}</span>
  )
  const [lo, mid, hi] = s.range_pct!
  return (
    <span className="text-[12px] tabular-nums" style={{ color: s.reads === 'loss' ? 'var(--color-bad)' : 'var(--color-good)' }}
      title={`Driver score ${s.score}. 68% range of production against its trend.`}>
      {s.year}: {pct(mid)} <span className="text-[var(--color-faint)]">({pct(lo)} to {pct(hi)}){s.capped ? ' · capped' : ''}</span>
    </span>
  )
}

export default function SupplyOutlook({ commodityId }: { commodityId: string }) {
  const q = useQuery({ queryKey: ['supply-outlook', commodityId], queryFn: () => api.get<Resp>(`/v1/supply/commodity/${commodityId}/outlook`) })
  const d = q.data
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={Telescope} hint="context, not volume at risk">Supply outlook</SectionHead>
        <InfoButton compact details={{ title: 'Supply outlook', sections: [
          { heading: HEADING.shows, body: "The seasons the yield record does not hold yet, read through each origin's published calibration and the season's weather over the crop's growing area. Context only — never part of volume at risk." },
          { heading: HEADING.read, body: 'Production against its trend, as a 68% range. A loss is shown only where the calibration passed its downside test, a gain only where it passed the upside rules; otherwise the season is held and the reason given.' },
        ] }} />
      </div>
      {q.isLoading ? <div className="text-[13px] text-[var(--color-faint)]">loading…</div>
        : q.error || !d ? <div className="text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the outlook.')}</div>
        : d.origins.length === 0 ? <div className="text-[13px] text-[var(--color-faint)]">No origin of {d.commodity} has a published calibration yet.</div>
        : (
        <div className="space-y-3">
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] tabular-nums">
              <thead><tr className="text-[var(--color-faint)] text-[11px] text-left">
                {['Origin', 'Driver', 'Calibration', 'Seasons not yet in the yield record', 'Season in progress'].map(h => <th key={h} className="font-medium py-1 pr-3">{h}</th>)}
              </tr></thead>
              <tbody>{d.origins.map(o => (
                <tr key={`${o.origin}-${o.driver}`} className="border-t border-[var(--color-line)] align-top">
                  <td className="py-1.5 pr-3"><span className="text-[var(--color-ink)]">{countryName(o.origin)}</span> <span className="text-[10.5px] text-[var(--color-faint)]">{o.own ? 'your origin' : 'alternative'}</span></td>
                  <td className="pr-3">{hazardLabel(o.driver)}</td>
                  <td className="pr-3 space-x-1"><Chip ok={o.downside_pass} yes="loss range" no="loss held" /><Chip ok={o.upside_pass} yes="gain range" no="gain held" /></td>
                  <td className="pr-3 space-y-0.5">{o.seasons.length === 0
                    ? <span className="text-[11px] text-[var(--color-faint)]">none — the yield record reaches {o.last_reported_year ?? '—'}; weather to {o.weather_through?.slice(0, 7) ?? '—'}</span>
                    : o.seasons.map(s => <div key={s.year}><SeasonCell s={s} /></div>)}</td>
                  <td className="pr-3 text-[11px] text-[var(--color-mute)]">{o.in_progress ? `${o.in_progress.year}: ${o.in_progress.months_observed} of ${o.in_progress.months} months observed — read when the season completes` : '—'}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          {d.own_without_calibration.length > 0 && <div className="text-[11.5px] text-[var(--color-mute)]">Your origins with no published calibration: {d.own_without_calibration.map(countryName).join(', ')}.</div>}
        </div>)}
    </Card>
  )
}
