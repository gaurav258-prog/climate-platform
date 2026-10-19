import { money } from '../lib/money'
import { HEADING, InfoButton, type Details } from './Details'
import { StatusChip } from './StatusChip'

// What a filing froze about its currency (multi-currency phase 3): the currency it presents in, every exchange rate it
// used (with where it came from), each entity's figures in its own currency and in the filing's (with the translation
// difference on income-type figures), and every group-internal exposure removed on consolidation. The conversion rules,
// their standard and each rate's working sit one click away.

interface Rate { currency: string; basis: string; period_start: string | null; rate_date: string; as_of: string; units_per_eur: number; source: string | null; source_label?: string; stale: boolean; note?: string | null }
interface EntityFx { entity_id: string | null; entity: string; functional_currency: string; n_assets: number; balances_functional: number; balances: number; flows_functional: number; flows: number; translation_difference: number }
interface Elim { asset: string | null; share_eliminated: number; value_eliminated: number }
export interface Fx {
  presentation_currency: string; period_end: string; basis: { balances: string; flows: string; own_book: string }
  rates_used: Rate[]; n_stale_rates: number; translation: EntityFx[]; translation_difference_total: number
  n_eliminations: number; value_eliminated_total: number; eliminations: Elim[]; unexplained_as_eur: { n: number; value: number }
}

const th = 'text-left text-[10px] uppercase tracking-wide text-[var(--color-faint)] font-normal pb-1 pr-3'
const td = 'py-1 pr-3 text-[11.5px] border-t border-[var(--color-line)]'
const num = `${td} tabular-nums text-right`
// the two rates translation.py records: the closing rate (balances) and the period average (income)
const KIND: Record<string, string> = { closing: 'Closing rate', average: 'Period average' }
const day = (s?: string | null) => s ? new Date(`${s.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'

const RULES = (fx: Fx): Details => ({
  title: 'How amounts are converted',
  sections: [
    { heading: HEADING.shows, body: `Every amount is presented in ${fx.presentation_currency}. Balances: ${fx.basis.balances}. Income: ${fx.basis.flows}. Each entity's own book: ${fx.basis.own_book}.` },
    { heading: 'Translation difference', body: 'Income translated at the average rate instead of the closing rate gives a translation difference, shown per entity.' },
    { heading: 'Legal basis', body: 'IAS 21 The Effects of Changes in Foreign Exchange Rates: paragraph 39 (assets and liabilities at the closing rate; income and expenses at the rates on the dates of the transactions), paragraph 40 (an average rate for the period in their place) and paragraph 41(a) (the exchange difference this gives).' },
  ],
})
const STALE: Details = { title: 'Rates older than usual', sections: [
  { heading: HEADING.shows, body: 'These rates were older than their source usually publishes when the filing was frozen. They are marked in the list of rates.' },
  { heading: HEADING.read, body: 'Check each marked rate: a source that corrects a rate later is found when the filing is reviewed again.' }] }
const UNEXPLAINED: Details = { title: 'Amounts taken as euro', sections: [
  { heading: HEADING.shows, body: 'Some stored amounts no longer match what was sent with their currency, so they were taken as euro.' },
  { heading: 'What you can do', body: 'Send those amounts again with their currency, then prepare the filing again.' }] }
const rateDetails = (r: Rate): Details => ({ title: `${r.currency} · ${KIND[r.basis] ?? 'Rate'}`, sections: [
  { heading: 'Source', body: r.source_label ?? 'Its source' },
  ...(r.note ? [{ heading: 'How it was set', body: r.note }] : []),
  ...(r.stale ? [{ heading: 'Older than usual', body: 'This rate was older than its source usually publishes when the filing was frozen.' }] : [])] })

export default function FilingFx({ fx }: { fx: Fx }) {
  const p = fx.presentation_currency
  const foreign = fx.translation.some(e => e.functional_currency !== p)
  return (
    <div className="rounded-xl border border-[var(--color-line-2)] p-3 mb-3">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <div className="flex items-center gap-2">
          <span className="text-[10.5px] uppercase tracking-widest text-[var(--color-faint)]">Currency</span>
          <StatusChip label={`Presented in ${p}`} tone="neutral" />
          <InfoButton compact details={RULES(fx)} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {fx.n_stale_rates > 0 && <span className="inline-flex items-center gap-1"><StatusChip label={`${fx.n_stale_rates} older than usual`} tone="warn" /><InfoButton compact details={STALE} /></span>}
          {fx.unexplained_as_eur.n > 0 && <span className="inline-flex items-center gap-1"><StatusChip label={`${fx.unexplained_as_eur.n} taken as euro · ${money(fx.unexplained_as_eur.value)}`} tone="warn" /><InfoButton compact details={UNEXPLAINED} /></span>}
        </div>
      </div>

      {(foreign || fx.translation.length > 1) && (
        <div className="overflow-x-auto mb-2">
          <table className="w-full">
            <thead><tr><th className={th}>Entity</th><th className={th}>Own currency</th><th className={`${th} text-right`}>Values (own)</th><th className={`${th} text-right`}>Values ({p})</th><th className={`${th} text-right`}>Income ({p})</th><th className={`${th} text-right`}>Translation difference</th></tr></thead>
            <tbody>{fx.translation.map(e => (
              <tr key={e.entity_id ?? 'none'}>
                <td className={td}>{e.entity} <span className="text-[var(--color-faint)]">· {e.n_assets}</span></td>
                <td className={td}>{e.functional_currency}</td>
                <td className={num}>{money(e.balances_functional, e.functional_currency)}</td>
                <td className={num}>{money(e.balances, p)}</td>
                <td className={num}>{e.flows ? money(e.flows, p) : '—'}</td>
                <td className={num}>{e.translation_difference ? money(e.translation_difference, p) : '—'}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}

      {fx.rates_used.length > 0 && (
        <div className="overflow-x-auto mb-2">
          <table className="w-full">
            <thead><tr><th className={th}>Rate</th><th className={th}>For</th><th className={`${th} text-right`}>Per euro</th><th className={th}>From</th><th className={th}><span className="sr-only">Details</span></th></tr></thead>
            <tbody>{fx.rates_used.map(r => (
              <tr key={`${r.currency}${r.basis}${r.as_of}${r.period_start}`}>
                <td className={td}>{r.currency} · {KIND[r.basis] ?? 'Rate'}</td>
                <td className={td}>{r.basis === 'average' ? `${day(r.period_start)} – ${day(r.as_of)}` : day(r.rate_date)}</td>
                <td className={num}>{r.units_per_eur.toFixed(4)}</td>
                <td className={td}>{r.source_label ?? 'Its source'}{r.stale && <StatusChip label="Older than usual" tone="warn" className="ml-2" />}</td>
                <td className={td}><div className="flex justify-end"><InfoButton compact details={rateDetails(r)} /></div></td>
              </tr>))}</tbody>
          </table>
        </div>
      )}

      {fx.n_eliminations > 0 && (
        <div className="text-[11.5px] text-[var(--color-mute)]">
          <div className="flex items-center gap-1.5">
            <span className="text-[var(--color-ink)]">{fx.n_eliminations} group-internal exposure(s) removed · {money(fx.value_eliminated_total, p)}</span>
            <InfoButton compact details={{ title: 'Group-internal exposures', sections: [
              { heading: HEADING.shows, body: 'Exposures one entity of the group holds on another are removed from the group filing, so nothing is counted twice. Each stays in its holder\'s own filing.' }] }} />
          </div>
          <ul className="mt-1 space-y-0.5">{fx.eliminations.slice(0, 8).map((e, i) => (
            <li key={i} className="text-[11px] tabular-nums">{e.asset ?? '—'} · {Math.round(e.share_eliminated * 100)}% · {money(e.value_eliminated, p)}</li>))}
          </ul>
        </div>
      )}
    </div>
  )
}
