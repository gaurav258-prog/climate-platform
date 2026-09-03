import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { PageHeader, Card, StatGrid, SectionHead, PlainLead } from '../components/ui'
import ReviewTabs from '../components/ReviewTabs'

// Hazard coverage — the completeness scoreboard. Maps our channels onto the EU Taxonomy's 28 physical climate
// hazards (Appendix A), each stamped with a maturity tier. The load-bearing honesty point: coverage ≠
// calibration — a channel is only "Calibrated" once it passes the backtest; everything else says so plainly.
// Data is a static registry (core/hazard_taxonomy.py) served at /v1/meta/hazard-coverage.

type Tier = 'calibrated' | 'screening' | 'reference' | 'roadmap'
interface HZ { id: string; name: string; family: string; nature: string; tier: Tier; phase: string; source: string; internal: string[] }
interface Fam { family: string; label: string; hazards: HZ[] }
interface Summary { total: number; covered: number; roadmap: number; by_tier: Record<string, number>; by_phase: Record<string, number>; extra_channels: number }
interface Cov {
  reference: string; summary: Summary; families: Fam[]; extra_channels: HZ[]
  tiers: { tier: string; label: string; note: string }[]; note: string
}

const TIER: Record<Tier, { c: string; label: string }> = {
  calibrated: { c: 'var(--color-good)', label: 'Calibrated' },
  screening: { c: 'var(--color-warn)', label: 'Screening' },
  reference: { c: 'var(--color-sky)', label: 'Reference' },
  roadmap: { c: 'var(--color-slate)', label: 'Roadmap' },
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

export default function Coverage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['hazard-coverage'],
    queryFn: () => api.get<Cov>('/v1/meta/hazard-coverage'),
  })

  return (
    <div className="space-y-6">
      <ReviewTabs />
      <PageHeader
        eyebrow="Assess · Coverage"
        title="Hazard coverage"
        lead="Our channels mapped onto the EU Taxonomy's 28 physical climate hazards — each stamped with a maturity tier. Coverage is not the same claim as calibration: a channel only reads “Calibrated” once it passes the backtest, and everything else says exactly where it stands."
      />

      {isLoading && <div className="mono text-[13px] text-[var(--color-faint)]">loading…</div>}
      {error && <div className="mono text-[13px] text-[var(--color-bad)]">could not load coverage</div>}

      {data && (
        <>
          <StatGrid cols={4} items={[
            { label: 'EU Taxonomy hazards', value: data.summary.total },
            { label: 'Covered today', value: data.summary.covered, accent: 'var(--color-good)', sub: `${data.summary.by_tier.calibrated} calibrated · ${data.summary.by_tier.screening} screening` },
            { label: 'On the roadmap', value: data.summary.roadmap, sub: 'across 4 phases' },
            { label: 'Beyond the 28', value: `+${data.summary.extra_channels}`, sub: 'seismic · volcanic · pollution' },
          ]} />

          {/* tier legend — the honesty spine */}
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

          {/* the 28, by family */}
          {data.families.map(f => (
            <div key={f.family} className="space-y-3">
              <SectionHead hint={`${f.hazards.length} hazards`}>{f.label}</SectionHead>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {f.hazards.map(h => <HazardTile key={h.id} h={h} />)}
              </div>
            </div>
          ))}

          {/* extra channels beyond the EU list */}
          <div className="space-y-3">
            <SectionHead hint="not on the EU climate list — geophysical / nature">Beyond the 28</SectionHead>
            <PlainLead>Channels we carry that sit outside Appendix A — coverage we hold in addition to the EU climate hazards.</PlainLead>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {data.extra_channels.map(h => <HazardTile key={h.id} h={h} />)}
            </div>
          </div>

          <p className="mono text-[11px] text-[var(--color-faint)]">Reference: {data.reference}</p>
        </>
      )}
    </div>
  )
}
