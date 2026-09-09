import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { bucketLabel, hazardLabel, horizonLabel, scenarioLabel } from '../lib/hazards'
import { Card, PageHeader, StatGrid } from '../components/ui'

// The independent lens: the submitted template beside the same template rebuilt from the shadow book, cell by
// cell, with every gap split into scope / basis / scoring / unmatched (they add up exactly). A flag is a question.
interface Cell { key: string; geography: string; sector: string; submitted_gross: number | null; submitted_sensitive: number | null
  rebuilt_gross: number | null; rebuilt_sensitive: number | null; submitted_share_pct: number | null; rebuilt_share_pct: number | null
  coverage_pct: number | null; gap: { scope: number; coverage: number; basis: number; scoring: number; unmatched: number }; flag: string; reason: string }
interface Lens { status: string; message?: string; tier: number | null; precision: string; period_label: string; n_cells: number; n_flagged: number
  totals: { submitted: number; rebuilt: number; scope: number; coverage: number; basis: number; scoring: number; unmatched: number }; total_gap: number
  regulator_basis: { scenario: string; horizon: string }; bank_basis: { scenario: string; horizon: string; stated: boolean; method_note: string | null; separable: boolean; note: string | null }
  shadow_book: { n_rows: number; n_located: number; n_scored: number; location_precision: Record<string, number> }; cells: Cell[] }
const eur = (v: number | null | undefined) => v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v) >= 1e9 ? (Math.abs(v) / 1e9).toFixed(2) + 'bn' : Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toFixed(1) + 'm' : (Math.abs(v) / 1e3).toFixed(0) + 'k'}`
const PART: Record<string, { label: string; color: string }> = {
  scope: { label: 'scope', color: '#7F77DD' }, coverage: { label: 'unlocated (unverifiable)', color: '#B4B2A9' }, basis: { label: 'basis', color: '#1D9E75' }, scoring: { label: 'scoring', color: '#D85A30' }, unmatched: { label: 'unmatched', color: '#888780' } }

function GapBar({ gap }: { gap: Cell['gap'] }) {
  const parts = Object.entries(gap).filter(([, v]) => v !== 0)
  const tot = parts.reduce((a, [, v]) => a + Math.abs(v), 0)
  if (!tot) return <span className="mono text-[11px] text-[var(--color-faint)]">no gap</span>
  return (
    <div className="flex h-2.5 w-full rounded overflow-hidden bg-[var(--color-bg-2)]" title={parts.map(([k, v]) => `${PART[k].label} ${eur(v)}`).join(' · ')}>
      {parts.map(([k, v]) => <div key={k} style={{ width: `${100 * Math.abs(v) / tot}%`, background: PART[k].color }} />)}
    </div>)
}

export default function SupervisorLens() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['sup-lens', orgId], queryFn: () => api.get<Lens>(`/v1/supervisor/entity/${orgId}/lens`) })
  const [open, setOpen] = useState<string | null>(null)
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">rebuilding the template independently…</div>
  if (!d) return <div className="h-[60vh] grid place-items-center text-[var(--color-bad)] text-sm">Could not open the lens.</div>
  if (d.status === 'no_submission') return (
    <div className="fadeup space-y-4"><Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <Card className="p-6 text-[13px] text-[var(--color-mute)]">{d.message} <Link to={`/supervised/${orgId}/intake`} className="text-[var(--color-sky)] hover:underline">Go to intake →</Link></Card></div>)
  const t = d.totals
  return (
    <div className="fadeup space-y-6">
      <Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <PageHeader eyebrow={`Independent lens · Tier ${d.tier} · ${d.precision}`} title={`Submitted vs rebuilt · ${d.period_label}`}
        lead={`Your basis ${scenarioLabel(d.regulator_basis.scenario)} · ${horizonLabel(d.regulator_basis.horizon)}${d.bank_basis.stated ? `; the entity states ${scenarioLabel(d.bank_basis.scenario)} · ${horizonLabel(d.bank_basis.horizon)}` : '; the entity stated no basis'}. Rebuilt from ${d.shadow_book.n_rows.toLocaleString()} granular rows, ${d.shadow_book.n_located.toLocaleString()} region-located, ${d.shadow_book.n_scored.toLocaleString()} scored. A flag is a question, not a finding.`} />
      {d.status === 'no_shadow_book' && <Card className="p-4 text-[12.5px] text-[var(--color-warn)]">{d.message}</Card>}
      {d.bank_basis.note && <Card className="p-4 text-[12.5px] text-[var(--color-mute)]">Basis: {d.bank_basis.note}.</Card>}
      <StatGrid cols={4} items={[
        { label: 'Sensitive · submitted', value: eur(t.submitted) },
        { label: 'Sensitive · rebuilt', value: eur(t.rebuilt), sub: `gap ${eur(d.total_gap)}` },
        { label: 'Cells flagged', value: `${d.n_flagged} / ${d.n_cells}`, accent: d.n_flagged ? 'var(--color-warn)' : 'var(--color-good)', sub: '≥ 10 pp share difference or unmatched' },
        { label: 'Gap by reason', value: `${Math.round(100 * Math.abs(t.scoring) / Math.max(1, Math.abs(t.scope) + Math.abs(t.coverage) + Math.abs(t.basis) + Math.abs(t.scoring) + Math.abs(t.unmatched)))}% scoring`, sub: `scope ${eur(t.scope)} · unlocated ${eur(t.coverage)} · basis ${eur(t.basis)} · unmatched ${eur(t.unmatched)}` },
      ]} />
      <Card className="p-5">
        <div className="flex items-center gap-4 mb-3 mono text-[10.5px] text-[var(--color-faint)]">
          {Object.entries(PART).map(([k, p]) => <span key={k} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: p.color }} />{p.label}</span>)}
          <span>· share = sensitive ÷ gross · coverage = rows with a resolved region</span>
        </div>
        <div className="overflow-x-auto">
          <table className="data-table w-full text-[12px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="">Cell</th><th className="num">Submitted gross</th><th className="num">Submitted share</th>
              <th className="num">Rebuilt gross</th><th className="num">Rebuilt share</th><th className="num">Coverage</th>
              <th className="w-40">Gap split</th><th className="">Why it differs</th></tr></thead>
            <tbody>{d.cells.map(c => (<>
              <tr key={c.key} className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] ${open === c.key ? 'bg-[var(--color-bg-2)]' : ''}`} onClick={() => setOpen(open === c.key ? null : c.key)}>
                <td className="text-[var(--color-ink)] whitespace-nowrap"><ChevronRight size={12} className={`inline mr-1 text-[var(--color-faint)] transition-transform ${open === c.key ? 'rotate-90' : ''}`} />{c.geography} · {c.sector}</td>
                <td className="num mono text-[var(--color-mute)]">{eur(c.submitted_gross)}</td>
                <td className="num mono text-[var(--color-mute)]">{c.submitted_share_pct != null ? `${c.submitted_share_pct}%` : '—'}</td>
                <td className="num mono text-[var(--color-mute)]">{eur(c.rebuilt_gross)}</td>
                <td className="num mono" style={{ color: c.flag === 'question' ? 'var(--color-warn)' : 'var(--color-mute)' }}>{c.rebuilt_share_pct != null ? `${c.rebuilt_share_pct}%` : '—'}</td>
                <td className="num mono text-[var(--color-faint)]">{c.coverage_pct != null ? `${c.coverage_pct}%` : '—'}</td>
                <td><GapBar gap={c.gap} /></td>
                <td className="text-[11.5px] text-[var(--color-mute)]">{c.flag === 'question' ? <>{c.reason} <Link onClick={e => e.stopPropagation()} to={`/supervisor/requests?new=1&entity=${orgId}&kind=information_request&geography=${encodeURIComponent(c.geography)}&sector=${encodeURIComponent(c.sector)}&title=${encodeURIComponent(`${c.geography} · ${c.sector}: ${c.reason}`)}`} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">raise with the entity →</Link></> : <span className="text-[var(--color-faint)]">within tolerance</span>}</td>
              </tr>
              {open === c.key && <tr key={c.key + '-drill'}><td colSpan={8} className="p-0"><CellDrill orgId={orgId} geography={c.geography} sector={c.sector} /></td></tr>}
            </>))}</tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}


// ── Drill-down: the submitted figure, every granular row behind the rebuilt one, the arithmetic, and per row
//    the hazard scores at its location. Nothing here is summarised away — this is the data set behind the number.
interface CellRow { instrument_id: string | null; name: string; outstanding_eur: number; collateral_country: string | null; region: string | null
  location_precision: string | null; lat: number | null; lon: number | null; nace_code: string | null; headline_hazard: string | null; headline_score: number | null; bucket: string | null; counts_as_sensitive: boolean }
interface CellResp { cell: { geography: string; sector: string }; scenario: string; horizon: string
  submitted: { gross_carrying_amount_eur: number; sensitive_physical_eur: number; period_label: string; source_file: string | null; basis?: { scenario?: string; horizon?: string; method_note?: string } } | null
  rebuilt: { rows: CellRow[]; submitted_share_pct: number | null; rebuilt_share_pct: number | null; located_value_eur: number; unlocated_value_eur: number; n_rows: number; n_located: number; n_sensitive: number; rule: string } }
interface Lookup { hazards: { hazard_type: string; status: string; risk_score: number | null; risk_bucket: string | null; reason?: string | null }[] }

function CellDrill({ orgId, geography, sector }: { orgId: string; geography: string; sector: string }) {
  const q = useQuery({ queryKey: ['sup-lens-cell', orgId, geography, sector], queryFn: () => api.get<CellResp>(`/v1/supervisor/entity/${orgId}/lens/cell?geography=${encodeURIComponent(geography)}&sector=${encodeURIComponent(sector)}`) })
  const [row, setRow] = useState<CellRow | null>(null)
  const d = q.data
  if (q.isLoading) return <div className="p-4 text-[12px] text-[var(--color-faint)]">opening the rows behind this cell…</div>
  if (!d) return <div className="p-4 text-[12px] text-[var(--color-bad)]">Could not open this cell.</div>
  const r = d.rebuilt
  return (
    <div className="p-4 border-t border-[var(--color-line)] bg-[var(--color-bg-2)] grid lg:grid-cols-[280px_1fr] gap-5">
      <div className="space-y-3">
        <div>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">As submitted by the entity</div>
          {d.submitted ? (
            <div className="text-[12.5px] text-[var(--color-ink)] space-y-0.5">
              <div>Gross carrying amount <b>{eur(d.submitted.gross_carrying_amount_eur)}</b></div>
              <div>Of which sensitive <b>{eur(d.submitted.sensitive_physical_eur)}</b> · {r.submitted_share_pct}%</div>
              <div className="mono text-[10.5px] text-[var(--color-faint)]">{d.submitted.period_label}{d.submitted.source_file ? ` · ${d.submitted.source_file}` : ''}{d.submitted.basis?.scenario ? ` · stated ${scenarioLabel(d.submitted.basis.scenario)} · ${horizonLabel(d.submitted.basis.horizon)}` : ''}</div>
              {d.submitted.basis?.method_note && <div className="text-[11px] text-[var(--color-mute)] italic">“{d.submitted.basis.method_note}”</div>}
            </div>) : <div className="text-[12px] text-[var(--color-faint)]">Not present in the submitted template.</div>}
        </div>
        <div>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">As rebuilt from your granular data · {scenarioLabel(d.scenario)} · {horizonLabel(d.horizon)}</div>
          <div className="text-[12.5px] text-[var(--color-ink)] space-y-0.5">
            <div>{r.n_rows} rows · {r.n_located} located · {r.n_sensitive} count as sensitive</div>
            <div>Located value <b>{eur(r.located_value_eur)}</b> · unlocated <b>{eur(r.unlocated_value_eur)}</b></div>
            <div>Rebuilt share <b>{r.rebuilt_share_pct != null ? `${r.rebuilt_share_pct}%` : '—'}</b> (sensitive ÷ located)</div>
          </div>
          <div className="text-[11px] text-[var(--color-mute)] mt-1">{r.rule}</div>
        </div>
      </div>
      <div className="min-w-0">
        <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">The rows · click one for the hazard scores at its location</div>
        <div className="overflow-x-auto max-h-[360px] overflow-y-auto border border-[var(--color-line)] rounded-lg">
          <table className="data-table w-full text-[11.5px]">
            <thead className="sticky top-0 bg-[var(--color-panel)]"><tr className="text-[var(--color-faint)] mono text-[9.5px] uppercase tracking-wide text-left">
              <th className="py-1.5 px-2">Instrument</th><th className="pr-2">Counterparty</th><th className="pr-2 text-right">Outstanding</th>
              <th className="pr-2">Collateral region</th><th className="pr-2">Precision</th><th className="pr-2">Headline hazard</th><th className="pr-2 text-right">Score</th><th className="pr-2">Sensitive</th></tr></thead>
            <tbody>{r.rows.map((x, i) => (
              <tr key={i} onClick={() => x.lat != null && setRow(row === x ? null : x)} className={`border-t border-[var(--color-line)] ${x.lat != null ? 'cursor-pointer hover:bg-[var(--color-panel)]' : 'opacity-60'} ${row === x ? 'bg-[var(--color-panel)]' : ''}`}>
                <td className="py-1 px-2 mono text-[var(--color-mute)]">{x.instrument_id ?? '—'}</td>
                <td className="pr-2 text-[var(--color-ink)]">{x.name}</td>
                <td className="pr-2 text-right mono">{eur(x.outstanding_eur)}</td>
                <td className="pr-2 text-[var(--color-mute)]">{x.region ?? (x.collateral_country ? `${x.collateral_country} (country only)` : '—')}</td>
                <td className="pr-2 mono text-[10.5px] text-[var(--color-faint)]">{x.location_precision === 'unlocated' ? 'unlocated' : x.location_precision?.replace('→', ' → ') ?? '—'}</td>
                <td className="pr-2 text-[var(--color-mute)]">{x.headline_hazard ? hazardLabel(x.headline_hazard) : '—'}</td>
                <td className="pr-2 text-right mono" style={{ color: x.counts_as_sensitive ? 'var(--color-bad)' : 'var(--color-mute)' }}>{x.headline_score != null ? `${Math.round(x.headline_score)} · ${bucketLabel(x.bucket)}` : '—'}</td>
                <td className="pr-2">{x.counts_as_sensitive ? <span className="mono text-[10px] text-[var(--color-bad)]">yes</span> : x.lat == null ? <span className="mono text-[10px] text-[var(--color-faint)]">unverifiable</span> : <span className="mono text-[10px] text-[var(--color-faint)]">no</span>}</td>
              </tr>))}</tbody>
          </table>
        </div>
        {row && row.lat != null && <RowHazards row={row} />}
      </div>
    </div>)
}

function RowHazards({ row }: { row: CellRow }) {
  const q = useQuery({ queryKey: ['lookup', row.lat, row.lon], queryFn: () => api.get<Lookup>(`/v1/lookup/score?lat=${row.lat}&lon=${row.lon}`) })
  const hz = (q.data?.hazards ?? []).filter(h => h.risk_score != null).sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
  return (
    <div className="mt-3 p-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)]">
      <div className="text-[12px] text-[var(--color-ink)] mb-1"><b>{row.name}</b> · {row.region ?? row.collateral_country} · location resolved at {row.location_precision === 'nuts3' ? 'NUTS-3 region level' : row.location_precision === 'postcode→nuts3' ? 'postcode → NUTS-3 region level' : row.location_precision} — every hazard scored at that point:</div>
      {q.isLoading ? <div className="text-[11.5px] text-[var(--color-faint)]">scoring…</div> : (
        <div className="flex flex-wrap gap-1.5">{hz.map(h => (
          <span key={h.hazard_type} className="mono text-[10.5px] px-1.5 py-0.5 rounded border border-[var(--color-line)]" style={{ color: (h.risk_bucket === 'H' || h.risk_bucket === 'VH') ? 'var(--color-bad)' : 'var(--color-mute)' }}>
            {hazardLabel(h.hazard_type)} {Math.round(h.risk_score ?? 0)} · {bucketLabel(h.risk_bucket)}</span>))}
          {hz.length === 0 && <span className="text-[11.5px] text-[var(--color-faint)]">no scores yet at this location</span>}</div>)}
      <div className="mono text-[10px] text-[var(--color-faint)] mt-1">headline = highest of these (today's basis); the cell's sensitivity uses the headline under the lens basis</div>
    </div>)
}
