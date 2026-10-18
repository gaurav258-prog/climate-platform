import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Waves, Wrench } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader, Card, StatGrid, SectionHead } from '../components/ui'
import { Drawer } from '../components/Drawer'
import { CloseButton } from '../components/Dialog'
import { DetailsBody, HEADING, InfoButton, messageDetails, type DetailSection, type Details, type Message } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'
import { Chip, HazardDrawer, NatureMark, RegionStrip, TIER_C, type Coverage as Cov, type Hazard, type Tier } from './coverage/HazardDrawer'

// Coverage, projections and limitations, to the UI standard (2026-10-16): the EU Taxonomy's 28 climate hazards as a
// family × tier matrix, how each is carried to future years, and what the engine deliberately does not model yet.
// Every word is the server's (coverage.* in the message catalogue); each hazard and limitation opens its details.

interface ProjItem { channel: string; label: string; projects: boolean; band: boolean; mode: string; hazard_id: string | null }
interface Proj {
  scenarios: { key: string; label: string }[]; horizons: string[]
  counts: { hazards: number; projected: number; flat: number; band: number }
  modes: { mode: string; message: Message; projects: boolean; channels: string[] }[]
  items: ProjItem[]
}
type LimStatus = 'tested_rejected' | 'deferred_needs_data' | 'disclosed_scope'
interface LimItem { id: string; status: LimStatus; area: string; message: Message; today: Message }
interface Lim { counts: Record<LimStatus, number>; statuses: ({ status: LimStatus } & Message)[]; items: LimItem[] }

const LIM_C: Record<LimStatus, string> = { tested_rejected: 'var(--color-warn)', deferred_needs_data: 'var(--color-sky)', disclosed_scope: 'var(--color-slate)' }
const SCN_C: Record<string, string> = { baseline: 'var(--scn-baseline)', orderly_1_5c: 'var(--scn-orderly)', disorderly_2c: 'var(--scn-disorderly)', hot_house_3_5c: 'var(--scn-hot)' }

const ABOUT = [
  { heading: HEADING.shows, body: 'How the platform covers the 28 climate hazards of the EU Taxonomy (Climate Delegated Act, Regulation 2021/2139, Appendix A) and three beyond it: how mature each one is, where it is validated, how it is carried to future years, and what the engine deliberately does not model yet.' },
  { heading: HEADING.read, body: 'Each hazard sits in its family and its tier. Validated: it passed a test on observed outcomes it was not built from. Indicator: a published layer used to screen; it never leads a headline or carries a figure. Reference context and reference layer: there is nothing observed to test against. Open a hazard for its source, its test, its future years and its limits.' },
  { heading: HEADING.sources, body: 'Each hazard names its own source in its details. Tests use records the scores were not built from, such as weather stations, satellite burn records, mapped flood extents, tide gauges and boreholes.' },
  { heading: HEADING.limits, body: 'Covering a hazard is not the same as validating it. Rank agreement runs from −1 to 1, and a hazard must reach the platform’s bar to be validated; hit rate runs from 0.5, which is chance, to 1.' },
]
const MATRIX_HELP: Details = {
  title: 'Hazards by family and tier',
  sections: [
    { heading: HEADING.read, body: 'Each row is a family of the EU Taxonomy’s climate hazards, plus the hazards we cover beyond the list. Each column is a tier. Open a hazard for its source, its test, how it is carried to future years and its limits.' },
    { heading: 'Symbols', body: 'The lightning mark is an acute hazard, a sudden event; the hourglass is a chronic one, a slow change. On a validated hazard, six small squares show the world regions where it holds: green validated, amber mixed results, red not validated, faded not tested.' },
  ],
}
const FUTURE_HELP: Details = {
  title: 'How each hazard is carried forward',
  sections: [
    { heading: HEADING.read, body: 'Each row is one way of carrying a hazard to future years; open a hazard for its mechanism, its basis and what is left out. Hazards held the same by design are a stated choice, not an omission.' },
    { heading: 'Symbols', body: 'The wave mark shows a hazard that carries the spread across climate models, or the likely range of sea-level rise, as a band rather than a single value.' },
  ],
}

type View = 'hazards' | 'future' | 'limits'
const VIEWS: { id: View; label: string }[] = [
  { id: 'hazards', label: 'Hazards' }, { id: 'future', label: 'Future years' }, { id: 'limits', label: 'Limitations' },
]

export default function Coverage() {
  const [view, setView] = useState<View>('hazards')
  const [hazard, setHazard] = useState<Hazard | null>(null)
  const cov = useQuery({ queryKey: ['hazard-coverage'], queryFn: () => api.get<Cov>('/v1/meta/hazard-coverage') })
  return (
    <div className="space-y-6">
      <ReviewTabs />
      <PageHeader eyebrow="Assess · Coverage" title="Coverage, projections and limitations" about={ABOUT}
        lead="Which climate hazards we score, how far ahead, and where we stop." />
      <div className="flex gap-1.5 flex-wrap">
        {VIEWS.map(t => (
          <button key={t.id} type="button" onClick={() => setView(t.id)} aria-pressed={view === t.id}
            className={`px-3.5 py-1.5 text-[12.5px] rounded-full border transition ${view === t.id
              ? 'border-[var(--color-sky)] text-[var(--color-ink)] font-medium bg-[color-mix(in_oklab,var(--color-sky)_10%,transparent)]'
              : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {t.label}
          </button>
        ))}
      </div>
      {cov.isError ? <div className="text-[12.5px] text-[var(--color-warn)]">The coverage could not be loaded. Try again shortly.</div>
        : !cov.data ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div> : <>
          {view === 'hazards' && <HazardsView cov={cov.data} open={setHazard} />}
          {view === 'future' && <FutureView cov={cov.data} open={setHazard} />}
          {view === 'limits' && <LimitsView />}
          {hazard && <HazardDrawer key={hazard.id} h={hazard} cov={cov.data} onClose={() => setHazard(null)} />}
        </>}
    </div>
  )
}

const all = (cov: Cov) => [...cov.families.flatMap(f => f.hazards), ...cov.extra_channels]

function HazardChip({ h, names, open, tier }: { h: Hazard; names: Record<string, string>; open: (h: Hazard) => void; tier?: string }) {
  const c = TIER_C[h.tier]
  return (
    <button type="button" onClick={() => open(h)}
      className="w-full flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-left text-[12.5px] hover:border-[var(--color-sky)] transition"
      style={{ borderColor: `color-mix(in oklab, ${c} 35%, transparent)`, background: `color-mix(in oklab, ${c} 6%, transparent)` }}>
      <NatureMark nature={h.nature} />
      <span className="flex-1 min-w-0 text-[var(--color-ink)] leading-snug">{h.label}</span>
      {tier && <span className="text-[11px] whitespace-nowrap" style={{ color: c }}>{tier}</span>}
      <RegionStrip h={h} names={names} />
    </button>
  )
}

function HazardsView({ cov, open }: { cov: Cov; open: (h: Hazard) => void }) {
  const c = cov.counts
  const tiers = cov.tiers.filter(t => (c.by_tier[t.tier] ?? 0) > 0)
  const tierName = Object.fromEntries(cov.tiers.map(t => [t.tier, t.label])) as Record<Tier, string>
  const names = Object.fromEntries(cov.regions.map(r => [r.region, r.label]))
  const rows = [...cov.families.map(f => ({ key: f.family, label: f.label, hazards: f.hazards })),
    { key: 'beyond', label: cov.extra_label, hazards: cov.extra_channels }]
  return (
    <>
      <StatGrid cols={4} items={[
        { label: 'EU climate hazards covered', value: `${c.covered} of ${c.total}` },
        { label: tierName.calibrated, value: c.by_tier.calibrated, accent: TIER_C.calibrated, sub: `${c.scope_claims.global ?? 0} validated globally` },
        { label: tierName.screening, value: c.by_tier.screening, accent: TIER_C.screening },
        { label: cov.extra_label, value: `+${c.extra_channels}` },
      ]} />
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-4"><SectionHead>Hazards by family and tier</SectionHead><InfoButton compact details={MATRIX_HELP} /></div>
        <div className="hidden md:grid gap-px rounded-lg overflow-hidden bg-[var(--color-line)] border border-[var(--color-line)]"
          style={{ gridTemplateColumns: `9rem repeat(${tiers.length}, minmax(0, 1fr))` }}>
          <div className="bg-[var(--color-panel)]" />
          {tiers.map(t => (
            <div key={t.tier} className="bg-[var(--color-panel)] px-3 py-2.5 flex items-center gap-1.5">
              <Chip color={TIER_C[t.tier]}>{t.label}</Chip>
              <span className="text-[12px] tabular-nums text-[var(--color-faint)]">{c.by_tier[t.tier]}</span>
              <InfoButton compact details={messageDetails(t)} />
            </div>
          ))}
          {rows.map(r => (
            <Fragment key={r.key}>
              <div className="bg-[var(--color-panel)] px-3 py-3">
                <div className="text-[12.5px] font-medium text-[var(--color-ink)]">{r.label}</div>
                <div className="text-[11px] text-[var(--color-faint)] tabular-nums">{r.hazards.length} hazards</div>
              </div>
              {tiers.map(t => (
                <div key={t.tier} className="bg-[var(--color-panel)] p-2 flex flex-col gap-1.5">
                  {r.hazards.filter(h => h.tier === t.tier).map(h => <HazardChip key={h.id} h={h} names={names} open={open} />)}
                </div>
              ))}
            </Fragment>
          ))}
        </div>
        <div className="md:hidden space-y-4">
          {rows.map(r => (
            <div key={r.key}>
              <div className="text-[12.5px] font-medium text-[var(--color-ink)] mb-1.5">{r.label}</div>
              <div className="flex flex-col gap-1.5">{r.hazards.map(h => <HazardChip key={h.id} h={h} names={names} open={open} tier={tierName[h.tier]} />)}</div>
            </div>
          ))}
        </div>
      </Card>
    </>
  )
}

function FutureView({ cov, open }: { cov: Cov; open: (h: Hazard) => void }) {
  const q = useQuery({ queryKey: ['projection-coverage'], queryFn: () => api.get<Proj>('/v1/meta/projection-coverage') })
  if (q.isError) return <div className="text-[12.5px] text-[var(--color-warn)]">The projections could not be loaded. Try again shortly.</div>
  if (!q.data) return <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
  const p = q.data
  const byId = Object.fromEntries(all(cov).map(h => [h.id, h]))
  const item = Object.fromEntries(p.items.map(i => [i.channel, i]))
  return (
    <>
      <StatGrid cols={3} items={[
        { label: 'Carried to future years', value: p.counts.projected, accent: 'var(--color-sky)', sub: `of ${p.counts.hazards} scored hazards` },
        { label: 'With a model spread', value: p.counts.band, accent: 'var(--color-good)' },
        { label: 'Held the same by design', value: p.counts.flat, accent: 'var(--color-slate)' },
      ]} />
      <Card className="p-5">
        <SectionHead className="mb-3">Scenarios and years</SectionHead>
        <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
          <div className="flex items-center">
            {p.horizons.map((y, i) => (
              <Fragment key={y}>
                {i > 0 && <span className="w-10 sm:w-14 h-px bg-[var(--color-line-2)]" />}
                <span className="flex flex-col items-center gap-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[var(--color-sky)]" />
                  <span className="text-[11.5px] text-[var(--color-mute)] tabular-nums">{y === 'current' ? 'Today' : y}</span>
                </span>
              </Fragment>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">{p.scenarios.map(s => <Chip key={s.key} color={SCN_C[s.key] ?? 'var(--color-slate)'}>{s.label}</Chip>)}</div>
        </div>
      </Card>
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-2"><SectionHead>How each hazard is carried forward</SectionHead><InfoButton compact details={FUTURE_HELP} /></div>
        <div className="divide-y divide-[var(--color-line)]">
          {p.modes.map(m => (
            <div key={m.mode} className="py-3 grid gap-2 md:grid-cols-[18rem_minmax(0,1fr)] items-start">
              <div className="flex items-center gap-1"><Chip color={m.projects ? 'var(--color-sky)' : 'var(--color-slate)'}>{m.message.label}</Chip><InfoButton compact details={messageDetails(m.message)} /></div>
              <div className="flex flex-wrap gap-1.5">
                {m.channels.map(ch => {
                  const it = item[ch]
                  const h = it.hazard_id ? byId[it.hazard_id] : undefined
                  return (
                    <button key={ch} type="button" disabled={!h} onClick={() => h && open(h)}
                      className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-line-2)] px-2.5 py-1 text-[12.5px] text-[var(--color-ink)] hover:border-[var(--color-sky)] transition disabled:hover:border-[var(--color-line-2)]">
                      {it.label}
                      {it.band && <Waves size={12} className="text-[var(--color-good)]" aria-label="Carries a model spread" />}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </>
  )
}

function LimitsView() {
  const q = useQuery({ queryKey: ['model-limitations'], queryFn: () => api.get<Lim>('/v1/meta/model-limitations') })
  const [shown, setShown] = useState<LimItem | null>(null)
  if (q.isError) return <div className="text-[12.5px] text-[var(--color-warn)]">The limitations could not be loaded. Try again shortly.</div>
  if (!q.data) return <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
  const d = q.data
  const status = Object.fromEntries(d.statuses.map(s => [s.status, s])) as Record<LimStatus, Lim['statuses'][number]>
  return (
    <>
      <StatGrid cols={3} items={d.statuses.map(s => ({ label: s.label, value: d.counts[s.status], accent: LIM_C[s.status] }))} />
      <div className="grid gap-3 md:grid-cols-2">
        {d.items.map(it => (
          <Card key={it.id} className="p-4 cursor-pointer hover:border-[var(--color-sky)] transition" onClick={() => setShown(it)}>
            <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
              <Chip color={LIM_C[it.status]}>{status[it.status].label}</Chip>
              <span className="text-[11.5px] text-[var(--color-faint)]">{it.area}</span>
            </div>
            <div className="text-[14.5px] font-semibold text-[var(--color-ink)] leading-snug">{it.message.label}</div>
            <div className="text-[12px] text-[var(--color-mute)] mt-1.5 flex items-center gap-1.5"><Wrench size={12} className="shrink-0" />{it.today.label}</div>
          </Card>
        ))}
      </div>
      {shown && <LimitDrawer it={shown} status={status[shown.status]} onClose={() => setShown(null)} />}
    </>
  )
}

function LimitDrawer({ it, status, onClose }: { it: LimItem; status: Message; onClose: () => void }) {
  const d = it.message.detail ?? {}
  const sections: DetailSection[] = [
    ...(d.what ? [{ heading: 'What it is', body: d.what }] : []),
    ...(d.why ? [{ heading: 'Evidence', body: d.why }] : []),
    { heading: 'How it is handled today', body: <><span className="font-medium">{it.today.label}.</span> {it.today.detail?.what}</> },
    ...(d.next ? [{ heading: 'What would close it', body: d.next }] : []),
  ]
  return (
    <Drawer label={it.message.label} onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span className="inline-flex items-center gap-1"><Chip color={LIM_C[it.status]}>{status.label}</Chip><InfoButton compact details={messageDetails(status)} /></span>
            <span className="text-[11.5px] text-[var(--color-faint)]">{it.area}</span>
          </div>
          <div className="text-[18px] font-semibold text-[var(--color-ink)] leading-snug">{it.message.label}</div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="mt-5"><DetailsBody sections={sections} /></div>
    </Drawer>
  )
}
