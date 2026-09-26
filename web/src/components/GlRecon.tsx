import { useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Upload, CheckCircle2, AlertTriangle, Download } from 'lucide-react'
import { api, upload as uploadFile, download } from '../lib/api'
import MoneyDeclaration from './MoneyDeclaration'
import { toast } from '../lib/toast'
import { Card, StatGrid, type StatItem } from './ui'

// General-ledger reconciliation — tie the reported book TOTAL back to the customer's GL control accounts
// (gate 4). Upload a GL trial-balance; the card shows reported vs GL vs variance against a tolerance. Honest:
// nothing is shown until a GL is provided, and a variance is reported as-is.

interface Acct { account_code: string; account_name: string | null; balance_eur: number; control_for: string | null }
interface Recon {
  available: boolean; reason?: string; as_of?: string | null
  reported_book_eur?: number; gl_book_eur?: number; variance_eur?: number; variance_pct?: number | null
  tolerance_pct?: number; reconciled?: boolean; n_accounts?: number; accounts?: Acct[]
}
// Reconciliation figures must FOOT visibly (reported − GL = variance, and the account rows sum to GL), so
// they are shown at a fixed €m precision with thousands separators — never abbreviated to €Xbn, which would
// round two nearly-equal totals to a fake gap larger than the real variance.
const eur = (n?: number | null) => n == null ? '—'
  : `${n < 0 ? '−' : ''}€${(Math.abs(n) / 1e6).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}m`

export default function GlRecon() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const q = useQuery({ queryKey: ['gl-recon'], queryFn: () => api.get<Recon>('/v1/gl/reconciliation') })
  const d = q.data
  if (d && !d.available && d.reason === 'unsupported_sector') return null

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try {
      const r = await uploadFile<{ rows: number; n_skipped: number; skipped: { row: number; reason: string }[] }>('/v1/gl/upload', f, 'file', { currency: ccy, book_date: bookDate })
      qc.invalidateQueries({ queryKey: ['gl-recon'] })
      if (r.n_skipped) toast.error(`${r.rows} balances saved; ${r.n_skipped} row(s) not used — e.g. row ${r.skipped[0].row}: ${r.skipped[0].reason}`)
      else toast.success('GL uploaded and reconciled.')
    }
    catch (e: unknown) { toast.error((e as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'Upload failed — check the template columns.') }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const FORMAT_HINT = "CSV file. Required columns: account_code, balance. Optional: currency (per row), account_name, "
    + "control_for (defaults to 'book' — the reported total this reconciles against), as_of_date (per row). "
    + "One upload = one dated batch; reconciliation always uses your latest upload."
  const uploadBtn = (
    <>
      <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
      <button onClick={() => fileRef.current?.click()} disabled={!ccy || !bookDate} title={!ccy || !bookDate ? 'Choose the currency and book date first' : FORMAT_HINT} className="disabled:opacity-45 inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Upload GL</button>
    </>
  )

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Landmark size={15} className="text-[var(--color-blue)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">General-ledger reconciliation</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· reported book tied back to the ledger</span>
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => download('/v1/gl/template.csv', 'tellumen_gl_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title={"Download a blank CSV with the right columns. " + FORMAT_HINT}><Download size={13} /></button>
          {uploadBtn}
        </span>
      </div>
      <div className="text-[11px] text-[var(--color-faint)] -mt-2 mb-3">
        <div className="mb-2"><MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate}
          note="Balances convert to EUR at the book date's official rate; a row's own currency / as_of_date columns override these." /></div>
        CSV · <span className="mono">account_code</span>, <span className="mono">balance</span> required ·{' '}
        <span className="mono">account_name</span>, <span className="mono">control_for</span>,{' '}
        <span className="mono">as_of_date</span> optional · one upload = one dated batch, latest one used
      </div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !d.available ? (
          <div className="text-[12.5px] text-[var(--color-mute)] py-3">
            No general ledger uploaded yet — upload one above and Tellumen ties the reported book total back to it.
          </div>
        ) : (
          <>
            <StatGrid className="mb-3" cols={4} items={[
              { label: 'Reported book', value: eur(d.reported_book_eur) },
              { label: 'GL balance', value: eur(d.gl_book_eur) },
              { label: `Variance${d.variance_pct != null ? ` · ${d.variance_pct}%` : ''}`, value: eur(d.variance_eur), accent: d.reconciled ? 'var(--color-good)' : 'var(--color-bad)' },
              { label: 'Status',
                value: d.reconciled
                  ? <span className="inline-flex items-center gap-1.5 mono text-[11px]" style={{ color: 'var(--color-good)' }}><CheckCircle2 size={14} /> Reconciled</span>
                  : <span className="inline-flex items-center gap-1.5 mono text-[11px]" style={{ color: 'var(--color-bad)' }}><AlertTriangle size={14} /> Out of tolerance</span>,
                sub: `±${d.tolerance_pct}% · as of ${d.as_of ?? '—'}` },
            ] satisfies StatItem[]} />
            {(d.accounts?.length ?? 0) > 0 && (
              <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
                {d.accounts!.slice(0, 6).map(a => (
                  <div key={a.account_code} className="flex items-center gap-3 py-1.5 text-[12px]">
                    <span className="mono text-[11px] text-[var(--color-faint)] shrink-0 w-14">{a.account_code}</span>
                    <span className="flex-1 min-w-0 truncate text-[var(--color-mute)]">{a.account_name}</span>
                    <span className="mono tabular-nums text-[var(--color-ink)] shrink-0">{eur(a.balance_eur)}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
    </Card>
  )
}
