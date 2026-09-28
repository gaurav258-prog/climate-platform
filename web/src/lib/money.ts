/** One money formatter for the whole app (multi-currency phase 5).
 *
 *  Symbols come from Intl's 'en-001' locale — the same CLDR data as the server's ISO 4217 reference
 *  (services/reference/iso4217.display_symbol): '€', 'US$', 'CA$', and a code where the symbol would be ambiguous
 *  ('CHF', 'SEK', followed by a space).
 *
 *  Two kinds of amount:
 *    money(n, ccy)      — an amount already in a known currency: a filing's own currency, a fund's base, an invoice.
 *    balance(n) / flow(n) — an engine amount (the engine keeps everything in EUR) shown in the organisation's
 *                        presentation currency: a balance (exposure, value, capital) at the latest closing rate, a flow
 *                        (annual expected loss, premiums, revenue, spend) at the 12-month average — the rate policy a
 *                        filing uses (services/governance/display_currency.py). In EUR nothing is translated.
 *  The display currency is loaded once at sign-in (App → setDisplay), like the server's money_format.current. */

const cache = new Map<string, string>()

export function currencySymbol(ccy = 'EUR'): string {
  const code = (ccy || 'EUR').toUpperCase()
  let s = cache.get(code)
  if (s === undefined) {
    try {
      s = new Intl.NumberFormat('en-001', { style: 'currency', currency: code }).formatToParts(0)
        .find(p => p.type === 'currency')?.value ?? code
    } catch { s = code }
    if (/[A-Za-z]$/.test(s)) s = `${s} `
    cache.set(code, s)
  }
  return s
}

export interface MoneyOpts { full?: boolean }

/** '€12.3m' · 'US$1.20bn' · 'CHF 950k' · '−€4.1m'; { full: true } → '€12,345,678' */
export function money(n: number | null | undefined, ccy = 'EUR', opts: MoneyOpts = {}): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const s = currencySymbol(ccy), a = Math.abs(n), sign = n < 0 ? '−' : ''
  if (opts.full) return `${sign}${s}${Math.round(a).toLocaleString('en-GB')}`
  if (a >= 1e9) return `${sign}${s}${(a / 1e9).toFixed(2)}bn`
  if (a >= 1e6) return `${sign}${s}${(a / 1e6).toFixed(1)}m`
  if (a >= 1e3) return `${sign}${s}${Math.round(a / 1e3).toLocaleString('en-GB')}k`
  return `${sign}${s}${Math.round(a).toLocaleString('en-GB')}`
}

/** An exact amount held in minor units (cents for EUR, none for JPY — CLDR/ISO 4217 minor units): invoices, prices.
 *  (250000, 'EUR') → '€2,500' · (123456, 'USD') → 'US$1,234.56' */
export function minorAmount(minor: number | null | undefined, ccy = 'EUR'): string {
  if (minor == null || !Number.isFinite(minor)) return '—'
  let digits = 2
  try { digits = new Intl.NumberFormat('en-001', { style: 'currency', currency: ccy }).resolvedOptions().maximumFractionDigits ?? 2 } catch { /* unknown code: 2 */ }
  const v = minor / 10 ** digits, sign = v < 0 ? '−' : ''
  const whole = Number.isInteger(v)
  return `${sign}${currencySymbol(ccy)}${Math.abs(v).toLocaleString('en-GB', { minimumFractionDigits: whole ? 0 : digits, maximumFractionDigits: digits })}`
}

export interface Rate { units_per_eur: number; rate_date: string | null; source: string | null; basis: string | null; stale: boolean; note: string | null; period_start?: string | null; period_end?: string | null }
export interface Display { currency: string; engine_currency: string; flow_policy: string; as_of: string; balance: Rate; flow: Rate; note: string | null }

const IDENTITY: Rate = { units_per_eur: 1, rate_date: null, source: 'identity', basis: 'identity', stale: false, note: null }
let display: Display = { currency: 'EUR', engine_currency: 'EUR', flow_policy: 'period_average', as_of: '', balance: IDENTITY, flow: IDENTITY, note: null }

export function setDisplay(d: Display) { display = d }
export function getDisplay(): Display { return display }
/** The organisation's presentation currency code ('EUR', 'USD', …). */
export function displayCurrency(): string { return display.currency }
/** Its symbol, for column headers and axis titles: 'Value (€)' → `Value (${displaySymbol().trim()})`. */
export function displaySymbol(): string { return currencySymbol(display.currency) }

/** An engine (EUR) balance in the organisation's currency, at the closing rate. */
export function balance(n: number | null | undefined, opts: MoneyOpts = {}): string {
  return money(n == null ? n : n * display.balance.units_per_eur, display.currency, opts)
}
/** An engine (EUR) flow — an amount per year — in the organisation's currency, at the average rate. */
export function flow(n: number | null | undefined, opts: MoneyOpts = {}): string {
  return money(n == null ? n : n * display.flow.units_per_eur, display.currency, opts)
}
/** The number only, translated (for charts that format their own ticks). */
export function balanceValue(n: number): number { return n * display.balance.units_per_eur }
export function flowValue(n: number): number { return n * display.flow.units_per_eur }

/** One line saying how screen amounts are translated — null when the organisation presents in EUR. */
export function displayNote(): string | null {
  if (display.note) return display.note
  if (display.currency === display.engine_currency) return null
  const b = display.balance, f = display.flow, c = display.currency
  const src = (r: Rate) => `${(r.source || '').toUpperCase()}${r.stale ? ', stale' : ''}`
  const bal = `balances at the ${src(b)} closing rate${b.rate_date ? ` of ${b.rate_date}` : ''} (${b.units_per_eur.toFixed(4)} ${c} per EUR)`
  const fl = display.flow_policy === 'closing' ? 'flows at the same closing rate'
    : `flows at the 12-month average (${f.units_per_eur.toFixed(4)} ${c} per EUR, ${src(f)})`
  return `Amounts shown in ${c}, translated from EUR: ${bal}; ${fl}. Filings use their own period-end rates.`
}
