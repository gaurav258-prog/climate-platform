import { useEffect, useState } from 'react'
import { api } from '../lib/api'

// Every money input declares the currency of its amounts and the date they describe — never assumed (multi-currency
// review, 2026-09-26). One control, used by every upload and form that takes money: amounts convert to EUR at that
// date's official rate (balances) or the average of the 12 months to it (yearly figures).

let cached: string[] | null = null

export function useCurrencies() {
  const [list, setList] = useState<string[]>(cached ?? [])
  useEffect(() => {
    if (cached) return
    api.get<{ currencies: string[] }>('/v1/intake/fx/currencies').then(r => { cached = r.currencies; setList(r.currencies) }).catch(() => setList([]))
  }, [])
  return list
}

const field = 'block mt-0.5 rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 mono text-[12px] text-[var(--color-ink)]'

export default function MoneyDeclaration({ currency, setCurrency, bookDate, setBookDate, dateLabel = 'Book date (the date the figures describe)', note, withDate = true }: {
  currency: string; setCurrency: (v: string) => void; bookDate?: string; setBookDate?: (v: string) => void
  dateLabel?: string; note?: string; withDate?: boolean
}) {
  const list = useCurrencies()
  return (
    <div className="flex items-end gap-3 flex-wrap text-[11.5px] text-[var(--color-mute)]">
      <label>Amounts are in
        <select value={currency} onChange={e => setCurrency(e.target.value)} className={field} aria-label="Currency of the amounts">
          <option value="">— currency —</option>
          {list.map(c => <option key={c} value={c}>{c}</option>)}
        </select></label>
      {withDate && setBookDate && (
        <label>{dateLabel}
          <input type="date" value={bookDate ?? ''} max={new Date().toISOString().slice(0, 10)} onChange={e => setBookDate(e.target.value)} className={field} /></label>
      )}
      {note && <span className="text-[10.5px] text-[var(--color-faint)] basis-full">{note}</span>}
    </div>
  )
}
