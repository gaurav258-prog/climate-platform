import { useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { TrendingUp, Upload, Download } from 'lucide-react'
import { api, upload as uploadFile, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card } from './ui'

// Commodity price pressure — observed authoritative price indices (FAO / World Bank / USDA) weighted by the
// book's spend. Tellumen never forecasts a price; this is the observed move on commodities the buyer sources,
// turned into input-cost pressure on the bill of materials. A commodity with no index is shown as uncovered.

interface Item { commodity: string; spend_eur: number; covered: boolean; shock_pct: number | null; latest_period?: string; source?: string; pressure_eur: number }
interface Resp { available: boolean; reason?: string; summary?: { total_spend_eur: number; covered_spend_eur: number; coverage_pct: number; input_cost_pressure_eur: number; pressure_pct_of_spend: number }; commodities?: Item[] }
const eur = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

export default function PricePressure() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const q = useQuery({ queryKey: ['price-pressure'], queryFn: () => api.get<Resp>('/v1/prices/pressure') })
  const d = q.data
  if (d && !d.available && d.reason === 'no_sourcing_book') return null

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { await uploadFile('/v1/prices/upload', f); qc.invalidateQueries({ queryKey: ['price-pressure'] }); toast.success('Price indices loaded.') }
    catch { toast.error('Upload failed — check the template columns.') }
    finally { if (fileRef.current) fileRef.current.value = '' }
  }
  const s = d?.summary

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <TrendingUp size={15} className="text-[var(--color-warn)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">Commodity price pressure</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· observed index moves on your spend</span>
        <span className="ml-auto flex items-center gap-2">
          <button onClick={() => download('/v1/prices/template.csv', 'tellumen_price_index_template.csv').catch(() => {})} className="text-[var(--color-faint)] hover:text-[var(--color-sky)]" title="Download template"><Download size={13} /></button>
          <input ref={fileRef} type="file" accept=".csv" onChange={onFile} className="hidden" />
          <button onClick={() => fileRef.current?.click()} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-2.5 py-1.5 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Upload size={13} /> Load indices</button>
        </span>
      </div>

      {!d ? <div className="text-[12.5px] text-[var(--color-faint)] py-4">Loading…</div>
        : !s ? (
          <div className="text-[12.5px] text-[var(--color-mute)] py-3">
            Load observed commodity price indices (FAO / World Bank / USDA — columns: <span className="mono text-[11px]">source, commodity, period_ym, index_value, unit</span>) and Tellumen shows the input-cost pressure they put on your sourcing spend.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-3">
              <div><div className="display text-[20px] leading-none tabular-nums" style={{ color: 'var(--color-warn)' }}>{eur(s.input_cost_pressure_eur)}</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Input-cost pressure</div></div>
              <div><div className="display text-[20px] leading-none tabular-nums text-[var(--color-ink)]">{s.pressure_pct_of_spend}%</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">of spend</div></div>
              <div><div className="display text-[20px] leading-none tabular-nums text-[var(--color-ink)]">{eur(s.total_spend_eur)}</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Sourcing spend</div></div>
              <div><div className="display text-[20px] leading-none tabular-nums text-[var(--color-ink)]">{s.coverage_pct}%</div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mt-1.5">Priced-index coverage</div></div>
            </div>
            <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
              {d.commodities!.map(c => (
                <div key={c.commodity} className="flex items-center gap-3 py-1.5 text-[12px]">
                  <span className="text-[var(--color-ink)] shrink-0 w-24 truncate">{c.commodity}</span>
                  <span className="mono text-[11px] shrink-0 w-16" style={{ color: c.shock_pct == null ? 'var(--color-faint)' : c.shock_pct > 0 ? 'var(--color-bad)' : 'var(--color-good)' }}>
                    {c.shock_pct == null ? 'no index' : `${c.shock_pct > 0 ? '+' : ''}${c.shock_pct}%`}
                  </span>
                  <span className="flex-1 min-w-0" />
                  <span className="mono text-[11px] text-[var(--color-faint)] shrink-0">{eur(c.spend_eur)} spend</span>
                  <span className="mono tabular-nums shrink-0 w-16 text-right" style={{ color: c.pressure_eur > 0 ? 'var(--color-warn)' : 'var(--color-faint)' }}>{c.pressure_eur > 0 ? eur(c.pressure_eur) : '—'}</span>
                </div>
              ))}
            </div>
            <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2.5">Observed agency indices — not a Tellumen forecast · pressure = spend × positive move vs a 12-month baseline · uncovered commodities shown as 'no index'</div>
          </>
        )}
    </Card>
  )
}
