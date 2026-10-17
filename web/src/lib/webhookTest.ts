// What a webhook test-send tells the user (E183): a delivered test is a success, anything else an error to fix.
export function webhookTestOutcome(r: { status: string; http_status: number | null }): { ok: boolean; text: string } {
  if (r.status === 'delivered') return { ok: true, text: `Test delivered (HTTP ${r.http_status}).` }
  return { ok: false, text: `Test failed (${r.http_status ? 'HTTP ' + r.http_status : 'no response'}). Check the URL.` }
}
