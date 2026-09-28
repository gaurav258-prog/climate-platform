// Money in a stated currency. A figure's currency always comes from the data — a filing's presentation currency, an
// entity's functional currency, a fund's base currency — never assumed. The written symbol comes from the browser's
// own CLDR data in international English ('en-001'): '€', 'US$', 'CA$', 'JP¥' — the same reference the server uses
// (data/reference/iso4217.csv), so a dollar is never mistaken for another; a currency without a symbol is written by
// its code ('SEK 950k').
const cache = new Map<string, string>()

export function currencySymbol(ccy = 'EUR'): string {
  const code = (ccy || 'EUR').toUpperCase()
  let s = cache.get(code)
  if (s === undefined) {
    try {
      s = new Intl.NumberFormat('en-001', { style: 'currency', currency: code }).formatToParts(0)
        .find(p => p.type === 'currency')?.value ?? code
    } catch { s = code }                                 // not an ISO 4217 code the browser knows: show it as written
    if (/[A-Za-z]$/.test(s)) s = `${s} `
    cache.set(code, s)
  }
  return s
}

/** '€12.3m' · 'US$1.20bn' · 'CHF 950k' */
export function money(n: number | null | undefined, ccy = 'EUR'): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const s = currencySymbol(ccy), a = Math.abs(n)
  if (a >= 1e9) return `${s}${(n / 1e9).toFixed(2)}bn`
  if (a >= 1e6) return `${s}${(n / 1e6).toFixed(1)}m`
  if (a >= 1e3) return `${s}${Math.round(n / 1e3).toLocaleString('en-GB')}k`
  return `${s}${Math.round(n).toLocaleString('en-GB')}`
}
