import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { PageHeader, Card, StatGrid, SectionHead, PlainLead } from '../components/ui'
import ReviewTabs from '../components/ReviewTabs'

// The honesty triangle — three auditable registries a supervisor can read straight:
//   • Hazard coverage    (/v1/meta/hazard-coverage)     — do we score it? (EU Taxonomy's 28, by maturity tier)
//   • Projection posture (/v1/meta/projection-coverage) — how do we carry it to 2030/2050/2100?
//   • Model limitations  (/v1/meta/model-limitations)   — what don't we model, and why?
// All static registries (no tenant data); the load-bearing point is that coverage ≠ calibration and a gap is
// named, never hidden.

type Tier = 'calibrated' | 'screening' | 'reference' | 'roadmap'
interface HZ { id: string; name: string; family: string; nature: string; tier: Tier; phase: string; source: string; internal: string[] }
interface Fam { family: string; label: string; hazards: HZ[] }
interface Summary { total: number; covered: number; roadmap: number; by_tier: Record<string, number>; by_phase: Record<string, number>; extra_channels: number }
interface Cov {
  reference: string; summary: Summary; families: Fam[]; extra_channels: HZ[]
  tiers: { tier: string; label: string; note: string }[]; note: string
}

interface ProjItem { hazard: string; projects: boolean; mode: string; mode_label: string; mechanism: string; basis: string; band: boolean; gaps: string[] }
interface Proj {
  version: string; projection_engine_version: string; scenarios: string[]; horizons: string[]
  n_hazards: number; n_projected: number; n_flat_by_design: number; n_with_band: number; items: ProjItem[]; note: string
}

type LimStatus = 'tested_rejected' | 'deferred_needs_data' | 'disclosed_scope'
interface LimItem { id: string; area: string; status: LimStatus; status_label: string; title: string; summary: string; evidence: string; current_treatment: string; unlock: string }
interface Lim {
  version: string; n_limitations: number; counts: Record<LimStatus, number>
  statuses: { status: LimStatus; label: string }[]; items: LimItem[]; note: string
}

const TIER: Record<Tier, { c: string; label: string }> = {
  calibrated: { c: 'var(--color-good)', label: 'Calibrated' },
  screening: { c: 'var(--color-warn)', label: 'Screening' },
  reference: { c: 'var(--color-sky)', label: 'Reference' },
  roadmap: { c: 'var(--color-slate)', label: 'Roadmap' },
}
const LIM_C: Record<LimStatus, string> = {
  tested_rejected: 'var(--color-warn)', deferred_needs_data: 'var(--color-sky)', disclosed_scope: 'var(--color-slate)',
}

function chip(color: string, text: string) {
  return (
    <span className="mono text-[10px] font-semibold px-2 py-1 rounded-full whitespace-nowrap"
      style={{ color, background: `color-mix(in oklab, ${color} 15%, transparent)` }}>{text}</span>
  )
}

function Badge({ h }: { h: HZ }) {
  if (h.phase === 'now') { const t = TIER[h.tier]; return chip(t.c, t.label) }
  return chip(TIER.roadmap.c, `Phase ${h.phase.slice(1)}`)
}

function HazardTile({ h }: { h: HZ }) {
  const acute = h.nature === 'acute'
  return (
    <div className="rounded-lg border px-3.5 py-3 flex items-start gap-2.5"
      style={{ borderColor: h.phase === 'now' ? TIER[h.tier].c + '44' : 'var(--color-line-2)' }}>
      <span title={h.nature} className="mono text-[9px] font-semibold mt-0.5 rounded px-1.5 py-0.5 shrink-0"
        style={{ color: acute ? 'var(--color-warn)' : 'var(--color-sky)', background: `color-mix(in oklab, ${acute ? 'var(--color-warn)' : 'var(--color-sky)'} 12%, transparent)` }}>
        {acute ? 'A' : 'C'}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium text-[var(--color-ink)] leading-snug">{h.name}</div>
        <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5 leading-snug">{h.source}</div>
      </div>
      <div className="shrink-0"><Badge h={h} /></div>
    </div>
  )
}

// ── view 1: hazard coverage (unchanged content) ──────────────────────────────────────────────────
function CoverageView() {
  const { data, isLoading, error } = useQuery({ queryKey: ['hazard-coverage'], queryFn: () => api.get<Cov>('/v1/meta/hazard-coverage') })
  if (isLoading) return <div className="mono text-[13px] text-[var(--color-faint)]">loading…</div>
  if (error || !data) return <div className="mono text-[13px] text-[var(--color-bad)]">could not load coverage</div>
  return (
    <>
      <StatGrid cols={4} items={[
        { label: 'EU Taxonomy hazards', value: data.summary.total },
        { label: 'Covered today', value: data.summary.covered, accent: 'var(--color-good)', sub: `${data.summary.by_tier.calibrated} calibrated · ${data.summary.by_tier.screening} screening` },
        { label: 'On the roadmap', value: data.summary.roadmap, sub: 'across 4 phases' },
        { label: 'Beyond the 28', value: `+${data.summary.extra_channels}`, sub: 'seismic · volcanic · pollution' },
      ]} />
      <Card className="p-5">
        <SectionHead>How to read the tiers</SectionHead>
        <PlainLead className="mt-1 mb-3">{data.note}</PlainLead>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {data.tiers.map(t => (
            <div key={t.tier} className="rounded-lg border border-[var(--color-line-2)] px-3.5 py-3">
              <div className="mb-1.5">{chip(TIER[t.tier as Tier].c, t.label)}</div>
              <div className="text-[12px] text-[var(--color-mute)] leading-snug">{t.note}</div>
            </div>
          ))}
        </div>
      </Card>
      {data.families.map(f => (
        <div key={f.family} className="space-y-3">
          <SectionHead hint={`${f.hazards.length} hazards`}>{f.label}</SectionHead>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{f.hazards.map(h => <HazardTile key={h.id} h={h} />)}</div>
        </div>
      ))}
      <div className="space-y-3">
        <SectionHead hint="not on the EU climate list — geophysical / nature">Beyond the 28</SectionHead>
        <PlainLead>Channels we carry that sit outside Appendix A — coverage we hold in addition to the EU climate hazards.</PlainLead>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">{data.extra_channels.map(h => <HazardTile key={h.id} h={h} />)}</div>
      </div>
      <p className="mono text-[11px] text-[var(--color-faint)]">Reference: {data.reference}</p>
    </>
  )
}

const HAZ_LABEL: Record<string, string> = {
  flood: 'Flooding', storm: 'Storms & wind', wildfire: 'Wildfire', coastal_flood: 'Coastal flood (sea-level rise)',
  heavy_precip: 'Heavy rainfall', frost: 'Frost & cold snaps', heat_acute: 'Extreme heat', heat_chronic: 'Rising average heat',
  drought: 'Drought', soil_water: 'Soil-water stress', temp_variability: 'Temperature variability', precip_variability: 'Rainfall variability',
  changing_temp: 'Warming trend', changing_precip: 'Shifting rainfall', seismic: 'Earthquake', volcanic: 'Volcanic', landslide: 'Landslide',
}
const hz = (id: string) => HAZ_LABEL[id] ?? id.replace(/_/g, ' ')

function ProjTile({ it }: { it: ProjItem }) {
  const c = it.projects ? 'var(--color-sky)' : 'var(--color-slate)'
  return (
    <div className="rounded-lg border px-3.5 py-3" style={{ borderColor: c + '33' }}>
      <div className="flex items-start justify-between gap-2 mb-1">
        <div className="text-[13.5px] font-medium text-[var(--color-ink)] capitalize">{hz(it.hazard)}</div>
        <div className="flex gap-1.5 shrink-0">
          {it.band && chip('var(--color-good)', 'band')}
          {chip(c, it.projects ? 'projects' : 'flat by design')}
        </div>
      </div>
      <div className="text-[12.5px] text-[var(--color-mute)] leading-snug">{it.mechanism}</div>
      <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1 leading-snug">{it.basis}</div>
      {it.gaps.map((g, i) => (
        <div key={i} className="text-[11.5px] text-[var(--color-faint)] mt-1.5 pl-2 border-l-2" style={{ borderColor: 'var(--color-warn)' }}>{g}</div>
      ))}
    </div>
  )
}

// ── view 2: projection posture ───────────────────────────────────────────────────────────────────
function ProjectionView() {
  const { data, isLoading, error } = useQuery({ queryKey: ['projection-coverage'], queryFn: () => api.get<Proj>('/v1/meta/projection-coverage') })
  if (isLoading) return <div className="mono text-[13px] text-[var(--color-faint)]">loading…</div>
  if (error || !data) return <div className="mono text-[13px] text-[var(--color-bad)]">could not load projection posture</div>
  const projected = data.items.filter(i => i.projects)
  const flat = data.items.filter(i => !i.projects)
  return (
    <>
      <StatGrid cols={4} items={[
        { label: 'Hazards', value: data.n_hazards },
        { label: 'Projected forward', value: data.n_projected, accent: 'var(--color-sky)', sub: 'physically-grounded mechanism' },
        { label: 'Flat by design', value: data.n_flat_by_design, sub: 'geophysical / susceptibility' },
        { label: 'Carry a spread band', value: data.n_with_band, accent: 'var(--color-good)', sub: 'CMIP6 / AR6 model range' },
      ]} />
      <Card className="p-5">
        <SectionHead>How each hazard is carried forward</SectionHead>
        <PlainLead className="mt-1">{data.note}</PlainLead>
        <div className="mono text-[10.5px] text-[var(--color-faint)] mt-2">scenarios {data.scenarios.join(' · ')} × horizons {data.horizons.join(' · ')} · engine {data.projection_engine_version}</div>
      </Card>
      <div className="space-y-3">
        <SectionHead hint={`${projected.length} hazards`}>Projected — physically-grounded, cited</SectionHead>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">{projected.map(it => <ProjTile key={it.hazard} it={it} />)}</div>
      </div>
      <div className="space-y-3">
        <SectionHead hint="a deliberate choice, not an omission">Flat by design</SectionHead>
        <PlainLead>A geophysical hazard has no climate-scenario response; a terrain-susceptibility layer is a predisposition, not a triggering nowcast. Held flat and stated as such.</PlainLead>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">{flat.map(it => <ProjTile key={it.hazard} it={it} />)}</div>
      </div>
    </>
  )
}

// ── view 3: model limitations ────────────────────────────────────────────────────────────────────
function LimField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mt-2">
      <div className="mono text-[9.5px] font-semibold uppercase tracking-wide text-[var(--color-faint)]">{label}</div>
      <div className="text-[12.5px] text-[var(--color-mute)] leading-snug mt-0.5">{children}</div>
    </div>
  )
}
function LimCard({ it }: { it: LimItem }) {
  const c = LIM_C[it.status]
  return (
    <Card className="p-5" style={{ borderColor: c + '33' }}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-[15px] font-semibold text-[var(--color-ink)]">{it.title}</div>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">{it.area}</div>
        </div>
        <div className="shrink-0">{chip(c, it.status.replace(/_/g, ' '))}</div>
      </div>
      <div className="text-[13px] text-[var(--color-mute)] leading-snug mt-2">{it.summary}</div>
      <LimField label="Evidence">{it.evidence}</LimField>
      <LimField label="How it's handled today">{it.current_treatment}</LimField>
      <LimField label="What would close it">{it.unlock}</LimField>
    </Card>
  )
}
function LimitationsView() {
  const { data, isLoading, error } = useQuery({ queryKey: ['model-limitations'], queryFn: () => api.get<Lim>('/v1/meta/model-limitations') })
  if (isLoading) return <div className="mono text-[13px] text-[var(--color-faint)]">loading…</div>
  if (error || !data) return <div className="mono text-[13px] text-[var(--color-bad)]">could not load limitations</div>
  return (
    <>
      <StatGrid cols={3} items={[
        { label: 'Tested & rejected', value: data.counts.tested_rejected, accent: 'var(--color-warn)', sub: 'measured, left out — not fabricated' },
        { label: 'Deferred — needs a feed', value: data.counts.deferred_needs_data, accent: 'var(--color-sky)', sub: 'buildable with named data' },
        { label: 'Scope boundaries', value: data.counts.disclosed_scope, sub: 'stated by design' },
      ]} />
      <Card className="p-5"><SectionHead>What we deliberately don't model yet</SectionHead><PlainLead className="mt-1">{data.note}</PlainLead></Card>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">{data.items.map(it => <LimCard key={it.id} it={it} />)}</div>
    </>
  )
}

type SubTab = 'coverage' | 'projections' | 'limitations'
const SUBTABS: { id: SubTab; label: string }[] = [
  { id: 'coverage', label: 'Hazard coverage' },
  { id: 'projections', label: 'Projection posture' },
  { id: 'limitations', label: 'Model limitations' },
]

export default function Coverage() {
  const [sub, setSub] = useState<SubTab>('coverage')
  return (
    <div className="space-y-6">
      <ReviewTabs />
      <PageHeader
        eyebrow="Assess · Coverage & honesty"
        title="Coverage, projections & limitations"
        lead="Three auditable registries, read straight: which hazards we score and how mature each is, how we carry every hazard forward to 2030/2050/2100, and what we deliberately do not model yet — with the evidence and the exact feed that would close each gap."
      />
      <div className="flex gap-1.5 flex-wrap">
        {SUBTABS.map(t => (
          <button key={t.id} onClick={() => setSub(t.id)}
            className={`px-3.5 py-1.5 text-[12.5px] rounded-full border transition ${sub === t.id
              ? 'border-[var(--color-sky)] text-[var(--color-ink)] font-medium bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]'
              : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {sub === 'coverage' && <CoverageView />}
      {sub === 'projections' && <ProjectionView />}
      {sub === 'limitations' && <LimitationsView />}
    </div>
  )
}
