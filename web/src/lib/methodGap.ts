// The method keys a gap names ('not stated: method.damage_ratio (flood/H), method.at_risk_level' → the two keys), so a
// screen can name them in customer words (lib/labels.ts) instead of printing the keys.
export function gapMethodKeys(gap: string): string[] {
  if (!gap.startsWith('not stated: ')) return []
  return [...new Set(gap.slice('not stated: '.length).split(',').map(s => s.trim().split(' ')[0]).filter(k => k.startsWith('method.')))]
}
