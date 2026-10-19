// What the KRI screens say about a whole set and about a saved band — kept free of imports so a node test reads them
// (web/tests/kriWords.test.ts).

// the headline over a set: breaches first, then warnings; 'within appetite' only when some indicator is graded at all
export function heroTitle({ red, amber, ok }: { red: number; amber: number; ok: number }): string {
  if (red > 0) return `${red} indicator${red === 1 ? '' : 's'} in breach.`
  if (amber > 0) return `${amber} indicator${amber === 1 ? '' : 's'} in warning.`
  return ok > 0 ? 'Every graded indicator is within appetite.' : 'No appetite band is set on these indicators yet.'
}

// what saving a band did: applied, or sent for a second person's approval (the band is unchanged until then)
export function bandSaved(status?: string | null): string {
  return status === 'pending_approval'
    ? 'Sent for approval — the band changes once a second person approves it.'
    : 'Appetite band updated.'
}
