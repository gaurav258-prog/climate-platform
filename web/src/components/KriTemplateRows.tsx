import { useState } from 'react'
import { InfoButton, HEADING } from './Details'
import { balance } from '../lib/money'

// The Pillar 3 physical-risk template prints exposure per sector or collateral row, with no book total (E98). Its
// indicators — one per row and kind of event — are picked by row here instead of crowding the indicator grid; each
// opens the indicator's drawer (trend across filings, how it is computed), like any tile. The template's row and
// column numbers are references: they sit in the drawer, one click away.
export interface RowKpi {
  key: string; label: string; value: number | null; group?: string
  row?: { id: string; label: string }; column?: string; column_name?: string
  status?: 'ok' | 'amber' | 'red' | null
}
export interface HistFigure { key: string; value: number | null; group?: string }
export interface HistRow { label: string; figures?: HistFigure[] }

const ABOUT = {
  title: 'Exposure by sector row',
  sections: [
    { heading: HEADING.shows, body: 'For one sector or collateral row of your Pillar 3 physical-risk template: the gross carrying amount of the exposures sensitive to chronic events only, to acute events only, and to both, at or above your stated at-risk level, in all countries.' },
    { heading: HEADING.read, body: 'Each figure is live, over today’s book; beneath it is the figure your last filing printed for the same row. Open one for its trend across filings.' },
  ],
}

export default function KriTemplateRows({ kpis, history, onOpen }: { kpis: RowKpi[]; history: HistRow[]; onOpen: (key: string) => void }) {
  const rows = kpis.reduce<{ id: string; label: string }[]>((acc, k) => (k.row && !acc.some(r => r.id === k.row!.id) ? [...acc, k.row] : acc), [])
  const [rowId, setRowId] = useState(rows[0]?.id ?? '')
  const cells = kpis.filter(k => k.row?.id === rowId)
  const last = [...history].reverse().find(h => (h.figures ?? []).some(f => f.group && cells.some(c => c.key === f.key)))
  const filed = (key: string) => last?.figures?.find(f => f.key === key)?.value
  const max = Math.max(1, ...cells.map(c => c.value ?? 0))
  if (!rows.length) return null
  return (
    <div>
      <div className="flex items-center gap-2 flex-wrap mb-3">
        <select value={rowId} onChange={e => setRowId(e.target.value)} aria-label="Sector row"
          className="bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-md px-2 py-1.5 text-[12.5px] text-[var(--color-ink)] max-w-full">
          {rows.map(r => <option key={r.id} value={r.id}>{r.label}</option>)}
        </select>
        <InfoButton compact details={ABOUT} />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {cells.map(k => {
          const f = filed(k.key)
          return (
            <button key={k.key} onClick={() => onOpen(k.key)}
              className="text-left rounded-xl border border-[var(--color-line)] hover:border-[var(--color-line-2)] bg-[var(--color-panel)] px-4 py-3 transition">
              <div className="text-[12px] text-[var(--color-mute)]">{k.column_name}</div>
              <div className="display text-[20px] leading-none mt-1.5 tabular-nums" style={{ color: 'var(--color-bad)' }}>{k.value == null ? '—' : balance(k.value)}</div>
              <div className="mt-2 h-1 rounded-full bg-[var(--color-panel-2)]"><div className="h-full rounded-full bg-[var(--color-bad)] opacity-70" style={{ width: `${Math.max(2, 100 * (k.value ?? 0) / max)}%` }} /></div>
              <div className="text-[11.5px] text-[var(--color-faint)] mt-2 tabular-nums">
                {last ? <>Filed {last.label}: {f == null ? '—' : balance(f)}</> : 'Not filed yet'}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
