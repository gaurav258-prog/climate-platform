import { useQuery } from '@tanstack/react-query'
import { useNavigate, Navigate } from 'react-router-dom'
import { ArrowRight, AlertCircle, AlertTriangle, Info, CheckCircle2, PackageX, Building2, MapPin, TreePine, Percent } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { PageHeader, HeroBanner, SectionHead } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

interface Task { key: string; title: string; detail: string; severity: 'action' | 'warning' | 'info' | 'good'; cta_label: string; cta_href: string }
interface TasksResp { tasks: Task[]; all_clear: boolean }

const SEV: Record<Task['severity'], { icon: typeof AlertCircle; color: string; ring: string }> = {
  action:  { icon: AlertCircle,   color: 'var(--color-sky)',  ring: 'var(--color-sky)' },
  warning: { icon: AlertTriangle, color: 'var(--color-warn)', ring: 'var(--color-warn)' },
  info:    { icon: Info,          color: 'var(--color-blue)', ring: 'var(--color-line-2)' },
  good:    { icon: CheckCircle2,  color: 'var(--color-good)', ring: 'var(--color-good)' },
}

function TaskFeed() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const q = useQuery({ queryKey: ['my-tasks'], queryFn: () => api.get<TasksResp>('/v1/me/tasks') })
  const tasks = q.data?.tasks ?? []
  const first = (profile?.user?.name || profile?.user?.email || '').split(/[ @]/)[0]

  return (
    <div>
      <SectionHead className="mb-3">{first ? `What needs you, ${first}` : 'What needs you now'}</SectionHead>
      {q.isLoading && <div className="text-[13px] text-[var(--color-faint)]">Checking your workspace…</div>}
      {!q.isLoading && tasks.length === 0 && (
        <div className="flex items-center gap-3 rounded-2xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5">
          <CheckCircle2 size={20} className="text-[var(--color-good)]" />
          <div>
            <div className="text-[14px] text-[var(--color-ink)]">You're all caught up.</div>
            <div className="text-[12px] text-[var(--color-faint)]">Nothing needs your attention right now — the overview below shows your standing exposure.</div>
          </div>
        </div>
      )}
      <div className="grid gap-2.5">
        {tasks.map(t => {
          const s = SEV[t.severity]
          return (
            <button key={t.key} onClick={() => nav(t.cta_href)}
              className="group flex items-center gap-4 text-left rounded-2xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-4 hover:border-[color:var(--tint)] transition"
              style={{ ['--tint' as string]: s.ring }}>
              <div className="grid place-items-center h-9 w-9 shrink-0 rounded-xl"
                style={{ background: `color-mix(in oklab, ${s.color} 14%, transparent)` }}>
                <s.icon size={18} style={{ color: s.color }} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[14px] text-[var(--color-ink)] font-medium">{t.title}</div>
                <div className="text-[12px] text-[var(--color-faint)] truncate">{t.detail}</div>
              </div>
              <div className="shrink-0 inline-flex items-center gap-1.5 text-[12.5px] font-medium mono"
                style={{ color: s.color }}>
                {t.cta_label} <ArrowRight size={15} className="group-hover:translate-x-0.5 transition" />
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

interface Summary {
  rollup: { volume_at_risk_eur: number; pct_cogs_at_risk: number }
  eudr: { summary: Record<string, number> }
  commodities?: { commodity: string; volume_at_risk_eur: number | null; top_hazard: string | null }[]
}
interface Site { site_id: string; name: string; site_type: string; hazard_score: number | null; top_hazard: string | null; value_eur: number | null }
interface SitesResp { sites: Site[] }
interface Plot { plot_id: string; plot_name: string; commodity: string; top_hazard: string | null; hazard_score: number | null; spend_eur: number
  eudr_covered?: boolean; eudr_determination?: string | null }
interface Portfolio { plots: Plot[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const pretty = hazardLabel
const hz = (s?: number | null) => s == null ? 'var(--color-faint)' : s >= 60 ? 'var(--color-bad)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-good)'

export default function Home() {
  const { profile } = useAuth()
  const nav = useNavigate()
  // Home is the agriculture cockpit (it reads the /v1/supply/* endpoints). The financial verticals have
  // their own operating surface — send them to the Portfolio instead of loading agri data they don't have.
  const isFin = ['bank', 'insurer', 'asset_manager', 'reit'].includes(profile?.org?.type ?? '')
  const sum = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary'), enabled: !isFin })
  const sites = useQuery({ queryKey: ['sites'], queryFn: () => api.get<SitesResp>('/v1/supply/sites'), enabled: !isFin })
  const pf = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio'), enabled: !isFin })
  if (isFin) return <Navigate to="/portfolio" replace />

  const s = sum.data
  const siteList = sites.data?.sites ?? []
  const sitesElevated = siteList.filter(x => (x.hazard_score ?? 0) >= 40).length
  const plots = pf.data?.plots ?? []
  const coveredPlots = plots.filter(p => p.eudr_covered).length
  const defFree = plots.filter(p => p.eudr_determination === 'deforestation_free').length

  // biggest exposures across the whole book (sites + suppliers), for the granular strip — each opens its detail
  const exposures = [
    ...siteList.map(x => ({ name: x.name, kind: x.site_type.replace(/_/g, ' '), hazard: x.top_hazard, score: x.hazard_score, href: `/detail/site/${x.site_id}` })),
    ...plots.map(p => ({ name: p.plot_name, kind: p.commodity, hazard: p.top_hazard, score: p.hazard_score, href: `/detail/plot/${p.plot_id}` })),
  ].filter(e => e.score != null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 6)

  return (
    <div className="fadeup space-y-7">
      {/* brand masthead — the live-Earth video now runs on the Data foundation page */}
      <div className="pt-1">
        <h1 className="display text-[clamp(26px,3.6vw,40px)] font-semibold italic leading-tight">
          See what's coming. <span className="text-[var(--color-sky)]">Any place on Earth.</span>
        </h1>
        <p className="mono mt-2 text-[11px] uppercase tracking-[0.28em] text-[var(--color-blue)]">Tellumen · Light on the Earth</p>
      </div>

      {/* role-shaped task feed — the cockpit leads with what needs YOU now, not just state */}
      <TaskFeed />

      <PageHeader eyebrow={`${profile?.org?.name} · agriculture workspace`} title="Overview"
        lead="Your climate risk across operations and sourcing — one glance, then click any tile to open the detail." />

      {/* the rich cockpit hero — narrative + live posture tiles */}
      <HeroBanner
        eyebrow="Standing exposure"
        title={(s?.rollup.volume_at_risk_eur ?? 0) > 0 || sitesElevated > 0 ? 'Climate is pressing on your book.' : 'Your book is running clear.'}
        lead="Your climate exposure across operations and sourcing, rolled to euros on the bill of materials — one glance at the whole book."
        stat={[
          { label: 'Volume at risk (physical)', value: eur(s?.rollup.volume_at_risk_eur), icon: PackageX, tone: '#E8853C', onClick: () => nav('/cogs') },
          { label: 'Operational sites', value: siteList.length, icon: Building2, tone: sitesElevated ? '#E8853C' : undefined, onClick: () => nav('/operations') },
          { label: 'Sourcing plots', value: plots.length, icon: MapPin, tone: 'var(--color-sky)', onClick: () => nav('/sourcing') },
          { label: 'EUDR deforestation-free', value: coveredPlots ? `${defFree}/${coveredPlots}` : '—', icon: TreePine, tone: '#4FA46E', onClick: () => nav('/sourcing') },
          { label: 'of COGS at risk', value: `${(s?.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`, icon: Percent, onClick: () => nav('/cogs') },
        ]} />

      {/* granular strip — what's driving the numbers, clickable */}
      <div>
        <SectionHead className="mb-3">Biggest exposures right now</SectionHead>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {exposures.map((e, i) => (
            <button key={i} onClick={() => window.open(e.href, '_blank')}
              className="text-left rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-3.5 hover:border-[var(--color-sky)] transition">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[13px] text-[var(--color-ink)] truncate">{e.name}</span>
                <span className="mono text-[13px] shrink-0" style={{ color: hz(e.score) }}>{Math.round(e.score as number)}</span>
              </div>
              <div className="text-[11px] text-[var(--color-faint)] mt-0.5">{pretty(e.hazard)} · {e.kind}</div>
            </button>
          ))}
          {exposures.length === 0 && <div className="text-[13px] text-[var(--color-faint)]">Add sites or suppliers to see your exposures.</div>}
        </div>
      </div>
    </div>
  )
}
