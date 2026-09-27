import { money } from '../lib/money'

// What a filing froze about its currency (multi-currency phase 3): the currency it presents in, the rate basis,
// every exchange rate it used, each entity's figures in its own currency and in the filing's (with the IAS 21.41(a)
// difference on income-type figures), and every group-internal exposure removed on consolidation.

interface Rate { currency: string; basis: string; period_start: string | null; rate_date: string; as_of: string; units_per_eur: number; source: string | null; stale: boolean }
interface EntityFx { entity_id: string | null; entity: string; functional_currency: string; n_assets: number; balances_functional: number; balances: number; flows_functional: number; flows: number; translation_difference: number }
interface Elim { asset: string | null; share_eliminated: number; value_eliminated: number }
export interface Fx {
  presentation_currency: string; period_end: string; basis: { balances: string; flows: string; own_book: string }
  rates_used: Rate[]; n_stale_rates: number; translation: EntityFx[]; translation_difference_total: number
  n_eliminations: number; value_eliminated_total: number; eliminations: Elim[]; unexplained_as_eur: { n: number; value: number }
}

const th = 'text-left mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-normal pb-1 pr-3'
const td = 'py-1 pr-3 text-[11.5px] border-t border-[var(--color-line)]'
const num = `${td} mono tabular-nums text-right`

export default function FilingFx({ fx }: { fx: Fx }) {
  const p = fx.presentation_currency
  const foreign = fx.translation.some(e => e.functional_currency !== p)
  return (
    <div className="rounded-xl border border-[var(--color-line-2)] p-3 mb-3">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-1">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Currency · presented in <span className="text-[var(--color-ink)]">{p}</span></div>
        <div className="text-[11px] text-[var(--color-mute)]">Balances: {fx.basis.balances} · income: {fx.basis.flows}</div>
      </div>
      {fx.n_stale_rates > 0 && <div className="text-[11.5px] mb-2" style={{ color: 'var(--color-warn)' }}>{fx.n_stale_rates} rate(s) were older than their source's usual publication — marked below.</div>}
      {fx.unexplained_as_eur.n > 0 && <div className="text-[11.5px] mb-2" style={{ color: 'var(--color-warn)' }}>{fx.unexplained_as_eur.n} stored amount(s) ({money(fx.unexplained_as_eur.value)}) no longer match what was sent; they were taken as EUR.</div>}

      {(foreign || fx.translation.length > 1) && (
        <div className="overflow-x-auto mb-2">
          <table className="w-full">
            <thead><tr><th className={th}>Entity</th><th className={th}>Own currency</th><th className={`${th} text-right`}>Values (own)</th><th className={`${th} text-right`}>Values ({p})</th><th className={`${th} text-right`}>Income ({p})</th><th className={`${th} text-right`} title="IAS 21.41(a): income translated at the average rate instead of the closing rate">Translation difference</th></tr></thead>
            <tbody>{fx.translation.map(e => (
              <tr key={e.entity_id ?? 'none'}>
                <td className={td}>{e.entity} <span className="text-[var(--color-faint)]">· {e.n_assets}</span></td>
                <td className={`${td} mono`}>{e.functional_currency}</td>
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
            <thead><tr><th className={th}>Rate</th><th className={th}>For</th><th className={`${th} text-right`}>per EUR</th><th className={th}>Source</th></tr></thead>
            <tbody>{fx.rates_used.map(r => (
              <tr key={`${r.currency}${r.basis}${r.as_of}${r.period_start}`}>
                <td className={`${td} mono`}>{r.currency} · {r.basis}</td>
                <td className={td}>{r.basis === 'average' ? `${r.period_start} → ${r.as_of}` : r.rate_date?.slice(0, 10)}</td>
                <td className={num}>{r.units_per_eur.toFixed(4)}</td>
                <td className={td}>{r.source ?? '—'}{r.stale && <span style={{ color: 'var(--color-warn)' }}> · stale</span>}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}

      {fx.n_eliminations > 0 && (
        <div className="text-[11.5px] text-[var(--color-mute)]">
          <span className="text-[var(--color-ink)]">{fx.n_eliminations} group-internal exposure(s) removed</span> · {money(fx.value_eliminated_total, p)} — kept in each holder's own filing.
          <ul className="mt-1 space-y-0.5">{fx.eliminations.slice(0, 8).map((e, i) => (
            <li key={i} className="mono text-[10.5px]">{e.asset ?? '—'} · {Math.round(e.share_eliminated * 100)}% · {money(e.value_eliminated, p)}</li>))}
          </ul>
        </div>
      )}
    </div>
  )
}
