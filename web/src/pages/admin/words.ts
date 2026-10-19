// What the control center says after a save — kept free of imports so a node test reads it (web/tests/adminWords.test.ts).

// A governed change (reporting basis, methodology choice, appetite band) either applies or waits for a second person:
// services/governance/config_governance.submit_or_apply_config answers status 'applied' or 'pending_approval'. Only an
// applied change is announced as saved; one that waits says so, and the setting is unchanged until it is approved.
export function savedWords(status: string | null | undefined, applied: string): string {
  return status === 'pending_approval'
    ? 'Sent for approval — it changes once a second person approves it.'
    : applied
}
