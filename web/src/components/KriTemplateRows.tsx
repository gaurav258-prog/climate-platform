import { useState } from 'react'
import { balance } from '../lib/money'

// Pillar 3 Template 5 prints physical risk per sector / collateral row with no book total (E98). Its KRIs — one per row
// and column — are picked by row here instead of crowding the indicator grid; each card opens the KRI's drill (trend
// across filings, methodology), like any tile.
export interface RowKpi {
  key: string; label: string; value: number | null; hint: string | null; group?: string
  row?: { id: string; label: string }; column?: string; filed_basis?: string | null; reg?: string
  status?: 'ok' | 'amber' | 'red' | null
}
export interface HistFigure { key: string; value: number | null; group?: string }
export interface HistRow { label: string; figures?: HistFigure[] }

const COL: Record<string, string> = { h: 'Chronic only', i: 'Acute only', j: 'Chronic and acute' }

export default function KriTemplateRows({ kpis, history, onOpen }: { kpis: RowKpi[]; history: HistRow[]; onOpen: (key: string) => void }) {
  const rows = kpis.reduce<{ id: string; label: string }[]>((acc, k) => (k.row && !acc.some(r => r.id === k.row!.id) ? [...acc, k.row] : acc), [])
  const [rowId, setRowId] = useState(rows[0]?.id ?? '')
  const cells = kpis.filter(k => k.row?.id === rowId)
  const last = [...history].reverse().find(h => (h.figures ?? []).some(f => f.group && cells.some(c => c.key === f.key)))
  const filed = (key: string) => last?.figures?.find(f => f.key === key)?.value
  if (!rows.length) return null
  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Template 5 · row</div>
        <select value={rowId} onChange={e => setRowId(e.target.value)} aria-label="Template 5 row"
          className="bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1 text-[12px] text-[var(--color-ink)] max-w-full">
          {rows.map(r => <option key={r.id} value={r.id}>{r.id} · {r.label}</option>)}
        </select>
        <div className="mono text-[9.5px] text-[var(--color-faint)]">all geographies · gross carrying amount sensitive at or above your stated level</div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {cells.map(k => (
          <button key={k.key} onClick={() => onOpen(k.key)} title={k.hint ?? undefined}
            className="text-left rounded-lg border border-[var(--color-line)] hover:border-[var(--color-line-2)] bg-[var(--color-panel)] px-4 py-3 transition">
            <div className="display text-[20px] leading-none" style={{ color: '#fb7185' }}>{k.value == null ? '—' : balance(k.value)}</div>
            <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-2">Column {k.column} · {COL[k.column ?? ''] ?? k.column}</div>
            <div className="mono text-[9px] text-[var(--color-faint)] mt-1">
              {last ? <>last filed ({last.label}): {filed(k.key) == null ? '—' : balance(filed(k.key)!)}</> : 'no filed history yet'}
            </div>
          </button>
        ))}
      </div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2">Live over today's book · each figure is a printed Template 5 cell · open one for its trend across filings</div>
    </div>
  )
}
