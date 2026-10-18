import { Link } from 'react-router-dom'
import { ChevronLeft, MessageSquarePlus } from 'lucide-react'
import clsx from 'clsx'
import type { DetailSection } from '../../components/Details'
import { horizonLabel, scenarioLabel } from '../../lib/hazards'

// The supervisor's two checks of one entity's filed template, in customer words (UI standard, 2026-10-16). They were
// 'Tier 1' and 'Tier 2'; the names now say what each is, and every screen that links to them uses the same words.
export const QUICK = 'Quick check'      // the filed template alone, against the range the platform's hazard maps give each region
export const FULL = 'Full rebuild'      // the same template rebuilt from the supervisor's own granular data (the independent lens)

export const TWO_CHECKS: DetailSection = {
  heading: 'Two checks',
  body: `${QUICK}: the filed template alone, each cell's share against the typical range for its country's regions. It needs no data beyond the template. ${FULL}: the same template rebuilt from your own granular data, so every difference can be traced to its cause and its rows.`,
}

// A cell of the template in customer words (the server names both codes: services/supervision/cell_labels.py).
export interface Named { geography_label: string; sector_label: string }
export const cellName = (c: Named) => `${c.geography_label} · ${c.sector_label}`

export const basisText = (scenario?: string | null, horizon?: string | null) => `${scenarioLabel(scenario)} · ${horizonLabel(horizon)}`
export const pct = (v: number | null | undefined) => v == null ? '—' : `${v}%`

const back = 'inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline'
export const BackToEntity = ({ orgId }: { orgId: string }) => <Link to={`/supervised/${orgId}`} className={back}><ChevronLeft size={13} /> Entity file</Link>

// The switch between the two checks of the same entity.
export function CheckSwitch({ orgId, current }: { orgId: string; current: 'quick' | 'full' }) {
  const item = (to: string, label: string, on: boolean) => (
    <Link to={to} aria-current={on ? 'page' : undefined}
      className={clsx('px-3 py-1.5 text-[12.5px] rounded-md transition', on ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>
      {label}
    </Link>)
  return (
    <nav aria-label="Checks of this entity" className="inline-flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
      {item(`/supervised/${orgId}/plausibility`, QUICK, current === 'quick')}
      {item(`/supervised/${orgId}/lens`, FULL, current === 'full')}
    </nav>
  )
}

// Raise a cell with the entity: a new information request, prefilled with the cell and why it stands out.
export function RaiseLink({ orgId, cell, why, short }: { orgId: string; cell: Named & { geography: string; sector: string }; why: string; short?: boolean }) {
  const q = new URLSearchParams({ new: '1', entity: orgId, kind: 'information_request', geography: cell.geography, sector: cell.sector, title: `${cellName(cell)}: ${why}` })
  return (
    <Link to={`/supervisor/requests?${q}`} onClick={e => e.stopPropagation()} aria-label={`Raise ${cellName(cell)} with the entity`}
      className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline whitespace-nowrap">
      <MessageSquarePlus size={13} />{short ? 'Raise' : 'Raise with the entity'}
    </Link>)
}
