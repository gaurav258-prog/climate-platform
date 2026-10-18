import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Scale, Split } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { money } from '../lib/money'
import { Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { HBar } from '../components/Charts'
import { Dialog } from '../components/Dialog'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine, type Message } from '../components/Details'
import MethodGap from '../components/MethodGap'
import { BackToEntity, CheckSwitch, FULL, TWO_CHECKS, basisText, cellName, type Named } from './supervisorAnalysis/checks'
import { CellDrawer, PART, PARTS, signed, type Part } from './supervisorAnalysis/LensCell'

// The full rebuild (the independent lens), to the UI standard (2026-10-16): the entity's filed template beside the
// same template rebuilt from the supervisor's own granular data. The main screen is the totals, the filed-versus-rebuilt
// bars per cell and the causes of the difference; a cell's rows and arithmetic open in a side drawer, every
// explanation one click away in the server's catalogue words.
export interface Cell extends Named {
  key: string; geography: string; sector: string; submitted_gross: number | null; submitted_sensitive: number | null
  rebuilt_gross: number | null; rebuilt_sensitive: number | null; submitted_share_pct: number | null; rebuilt_share_pct: number | null
  coverage_pct: number | null; gap: Record<Part, number>; flag: 'ok' | 'question'; reason: Message | null
}
export interface Lens {
  status: 'ok' | 'no_shadow_book' | 'gap' | 'no_submission'; entity_name: string | null; gap?: string; message?: Message | null
  precision: string; period_label: string; n_cells: number; n_flagged: number; flag_pp: number
  totals: Record<'submitted' | 'rebuilt' | Part, number>; total_gap: number
  regulator_basis: { scenario: string; horizon: string }
  bank_basis: { scenario: string; horizon: string; stated: boolean; method_note: string | null; message: Message | null }
  at_risk_level: { regulator: number; entity: number | null; message: Message | null }
  shadow_book: { n_rows: number; n_located: number; n_scored: number }; cells: Cell[]
}

const ABOUT = [
  { heading: HEADING.shows, body: 'The template the entity filed, cell by cell, beside the same template rebuilt from your granular data with the platform’s hazard scores, at your scenario, year and at-risk threshold.' },
  { heading: HEADING.read, body: 'Each difference between the rebuilt and the filed amount is split into its causes: a different exposure, exposure that could not be located, a different basis, a different risk assessment, or a cell on one side only. The parts add up to the whole difference. A marked cell is a question for the entity, not a finding.' },
  TWO_CHECKS,
  { heading: HEADING.sources, body: 'The template, as filed. Your granular data, located by the region code, postcode or coordinates each row carries. Hazard scores from the platform’s engine, the same one the entity’s own workspace uses.' },
  { heading: HEADING.limits, body: 'Locations are resolved to a region (NUTS-3), not to an address. A row without a usable location cannot be scored: it is counted and shown apart, never placed at a country’s centre.' },
]
const TOP = 12

export default function SupervisorLens() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['sup-lens', orgId], queryFn: () => api.get<Lens>(`/v1/supervisor/entity/${orgId}/lens`) })
  const [open, setOpen] = useState<Cell | null>(null)
  const [part, setPart] = useState<Part | null>(null)
  const [all, setAll] = useState(false)
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">Rebuilding the template…</div>
  const header = (
    <PageHeader eyebrow={FULL} title={d?.entity_name ?? 'Supervised entity'} lead="Filed figures against the same template rebuilt from your granular data."
      about={ABOUT} actions={<CheckSwitch orgId={orgId} current="full" />}>
      {d?.status === 'ok' || d?.status === 'no_shadow_book' ? <Basis d={d} /> : null}
    </PageHeader>)
  if (!d) return <Shell orgId={orgId} header={header}><Card className="p-6 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'The full rebuild could not be opened.')}</Card></Shell>
  if (d.status === 'gap') return <Shell orgId={orgId} header={header}><MethodGap gap={d.gap} what={FULL} /></Shell>
  if (d.status === 'no_submission') return (
    <Shell orgId={orgId} header={header}>
      <Card className="p-6 flex flex-wrap items-center gap-4 text-[13.5px]">
        {d.message && <MessageLine m={d.message} className="text-[var(--color-ink)]" />}
        <Link to={`/supervised/${orgId}/intake`} className="text-[12.5px] text-[var(--color-sky)] hover:underline">Open Intake</Link>
      </Card>
    </Shell>)
  const t = d.totals
  const notices = [d.status === 'no_shadow_book' ? d.message : null, d.bank_basis.message, d.at_risk_level.message].filter((m): m is Message => !!m)
  const cells = all ? d.cells : d.cells.slice(0, TOP)
  const scale = Math.max(1, ...d.cells.map(c => Math.max(c.submitted_sensitive ?? 0, c.rebuilt_sensitive ?? 0)))
  const parts = PARTS.filter(p => t[p]).map(p => ({ label: PART[p].label, value: t[p], color: PART[p].color }))
  return (
    <Shell orgId={orgId} header={header}>
      {notices.length > 0 && (
        <Card className="px-4 py-3 space-y-1.5 border-[var(--color-warn)]/40">
          {notices.map(m => <div key={m.code} className="flex flex-wrap items-center gap-3 text-[12.5px] text-[var(--color-warn)]">
            <MessageLine m={m} />
            {m.code !== 'supervision.lens.entity_level_missing' && <Link to={`/supervised/${orgId}/intake`} className="text-[var(--color-sky)] hover:underline">Open Intake</Link>}
          </div>)}
        </Card>)}
      <StatGrid cols={4} items={[
        { label: 'Filed as sensitive', value: money(t.submitted, 'EUR'), sub: d.period_label },
        { label: 'Rebuilt as sensitive', value: money(t.rebuilt, 'EUR'), sub: `${d.shadow_book.n_rows.toLocaleString()} rows of your data` },
        { label: 'Difference', value: signed(d.total_gap), sub: t.submitted ? `${d.total_gap >= 0 ? '+' : '−'}${Math.abs(Math.round(100 * d.total_gap / t.submitted))}% of the filed amount` : undefined, accent: d.total_gap ? 'var(--color-warn)' : undefined },
        { label: 'Cells to raise', value: `${d.n_flagged} of ${d.n_cells}`, accent: d.n_flagged ? 'var(--color-warn)' : 'var(--color-good)' },
      ]} />
      <div className="grid gap-6 lg:grid-cols-[3fr_2fr] items-start">
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
            <SectionHead icon={Scale}>Filed against rebuilt</SectionHead>
            <InfoButton compact details={{ title: 'Filed against rebuilt', sections: [
              { heading: HEADING.read, body: `Each row is one cell of the template: the amount the entity filed as sensitive to physical risk, and the amount rebuilt from your granular data. A cell is marked when the two shares differ by ${d.flag_pp} percentage points or more, or when it appears on one side only. Select a cell for its rows and arithmetic.` },
            ] }} />
            <span className="ml-auto inline-flex items-center gap-3 text-[11.5px] text-[var(--color-mute)]">
              <Swatch color="var(--color-slate)" label="Filed" /><Swatch color="var(--color-sky)" label="Rebuilt" />
            </span>
          </div>
          <div className="space-y-1">
            {cells.map(c => <CellRow key={c.key} c={c} scale={scale} onOpen={() => setOpen(c)} />)}
          </div>
          {d.cells.length > TOP && (
            <button type="button" onClick={() => setAll(!all)} className="mt-3 text-[12px] text-[var(--color-sky)] hover:underline">
              {all ? `Show the ${TOP} largest differences` : `Show all ${d.cells.length} cells`}
            </button>)}
        </Card>
        <Card className="p-5">
          <div className="flex items-center gap-2 mb-4">
            <SectionHead icon={Split}>Why the figures differ</SectionHead>
            <InfoButton compact details={{ title: 'Why the figures differ', sections: [
              { heading: HEADING.read, body: 'How much of the difference between the rebuilt and the filed amount comes from each cause, across all cells. The parts add up to the whole difference. A positive amount means the rebuild finds more sensitive exposure than the entity filed. Select a cause for what it means and where it weighs most.' },
            ] }} />
          </div>
          {parts.length ? <HBar data={parts} format={signed} labelWidth="w-44" onBar={i => setPart(PARTS.filter(p => t[p])[i])} />
            : <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">The rebuilt and the filed amounts agree.</div>}
        </Card>
      </div>
      {part && <PartDialog part={part} cells={d.cells} onClose={() => setPart(null)} onCell={c => { setPart(null); setOpen(c) }} />}
      {open && <CellDrawer orgId={orgId} cell={open} lens={d} onClose={() => setOpen(null)} />}
    </Shell>
  )
}

function Shell({ orgId, header, children }: { orgId: string; header: React.ReactNode; children: React.ReactNode }) {
  return <div className="fadeup space-y-6"><BackToEntity orgId={orgId} />{header}{children}</div>
}

const Swatch = ({ color, label }: { color: string; label: string }) => <span className="inline-flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />{label}</span>

// The basis each side is read at: yours (the rebuild) and the one the entity states (its template).
function Basis({ d }: { d: Lens }) {
  const lvl = d.at_risk_level
  return (
    <div className="flex flex-wrap gap-1.5 mt-3">
      <StatusChip tone="neutral" label={`Your basis · ${basisText(d.regulator_basis.scenario, d.regulator_basis.horizon)} · threshold ${lvl.regulator}`} />
      <StatusChip tone={d.bank_basis.stated && lvl.entity != null ? 'neutral' : 'warn'}
        label={`Entity’s basis · ${d.bank_basis.stated ? basisText(d.bank_basis.scenario, d.bank_basis.horizon) : 'not stated'} · threshold ${lvl.entity ?? 'not stated'}`} />
    </div>
  )
}

function CellRow({ c, scale, onOpen }: { c: Cell; scale: number; onOpen: () => void }) {
  const w = (v: number | null) => `${v ? Math.max(0.8, (v / scale) * 100) : 0}%`
  const name = cellName(c)
  return (
    <button type="button" onClick={onOpen} aria-label={`${name}: open its rows`}
      className="w-full grid grid-cols-[minmax(0,11rem)_1fr_auto] sm:grid-cols-[minmax(0,14rem)_1fr_auto] items-center gap-3 px-2 py-1.5 rounded-md text-left hover:bg-[var(--color-panel-2)] transition">
      <span className="text-[12.5px] text-[var(--color-ink)] truncate" title={name}>{name}</span>
      <span className="space-y-[3px]" title={`Filed ${money(c.submitted_sensitive, 'EUR')} · rebuilt ${money(c.rebuilt_sensitive, 'EUR')}`}>
        <span className="block h-2 rounded-full bg-[var(--color-panel-2)]"><span className="block h-full rounded-full bg-[var(--color-slate)]" style={{ width: w(c.submitted_sensitive) }} /></span>
        <span className="block h-2 rounded-full bg-[var(--color-panel-2)]"><span className="block h-full rounded-full bg-[var(--color-sky)]" style={{ width: w(c.rebuilt_sensitive) }} /></span>
      </span>
      <span className="justify-self-end">{c.flag === 'question' && c.reason ? <StatusChip tone="warn" label={c.reason.label} /> : null}</span>
    </button>
  )
}

function PartDialog({ part, cells, onClose, onCell }: { part: Part; cells: Cell[]; onClose: () => void; onCell: (c: Cell) => void }) {
  const top = cells.filter(c => c.gap[part]).sort((a, b) => Math.abs(b.gap[part]) - Math.abs(a.gap[part])).slice(0, 6)
  return (
    <Dialog title={PART[part].label} onClose={onClose} className="max-w-xl">
      <p className="text-[13.5px] leading-relaxed text-[var(--color-ink)] m-0">{PART[part].what}</p>
      {top.length > 0 && <>
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-5 mb-2">Where it weighs most</h4>
        <div className="space-y-1">
          {top.map(c => (
            <button key={c.key} type="button" onClick={() => onCell(c)} className="w-full flex items-center justify-between gap-3 px-2 py-1.5 rounded-md text-left text-[12.5px] hover:bg-[var(--color-panel-2)]">
              <span className="truncate text-[var(--color-ink)]">{cellName(c)}</span><span className="tabular-nums text-[var(--color-mute)]">{signed(c.gap[part])}</span>
            </button>))}
        </div>
      </>}
    </Dialog>
  )
}
