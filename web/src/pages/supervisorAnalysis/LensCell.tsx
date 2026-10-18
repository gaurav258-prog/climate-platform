import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { money } from '../../lib/money'
import { pressable } from '../../lib/pressable'
import { bucketLabel, hazardLabel } from '../../lib/hazards'
import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../../components/Details'
import { RaiseLink, basisText, cellName, pct, type Named } from './checks'
import type { Cell, Lens } from '../SupervisorLens'

// One cell of the full rebuild, in a side drawer: the filed and the rebuilt figure on one scale, the causes of the
// difference, and every row of the supervisor's granular data behind the rebuilt figure — select a row for the hazard
// scores at its location. Nothing is summarised away: this is the data behind the number.
export type Part = 'scope' | 'coverage' | 'basis' | 'scoring' | 'unmatched'
export const PARTS: Part[] = ['scoring', 'scope', 'basis', 'coverage', 'unmatched']
export const PART: Record<Part, { label: string; color: string; what: string }> = {
  scope: { label: 'Different exposure', color: '#7F77DD', what: 'The entity reports a different amount for the cell than your granular data holds for it. The difference is valued at the entity’s own share.' },
  coverage: { label: 'Not located', color: '#B4B2A9', what: 'Exposure in your granular data without a usable location. It cannot be checked, so the entity’s own share is assumed for it and the amount is shown here, never as a different risk assessment.' },
  basis: { label: 'Different basis', color: '#1D9E75', what: 'The entity’s stated scenario, year or at-risk threshold differs from yours. This part is the rebuild at your basis against the rebuild at the entity’s.' },
  scoring: { label: 'Different risk assessment', color: '#D85A30', what: 'At the same exposure and basis, the entity’s share of exposure sensitive to physical risk differs from the share rebuilt from the platform’s hazard scores.' },
  unmatched: { label: 'On one side only', color: '#888780', what: 'Cells that appear only in the filed template or only in your granular data.' },
}
export const signed = (v: number) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${money(Math.abs(v), 'EUR')}`

const LOCATED_BY: Record<string, string> = { nuts3: 'Region code', 'postcode→nuts3': 'Postcode', point: 'Coordinates', unlocated: 'Not located' }

interface Row {
  instrument_id: string | null; name: string; outstanding_eur: number; collateral_country: string | null; region: string | null
  location_precision: string | null; lat: number | null; lon: number | null; headline_hazard: string | null; headline_score: number | null
  bucket: string | null; counts_as_sensitive: boolean
}
interface CellResp {
  cell: Named; scenario: string; horizon: string
  submitted: { gross_carrying_amount_eur: number; sensitive_physical_eur: number; period_label: string; basis?: { method_note?: string } } | null
  rebuilt?: { rows: Row[]; submitted_share_pct: number | null; rebuilt_share_pct: number | null; located_value_eur: number; unlocated_value_eur: number
    n_rows: number; n_located: number; n_sensitive: number; rule: Message }
}

const fact = (label: string, value: React.ReactNode) => value == null || value === '' ? null : (
  <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]">
    <span className="text-[var(--color-mute)]">{label}</span><span className="text-right text-[var(--color-ink)]">{value}</span>
  </div>)
const h4 = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0">{t}</h4>

export function CellDrawer({ orgId, cell, lens, onClose }: { orgId: string; cell: Cell; lens: Lens; onClose: () => void }) {
  const q = useQuery({
    queryKey: ['sup-lens-cell', orgId, cell.geography, cell.sector],
    queryFn: () => api.get<CellResp>(`/v1/supervisor/entity/${orgId}/lens/cell?${new URLSearchParams({ geography: cell.geography, sector: cell.sector })}`),
  })
  const [row, setRow] = useState<Row | null>(null)
  const r = q.data?.rebuilt
  const name = cellName(cell)
  const scale = Math.max(1, cell.submitted_sensitive ?? 0, cell.rebuilt_sensitive ?? 0)
  const parts = (Object.keys(PART) as Part[]).filter(p => cell.gap[p])
  const partTotal = parts.reduce((a, p) => a + Math.abs(cell.gap[p]), 0)
  return (
    <Drawer label={name} onClose={onClose} className="w-full max-w-2xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5 space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[16px] font-semibold text-[var(--color-ink)]">{name}</div>
          <div className="text-[12px] text-[var(--color-mute)]">{lens.period_label} · your basis {basisText(lens.regulator_basis.scenario, lens.regulator_basis.horizon)}</div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
        {cell.flag === 'question' && cell.reason ? <>
          <StatusChip tone="warn" label="To raise" />
          <span className="text-[var(--color-ink)]"><MessageLine m={cell.reason} /></span>
          <RaiseLink orgId={orgId} cell={cell} why={cell.reason.label} />
        </> : <StatusChip tone="good" label="Within tolerance" />}
      </div>

      <div className="space-y-2.5">
        {[{ k: 'Filed', v: cell.submitted_sensitive, share: cell.submitted_share_pct, of: 'of the filed amount', color: 'var(--color-slate)' },
          { k: 'Rebuilt', v: cell.rebuilt_sensitive, share: cell.rebuilt_share_pct, of: 'of the located amount', color: 'var(--color-sky)' }].map(x => (
          <div key={x.k}>
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className="text-[var(--color-ink)]">{x.k} as sensitive</span>
              <span className="display text-[18px] tabular-nums">{x.v == null ? '—' : money(x.v, 'EUR')}</span>
            </div>
            <div className="h-2.5 rounded-full bg-[var(--color-panel-2)] mt-1 overflow-hidden">
              {x.v != null && <div className="h-full rounded-full" style={{ width: `${Math.max(1, (x.v / scale) * 100)}%`, background: x.color }} />}
            </div>
            <div className="text-[11px] text-[var(--color-faint)] mt-0.5 tabular-nums">{pct(x.share)} {x.of}</div>
          </div>))}
      </div>

      {parts.length > 0 && (
        <div className="space-y-2">
          {h4('Why it differs')}
          <div className="flex h-3 gap-[2px] rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label="The difference split by cause">
            {parts.map(p => <div key={p} title={`${PART[p].label} ${signed(cell.gap[p])}`} style={{ width: `${(Math.abs(cell.gap[p]) / partTotal) * 100}%`, background: PART[p].color }} />)}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)] tabular-nums">
            {parts.map(p => <span key={p} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: PART[p].color }} />{PART[p].label} {signed(cell.gap[p])}</span>)}
          </div>
        </div>)}

      <div>
        {fact('Filed amount', money(cell.submitted_gross, 'EUR'))}
        {fact('Amount in your granular data', money(cell.rebuilt_gross, 'EUR'))}
        {fact('Located', pct(cell.coverage_pct))}
        {r && fact('Rows', `${r.n_rows} · ${r.n_located} located · ${r.n_sensitive} sensitive`)}
        {q.data?.submitted?.basis?.method_note && fact('Entity’s method note', `“${q.data.submitted.basis.method_note}”`)}
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2">{h4('Rows behind the rebuilt figure')}{r && <InfoButton compact details={messageDetails(r.rule)} />}</div>
        {q.isLoading ? <div className="text-[12px] text-[var(--color-faint)]">Opening the rows…</div>
          : !r ? <div className="text-[12px] text-[var(--color-faint)]">No rows to show.</div> : (
          <div className="overflow-x-auto max-h-[380px] overflow-y-auto border border-[var(--color-line)] rounded-lg">
            <table className="w-full text-[12px] tabular-nums">
              <thead className="sticky top-0 bg-[var(--color-panel)]"><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
                <th className="py-1.5 px-2 font-medium">Counterparty</th><th className="pr-2 font-medium text-right">Outstanding</th>
                <th className="pr-2 font-medium">Region</th><th className="pr-2 font-medium">Located by</th>
                <th className="pr-2 font-medium">Highest hazard</th><th className="pr-2 font-medium">Sensitive</th>
              </tr></thead>
              <tbody>{r.rows.map((x, i) => (
                <tr key={i} {...pressable(x.lat != null && (() => setRow(row === x ? null : x)), { row: true, expanded: row === x })}
                  className={`border-b border-[var(--color-line)] ${x.lat != null ? 'cursor-pointer hover:bg-[var(--color-panel-2)]' : ''} ${row === x ? 'bg-[var(--color-panel-2)]' : ''}`}>
                  <td className="py-1.5 px-2 text-[var(--color-ink)]">{x.name}</td>
                  <td className="pr-2 text-right">{money(x.outstanding_eur, 'EUR')}</td>
                  <td className="pr-2 text-[var(--color-mute)]">{x.region ?? 'Country only'}</td>
                  <td className="pr-2 text-[var(--color-mute)]">{LOCATED_BY[x.location_precision ?? 'unlocated'] ?? 'Region'}</td>
                  <td className="pr-2 text-[var(--color-mute)]">{x.headline_hazard ? `${hazardLabel(x.headline_hazard)} · ${Math.round(x.headline_score ?? 0)}` : '—'}</td>
                  <td className="pr-2">{x.lat == null ? <StatusChip tone="neutral" label="Not located" /> : x.counts_as_sensitive ? <StatusChip tone="bad" label="Yes" /> : <StatusChip tone="neutral" label="No" />}</td>
                </tr>))}</tbody>
            </table>
          </div>)}
        {row && <RowHazards row={row} />}
      </div>
    </Drawer>
  )
}

interface Lookup { hazards: { hazard_type: string; risk_score: number | null; risk_bucket: string | null }[] }

function RowHazards({ row }: { row: Row }) {
  const q = useQuery({ queryKey: ['lookup', row.lat, row.lon], queryFn: () => api.get<Lookup>(`/v1/lookup/score?lat=${row.lat}&lon=${row.lon}`) })
  const hz = (q.data?.hazards ?? []).filter(h => h.risk_score != null).sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
  return (
    <div className="p-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[12.5px]">
        <b className="text-[var(--color-ink)]">{row.name}</b>
        <span className="text-[var(--color-mute)]">{row.region ?? row.collateral_country}</span>
        {row.instrument_id && <span className="text-[var(--color-faint)]">Reference {row.instrument_id}</span>}
        <InfoButton compact details={{ title: 'Hazard scores at this location', sections: [
          { heading: HEADING.shows, body: 'Every hazard the platform scores at this row’s location, today.' },
          { heading: HEADING.read, body: 'The score in the table is the highest one under your basis, your scenario and year. The row counts as sensitive when that score is at or above your at-risk threshold.' },
        ] }} />
      </div>
      {q.isLoading ? <div className="text-[11.5px] text-[var(--color-faint)]">Scoring…</div> : (
        <div className="flex flex-wrap gap-1.5">
          {hz.map(h => <StatusChip key={h.hazard_type} tone={h.risk_bucket === 'VH' ? 'bad' : h.risk_bucket === 'H' ? 'warn' : 'neutral'}
            label={`${hazardLabel(h.hazard_type)} ${Math.round(h.risk_score ?? 0)} · ${bucketLabel(h.risk_bucket)}`} />)}
          {hz.length === 0 && <span className="text-[11.5px] text-[var(--color-faint)]">No scores yet at this location.</span>}
        </div>)}
    </div>
  )
}
