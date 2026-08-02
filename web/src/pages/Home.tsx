import { useQuery } from '@tanstack/react-query'
import { useNavigate, Navigate } from 'react-router-dom'
import { ArrowUpRight, ArrowRight, Boxes, Building2, Sprout, ShieldCheck, TrendingDown, AlertCircle, AlertTriangle, Info, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow } from '../components/ui'
import LiveEarthHero from '../components/LiveEarthHero'

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
      <div className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-faint)] mb-3">
        {first ? `What needs you, ${first}` : 'What needs you now'}
      </div>
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
const pretty = (h?: string | null) => !h ? '—' : h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const hz = (s?: number | null) => s == null ? 'var(--color-faint)' : s >= 60 ? 'var(--color-bad)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-good)'

export default function Home() {
  const nav = useNavigate()
  const { profile } = useAuth()
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
  const topCommodity = (s?.commodities ?? []).filter(c => (c.volume_at_risk_eur ?? 0) > 0)
    .sort((a, b) => (b.volume_at_risk_eur ?? 0) - (a.volume_at_risk_eur ?? 0))[0]

  // biggest exposures across the whole book (sites + suppliers), for the granular strip — each opens its detail
  const exposures = [
    ...siteList.map(x => ({ name: x.name, kind: x.site_type.replace(/_/g, ' '), hazard: x.top_hazard, score: x.hazard_score, href: `/detail/site/${x.site_id}` })),
    ...plots.map(p => ({ name: p.plot_name, kind: p.commodity, hazard: p.top_hazard, score: p.hazard_score, href: `/detail/plot/${p.plot_id}` })),
  ].filter(e => e.score != null).sort((a, b) => (b.score ?? 0) - (a.score ?? 0)).slice(0, 6)

  return (
    <div className="fadeup space-y-7">
      {/* live Earth-from-space hero */}
      <LiveEarthHero height="46vh">
        <div className="display text-[clamp(34px,5.5vw,60px)] font-semibold italic leading-none text-[#F4EFE6]">
          Tel<span className="text-[var(--color-sky)]">lumen</span>
        </div>
        <div className="mono mt-3 text-[11px] uppercase tracking-[0.28em] text-[var(--color-blue)]">Light on the Earth</div>
        <p className="display italic mt-5 max-w-2xl text-[clamp(18px,2.6vw,30px)] font-light leading-tight text-[#F4EFE6]">
          See what's coming. <span className="text-[var(--color-sky)]">Any place on Earth.</span>
        </p>
      </LiveEarthHero>

      {/* role-shaped task feed — the cockpit leads with what needs YOU now, not just state */}
      <TaskFeed />

      <div>
        <Eyebrow>{profile?.org?.name} · agriculture workspace</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Overview</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Your climate risk across operations and sourcing — one glance, then click any tile to open the detail.</p>
      </div>

      {/* KPI widgets — each clickable → its detail view */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Widget icon={TrendingDown} tone="warn" onClick={() => nav('/cogs')}
          value={eur(s?.rollup.volume_at_risk_eur)} label="Volume at risk (physical)"
          sub={s ? `${s.rollup.pct_cogs_at_risk.toFixed(2)}% of COGS · top: ${topCommodity ? `${topCommodity.commodity} ${eur(topCommodity.volume_at_risk_eur)}` : '—'}` : '…'} />
        <Widget icon={Building2} onClick={() => nav('/operations')}
          value={siteList.length} label="Operational sites"
          sub={`${sitesElevated} at elevated hazard (≥40)`} tone={sitesElevated ? 'warn' : 'ink'} />
        <Widget icon={Sprout} onClick={() => nav('/sourcing')}
          value={plots.length} label="Sourcing plots"
          sub={`geolocated & scored · ${eur(plots.reduce((a, p) => a + (p.spend_eur ?? 0), 0))} spend`} />
        <Widget icon={ShieldCheck} tone="good" onClick={() => nav('/disclosure')}
          value={coveredPlots ? `${defFree}/${coveredPlots}` : '—'} label="EUDR deforestation-free"
          sub={coveredPlots ? `of ${coveredPlots} EUDR-covered plots` : 'no EUDR-covered plots'} />
        <Widget icon={Boxes} onClick={() => nav('/cogs')}
          value={`${(s?.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`} label="of COGS at risk"
          sub="physical climate exposure on the bill of materials" />
      </div>

      {/* granular strip — what's driving the numbers, clickable */}
      <div>
        <div className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-faint)] mb-3">Biggest exposures right now</div>
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

function Widget({ icon: Icon, value, label, sub, onClick, tone = 'ink', hideIfUndef }:
  { icon: typeof Boxes; value: React.ReactNode; label: string; sub: string; onClick: () => void; tone?: 'ink' | 'good' | 'warn'; hideIfUndef?: boolean }) {
  if (hideIfUndef && (value === '—' || value === undefined)) return null
  const c = tone === 'good' ? 'var(--color-good)' : tone === 'warn' ? 'var(--color-warn)' : 'var(--color-ink)'
  return (
    <button onClick={onClick}
      className="group text-left rounded-2xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5 hover:border-[var(--color-sky)] transition">
      <div className="flex items-start justify-between">
        <Icon size={18} className="text-[var(--color-sky)]" />
        <ArrowUpRight size={16} className="text-[var(--color-faint)] group-hover:text-[var(--color-sky)] transition" />
      </div>
      <div className="mt-3 text-[28px] font-semibold leading-none" style={{ color: c }}>{value}</div>
      <div className="mt-1.5 text-[13px] text-[var(--color-ink)]">{label}</div>
      <div className="mt-1 text-[11px] text-[var(--color-faint)]">{sub}</div>
    </button>
  )
}
