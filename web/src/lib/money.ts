// Money in a stated currency (multi-currency phase 3). A figure's currency always comes from the data — a filing's
// presentation currency, an entity's functional currency — never assumed. EUR stays '€'; others use their symbol
// or ISO code, so a USD filing can't read as euros.
const SYMBOL: Record<string, string> = {
  EUR: '€', USD: 'US$', GBP: '£', JPY: '¥', CHF: 'CHF ', SEK: 'SEK ', NOK: 'NOK ', DKK: 'DKK ', PLN: 'PLN ', CZK: 'CZK ',
  HUF: 'HUF ', RON: 'RON ', CAD: 'C$', AUD: 'A$', BRL: 'R$', INR: '₹',
}
export const currencySymbol = (ccy = 'EUR') => SYMBOL[ccy] ?? `${ccy} `

/** '€12.3m' · 'US$1.20bn' · 'CHF 950k' */
export function money(n: number | null | undefined, ccy = 'EUR'): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const s = currencySymbol(ccy), a = Math.abs(n)
  if (a >= 1e9) return `${s}${(n / 1e9).toFixed(2)}bn`
  if (a >= 1e6) return `${s}${(n / 1e6).toFixed(1)}m`
  if (a >= 1e3) return `${s}${Math.round(n / 1e3).toLocaleString('en-GB')}k`
  return `${s}${Math.round(n).toLocaleString('en-GB')}`
}
