// A figure's change against a base, as a screen shows it ('+8%'), or null when there is no change to show: no figure,
// or a base of zero or none — never the text "null" (E304: a projected card read "null vs today" when today's figure
// was €0). A caller shows its chip only when this is not null.
export function changeVs(now: number | null | undefined, base: number | null | undefined): string | null {
  if (now == null || base == null || base === 0) return null
  const p = ((now - base) / base) * 100
  return `${now >= base ? '+' : ''}${p.toFixed(0)}%`
}
