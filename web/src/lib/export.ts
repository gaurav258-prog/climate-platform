// Shared client-side data export — ONE provenance-stamped path for "export what I'm looking at", so a
// customer can take any Tellumen cut into their own BI / reporting tool. This is the universal Tier-1
// primitive across every module; the server-rendered regulator packs (XBRL / iXBRL / the book .xlsx) keep
// their own endpoints via lib/api `download()`. Every file carries a header line naming the view, the org,
// the reporting basis (scenario / horizon / date) and, where relevant, an EXPLORATORY (not a filed figure)
// marker — so an exported number stays traceable to the platform and is never mistaken for an attested one.

export interface ExportColumn { key: string; label: string }
export interface ExportMeta {
  title: string
  org?: string
  basis?: Record<string, string | number | null | undefined>
  exploratory?: boolean
}

const esc = (v: unknown): string => {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** Build a provenance-stamped CSV string from columns + rows. */
export function toCsv(columns: ExportColumn[], rows: Record<string, unknown>[], meta: ExportMeta): string {
  const lines: string[] = []
  lines.push(`# ${meta.title}${meta.org ? ` · ${meta.org}` : ''}${meta.exploratory ? ' · EXPLORATORY (not a filed figure)' : ''}`)
  if (meta.basis) {
    const b = Object.entries(meta.basis).filter(([, v]) => v != null && v !== '')
      .map(([k, v]) => `${k}: ${v}`).join(' · ')
    if (b) lines.push(`# ${b}`)
  }
  lines.push(`# exported ${new Date().toISOString().slice(0, 19).replace('T', ' ')} UTC`)
  lines.push(columns.map(c => esc(c.label)).join(','))
  for (const r of rows) lines.push(columns.map(c => esc(r[c.key])).join(','))
  return lines.join('\n') + '\n'
}

/** Serialize + trigger a browser download of a CSV for the current view. */
export function downloadCsv(filename: string, columns: ExportColumn[], rows: Record<string, unknown>[], meta: ExportMeta): void {
  const url = URL.createObjectURL(new Blob([toCsv(columns, rows, meta)], { type: 'text/csv;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
