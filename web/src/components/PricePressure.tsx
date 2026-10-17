import { useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { TrendingUp, Upload, Download } from 'lucide-react'
import { api, apiDetail, apiMessage, upload as uploadFile, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, StatGrid, type StatItem } from './ui'
import { money } from '../lib/money'
import { HEADING, InfoButton, MessageLine, type Details, type Message } from './Details'

// Commodity price pressure — observed authoritative price indices (World Bank, EU agri-food portal) weighted by the
// book's spend. Tellumen never forecasts a price; this is the observed move on commodities the buyer sources,
// turned into input-cost pressure on the bill of materials. A commodity with no usable index says why (a server
// message, agri.data.price.*), and the method sits behind the card's ⓘ (UI standard, 2026-10-16).

interface Item { commodity: string; spend_eur: number; covered: boolean; shock_pct: number | null; price_move_pct?: number; currency_effect_pct?: number; quote_currency?: string; reason_message?: Message; latest_period?: string; pressure_eur: number }
interface Resp { available: boolean; summary?: { total_spend_eur: number; covered_spend_eur: number; coverage_pct: number; input_cost_pressure_eur: number; pressure_pct_of_spend: number }; commodities?: Item[]; currency?: string }

const signed = (n: number) => `${n > 0 ? '+' : ''}${n}%`
const about = (ccy: string): Details => ({
  title: 'Commodity price pressure', sections: [
    { heading: HEADING.shows, body: 'The input-cost pressure that observed price moves put on your sourcing spend: each commodity’s spend times the rise in its price.' },
    { heading: HEADING.read, body: `A move compares the latest month with the average of the twelve months before it, measured in ${ccy}. A price quoted in another currency is converted month by month, so its move includes that currency’s own move, shown beside it. Only a rise counts as pressure.` },
    { heading: HEADING.sources, body: 'Monthly price series from the World Bank commodity price data and the European Commission’s agri-food data portal, or series you load yourself. The template has one row per commodity and month: its source, commodity, month, index value, unit and currency.' },
    { heading: HEADING.limits, body: 'Observed prices only; this is not a price forecast. A commodity without a usable price series is shown with the reason and carries no pressure.' },
  ],
})

export default function PricePressure() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const q = useQuery({ queryKey: ['price-pressure'], queryFn: () => api.get<Resp>('/v1/prices/pressure') })
  const d = q.data
  if (d && !d.available) return null          // no sourcing plots: there is no spend to put a price move on

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { await uploadFile('/v1/prices/upload', f); qc.invalidateQueries({ queryKey: ['price-pressure'] }); toast.success('Price series loaded.') }
    catch (err) { toast.error(apiDetail(err)?.what ?? apiMessage(err, 'The file could not be loaded.')) }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const s = d?.summary
  const ccy = d?.currency ?? 'EUR'
  const eur = (n?: number | null) => money(n, ccy)

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <TrendingUp size={15} className="text-[var(--color-warn)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)] m-0">Commodity price pressure</h3>
        <InfoButton compact details={about(ccy)} />
        <span className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => download('/v1/prices/template.csv', 'tellumen_price_index_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download the template" aria-label="Download the template"><Download size={13} /></button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button type="button" onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Load indices</button>
        </span>
      </div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !s ? <div className="text-[12.5px] text-[var(--color-mute)] py-3">No price series loaded yet.</div> : (
          <>
            <StatGrid className="mb-3" cols={4} items={[
              { label: 'Input-cost pressure', value: eur(s.input_cost_pressure_eur), accent: 'var(--color-warn)' },
              { label: 'of spend', value: `${s.pressure_pct_of_spend}%` },
              { label: 'Sourcing spend', value: eur(s.total_spend_eur) },
              { label: 'Spend with a price', value: `${s.coverage_pct}%` },
            ] satisfies StatItem[]} />
            <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
              {d.commodities!.map(c => (
                <div key={c.commodity} className="flex items-center gap-3 py-1.5 text-[12px]">
                  <span className="text-[var(--color-ink)] shrink-0 w-20 sm:w-24 truncate">{c.commodity}</span>
                  {c.shock_pct == null ? (
                    <span className="flex-1 min-w-0 text-[var(--color-faint)] truncate">{c.reason_message ? <MessageLine m={c.reason_message} /> : 'No price index'}</span>
                  ) : (<>
                    <span className="shrink-0 w-16 tabular-nums font-medium" style={{ color: c.shock_pct > 0 ? 'var(--color-bad)' : 'var(--color-good)' }}>{signed(c.shock_pct)}</span>
                    <span className="flex-1 min-w-0 text-[11px] text-[var(--color-faint)] truncate tabular-nums">
                      {c.quote_currency && c.quote_currency !== ccy && c.price_move_pct != null
                        ? `price ${signed(c.price_move_pct)} in ${c.quote_currency} · currency ${signed(c.currency_effect_pct ?? 0)}` : ''}
                    </span>
                  </>)}
                  <span className="hidden sm:inline text-[11px] text-[var(--color-faint)] shrink-0 tabular-nums">{eur(c.spend_eur)} spend</span>
                  <span className="tabular-nums shrink-0 w-16 text-right" style={{ color: c.pressure_eur > 0 ? 'var(--color-warn)' : 'var(--color-faint)' }}>{c.pressure_eur > 0 ? eur(c.pressure_eur) : '—'}</span>
                </div>
              ))}
            </div>
          </>
        )}
    </Card>
  )
}
