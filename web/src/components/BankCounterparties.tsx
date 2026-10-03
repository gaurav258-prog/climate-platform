import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Building2 } from 'lucide-react'
import { api } from '../lib/api'
import { pressable } from '../lib/pressable'
import { balance } from '../lib/money'
import { Dialog } from './Dialog'
import ValidatedUpload from './ValidatedUpload'

// The loan book's counterparties (E119): what is a fact of the counterparty — its total liabilities (accounting
// liabilities and shareholders' equity) with its balance-sheet date, the denominator of Pillar 3 Template 1 column i — is
// stated ONCE per counterparty, through the governed intake, matched to the exposures by the loan tape's counterparty id.
// Where the exposures of one counterparty used to state different figures, none was picked: the conflict is shown here
// and blocks Template 1 until the one figure is stated.

interface Statement { entity_id: string; eur: number; date: string; source?: { amount?: number; currency?: string } | null }
interface Cp {
  counterparty_ref: string; counterparty_name: string | null; total_liabilities_eur: number | null
  total_liabilities_date: string | null; liabilities_conflict: Statement[] | null; issuer_name: string | null
  revenue_eur: number | null; revenue_period_end: string | null
  n_exposures: number; gross_eur: number | null
}

export default function BankCounterparties() {
  const qc = useQueryClient()
  const list = useQuery({ queryKey: ['bank-counterparties'], queryFn: () => api.get<{ counterparties: Cp[]; n_exposures_without_counterparty: number }>('/v1/bank/counterparties') })
  const [conflict, setConflict] = useState<Cp | null>(null)
  const rows = list.data?.counterparties ?? []
  const noId = list.data?.n_exposures_without_counterparty ?? 0
  const unstated = rows.filter(r => r.n_exposures > 0 && r.total_liabilities_eur == null && !r.liabilities_conflict).length
  const conflicts = rows.filter(r => r.liabilities_conflict).length

  return (
    <div className="px-5 pt-2 pb-5 border-t border-[var(--color-line)] mt-2 space-y-3">
      <div>
        <div className="text-[13px] text-[var(--color-ink)] font-medium mb-0.5 flex items-center gap-1.5"><Building2 size={14} /> Counterparties — one figure each</div>
        <p className="text-[12px] text-[var(--color-mute)] max-w-3xl">
          Pillar 3 Template 1 column i compares your exposures towards a counterparty with the counterparty&rsquo;s total liabilities
          (accounting liabilities and shareholders&rsquo; equity); where you use a sector-average scope 3 intensity per EUR million of revenue,
          it multiplies the counterparty&rsquo;s revenue. State each figure once per counterparty, with the end of the financial year it is
          taken from, using the counterparty id your loan tape gives it (its LEI or your own id).
        </p>
      </div>
      {(noId > 0 || unstated > 0 || conflicts > 0) && (
        <div className="rounded-lg border border-[var(--color-warn)]/40 px-3 py-2 text-[12px] text-[var(--color-ink)] flex flex-wrap gap-x-4 gap-y-1">
          <AlertTriangle size={13} className="text-[var(--color-warn)] self-center" />
          {noId > 0 && <span>{noId} exposures carry no counterparty id — they cannot enter Template 1 columns i–k</span>}
          {unstated > 0 && <span>{unstated} counterparties have no total liabilities stated</span>}
          {conflicts > 0 && <span>{conflicts} counterparties have conflicting figures — none was picked</span>}
        </div>
      )}
      {rows.length > 0 && (
        <div className="max-h-72 overflow-auto rounded-lg border border-[var(--color-line)]">
          <table className="w-full min-w-[860px] text-[12px] [&_th]:px-2 [&_th]:py-1.5 [&_th]:whitespace-nowrap [&_td]:px-2 [&_td]:py-1.5 [&_td]:whitespace-nowrap">
            <thead className="sticky top-0 bg-[var(--color-panel)]"><tr className="mono text-[9.5px] uppercase text-[var(--color-faint)] text-left">
              <th>Counterparty id</th><th>Name</th><th className="text-right">Exposures</th>
              <th className="text-right">Total liabilities and equity</th><th>Balance sheet</th>
              <th className="text-right">Revenue</th><th>Year ending</th><th>Issuer (by LEI)</th></tr></thead>
            <tbody>{rows.map(r => (
              <tr key={r.counterparty_ref} className="border-t border-[var(--color-line)]">
                <td className="mono">{r.counterparty_ref}</td>
                <td className="text-[var(--color-mute)]">{r.counterparty_name ?? '—'}</td>
                <td className="text-right tabular-nums">{r.n_exposures}</td>
                <td className="text-right tabular-nums">
                  {r.liabilities_conflict
                    ? <span {...pressable(() => setConflict(r), { label: `Conflicting figures for ${r.counterparty_ref}` })}
                        className="text-[var(--color-warn)] underline decoration-dotted cursor-pointer">conflict · {r.liabilities_conflict.length} figures</span>
                    : r.total_liabilities_eur != null ? balance(r.total_liabilities_eur) : <span className="text-[var(--color-faint)]">not stated</span>}
                </td>
                <td className="mono text-[var(--color-mute)]">{r.total_liabilities_date ?? '—'}</td>
                <td className="text-right tabular-nums">{r.revenue_eur != null ? balance(r.revenue_eur) : <span className="text-[var(--color-faint)]">not stated</span>}</td>
                <td className="mono text-[var(--color-mute)]">{r.revenue_period_end ?? '—'}</td>
                <td className="text-[var(--color-mute)]">{r.issuer_name ?? '—'}</td>
              </tr>))}</tbody>
          </table>
        </div>
      )}
      <ValidatedUpload
        intro={<>One row per counterparty: its id as on the loan tape, its total liabilities and equity, its revenue, and the <b className="text-[var(--color-ink)]">financial year end</b> (book_date) they are taken from. Total liabilities convert at that date&rsquo;s closing rate, revenue at the average rate of the year to it. Checked like the loan tape; a failed check goes to a second person.</>}
        dropLabel="counterparties file" template="bank_counterparties"
        endpoints={{ validate: '/v1/bank/counterparties/validate', upload: '/v1/bank/counterparties/upload', template: '/v1/bank/counterparties/template.xlsx', templateFile: 'tellumen_counterparties_template.xlsx' }}
        onDone={() => qc.invalidateQueries({ queryKey: ['bank-counterparties'] })}
        renderDone={res => <>Stated <b>{Number(res.n_uploaded) || 0}</b> counterpart{Number(res.n_uploaded) === 1 ? 'y' : 'ies'} — saved.</>}
      />
      {conflict && (
        <Dialog title={`Conflicting figures · ${conflict.counterparty_ref}`} onClose={() => setConflict(null)}>
          <p className="text-[12.5px] text-[var(--color-mute)] mb-3">
            These exposures stated different total liabilities for the same counterparty before the figure became the
            counterparty&rsquo;s own. None was picked; state the one figure in a counterparties file to resolve it.
          </p>
          <table className="w-full text-[12px]">
            <thead><tr className="mono text-[9.5px] uppercase text-[var(--color-faint)] text-left"><th className="py-1">Exposure</th><th className="text-right">EUR</th><th>Date</th><th>As sent</th></tr></thead>
            <tbody>{(conflict.liabilities_conflict ?? []).map(s => (
              <tr key={s.entity_id} className="border-t border-[var(--color-line)]">
                <td className="py-1.5 mono text-[10.5px]">{s.entity_id.slice(0, 8)}</td>
                <td className="text-right tabular-nums">{balance(s.eur)}</td>
                <td className="mono">{s.date}</td>
                <td className="mono text-[var(--color-mute)]">{s.source?.amount != null ? `${s.source.amount} ${s.source.currency ?? ''}` : '—'}</td>
              </tr>))}</tbody>
          </table>
        </Dialog>
      )}
    </div>
  )
}
