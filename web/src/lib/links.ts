// Deep-link helpers so any module can drill straight into the granular detail underneath an item.

// Open a filing's full drawer (lifecycle, frozen snapshot, lineage, validation, variance, exports).
// FIN sectors live on /compliance, the agri workspace on /filings — both render the cockpit.
export function filingLink(orgType: string | undefined, filingId: string): string {
  const base = orgType === 'manufacturer' ? '/filings' : '/compliance'
  return `${base}?filing=${filingId}`
}

// Open the task board with a specific task's detail drawer.
export const taskLink = (taskId: string) => `/tasks?task=${taskId}`
