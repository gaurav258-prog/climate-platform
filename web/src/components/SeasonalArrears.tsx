import { useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Sprout, Upload, Download } from 'lucide-react'
import { api, upload as uploadFile, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, StatGrid, type StatItem } from './ui'

// Seasonal-arrears overlay — separate normal harvest-cycle carry-over from genuine deterioration. Upload the
// agri book's days-past-due; the card classifies each past-due loan against a documented crop calendar, with
// a rationale for every reclassification. An explainable management overlay — never a replacement for IFRS-9.

interface Loan { loan_ref: string; borrower_name: string | null; crop: string | null; region: string | null; country: string | null; exposure_eur: number; days_past_due: number; classification: string; rationale: string }
interface Resp {
  available: boolean; reason?: string; as_of?: string | null; assessed_month?: number; seasonal_cap_days?: number
  summary?: { n_past_due: number; past_due_eur: number; n_seasonal: number; seasonal_eur: number
             n_climate_attributed: number; climate_attributed_eur: number
             n_genuine: number; genuine_eur: number; reclassified_pct: number; n_not_checked_no_country: number }
  loans?: Loan[]
}
const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const BADGE: Record<string, { color: string; bg: string }> = {
  seasonal: { color: 'var(--color-warn)', bg: 'color-mix(in oklab, var(--color-warn) 14%, transparent)' },
  climate_attributed: { color: 'var(--color-sky)', bg: 'color-mix(in oklab, var(--color-sky) 14%, transparent)' },
  genuine: { color: 'var(--color-bad)', bg: 'color-mix(in oklab, var(--color-bad) 14%, transparent)' },
}

export default function SeasonalArrears() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const q = useQuery({ queryKey: ['seasonal-arrears'], queryFn: () => api.get<Resp>('/v1/arrears/assessment') })
  const d = q.data

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { await uploadFile('/v1/arrears/upload', f); qc.invalidateQueries({ queryKey: ['seasonal-arrears'] }); toast.success('Arrears uploaded and assessed.') }
    catch { toast.error('Upload failed — check the template columns.') }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const s = d?.summary
  const FORMAT_HINT = "CSV file. Required columns: loan_ref, days_past_due. Optional: borrower_name, crop, "
    + "region, country (ISO-2 — enables climate-attributed yield-shock checking), exposure_eur, as_of_date. "
    + "One upload = one dated batch; the latest one is assessed."

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Sprout size={15} className="text-[var(--color-good)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">Seasonal-arrears overlay</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· harvest carry-over vs genuine deterioration</span>
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => download('/v1/arrears/template.csv', 'tellumen_arrears_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title={"Download a blank CSV with the right columns. " + FORMAT_HINT}><Download size={13} /></button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} title={FORMAT_HINT} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Upload arrears</button>
        </span>
      </div>
      <div className="text-[11px] text-[var(--color-faint)] -mt-2 mb-3">
        CSV · <span className="mono">loan_ref</span>, <span className="mono">days_past_due</span> required ·{' '}
        <span className="mono">borrower_name</span>, <span className="mono">crop</span>,{' '}
        <span className="mono">region</span>, <span className="mono">country</span> (enables climate-shock check),{' '}
        <span className="mono">exposure_eur</span>, <span className="mono">as_of_date</span> optional · one upload = one dated batch, latest one used
      </div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !d.available ? (
          <div className="text-[12.5px] text-[var(--color-mute)] py-3">
            No arrears uploaded — upload the book's days-past-due above and Tellumen separates seasonal carry-over, a climate-attributed bad harvest (observed national yield shock, when <span className="mono text-[11px]">country</span> is given), and genuine deterioration.
          </div>
        ) : s ? (
          <>
            <StatGrid cols={5} className="mb-3" items={[
              { label: <>Past due · {s.n_past_due}</>, value: eur(s.past_due_eur) },
              { label: <>Seasonal · {s.n_seasonal}</>, value: eur(s.seasonal_eur), accent: 'var(--color-warn)' },
              { label: <>Climate-attributed · {s.n_climate_attributed}</>, value: eur(s.climate_attributed_eur), accent: 'var(--color-sky)' },
              { label: <>Genuine · {s.n_genuine}</>, value: eur(s.genuine_eur), accent: 'var(--color-bad)' },
              { label: 'Reclassified', value: `${s.reclassified_pct}%` },
            ] satisfies StatItem[]} />
            <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
              {d.loans!.slice(0, 8).map(l => (
                <div key={l.loan_ref} className="flex items-center gap-2.5 py-1.5 text-[12px]">
                  <span className="mono text-[10px] px-1.5 py-0.5 rounded shrink-0" style={BADGE[l.classification] ? { color: BADGE[l.classification].color, background: BADGE[l.classification].bg } : undefined}>{l.classification.replace('_', ' ')}</span>
                  <span className="text-[var(--color-ink)] shrink-0">{l.borrower_name || l.loan_ref}</span>
                  <span className="text-[var(--color-mute)] truncate flex-1 min-w-0 hidden sm:block">· {l.rationale}</span>
                  <span className="mono text-[11px] text-[var(--color-faint)] shrink-0">{l.days_past_due}d</span>
                  <span className="mono tabular-nums text-[var(--color-ink)] shrink-0 w-14 text-right">{eur(l.exposure_eur)}</span>
                </div>
              ))}
            </div>
            <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2.5">
              Explainable overlay · not a replacement for IFRS-9 staging · seasonal cap {d.seasonal_cap_days}d · assessed month {d.assessed_month} · Northern-hemisphere crop calendar (configurable)
              {s.n_not_checked_no_country > 0 && <> · {s.n_not_checked_no_country} loan{s.n_not_checked_no_country === 1 ? '' : 's'} had no country on record — climate shock not checked, shown as genuine</>}
            </div>
          </>
        ) : null}
    </Card>
  )
}
