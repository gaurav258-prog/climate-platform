import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Card, StatGrid, type StatItem } from '../../components/ui'
import { HBar } from '../../components/Charts'
import MethodGap from '../../components/MethodGap'
import type { Message } from '../../components/Details'
import { api } from '../../lib/api'
import { balance, flow } from '../../lib/money'
import { CardHead, GapLine, METHOD_TAB, calcDetails } from './common'

// The insurer's cards: the catastrophe accumulation of the insured book, a reinsurance programme tested against it, and
// the climate value at risk of the insurer's own investments.

export interface Cat {
  available: boolean; gap?: string; mean_annual_loss_eur: number; sum_independent_eal_eur: number; mean_reconciles: boolean
  pml_eur: number | null; pml_return_period: number | null; tail_to_mean_multiple: number | null; n_zones: number
  aep_eur: Record<string, number>; pml_gap_message?: Message; method_message?: Message
}

export function CatAccumulation({ cat }: { cat?: Cat }) {
  if (cat?.gap) return <MethodGap gap={cat.gap} what="Catastrophe accumulation" />
  if (!cat || !cat.available) return null
  const rp = cat.pml_return_period
  const metrics: StatItem[] = [
    { label: rp ? `Largest event · 1 in ${rp} years` : 'Largest event', value: balance(cat.pml_eur), accent: 'var(--color-warn)', sub: 'probable maximum loss' },
    { label: '1-in-100-year total', value: balance(cat.aep_eur.rp_100) },
    { label: '1-in-250-year total', value: balance(cat.aep_eur.rp_250) },
    { label: 'Mean yearly loss', value: flow(cat.mean_annual_loss_eur), sub: cat.tail_to_mean_multiple ? `tail ${cat.tail_to_mean_multiple}× the mean` : undefined },
  ]
  const details = calcDetails('Catastrophe accumulation',
    'The loss in a bad year when one event hits many insured locations at once: the correlated tail that adding up each location’s expected loss hides.',
    cat.method_message,
    `The book falls into ${cat.n_zones} hazard-and-region zones. The simulated mean yearly loss is ${flow(cat.mean_annual_loss_eur)}; the locations’ own expected yearly losses add up to ${flow(cat.sum_independent_eal_eur)}${cat.mean_reconciles ? ', and the two agree' : ''}. The bars give the total yearly loss exceeded once in each number of years.`)
  const ladder = [10, 50, 100, 200, 250].filter(t => cat.aep_eur[`rp_${t}`] != null)
  return (
    <Card className="p-5">
      <CardHead title="Catastrophe accumulation" details={details} />
      {!rp && cat.pml_gap_message && <div className="mb-3"><GapLine what="Largest event" m={cat.pml_gap_message} to={METHOD_TAB} /></div>}
      <StatGrid items={metrics} />
      <div className="mt-4">
        <div className="text-[12px] text-[var(--color-mute)] mb-2">Total yearly loss, by return period</div>
        <HBar data={ladder.map(t => ({
          label: `1 in ${t} years`, value: cat.aep_eur[`rp_${t}`],
          color: rp && t >= rp ? 'var(--color-warn)' : 'var(--color-sky)' }))} format={balance} height={18} />
      </div>
    </Card>
  )
}

interface ReinsNet { net_pml_eur: number; ceded_pml_eur: number; cession_ratio_pct: number | null; basis_message?: Message }
interface Reinsurance { available: boolean; gap?: string; pml_return_period: number; gross_pml_eur: number; net: ReinsNet }

// A what-if: the insurer enters a programme to test; nothing is pre-filled (no illustrative treaty). Filings use the
// treaty attested for the period.
export function InsurerReinsuranceCard({ scenario, horizon }: { scenario: string; horizon: string }) {
  const [qs, setQs] = useState<number | null>(null)
  const [att, setAtt] = useState<number | null>(null)   // €m
  const [lim, setLim] = useState<number | null>(null)   // €m
  const ready = qs != null && att != null && lim != null
  const q = useQuery({
    queryKey: ['insurer-reins', scenario, horizon, qs, att, lim], enabled: ready,
    queryFn: () => api.get<Reinsurance>(`/v1/insurance/reinsurance?scenario=${scenario}&horizon=${horizon}&quota_share_pct=${qs}&xol_attachment_eur=${(att ?? 0) * 1e6}&xol_limit_eur=${(lim ?? 0) * 1e6}`),
  })
  const d = ready ? q.data : undefined
  if (d?.gap) return <MethodGap gap={d.gap} what="Net of reinsurance" />
  if (d && !d.available) return null
  const n = d?.net
  const details = calcDetails('Net of reinsurance',
    'The catastrophe loss you keep after a reinsurance programme you enter here: a quota share and a catastrophe excess-of-loss layer, tested against your book. Filings use the treaty you attest for the period.',
    n?.basis_message)
  return (
    <Card className="p-5">
      <CardHead title="Net of reinsurance" hint="what hits your capital" details={details} />
      <div className="flex flex-wrap items-end gap-3 mb-4">
        <Field label="Quota share" val={qs} set={setQs} suf="%" />
        <Field label="Excess-of-loss attachment" val={att} set={setAtt} suf="€m" />
        <Field label="Excess-of-loss limit" val={lim} set={setLim} suf="€m" />
      </div>
      {!ready && <div className="text-[12.5px] text-[var(--color-mute)]">Enter a programme to test it.</div>}
      {d && n && <>
        <StatGrid items={[
          { label: `Gross largest event · 1 in ${d.pml_return_period} years`, value: balance(d.gross_pml_eur) },
          { label: 'Net retained', value: balance(n.net_pml_eur), accent: 'var(--color-good)' },
          { label: 'Ceded to reinsurers', value: balance(n.ceded_pml_eur) },
          { label: 'Share ceded', value: n.cession_ratio_pct == null ? '—' : `${n.cession_ratio_pct}%` },
        ]} />
        <div className="mt-4">
          <HBar data={[
            { label: 'Gross', value: d.gross_pml_eur, color: 'var(--color-warn)' },
            { label: 'Net retained', value: n.net_pml_eur, color: 'var(--color-good)' },
            { label: 'Ceded', value: n.ceded_pml_eur, color: 'var(--color-sky)' },
          ]} format={balance} height={18} />
        </div>
      </>}
    </Card>
  )
}

function Field({ label, val, set, suf }: { label: string; val: number | null; set: (v: number | null) => void; suf: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11.5px] text-[var(--color-mute)]">{label}</span>
      <span className="inline-flex items-center gap-1 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2 py-1">
        <input type="number" value={val ?? ''} min={0} placeholder="—" aria-label={label}
          onChange={e => set(e.target.value === '' ? null : Math.max(0, Number(e.target.value)))} className="w-20 bg-transparent text-[13px] tabular-nums outline-none" />
        <span className="text-[11px] text-[var(--color-faint)]">{suf}</span>
      </span>
    </label>
  )
}

interface InvestVar { available: boolean; gap?: string; var99_eur: number; physical_expected_eur: number; transition_expected_eur: number; combined_pct_of_book: number; gap_message?: Message; method_message?: Message }
interface Investments { n_holdings: number; n_scored: number; total_value_eur: number; climate_var: InvestVar }

export function InsurerInvestmentsCard({ scenario, horizon }: { scenario: string; horizon: string }) {
  const q = useQuery({ queryKey: ['insurer-investments', scenario, horizon], queryFn: () => api.get<Investments>(`/v1/insurance/investments?scenario=${scenario}&horizon=${horizon}`) })
  const d = q.data, v = d?.climate_var
  if (!d || !d.n_holdings || !v) return null
  if (!v.available) return v.gap_message ? <GapLine what="Investments · climate value at risk" m={v.gap_message} to={METHOD_TAB} />
    : v.gap ? <MethodGap gap={v.gap} what="Investments · climate value at risk" /> : null
  const details = calcDetails('Investments · climate value at risk',
    `Your own investment book: physical and transition climate risk combined, as asset managers see theirs. ${d.n_scored} of ${d.n_holdings} positions are scored; the rest are left out, never estimated. The insured book is in the cards above.`,
    v.method_message)
  return (
    <Card className="p-5">
      <CardHead title="Investments · climate value at risk" hint={`${d.n_scored} of ${d.n_holdings} scored`} details={details} />
      <StatGrid items={[
        { label: 'Climate value at risk (99%)', value: balance(v.var99_eur), accent: 'var(--color-warn)' },
        { label: 'Of the investment book', value: `${v.combined_pct_of_book}%`, sub: balance(d.total_value_eur) },
        { label: 'Physical', value: balance(v.physical_expected_eur) },
        { label: 'Transition', value: balance(v.transition_expected_eur) },
      ]} />
    </Card>
  )
}
