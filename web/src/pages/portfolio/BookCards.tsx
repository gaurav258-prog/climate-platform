import { Card, StatGrid, type StatItem } from '../../components/ui'
import MethodGap from '../../components/MethodGap'
import { InfoButton, type Message } from '../../components/Details'
import { hazardLabel } from '../../lib/labels'
import { balance } from '../../lib/money'
import { CardHead, Chip, calcDetails, pct } from './common'

// The bank's and the property owner's cards: the expected value loss with its range, transition risk on the loan book
// and on its real-estate collateral, energy-performance stranding and resilience spend on a property book.

export interface LossBand { expected_value_loss_eur: number | null; loss_low_eur: number | null; loss_high_eur: number | null; band_pct: number | null; ci_coverage_pct: number; gap?: string; method_message?: Message }

export function ValueLossBand({ band }: { band?: LossBand }) {
  if (band?.gap) return <MethodGap gap={band.gap} what="Expected value loss" />
  if (!band || !band.expected_value_loss_eur) return null
  const ranged = band.loss_low_eur !== band.loss_high_eur
  const details = calcDetails('Expected value loss',
    'The value your book is expected to lose to physical climate risk on your stated valuation haircuts, with the range its scores’ confidence intervals give.',
    band.method_message,
    `${band.ci_coverage_pct}% of the scored value has a confidence interval on its score.`)
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-1">
      <span className="text-[12.5px] text-[var(--color-mute)]">Expected value loss</span>
      <span className="text-[15px] font-semibold text-[var(--color-ink)] tabular-nums">{balance(band.expected_value_loss_eur)}</span>
      {ranged && <span className="text-[12.5px] text-[var(--color-mute)] tabular-nums">range {balance(band.loss_low_eur)} – {balance(band.loss_high_eur)}</span>}
      <span className="ml-auto"><InfoButton compact details={details} /></span>
    </div>
  )
}

interface Sector { nace_division: string; label: string; transition_el_eur: number }
export interface Transition {
  available: boolean; gap?: string; financed_emissions_tco2e: number; emissions_reported_pct: number | null; n_emissions_estimated: number
  transition_expected_loss_eur: number; transition_el_pct_of_outstanding: number | null; exposure_weighted_transition_score: number | null
  score_coverage_pct: number | null; by_sector: Sector[]; method_message?: Message
}

const tonnes = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(1)} Mt` : n >= 1e3 ? `${(n / 1e3).toFixed(0)} kt` : `${Math.round(n)} t`

export function TransitionCard({ t, pathway }: { t?: Transition; pathway: string }) {
  if (t?.gap) return <MethodGap gap={t.gap} what="Transition risk on the loan book" />
  if (!t || !t.available) return null
  const metrics: StatItem[] = [
    { label: 'Transition expected loss', value: balance(t.transition_expected_loss_eur), sub: `${pct(t.transition_el_pct_of_outstanding)} of outstanding`, accent: 'var(--color-warn)' },
    { label: 'Financed emissions (scope 1 and 2)', value: tonnes(t.financed_emissions_tco2e), sub: 'tonnes of CO₂ equivalent' },
    { label: 'Weighted transition score', value: t.exposure_weighted_transition_score ?? '—', sub: t.score_coverage_pct != null ? `${t.score_coverage_pct}% of outstanding scored` : undefined },
    { label: 'Emissions reported', value: pct(t.emissions_reported_pct), sub: t.n_emissions_estimated ? `${t.n_emissions_estimated} estimated` : undefined },
  ]
  const details = calcDetails('Transition risk on the loan book',
    `The low-carbon shift on your borrowers under ${pathway}: the loss your loan book is expected to take, its financed emissions, and the sectors that carry the loss.`,
    t.method_message)
  return (
    <Card className="p-5">
      <CardHead title="Transition risk on the loan book" hint={pathway} details={details} />
      <StatGrid items={metrics} />
      {t.by_sector?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {t.by_sector.slice(0, 4).map(s => <Chip key={s.nace_division}>{s.label} · {balance(s.transition_el_eur)}</Chip>)}
        </div>
      )}
    </Card>
  )
}

interface TopCollateral { asset_id: string; name: string; epc_rating: string; original_ltv_pct: number | null; stressed_ltv_pct: number | null; collateral_value_at_risk_eur: number }
export interface CollateralStranding {
  available: boolean; gap?: string; n_re_loans: number; n_discounted: number; collateral_value_at_risk_eur: number; loan_value_at_risk_eur: number
  retrofit_capex_to_derisk_eur: number; exposure_weighted_ltv_pct: number | null; stressed_ltv_pct: number | null; ltv_uplift_pp: number | null
  epc_coverage_pct: number | null; top_exposures: TopCollateral[]; basis_message?: Message
}

export function CollateralStrandingCard({ cs }: { cs?: CollateralStranding }) {
  if (cs?.available && cs.gap) return <MethodGap gap={cs.gap} what="Energy stranding of collateral" />
  if (!cs || !cs.available || !cs.n_re_loans) return null
  const metrics: StatItem[] = [
    { label: 'Collateral value at risk', value: balance(cs.collateral_value_at_risk_eur), accent: cs.n_discounted > 0 ? 'var(--color-warn)' : undefined },
    { label: 'Loan-to-value after stranding', value: <>{pct(cs.exposure_weighted_ltv_pct)}<span className="text-[14px] text-[var(--color-faint)]"> → {pct(cs.stressed_ltv_pct)}</span></>,
      sub: cs.ltv_uplift_pp != null ? `+${cs.ltv_uplift_pp} points` : undefined },
    { label: 'Exposure uncovered', value: balance(cs.loan_value_at_risk_eur), accent: cs.loan_value_at_risk_eur > 0 ? 'var(--color-warn)' : undefined },
    { label: 'Retrofit cost to remove the risk', value: balance(cs.retrofit_capex_to_derisk_eur) },
  ]
  const details = calcDetails('Energy stranding of collateral',
    'Transition risk on the buildings that secure your real-estate loans: how far your brown discount for poor energy grades lowers the collateral, and what it would cost to retrofit.',
    cs.basis_message,
    `${cs.n_discounted} of ${cs.n_re_loans} real-estate loans are in a discounted grade; ${pct(cs.epc_coverage_pct)} of them have the energy grade, collateral value and balance on record. Loan-to-value figures are weighted by exposure.`)
  return (
    <Card className="p-5">
      <CardHead title="Energy stranding of collateral" hint={`${cs.n_discounted} of ${cs.n_re_loans} loans discounted`} details={details} />
      <StatGrid items={metrics} />
      {cs.n_discounted > 0 && cs.top_exposures.length > 0 && (
        <div className="mt-4">
          <div className="text-[12px] text-[var(--color-mute)] mb-2">Most-exposed collateral</div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {cs.top_exposures.slice(0, 6).map(t => (
              <div key={t.asset_id} className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-line-2)] px-3 py-2">
                <span className="text-[12.5px] text-[var(--color-ink)] truncate">{t.name}</span>
                <span className="text-[11.5px] text-[var(--color-mute)] shrink-0 tabular-nums">EPC {t.epc_rating} · {balance(t.collateral_value_at_risk_eur)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

export interface EnergyStranding {
  gap?: string; n_properties: number; n_assessed: number; n_discounted: number; value_at_stranding_risk_eur: number
  retrofit_capex_to_derisk_eur: number; pct_assessed_value_discounted: number | null; epc_coverage_pct: number | null; basis_message?: Message
}

export function EnergyStrandingCard({ es }: { es?: EnergyStranding }) {
  if (es?.n_assessed && es.gap) return <MethodGap gap={es.gap} what="Energy-performance stranding" />
  if (!es || !es.n_assessed) return null
  const metrics: StatItem[] = [
    { label: 'Value at stranding risk', value: balance(es.value_at_stranding_risk_eur), accent: es.n_discounted > 0 ? 'var(--color-warn)' : undefined },
    { label: 'Retrofit cost to remove the risk', value: balance(es.retrofit_capex_to_derisk_eur) },
    { label: 'Assessed value in discounted grades', value: pct(es.pct_assessed_value_discounted) },
    { label: 'Properties discounted', value: es.n_discounted, sub: `of ${es.n_assessed} assessed` },
  ]
  const details = calcDetails('Energy-performance stranding',
    'Transition risk on your properties: the value your brown discount for poor energy grades puts at risk, and the retrofit cost that removes it.',
    es.basis_message,
    `${es.n_assessed} of ${es.n_properties} properties (${pct(es.epc_coverage_pct)}) have an energy grade and a value on record.`)
  return (
    <Card className="p-5">
      <CardHead title="Energy-performance stranding" details={details} />
      <StatGrid items={metrics} />
    </Card>
  )
}

interface ResilienceHazard { hazard: string; resilience_capex_eur: number; avoided_loss_eur: number }
export interface Resilience {
  available: boolean; gap?: string; n_properties: number; total_resilience_capex_eur: number; total_avoided_loss_eur: number
  portfolio_benefit_cost_ratio: number | null; n_worth_retrofit: number; by_hazard: ResilienceHazard[]; method_message?: Message
}

export function ResilienceCard({ rc }: { rc?: Resilience }) {
  if (rc?.gap) return <MethodGap gap={rc.gap} what="Resilience spend" />
  if (!rc || !rc.available) return null
  const good = 'var(--color-good)'
  const bcr = rc.portfolio_benefit_cost_ratio
  const metrics: StatItem[] = [
    { label: 'Resilience spend', value: balance(rc.total_resilience_capex_eur), sub: `${rc.n_worth_retrofit} of ${rc.n_properties} properties worth it` },
    { label: 'Loss avoided', value: balance(rc.total_avoided_loss_eur), accent: good },
    { label: 'Loss avoided per euro spent', value: bcr == null ? '—' : `${bcr}×`, accent: bcr != null && bcr >= 1 ? good : undefined },
  ]
  const details = calcDetails('Resilience spend',
    'What it would cost to protect the properties worth retrofitting, and the physical loss that spend would avoid.',
    rc.method_message)
  return (
    <Card className="p-5">
      <CardHead title="Resilience spend" hint="cost and loss avoided" details={details} />
      <StatGrid items={metrics} cols={3} />
      {rc.by_hazard?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {rc.by_hazard.slice(0, 4).map(h => <Chip key={h.hazard}>{hazardLabel(h.hazard)} · spend {balance(h.resilience_capex_eur)} → avoid {balance(h.avoided_loss_eur)}</Chip>)}
        </div>
      )}
    </Card>
  )
}
