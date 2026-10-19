// The mapping note's words (UI standard, 2026-10-16): what a column mapping did to a file, each field by its name.

// What the mapping did to a file (services/intake/mapping.apply): each conversion names its field (label) beside its key.
export interface MappingReport {
  profile: string; auto?: boolean; unmapped_source_columns: string[]
  conversions: { field: string; label?: string; kind: string; factor?: number; currency?: string; currency_column?: string; n_values?: number }[]
}

// One conversion in words: the field by its name, never its key; a currency fixed, or read per row from a column.
export function conversionText(c: MappingReport['conversions'][number]): string {
  const f = c.label ?? 'A field'
  return c.kind === 'scale' ? `${f} × ${c.factor?.toLocaleString('en-GB')}`
    : c.kind === 'currency' ? (c.currency ? `${f} in ${c.currency}` : `${f}: currency per row from “${c.currency_column}”`)
    : `${f}: your values matched to ours`
}
