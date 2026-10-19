// A country's name in English from its ISO 3166-1 alpha-2 code ('ES' → 'Spain'), the code itself where the browser
// holds no name for it. Screens name a country; they never print its code alone.
let names: Intl.DisplayNames | null = null
export function countryName(code?: string | null): string {
  if (!code) return '—'
  try {
    names ??= new Intl.DisplayNames(['en'], { type: 'region' })
    return names.of(code.toUpperCase()) ?? code
  } catch {
    return code
  }
}
