import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Coins, Upload } from 'lucide-react'
import { api, upload as uploadFile } from '../lib/api'
import { toast } from '../lib/toast'
import { Card } from './ui'

// The organisation's own (treasury) exchange rates. Used first for its own amounts (principle 1: the client wins on
// facts about their own book), always compared with the official rate for the same day or period; a difference beyond
// the tolerance set under Methodology needs a second person (imports) or is refused (direct entries).

interface Rate { ccy: string; basis: string; period_start: string | null; rate_date: string; units_per_eur: number; source_note: string | null; submitted_at: string }
interface Accepted { currency: string; basis: string; rate_date: string; units_per_eur: number; official_units_per_eur: number | null; official_source: string | null; difference_pct: number | null }

export default function ClientRates() {
  const q = useQuery({ queryKey: ['client-rates'], queryFn: () => api.get<{ rates: Rate[] }>('/v1/intake/fx/client-rates') })
  const fileRef = useRef<HTMLInputElement>(null)
  const [last, setLast] = useState<{ accepted: Accepted[]; n_refused: number; refused: { row: number; reason: string }[] } | null>(null)
  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { const r = await uploadFile<{ accepted: Accepted[]; n_refused: number; refused: { row: number; reason: string }[] }>('/v1/intake/fx/client-rates/upload', f); setLast(r); q.refetch(); toast.success(`${r.accepted.length} rate(s) saved.`) }
    catch (err: unknown) { toast.error((err as { body?: { error?: { message?: string } } })?.body?.error?.message ?? 'Upload failed.') }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const rates = q.data?.rates ?? []
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-1"><Coins size={16} className="text-[var(--color-blue)]" /><h3 className="font-semibold">Your exchange rates</h3>
        <span className="ml-auto">
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><Upload size={13} /> Upload rates (CSV)</button>
        </span></div>
      <p className="text-[11.5px] text-[var(--color-faint)] mb-3 max-w-2xl">Optional. Your treasury rates are used for your own amounts, and always compared with the official rate (ECB, a rate fixed by law, or IMF) for the same day or period — beyond the tolerance under Methodology, a second person must accept it. CSV columns: <span className="mono">currency, rate_date, units_per_eur</span> (per 1 EUR, as the ECB quotes), optional <span className="mono">basis</span> (closing / period_average), <span className="mono">period_start</span> (for an average), <span className="mono">note</span>. Rates are kept; a new upload adds, never overwrites.</p>
      {last && last.accepted.length > 0 && (
        <div className="mb-3 text-[12px] overflow-x-auto">
          <table className="w-full"><thead><tr className="text-left mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]"><th className="font-normal py-1">Just saved</th><th className="font-normal">Yours</th><th className="font-normal">Official</th><th className="font-normal">Apart</th></tr></thead>
            <tbody>{last.accepted.slice(0, 12).map((a, i) => (
              <tr key={i} className="border-t border-[var(--color-line)]"><td className="py-1 mono">{a.currency} · {a.basis} · {a.rate_date}</td><td className="mono tabular-nums">{a.units_per_eur}</td>
                <td className="mono tabular-nums">{a.official_units_per_eur ?? '—'} <span className="text-[var(--color-faint)]">{a.official_source ?? ''}</span></td>
                <td className="mono tabular-nums">{a.difference_pct == null ? '—' : `${a.difference_pct}%`}</td></tr>))}</tbody></table>
          {last.n_refused > 0 && <div className="mt-1" style={{ color: 'var(--color-warn)' }}>{last.n_refused} row(s) not used — e.g. row {last.refused[0].row}: {last.refused[0].reason}</div>}
        </div>
      )}
      {rates.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">None on file — the official rates are used.</div> : (
        <div className="text-[12px] text-[var(--color-mute)]">{rates.length} rate(s) on file · latest: {rates.slice(0, 6).map(r => `${r.ccy} ${r.units_per_eur} (${r.basis === 'closing' ? r.rate_date : `${r.period_start}→${r.rate_date} avg`})`).join(' · ')}{rates.length > 6 ? ' …' : ''}</div>
      )}
    </Card>
  )
}
