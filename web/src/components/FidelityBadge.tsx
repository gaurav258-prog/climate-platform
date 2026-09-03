// Ground-Truth Fidelity — Tellumen's presentation of the validation fit (out-of-sample R² for continuous
// models, rank agreement for event models). Same number as the engine computes; a name and band a reader
// can act on. The tooltip always carries the raw statistics + the publish floor, so nothing is hidden.

export interface Fidelity {
  family: string
  family_label: string
  symbol: string
  value: number | null
  band: 'not_testable' | 'held' | 'directional' | 'reliable' | 'strong' | string
  band_label: string
  published: boolean
  floor: number
  basis: string
  r2_oos: number | null
  spearman: number | null
  auc: number | null
}

const BAND_COLOR: Record<string, string> = {
  strong: 'var(--color-good)',
  reliable: 'var(--color-sky)',
  directional: 'var(--color-warn)',
  held: 'var(--color-mute)',
  not_testable: 'var(--color-faint)',
}

export function FidelityBadge({ f, className }: { f?: Fidelity | null; className?: string }) {
  if (!f) return null
  const c = BAND_COLOR[f.band] ?? BAND_COLOR.not_testable
  const val = f.value == null ? '—' : Math.round(f.value)
  const title =
    `${f.family_label} — ${f.basis}. ` +
    (f.r2_oos != null ? `Out-of-sample R² = ${f.r2_oos}. ` : '') +
    (f.spearman != null ? `Spearman ρ = ${f.spearman}. ` : '') +
    (f.auc != null ? `AUC = ${f.auc}. ` : '') +
    `Publish floor at ${f.floor} of 100${f.published ? '' : ' — below it, so held back'}.`
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 whitespace-nowrap ${className ?? ''}`}
      style={{ background: `color-mix(in oklab, ${c} 14%, transparent)`, color: c }}
    >
      <span className="mono text-[12px] font-semibold tabular-nums">{f.symbol} {val}</span>
      <span className="text-[11px] font-medium">{f.band_label}</span>
    </span>
  )
}
