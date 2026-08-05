import { useQuery } from '@tanstack/react-query'
import { ExternalLink, FileSpreadsheet } from 'lucide-react'
import { api } from '../lib/api'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'

// The final form — the frozen disclosure rendered as the submittable datapoint form. Every line is labelled
// with its value and source (book = from the uploaded book · calculated = derived on the golden source).
// Cells become editable (with 4-eyes) in the next slice; the stable `key` is what an override targets.

interface Dp { key: string; label: string; value: number | string | null; fmt: string; unit: string | null; source: string; note: string | null }
interface Group { group: string; datapoints: Dp[] }
interface Form { framework: string; label: string; period_label: string; snapshot_version: number | null; official_form_url: string | null; groups: Group[] }

const eur = (n: number) => n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
export function fmtValue(d: Dp): string {
  const v = d.value
  if (v == null) return '—'
  if (typeof v === 'string') return v
  switch (d.fmt) {
    case 'eur': return eur(v)
    case 'pct': return `${v}%`
    case 'tco2e': return `${Math.round(v).toLocaleString('en-GB')}`
    default: return Number.isInteger(v) ? v.toLocaleString('en-GB') : v.toLocaleString('en-GB', { maximumFractionDigits: 2 })
  }
}
export const dpLabel = (d: Dp) => d.key.startsWith('hazard.') ? hazardLabel(d.label) : d.label

export default function FilingForm({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['filing-form', filingId], queryFn: () => api.get<Form>(`/v1/filings/${filingId}/form`) })
  const d = q.data
  if (!d || d.groups.length === 0) return null

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-2">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Final form · as it will be submitted</div>
        {d.official_form_url && <a href={d.official_form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 mono text-[10px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={11} /> official form <ExternalLink size={10} /></a>}
      </div>
      <Card className="p-0 overflow-hidden">
        {d.groups.map((g, gi) => (
          <div key={gi} className={gi > 0 ? 'border-t border-[var(--color-line)]' : ''}>
            <div className="px-4 py-2 bg-[var(--color-bg-2)] mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">{g.group}</div>
            <div className="divide-y divide-[var(--color-line)]">
              {g.datapoints.map(dp => (
                <div key={dp.key} className="flex items-center gap-3 px-4 py-2 text-[12.5px]">
                  <div className="min-w-0 flex-1">
                    <span className="text-[var(--color-ink)]">{dpLabel(dp)}</span>
                    {dp.unit && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">{dp.unit}</span>}
                    {dp.note && <span className="mono text-[10px] text-[var(--color-faint)] ml-1.5">· {dp.note}</span>}
                  </div>
                  <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0"
                    style={{ color: dp.source === 'book' ? 'var(--color-sky)' : 'var(--color-mute)', background: 'color-mix(in oklab, var(--color-line) 60%, transparent)' }}>
                    {dp.source === 'book' ? 'book' : 'calc'}
                  </span>
                  <span className="mono text-[12.5px] tabular-nums text-right w-28 shrink-0 text-[var(--color-ink)]">{fmtValue(dp)}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </Card>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2"><span className="text-[var(--color-sky)]">book</span> = from your uploaded book · <span className="text-[var(--color-mute)]">calc</span> = derived on the golden source</div>
    </div>
  )
}
