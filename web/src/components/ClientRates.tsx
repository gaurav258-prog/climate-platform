import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Coins, Download, Upload } from 'lucide-react'
import { ApiError, api, download, upload as uploadFile } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, SectionHead } from './ui'
import { Dialog } from './Dialog'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'

// The organisation's own (treasury) exchange rates. Used first for its own amounts (principle 1: the client wins on
// facts about their own book), always compared with the official rate for the same day or period; a difference beyond
// the tolerance set under Methodology needs a second person (imports) or is refused (direct entries). A refused row
// comes back as a catalogue message (services/reference/client_fx.submit).

interface Rate { ccy: string; basis: string; period_start: string | null; rate_date: string; units_per_eur: number }
interface Accepted { currency: string; basis_label: string; rate_date: string; units_per_eur: number; official_units_per_eur: number | null; difference_pct: number | null }
interface Refused { row: number; message: Message }
interface Result { accepted: Accepted[]; n_refused: number; refused: Refused[] }

const ABOUT = {
  title: 'Your exchange rates', sections: [
    { heading: HEADING.shows, body: 'Your treasury’s rates, used for your own amounts in place of the official rate.' },
    { heading: HEADING.read, body: 'Each rate is compared with the official rate for the same day or period — the European Central Bank’s, a rate fixed by law, or the International Monetary Fund’s. A rate further away than the tolerance set under Methodology needs a second person to accept it.' },
    { heading: 'The file', body: 'Download the template and add one row per rate: the currency, the date and the number of units of the currency per euro, as the European Central Bank quotes them. For an average rate, give the basis as an average for the period and the first day of the period. Rates are kept: a new file adds rates and never overwrites.' },
  ],
}

export default function ClientRates() {
  const q = useQuery({ queryKey: ['client-rates'], queryFn: () => api.get<{ rates: Rate[] }>('/v1/intake/fx/client-rates') })
  const fileRef = useRef<HTMLInputElement>(null)
  const [last, setLast] = useState<Result | null>(null)
  const [why, setWhy] = useState(false)
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try {
      const r = await uploadFile<Result>('/v1/intake/fx/client-rates/upload', f)
      setLast(r); q.refetch(); toast.success(`${r.accepted.length} rates saved.`)
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as { error?: { message?: string; refused?: Refused[] } } | null) : null
      if (body?.error?.refused) setLast({ accepted: [], n_refused: body.error.refused.length, refused: body.error.refused })
      toast.error(body?.error?.message ?? 'The file could not be uploaded.')
    } finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const rates = q.data?.rates ?? []
  const byCcy = [...rates.reduce((m, r) => (m.has(r.ccy) ? m : m.set(r.ccy, r)), new Map<string, Rate>()).values()]

  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <SectionHead icon={Coins} className="gap-1.5">Your exchange rates <InfoButton compact details={ABOUT} /></SectionHead>
        <span className="ml-auto flex gap-2">
          <button onClick={() => download('/v1/intake/fx/client-rates/template.csv', 'exchange-rates-template.csv').catch(() => toast.error('The template could not be downloaded.'))}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><Download size={13} /> Template</button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><Upload size={13} /> Upload rates</button>
        </span>
      </div>
      {rates.length === 0
        ? <StatusChip tone="neutral" label="None on file — the official rates are used" />
        : (
          <div className="flex flex-wrap gap-2">
            {byCcy.slice(0, 10).map(r => (
              <span key={r.ccy} className="rounded-lg border border-[var(--color-line)] px-2.5 py-1.5 text-[12px]">
                <span className="font-medium text-[var(--color-ink)]">{r.ccy}</span>
                <span className="ml-2 tabular-nums text-[var(--color-mute)]">{r.units_per_eur}</span>
                <span className="ml-2 text-[11.5px] text-[var(--color-faint)]">{r.basis === 'closing' ? r.rate_date : `${r.period_start} to ${r.rate_date}`}</span>
              </span>
            ))}
            <span className="self-center text-[12px] text-[var(--color-faint)] tabular-nums">{rates.length} on file</span>
          </div>
        )}
      {last && (last.accepted.length > 0 || last.n_refused > 0) && (
        <div className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
          {last.accepted.length > 0 && (
            <div className="overflow-x-auto">
              <table className="data-table w-full text-[12px]">
                <thead><tr><th>Just saved</th><th>Yours</th><th>Official</th><th>Apart</th></tr></thead>
                <tbody>{last.accepted.slice(0, 12).map((a, i) => (
                  <tr key={i}>
                    <td>{a.currency} · {a.basis_label} · {a.rate_date}</td>
                    <td className="tabular-nums">{a.units_per_eur}</td>
                    <td className="tabular-nums">{a.official_units_per_eur ?? '—'}</td>
                    <td className="tabular-nums">{a.difference_pct == null ? '—' : `${a.difference_pct}%`}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
          {last.n_refused > 0 && (
            <button onClick={() => setWhy(true)} className="inline-flex items-center gap-2 text-[12.5px] text-[var(--color-warn)] hover:underline">
              <StatusChip tone="warn" label={`${last.n_refused} rows not used`} /> See why
            </button>
          )}
        </div>
      )}
      {why && last && (
        <Dialog title="Rows not used" onClose={() => setWhy(false)}>
          <ul className="m-0 p-0 list-none divide-y divide-[var(--color-line)]">
            {last.refused.map(r => <li key={r.row} className="py-2 text-[12.5px] flex items-center gap-3"><span className="text-[var(--color-faint)] tabular-nums w-14">Row {r.row}</span><MessageLine m={r.message} /></li>)}
          </ul>
        </Dialog>
      )}
    </Card>
  )
}
