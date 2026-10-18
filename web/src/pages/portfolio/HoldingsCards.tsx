import { Card, StatGrid, type StatItem } from '../../components/ui'
import { HBar } from '../../components/Charts'
import MethodGap from '../../components/MethodGap'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { hazardLabel } from '../../lib/labels'
import { balance } from '../../lib/money'
import { CardHead, GapLine, METHOD_TAB, calcDetails } from './common'

// The asset manager's cards: physical and transition risk in one loss distribution, and where the book's climate risk
// concentrates (by region, by hazard, and in clusters one event would hit together).

export interface CombinedVar {
  available: boolean; gap?: string; gap_message?: Message; var99_eur: number; physical_expected_eur: number; transition_expected_eur: number
  combined_expected_eur: number; combined_pct_of_book: number; n_positions: number; method_message?: Message
}

export function CombinedVarCard({ c, pathway }: { c?: CombinedVar; pathway: string }) {
  if (c && !c.available) return c.gap_message ? <GapLine what="Combined climate value at risk" m={c.gap_message} to={METHOD_TAB} />
    : c.gap ? <MethodGap gap={c.gap} what="Combined climate value at risk" /> : null
  if (!c) return null
  const metrics: StatItem[] = [
    { label: 'Combined expected loss', value: balance(c.combined_expected_eur), sub: `${c.combined_pct_of_book}% of the book`, accent: 'var(--color-warn)' },
    { label: 'Physical', value: balance(c.physical_expected_eur) },
    { label: 'Transition', value: balance(c.transition_expected_eur) },
    { label: 'Value at risk (99%)', value: balance(c.var99_eur) },
  ]
  const details = calcDetails('Combined climate value at risk',
    `Physical and transition risk on your ${c.n_positions} scored holdings in one loss distribution, under ${pathway}: the expected loss, its two parts, and the loss exceeded in one year out of a hundred.`,
    c.method_message)
  return (
    <Card className="p-5">
      <CardHead title="Combined climate value at risk" hint={pathway} details={details} />
      <StatGrid items={metrics} />
    </Card>
  )
}

interface Region { region: string; value_eur: number; climate_var_eur: number | null; n: number; pct_of_book: number }
interface HazardRow { hazard: string; value_eur: number; climate_var_eur: number | null; n: number; pct_of_scored: number }
interface Cluster { hazard: string; region: string; value_eur: number; climate_var_eur: number | null; n: number; pct_of_book: number }
export interface Concentration {
  available: boolean; gap?: string; n_scored: number; n_unscored: number; coverage_pct: number
  effective_regions: number | null; effective_hazards: number | null; top_region: Region | null
  common_shock: Cluster | null; common_shock_var_pct_of_total: number | null
  by_region: Region[]; by_hazard: HazardRow[]; clusters: Cluster[]; flags: Message[]; method_message?: Message
}

type Drill = { onRegion?: (region: string) => void; onHazard?: (hazard: string) => void; onCluster?: (hazard: string, region: string) => void }

export function ConcentrationCard({ c, onRegion, onHazard, onCluster }: { c?: Concentration } & Drill) {
  if (!c || !c.available) return null
  // the climate value at risk needs the manager's stated haircuts; until then the bars show the value itself
  const known = !c.gap
  const of = (x: { climate_var_eur: number | null; value_eur: number }) => (known ? x.climate_var_eur ?? 0 : x.value_eur)
  const what = known ? 'Value at risk' : 'Value'
  const cs = c.common_shock
  const metrics: StatItem[] = [
    { label: 'Effective regions', value: c.effective_regions ?? '—', sub: 'independent regional bets' },
    { label: 'Effective hazards', value: c.effective_hazards ?? '—', sub: 'independent hazard bets' },
    { label: c.top_region ? `Top region · ${c.top_region.region}` : 'Top region', value: c.top_region ? `${c.top_region.pct_of_book}%` : '—',
      sub: 'of the book', accent: c.top_region && c.top_region.pct_of_book > 25 ? 'var(--color-warn)' : undefined },
    { label: 'Largest cluster', value: c.common_shock_var_pct_of_total == null ? '—' : `${c.common_shock_var_pct_of_total}%`,
      sub: 'of the value at risk', accent: 'var(--color-warn)' },
  ]
  const details = calcDetails('Climate-risk concentration',
    'Where the book’s climate risk sits: by region, by the hazard that leads each holding’s score, and in clusters of holdings one event would hit together. Click a bar to see those holdings in your book.',
    c.method_message,
    `${c.n_scored} of ${c.n_scored + c.n_unscored} holdings are scored (${c.coverage_pct}%).${known ? '' : ' Until your valuation haircuts are stated, the bars show the value of the holdings, not their value at risk.'}`)
  return (
    <Card className="p-5">
      <CardHead title="Climate-risk concentration" details={details} />
      {!known && <div className="mb-3"><MethodGap gap={c.gap} what="Value at risk" /></div>}
      <StatGrid items={metrics} />
      {c.flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {c.flags.map(f => (
            <span key={f.code} className="inline-flex items-center gap-1"><StatusChip tone="warn" label={f.label} /><InfoButton compact details={messageDetails(f)} /></span>
          ))}
        </div>
      )}
      {cs && (
        <div className="mt-3 rounded-lg border border-[var(--color-line-2)] px-3.5 py-2.5 text-[13px] text-[var(--color-ink)]">
          <span className="text-[var(--color-mute)]">One event hits together: </span>
          <span className="font-medium">{hazardLabel(cs.hazard)}</span> in <span className="font-medium">{cs.region}</span>
          <span className="text-[var(--color-mute)]"> · {cs.n} holdings · {balance(cs.value_eur)}</span>
          {known && cs.climate_var_eur != null && <span className="text-[var(--color-mute)]"> · {balance(cs.climate_var_eur)} at risk</span>}
        </div>
      )}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
        {c.by_region.length > 0 && (
          <div>
            <div className="text-[12px] text-[var(--color-mute)] mb-2">{what} by region</div>
            <HBar data={c.by_region.slice(0, 6).map(r => ({ label: r.region, value: of(r), sub: `${r.pct_of_book}%`, color: r.pct_of_book > 25 ? 'var(--color-warn)' : 'var(--color-sky)' }))}
              format={balance} height={18} onBar={onRegion ? i => onRegion(c.by_region[i].region) : undefined} />
          </div>
        )}
        {c.by_hazard.length > 0 && (
          <div>
            <div className="text-[12px] text-[var(--color-mute)] mb-2">{what} by hazard</div>
            <HBar data={c.by_hazard.slice(0, 6).map((h, i) => ({ label: hazardLabel(h.hazard), value: of(h), sub: `${h.n}`, color: i === 0 ? 'var(--color-warn)' : 'var(--color-blue)' }))}
              format={balance} height={18} labelWidth="w-44" onBar={onHazard ? i => onHazard(c.by_hazard[i].hazard) : undefined} />
          </div>
        )}
      </div>
      {c.clusters.length > 0 && (
        <div className="mt-4">
          <div className="text-[12px] text-[var(--color-mute)] mb-2">{what} by cluster · one event, one region</div>
          <HBar data={c.clusters.slice(0, 6).map(cl => ({ label: `${hazardLabel(cl.hazard)} · ${cl.region}`, value: of(cl), sub: `${cl.n} · ${cl.pct_of_book}%`, color: 'var(--color-warn)' }))}
            format={balance} height={18} labelWidth="w-56" onBar={onCluster ? i => onCluster(c.clusters[i].hazard, c.clusters[i].region) : undefined} />
        </div>
      )}
    </Card>
  )
}
