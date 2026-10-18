import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, Hourglass, Zap } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../../lib/auth'
import { Drawer } from '../../components/Drawer'
import { CloseButton } from '../../components/Dialog'
import { Button } from '../../components/ui'
import { DetailsBody, InfoButton, messageDetails, type DetailSection, type Message } from '../../components/Details'

// One hazard of the coverage page, to the UI standard (2026-10-16): its source, where it is validated, how it was
// tested, how it is carried to future years and its limits, all in the server's catalogue words (coverage.*).

export type Tier = 'calibrated' | 'by_nature' | 'screening' | 'reference' | 'roadmap'
export type RegionStatus = 'validated' | 'mixed' | 'fails' | 'untested'
export interface Projection { channel: string; label: string; projects: boolean; band: boolean; mode: string | null; mode_message: Message | null; message: Message }
export interface RegionEv { region: string; status: RegionStatus; message: Message | null }
export interface Hazard {
  id: string; name: string; label: string; family: string; nature: 'acute' | 'chronic'; tier: Tier; phase: string; internal: string[]
  message: Message; indicator: Message | null; projection: Projection[]; scope?: { claim: string; message: Message; regions: RegionEv[] }
}
export interface Coverage {
  counts: { total: number; covered: number; roadmap: number; by_tier: Record<Tier, number>; extra_channels: number; scope_claims: Record<string, number> }
  tiers: ({ tier: Tier } & Message)[]
  families: { family: string; label: string; hazards: Hazard[] }[]
  extra_label: string; extra_channels: Hazard[]
  regions: { region: string; label: string }[]
  region_statuses: { status: RegionStatus; label: string }[]
}

export const TIER_C: Record<Tier, string> = {
  calibrated: 'var(--color-good)', by_nature: 'var(--color-sky)', screening: 'var(--color-warn)', reference: 'var(--color-blue)', roadmap: 'var(--color-slate)',
}
const REGION_C: Record<RegionStatus, string> = {
  validated: 'var(--color-good)', mixed: 'var(--color-warn)', fails: 'var(--color-bad)', untested: 'var(--color-slate)',
}
// the six world regions as a tile map, roughly where they lie
const GEO = [['north_america', 'europe', 'asia'], ['latin_america_caribbean', 'africa', 'oceania']]
// a validated hazard links to where this organisation sees it on its own book; regulators have no book of their own
const BOOK_ROUTE: Record<string, string> = {
  bank: '/portfolio', insurer: '/portfolio', asset_manager: '/portfolio', reit: '/portfolio', manufacturer: '/cogs',
}

export function Chip({ color, children, className }: { color: string; children: ReactNode; className?: string }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 text-[11.5px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap', className)}
      style={{ color, background: `color-mix(in oklab, ${color} 14%, transparent)` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: color }} />{children}
    </span>
  )
}

// acute: a sudden event; chronic: a slow change
export function NatureMark({ nature, withLabel }: { nature: 'acute' | 'chronic'; withLabel?: boolean }) {
  const acute = nature === 'acute'
  const Icon = acute ? Zap : Hourglass
  const word = acute ? 'Acute' : 'Chronic'
  return (
    <span title={word} aria-label={withLabel ? undefined : word} className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)]">
      <Icon size={12} className={acute ? 'text-[var(--color-warn)]' : 'text-[var(--color-sky)]'} />{withLabel && word}
    </span>
  )
}

// six small squares, in the tile map's order: where a validated hazard holds
export function RegionStrip({ h, names }: { h: Hazard; names: Record<string, string> }) {
  if (!h.scope) return null
  const by = Object.fromEntries(h.scope.regions.map(r => [r.region, r.status]))
  const held = h.scope.regions.filter(r => r.status === 'validated').map(r => names[r.region])
  return (
    <span className="inline-grid grid-cols-3 gap-[2px]" role="img" aria-label={held.length ? `Validated in ${held.join(', ')}` : 'No region validated'}>
      {GEO.flat().map(r => <span key={r} className="w-[5px] h-[5px] rounded-[1px]" style={{ background: REGION_C[(by[r] ?? 'untested') as RegionStatus], opacity: by[r] && by[r] !== 'untested' ? 1 : 0.35 }} />)}
    </span>
  )
}

function RegionMap({ h, cov, selected, onSelect }: { h: Hazard; cov: Coverage; selected: string | null; onSelect: (r: string) => void }) {
  const names = Object.fromEntries(cov.regions.map(r => [r.region, r.label]))
  const statusName = Object.fromEntries(cov.region_statuses.map(s => [s.status, s.label]))
  const by = Object.fromEntries((h.scope?.regions ?? []).map(r => [r.region, r]))
  return (
    <div className="grid grid-cols-3 gap-1.5">
      {GEO.flat().map(r => {
        const st = (by[r]?.status ?? 'untested') as RegionStatus
        const c = REGION_C[st]
        return (
          <button key={r} type="button" onClick={() => onSelect(r)} aria-pressed={selected === r}
            className={clsx('rounded-lg border px-2 py-2 text-left transition', selected === r ? 'ring-2 ring-[var(--color-sky)]' : 'hover:border-[var(--color-sky)]')}
            style={{ borderColor: `color-mix(in oklab, ${c} 45%, transparent)`, background: `color-mix(in oklab, ${c} ${st === 'untested' ? 5 : 14}%, transparent)` }}>
            <div className="text-[11.5px] font-medium text-[var(--color-ink)] leading-tight">{names[r]}</div>
            <div className="text-[10.5px] mt-0.5" style={{ color: st === 'untested' ? 'var(--color-faint)' : c }}>{statusName[st]}</div>
          </button>
        )
      })}
    </div>
  )
}

function ProjectionHead({ p }: { p: Projection }) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {p.mode_message && <span className="inline-flex items-center gap-1"><Chip color={p.projects ? 'var(--color-sky)' : 'var(--color-slate)'}>{p.mode_message.label}</Chip><InfoButton compact details={messageDetails(p.mode_message)} /></span>}
        {p.band && <Chip color="var(--color-good)">Carries a model spread</Chip>}
      </div>
      <div className="font-medium">{p.message.label}</div>
      {p.message.detail?.what && <p className="m-0 text-[var(--color-mute)]">{p.message.detail.what}</p>}
    </div>
  )
}

function projectionSections(h: Hazard): DetailSection[] {
  return h.projection.flatMap(p => {
    const of = h.projection.length > 1 ? ` · ${p.label}` : ''
    const d = p.message.detail ?? {}
    return [
      { heading: `In future years${of}`, body: <ProjectionHead p={p} /> },
      ...(d.why ? [{ heading: `Projection basis${of}`, body: d.why }] : []),
      ...(d.next ? [{ heading: `Not projected${of}`, body: d.next }] : []),
    ]
  })
}

export function HazardDrawer({ h, cov, onClose }: { h: Hazard; cov: Coverage; onClose: () => void }) {
  const nav = useNavigate()
  const { profile } = useAuth()
  const [region, setRegion] = useState<string | null>(h.scope?.regions.find(r => r.message)?.region ?? null)
  const names = Object.fromEntries(cov.regions.map(r => [r.region, r.label]))
  const statusName = Object.fromEntries(cov.region_statuses.map(s => [s.status, s.label]))
  const tier = cov.tiers.find(t => t.tier === h.tier)
  const sel = h.scope?.regions.find(r => r.region === region)
  const d = h.message.detail ?? {}
  // a book is filtered by one hazard channel: only offer the link when the checklist item maps to exactly one
  const single = h.internal.length === 1 ? h.internal[0] : null
  const book = h.tier === 'calibrated' && single ? BOOK_ROUTE[profile?.org?.type ?? ''] : undefined
  return (
    <Drawer label={h.label} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            {tier && <span className="inline-flex items-center gap-1"><Chip color={TIER_C[h.tier]}>{tier.label}</Chip><InfoButton compact details={messageDetails(tier)} /></span>}
            {h.indicator && <span className="inline-flex items-center gap-1"><Chip color="var(--color-slate)">{h.indicator.label}</Chip><InfoButton compact details={messageDetails(h.indicator)} /></span>}
            <NatureMark nature={h.nature} withLabel />
          </div>
          <div className="text-[18px] font-semibold text-[var(--color-ink)] leading-snug">{h.label}</div>
          {h.name !== h.label && <div className="text-[12px] text-[var(--color-mute)] mt-0.5">EU Taxonomy: {h.name}</div>}
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="mt-4 flex justify-between gap-4 py-2 border-y border-[var(--color-line)] text-[12.5px]">
        <span className="text-[var(--color-mute)]">Source</span><span className="text-right text-[var(--color-ink)]">{h.message.label}</span>
      </div>
      <div className="mt-5">
        <DetailsBody sections={[
          ...(d.what ? [{ heading: 'What it measures', body: d.what }] : []),
          ...(h.scope ? [{ heading: 'Where it is validated', body: (
            <>
              <div className="flex items-center gap-1 mb-2"><Chip color={h.scope.claim === 'none' ? 'var(--color-slate)' : 'var(--color-good)'}>{h.scope.message.label}</Chip><InfoButton compact details={messageDetails(h.scope.message)} /></div>
              <RegionMap h={h} cov={cov} selected={region} onSelect={setRegion} />
              {sel && (
                <div className="mt-2 rounded-lg border border-[var(--color-line-2)] p-3 text-[12.5px]">
                  <div className="text-[var(--color-mute)]">{names[sel.region]} · {statusName[sel.status]}</div>
                  {sel.message ? <><div className="font-medium text-[var(--color-ink)] mt-0.5">{sel.message.label}</div>
                    <div className="text-[var(--color-mute)] mt-0.5">{sel.message.detail?.what}</div></>
                    : <div className="text-[var(--color-faint)] mt-0.5">Not tested in this region.</div>}
                </div>
              )}
            </>
          ) }] : []),
          ...(d.why ? [{ heading: h.tier === 'calibrated' || h.tier === 'screening' ? 'How it was tested' : 'Why there is no test', body: d.why }] : []),
          ...projectionSections(h),
          ...(d.next ? [{ heading: 'Limits', body: d.next }] : []),
        ]} />
      </div>
      {book && <div className="mt-6"><Button onClick={() => nav(`${book}?hazard=${single}&horizon=current`)}>See it on your book<ArrowRight size={14} className="inline -mt-0.5 ml-1" /></Button></div>}
    </Drawer>
  )
}
