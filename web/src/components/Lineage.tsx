import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ArrowDown, ArrowUp, Satellite } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'

// ── data shapes ────────────────────────────────────────────────────────────
interface Commodity { commodity: string; volume_at_risk_eur: number | null; calibration: string | null; top_hazard: string | null; yield_shock_pct: number | null }
interface Summary { rollup: { volume_at_risk_eur: number }; commodities: Commodity[] }
interface Plot { plot_id: string; commodity: string; plot_name: string; country: string | null; spend_eur: number; top_hazard: string | null; hazard_score: number | null; eudr_determination: string | null }
interface Portfolio { plots: Plot[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(2)}m` : `€${(n / 1e3).toFixed(0)}k`
const KIND: Record<string, string> = {
  report: 'var(--color-sky)', commodity: 'var(--color-warn)', plot: 'var(--color-ink)',
  feed: 'var(--color-blue)', score: 'var(--color-good)',
}

// ── a lineage node ──────────────────────────────────────────────────────────
interface Node { id: string; kind: keyof typeof KIND | string; label: string; value?: string; note?: string; share?: number; children?: Node[] }

function TreeRow({ node, depth }: { node: Node; depth: number }) {
  const [open, setOpen] = useState(depth < 1)
  const has = !!node.children?.length
  const c = KIND[node.kind] ?? 'var(--color-mute)'
  return (
    <div>
      <button onClick={() => has && setOpen(o => !o)}
        className={clsx('w-full flex items-center gap-2 text-left py-2 rounded-lg px-2 transition',
          has ? 'hover:bg-[var(--color-panel-2)] cursor-pointer' : 'cursor-default')}
        style={{ paddingLeft: depth * 20 + 8 }}>
        {has ? <ChevronRight size={14} className="text-[var(--color-faint)] transition-transform shrink-0" style={{ transform: open ? 'rotate(90deg)' : 'none' }} />
          : <span className="w-[14px] shrink-0" />}
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: c }} />
        <span className="mono text-[9px] uppercase tracking-widest shrink-0" style={{ color: c }}>{node.kind}</span>
        <span className="text-[13px] text-[var(--color-ink)] truncate">{node.label}</span>
        {node.note && <span className="text-[11px] text-[var(--color-faint)] truncate hidden sm:inline">{node.note}</span>}
        <span className="ml-auto flex items-center gap-3 shrink-0">
          {node.share != null && <span className="mono text-[10px] text-[var(--color-faint)]">{(node.share * 100).toFixed(0)}%</span>}
          {node.value && <span className="mono text-[12px] font-medium" style={{ color: c }}>{node.value}</span>}
        </span>
      </button>
      {has && open && <div className="border-l border-[var(--color-line)]" style={{ marginLeft: depth * 20 + 14 }}>
        {node.children!.map(ch => <TreeRow key={ch.id} node={ch} depth={depth + 1} />)}
      </div>}
    </div>
  )
}

// ── build the top-down tree from real data ─────────────────────────────────
function buildTopDown(sum: Summary, plots: Plot[]): Node {
  const total = sum.rollup.volume_at_risk_eur
  const byCommodity = sum.commodities.filter(c => (c.volume_at_risk_eur ?? 0) > 0)
    .sort((a, b) => (b.volume_at_risk_eur ?? 0) - (a.volume_at_risk_eur ?? 0))
  return {
    id: 'root', kind: 'report', label: 'Volume-at-risk (physical) — the report figure', value: eur(total),
    note: 'CSRD physical-risk / COGS-at-risk',
    children: byCommodity.map(c => {
      const cv = c.volume_at_risk_eur ?? 0
      const cplots = plots.filter(p => p.commodity === c.commodity)
      const spend = cplots.reduce((s, p) => s + (p.spend_eur ?? 0), 0)
      return {
        id: `c-${c.commodity}`, kind: 'commodity', label: c.commodity, value: eur(cv),
        share: total ? cv / total : 0, note: `${c.calibration ?? 'tested'} · ${c.top_hazard ?? ''} ${c.yield_shock_pct ?? ''}%`,
        children: cplots.map(p => ({
          id: `p-${p.plot_id}`, kind: 'plot', label: p.plot_name, value: eur(p.spend_eur),
          share: spend ? (p.spend_eur ?? 0) / spend : 0, note: `${p.country ?? ''}`,
          children: [
            { id: `s-${p.plot_id}`, kind: 'score', label: `Hazard score ${p.hazard_score?.toFixed(0) ?? '—'}`, note: p.top_hazard ?? '', value: p.top_hazard ?? '' },
            { id: `f1-${p.plot_id}`, kind: 'feed', label: 'ERA5 climatology', note: 'Copernicus — temperature / precip / soil moisture' },
            ...(p.eudr_determination ? [{ id: `f2-${p.plot_id}`, kind: 'feed', label: 'Hansen GFC forest-loss', note: 'EUDR deforestation check' }] : []),
          ],
        })),
      }
    }),
  }
}

// ── build the bottom-up chain for one plot ──────────────────────────────────
function buildBottomUp(plot: Plot, sum: Summary): Node[] {
  const com = sum.commodities.find(c => c.commodity === plot.commodity)
  const cv = com?.volume_at_risk_eur ?? null
  return [
    { id: 'b-feed', kind: 'feed', label: 'ERA5 climatology + Hansen forest-loss', note: 'the raw satellite feeds under this plot' },
    { id: 'b-score', kind: 'score', label: `Hazard score ${plot.hazard_score?.toFixed(0) ?? '—'}`, note: plot.top_hazard ?? '' },
    { id: 'b-plot', kind: 'plot', label: plot.plot_name, value: eur(plot.spend_eur), note: `${plot.country ?? ''} · spend` },
    { id: 'b-com', kind: 'commodity', label: `${plot.commodity} — volume at risk`, value: eur(cv), note: com?.calibration ?? 'tested' },
    { id: 'b-report', kind: 'report', label: 'Volume-at-risk (physical) — the report figure', value: eur(sum.rollup.volume_at_risk_eur), note: 'CSRD / COGS-at-risk' },
  ]
}

export default function Lineage() {
  const [dir, setDir] = useState<'down' | 'up'>('down')
  const [plotId, setPlotId] = useState<string>('')
  const sumQ = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary') })
  const pfQ = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })

  const plots = pfQ.data?.plots ?? []
  const tree = useMemo(() => (sumQ.data && pfQ.data) ? buildTopDown(sumQ.data, plots) : null, [sumQ.data, pfQ.data, plots])
  const selected = plots.find(p => p.plot_id === plotId) ?? plots[0]
  const chain = (sumQ.data && selected) ? buildBottomUp(selected, sumQ.data) : []

  return (
    <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-blue)] flex items-center gap-1.5"><Satellite size={12} /> Lineage</div>
          <div className="text-[13px] text-[var(--color-mute)]">
            {dir === 'down' ? 'Click a number to open what it’s made of — down to the satellite feed.' : 'Pick a plot to trace its data up into the report figure.'}
          </div>
        </div>
        <div className="flex gap-1 card p-1">
          <button onClick={() => setDir('down')} className={clsx('flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] transition', dir === 'down' ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]')}><ArrowDown size={13} /> Top-down</button>
          <button onClick={() => setDir('up')} className={clsx('flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] transition', dir === 'up' ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]')}><ArrowUp size={13} /> Bottom-up</button>
        </div>
      </div>

      {(sumQ.isLoading || pfQ.isLoading) ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">loading lineage…</div> :
        dir === 'down' ? (tree && <TreeRow node={tree} depth={0} />) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">granular point</span>
              <select value={selected?.plot_id ?? ''} onChange={e => setPlotId(e.target.value)}
                className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] outline-none focus:border-[var(--color-sky)]">
                {plots.map(p => <option key={p.plot_id} value={p.plot_id}>{p.plot_name}</option>)}
              </select>
            </div>
            <div className="relative">
              {chain.map((n, i) => {
                const c = KIND[n.kind] ?? 'var(--color-mute)'
                return (
                  <div key={n.id} className="flex items-stretch gap-3">
                    <div className="flex flex-col items-center">
                      <span className="w-2.5 h-2.5 rounded-full mt-4" style={{ background: c }} />
                      {i < chain.length - 1 && <span className="w-px flex-1 bg-[var(--color-line-2)]" />}
                    </div>
                    <div className="flex-1 card p-3 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="mono text-[9px] uppercase tracking-widest" style={{ color: c }}>{n.kind}</span>
                        <span className="text-[13px] text-[var(--color-ink)]">{n.label}</span>
                        {n.value && <span className="ml-auto mono text-[12px] font-medium" style={{ color: c }}>{n.value}</span>}
                      </div>
                      {n.note && <div className="text-[11px] text-[var(--color-faint)] mt-0.5">{n.note}</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
    </div>
  )
}
