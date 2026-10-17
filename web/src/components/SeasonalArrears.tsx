import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Sprout, Upload, Download, TriangleAlert } from 'lucide-react'
import { api, apiDetail, apiMessage, upload as uploadFile, download } from '../lib/api'
import MoneyDeclaration from './MoneyDeclaration'
import { toast } from '../lib/toast'
import { balance } from '../lib/money'
import { Card, StatGrid, type StatItem } from './ui'
import { StatusChip } from './StatusChip'
import { HEADING, InfoButton, MessageLine, type Details, type Message } from './Details'

// Seasonal-arrears overlay — separate normal harvest-cycle carry-over from genuine deterioration. Upload the
// agri book's days-past-due; the card classifies each past-due loan against a documented crop calendar, with
// the reason for every call as a server message (agri.data.arrears.*). An explainable management overlay — never a
// replacement for IFRS-9; the method sits behind the card's ⓘ (UI standard, 2026-10-16).

type Cls = 'seasonal' | 'climate_attributed' | 'genuine'
interface Loan { loan_ref: string; borrower_name: string | null; crop: string | null; country: string | null; exposure_eur: number; days_past_due: number; classification: Cls; reason_message: Message; check_message: Message | null }
interface Resp {
  available: boolean; message?: Message; as_of?: string | null; assessed_month?: number; seasonal_cap_days?: number; yield_shock_threshold_pct?: number
  summary?: { n_past_due: number; past_due_eur: number; n_seasonal: number; seasonal_eur: number
             n_climate_attributed: number; climate_attributed_eur: number
             n_genuine: number; genuine_eur: number; reclassified_pct: number; n_not_checked_no_country: number }
  loans?: Loan[]
}
const CLS: Record<Cls, { label: string; tone: 'warn' | 'neutral' | 'bad'; color: string }> = {
  seasonal: { label: 'Seasonal', tone: 'warn', color: 'var(--color-warn)' },
  climate_attributed: { label: 'Bad harvest', tone: 'neutral', color: 'var(--color-sky)' },
  genuine: { label: 'Genuine', tone: 'bad', color: 'var(--color-bad)' },
}
const about = (d?: Resp): Details => ({
  title: 'Seasonal arrears', sections: [
    { heading: HEADING.shows, body: 'Each past-due loan in your agricultural book, sorted three ways: harvest carry-over, a bad harvest, or genuine deterioration. Each loan gives the reason for its call.' },
    ...(d?.seasonal_cap_days != null && d.yield_shock_threshold_pct != null ? [{ heading: HEADING.read, body: `Seasonal: inside the crop’s harvest window and at most ${d.seasonal_cap_days} days past due, so usually repaid from the next sale. Bad harvest: the crop’s national production fell by more than ${Math.abs(d.yield_shock_threshold_pct)}% that season. Genuine: neither explains it.` }] : []),
    { heading: HEADING.sources, body: 'Your upload: one row per loan with its reference and days past due, and if you have them the borrower, crop, region, country, exposure, currency and as-of date. The harvest calendar follows FAO crop calendars for the northern hemisphere; national production comes from official crop statistics.' },
    { heading: HEADING.limits, body: 'A management view; it does not replace IFRS 9 staging, and the days past due are kept as uploaded. A loan with no country cannot be checked for a bad harvest and is counted as genuine. A national harvest figure explains a pattern, not one farm.' },
  ],
})

export default function SeasonalArrears() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const q = useQuery({ queryKey: ['seasonal-arrears'], queryFn: () => api.get<Resp>('/v1/arrears/assessment') })
  const d = q.data

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try {
      const r = await uploadFile<{ rows: number; n_skipped: number; skipped: { row: number; reason: string }[] }>('/v1/arrears/upload', f, 'file', { currency: ccy, book_date: bookDate })
      qc.invalidateQueries({ queryKey: ['seasonal-arrears'] })
      if (r.n_skipped) toast.error(`${r.rows} loans saved; ${r.n_skipped} rows not used. First: row ${r.skipped[0].row}, ${r.skipped[0].reason}.`)
      else toast.success('Arrears uploaded and assessed.')
    }
    catch (err) { toast.error(apiDetail(err)?.what ?? apiMessage(err, 'The file could not be uploaded.')) }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const s = d?.summary
  const parts = s ? [
    { k: 'seasonal' as const, n: s.n_seasonal, v: s.seasonal_eur },
    { k: 'climate_attributed' as const, n: s.n_climate_attributed, v: s.climate_attributed_eur },
    { k: 'genuine' as const, n: s.n_genuine, v: s.genuine_eur },
  ] : []
  const noCountry = d?.loans?.find(l => l.check_message)?.check_message

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Sprout size={15} className="text-[var(--color-good)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)] m-0">Seasonal arrears</h3>
        <InfoButton compact details={about(d)} />
        <span className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => download('/v1/arrears/template.csv', 'tellumen_arrears_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download the template" aria-label="Download the template"><Download size={13} /></button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={!ccy || !bookDate} title={!ccy || !bookDate ? 'Choose the currency and book date first' : undefined} className="disabled:opacity-45 inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Upload arrears</button>
        </span>
      </div>
      <div className="mb-3"><MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate}
        note="Exposures convert to euros at the official rate on the book date. A row’s own currency or as-of date overrides these." /></div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !d.available ? (
          <div className="text-[12.5px] text-[var(--color-mute)] py-3">{d.message ? <MessageLine m={d.message} /> : 'No arrears uploaded yet'}</div>
        ) : s ? (
          <>
            <StatGrid cols={4} className="mb-3" items={[
              { label: <>Past due · {s.n_past_due}</>, value: balance(s.past_due_eur) },
              ...parts.map(p => ({ label: <>{CLS[p.k].label} · {p.n}</>, value: balance(p.v), accent: CLS[p.k].color })),
            ] satisfies StatItem[]} />
            <div className="h-3 rounded-full bg-[var(--color-panel-2)] flex overflow-hidden mb-1" role="img"
              aria-label={parts.map(p => `${CLS[p.k].label} ${balance(p.v)}`).join(', ')}>
              {parts.filter(p => p.v > 0).map(p => <div key={p.k} style={{ width: `${(p.v / Math.max(1, s.past_due_eur)) * 100}%`, background: CLS[p.k].color }} />)}
            </div>
            <div className="text-[11.5px] text-[var(--color-faint)] mb-3 tabular-nums">{s.reclassified_pct}% of the past-due amount is explained by the harvest</div>
            <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
              {d.loans!.slice(0, 8).map(l => (
                <div key={l.loan_ref} className="flex items-center gap-2.5 py-1.5 text-[12px]">
                  <StatusChip label={CLS[l.classification].label} tone={CLS[l.classification].tone} className="shrink-0" />
                  <span className="text-[var(--color-ink)] min-w-0 truncate">{l.borrower_name || l.loan_ref}</span>
                  <span className="text-[var(--color-mute)] truncate flex-1 min-w-0 hidden sm:inline-flex"><MessageLine m={l.reason_message} /></span>
                  {l.check_message && <span title={l.check_message.label} aria-label={l.check_message.label}><TriangleAlert size={13} className="text-[var(--color-warn)] shrink-0" /></span>}
                  <span className="text-[11px] text-[var(--color-faint)] shrink-0 tabular-nums">{l.days_past_due} days</span>
                  <span className="tabular-nums text-[var(--color-ink)] shrink-0 w-14 text-right">{balance(l.exposure_eur)}</span>
                </div>
              ))}
            </div>
            {noCountry && s.n_not_checked_no_country > 0 && (
              <div className="text-[11.5px] text-[var(--color-warn)] mt-2.5 flex items-center gap-1.5">
                <TriangleAlert size={12} />{s.n_not_checked_no_country} {s.n_not_checked_no_country === 1 ? 'loan' : 'loans'}: <MessageLine m={noCountry} />
              </div>
            )}
          </>
        ) : null}
    </Card>
  )
}
