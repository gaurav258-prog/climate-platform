import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Upload, Download } from 'lucide-react'
import { api, apiDetail, apiMessage, upload as uploadFile, download } from '../lib/api'
import MoneyDeclaration from './MoneyDeclaration'
import { toast } from '../lib/toast'
import { balance } from '../lib/money'
import { Card, SectionHead, StatGrid, type StatItem } from './ui'
import { PairBars } from './Charts'
import { StatusChip } from './StatusChip'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'

// General-ledger reconciliation, to the UI standard (2026-10-16): the reported book total tied back to the customer's
// ledger accounts. Figures, a bar pair and where the difference sits against the tolerance on the main screen; the file
// format, the rule and every reason in pop-ups, in the server's catalogue words (codes ledger.*). Nothing is shown until
// a ledger is uploaded, and a difference is shown as it is. Used on Your data (DataHub).

interface Acct { account_code: string; account_name: string | null; balance_eur: number; control_for: string | null; counts: boolean }
interface Recon {
  available: boolean; message?: Message; as_of?: string | null
  reported_book_eur?: number; gl_book_eur?: number; variance_eur?: number; variance_pct?: number | null
  tolerance_pct?: number; reconciled?: boolean; n_accounts?: number; n_book_accounts?: number; accounts?: Acct[]
}
interface Saved { rows: number; n_skipped: number; skipped: { row: number; message: Message }[] }

// Reconciliation figures must FOOT visibly (reported − ledger = difference, and the book accounts add up to the ledger
// total), so they are full figures with thousands separators — never abbreviated to Xbn, which would round two nearly
// equal totals to a gap larger than the real difference. Ledger lines are balances (closing rate).
const amt = (n?: number | null) => balance(n, { full: true })
const ABOUT = [
  { heading: HEADING.shows, body: 'Your reported book total beside the total of the general-ledger accounts it ties to, and the difference between them.' },
  { heading: HEADING.read, body: 'Accounts marked as counting toward the book are added up to the ledger total; others are listed but not added. The difference is the reported book less that total.' },
  { heading: HEADING.sources, body: 'Your latest ledger upload, and your book as the engine computes it today. Balances convert to euros at the official rate of the book date; a row’s own currency and date override the ones chosen for the file.' },
  { heading: 'File format', body: 'A CSV file, one row per account: its code and its balance are required; its name, the reported total it ties to (the book when left empty), its currency and its date are optional. The template has the columns and an example row. One upload is one dated batch; the latest is used.' },
]

// where the difference sits on a scale of twice the tolerance either side, the tolerance band shaded
function ToleranceBar({ pct, tol }: { pct: number; tol: number }) {
  const span = Math.max(2 * tol, Math.abs(pct) * 1.15)
  const x = (v: number) => 50 + 50 * Math.max(-1, Math.min(1, v / span))
  const inside = Math.abs(pct) <= tol
  return (
    <div>
      <div className="relative h-3 rounded-full bg-[var(--color-panel-2)]" role="img" aria-label={`Difference ${pct} % against a tolerance of ${tol} %`}>
        <div className="absolute inset-y-0 rounded-full" style={{ left: `${x(-tol)}%`, right: `${100 - x(tol)}%`, background: 'color-mix(in oklab, var(--color-good) 24%, transparent)' }} />
        <div className="absolute inset-y-0 w-px bg-[var(--color-line-2)]" style={{ left: '50%' }} />
        <div className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 h-4 w-4 rounded-full border-2 border-[var(--color-panel)]"
          style={{ left: `${x(pct)}%`, background: inside ? 'var(--color-good)' : 'var(--color-bad)' }} />
      </div>
      <div className="flex justify-between text-[11px] text-[var(--color-faint)] tabular-nums mt-1">
        <span>−{tol} %</span><span>0</span><span>+{tol} %</span>
      </div>
    </div>
  )
}

export default function GlRecon() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const [saved, setSaved] = useState<Saved | null>(null)
  const [refused, setRefused] = useState<Message | null>(null)
  const [all, setAll] = useState(false)
  const q = useQuery({ queryKey: ['gl-recon'], queryFn: () => api.get<Recon>('/v1/gl/reconciliation') })
  const d = q.data
  if (d && !d.available && d.message?.code === 'ledger.unavailable.sector') return null

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    setRefused(null); setSaved(null)
    try {
      const r = await uploadFile<Saved>('/v1/gl/upload', f, 'file', { currency: ccy, book_date: bookDate })
      qc.invalidateQueries({ queryKey: ['gl-recon'] })
      setSaved(r)
      toast.success(`${r.rows} balance${r.rows === 1 ? '' : 's'} saved and reconciled.`)
    }
    catch (err) {
      const m = { label: apiMessage(err, 'The upload failed.'), detail: apiDetail(err) }
      setRefused(m); toast.error(m.label)
    }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const ready = !!ccy && !!bookDate
  const accounts = d?.accounts ?? []
  const shown = all ? accounts : accounts.slice(0, 6)

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        <Landmark size={15} className="text-[var(--color-blue)]" />
        <SectionHead>General-ledger reconciliation</SectionHead>
        <InfoButton compact details={{ title: 'General-ledger reconciliation', sections: ABOUT }} />
        <span className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => download('/v1/gl/template.csv', 'tellumen_gl_template.csv').catch(err => toast.error(apiMessage(err, 'The template could not be downloaded.')))}
            className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={13} />Template</button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button type="button" onClick={() => fileRef.current?.click()} disabled={!ready} title={ready ? undefined : 'Choose the currency and book date first'}
            className="disabled:opacity-45 inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} />Upload ledger</button>
        </span>
      </div>
      <MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate} />
      {refused && <MessageLine m={refused} className="text-[12.5px] text-[var(--color-bad)]" />}
      {saved && saved.n_skipped > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-[var(--color-warn)]">
          <span>{saved.rows} saved · {saved.n_skipped} row{saved.n_skipped === 1 ? '' : 's'} not used</span>
          <InfoButton compact details={{ title: 'Rows not used', sections: [{ heading: HEADING.shows, body: (
            <ul className="m-0 pl-4 space-y-1">{saved.skipped.map(s => <li key={s.row}>{s.message.detail?.what ?? s.message.label}</li>)}</ul>) }] }} />
        </div>
      )}

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-2">Loading…</div>
        : !d.available ? (d.message && <MessageLine m={d.message} className="text-[12.5px] text-[var(--color-mute)]" />)
        : (
          <>
            <StatGrid cols={4} items={[
              { label: 'Reported book', value: amt(d.reported_book_eur) },
              { label: 'Ledger total', value: amt(d.gl_book_eur), sub: `${d.n_book_accounts ?? 0} accounts` },
              { label: 'Difference', value: amt(d.variance_eur), sub: d.variance_pct != null ? `${d.variance_pct} % of the ledger` : undefined,
                accent: d.reconciled ? 'var(--color-good)' : 'var(--color-bad)' },
              { label: 'Status', value: <StatusChip label={d.reconciled ? 'Reconciled' : 'Outside tolerance'} tone={d.reconciled ? 'good' : 'bad'} />,
                sub: d.as_of ? `as of ${d.as_of}` : undefined },
            ] satisfies StatItem[]} />
            <div className="grid gap-5 md:grid-cols-2 items-center">
              <PairBars prior={d.gl_book_eur ?? 0} now={d.reported_book_eur ?? 0} format={v => balance(v)} labels={['Ledger', 'Book']} />
              {d.variance_pct != null && d.tolerance_pct != null && (
                <div className="space-y-1.5">
                  {d.message && <MessageLine m={d.message} className="text-[12px] text-[var(--color-mute)]" />}
                  <ToleranceBar pct={d.variance_pct} tol={d.tolerance_pct} />
                </div>
              )}
            </div>
            {accounts.length > 0 && (
              <div>
                <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                  {shown.map(a => (
                    <div key={a.account_code} className="flex items-center gap-3 py-1.5 text-[12.5px]">
                      <span className="text-[var(--color-faint)] shrink-0 w-16 truncate tabular-nums">{a.account_code}</span>
                      <span className="flex-1 min-w-0 truncate text-[var(--color-mute)]">{a.account_name || '—'}</span>
                      {!a.counts && <StatusChip label="Not in the book total" tone="neutral" />}
                      <span className="tabular-nums text-[var(--color-ink)] shrink-0">{amt(a.balance_eur)}</span>
                    </div>
                  ))}
                </div>
                {accounts.length > 6 && (
                  <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">
                    {all ? 'Show fewer' : `Show all ${accounts.length} accounts`}
                  </button>
                )}
              </div>
            )}
          </>
        )}
    </Card>
  )
}
