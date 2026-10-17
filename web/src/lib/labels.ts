import { useQuery } from '@tanstack/react-query'
import { api } from './api'

// Customer words for the platform's internal codes (UI standard, 2026-10-16): a code never reaches a screen as-is.
// The catalogue lives on the server (GET /v1/meta/labels, built from the reference registers) so the server and every
// screen use the same words; the hazard, scenario, framework and status helpers in lib/hazards.ts and the action
// names in lib/actionLabels.ts are the other two sources, re-exported here so a page imports labels from one place.
export { hazardLabel, scenarioLabel, horizonLabel, frameworkLabel, statusLabel, bucketLabel, modelLabel } from './hazards'
export { actionLabel } from './actionLabels'

export type Labels = { method: Record<string, string> }
const EMPTY: Labels = { method: {} }

export function useLabels(): Labels {
  const q = useQuery({ queryKey: ['meta-labels'], queryFn: () => api.get<Labels>('/v1/meta/labels'), staleTime: Infinity })
  return q.data ?? EMPTY
}

// A method parameter's short name ('method.at_risk_level' → 'Your at-risk threshold'); never the key itself.
export const methodLabel = (labels: Labels, key: string): string => labels.method[key] ?? 'A method choice'

export { gapMethodKeys } from './methodGap'
