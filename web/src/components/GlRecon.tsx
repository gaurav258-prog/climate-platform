import { useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark, Upload, CheckCircle2, AlertTriangle, Download } from 'lucide-react'
import { api, upload as uploadFile, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card } from './ui'

// General-ledger reconciliation — tie the reported book TOTAL back to the customer's GL control accounts
// (gate 4). Upload a GL trial-balance; the card shows reported vs GL vs variance against a tolerance. Honest:
// nothing is shown until a GL is provided, and a variance is reported as-is.

interface Acct { account_code: string; account_name: string | null; balance_eur: number; control_for: string | null }
interface Recon {
  available: boolean; reason?: string; as_of?: string | null
  reported_book_eur?: number; gl_book_eur?: number; variance_eur?: number; variance_pct?: number | null
  tolerance_pct?: number; reconciled?: boolean; n_accounts?: number; accounts?: Acct[]
}
const eur = (n?: number | null) => n == null ? '—' : `${n < 0 ? '−' : ''}` + (Math.abs(n) >= 1e9 ? `€${(Math.abs(n) / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(Math.abs(n) / 1e6).toFixed(1)}m` : `€${Math.round(Math.abs(n) / 1e3)}k`)

export default function GlRecon() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const q = useQuery({ queryKey: ['gl-recon'], queryFn: () => api.get<Recon>('/v1/gl/reconciliation') })
  const d = q.data
  if (d && !d.available && d.reason === 'unsupported_sector') return null

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { await uploadFile('/v1/gl/upload', f); qc.invalidateQueries({ queryKey: ['gl-recon'] }); toast.success('GL uploaded and reconciled.') }
    catch { toast.error('Upload failed — check the template columns.') }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const uploadBtn = (
    <>
      <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
      <button onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Upload GL</button>
    </>
  )

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <Landmark size={15} className="text-[var(--color-blue)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">General-ledger reconciliation</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· reported book tied back to the ledger</span>
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => download('/v1/gl/template.csv', 'tellumen_gl_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download template"><Download size={13} /></button>
          {uploadBtn}
        </span>
      </div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !d.available ? (
          <div className="text-[12.5px] text-[var(--color-mute)] py-3">
            No general ledger uploaded yet. Upload a GL trial-balance (columns: <span className="mono text-[11px]">account_code, account_name, balance_eur, control_for, as_of_date</span>) and Tellumen ties the reported book total back to it.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
              <div><div className="display text-[20px] leading-none tabular-nums text-[var(--color-ink)]">{eur(d.reported_book_eur)}</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Reported book</div></div>
              <div><div className="display text-[20px] leading-none tabular-nums text-[var(--color-ink)]">{eur(d.gl_book_eur)}</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">GL balance</div></div>
              <div><div className="display text-[20px] leading-none tabular-nums" style={{ color: d.reconciled ? 'var(--color-good)' : 'var(--color-bad)' }}>{eur(d.variance_eur)}</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Variance{d.variance_pct != null ? ` · ${d.variance_pct}%` : ''}</div></div>
              <div className="flex flex-col justify-center">
                {d.reconciled
                  ? <span className="inline-flex items-center gap-1.5 mono text-[11px]" style={{ color: 'var(--color-good)' }}><CheckCircle2 size={14} /> Reconciled</span>
                  : <span className="inline-flex items-center gap-1.5 mono text-[11px]" style={{ color: 'var(--color-bad)' }}><AlertTriangle size={14} /> Out of tolerance</span>}
                <span className="mono text-[9px] text-[var(--color-faint)] mt-1">±{d.tolerance_pct}% · as of {d.as_of ?? '—'}</span>
              </div>
            </div>
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
