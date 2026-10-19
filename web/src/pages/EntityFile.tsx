import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, MapPin, ShieldCheck, Users } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { HBar } from '../components/Charts'
import { MessageLine, type Message } from '../components/Details'
import { severityHex } from '../components/SiteMap'
import StageStrip, { type Step } from '../components/StageStrip'
import { hazardLabel, statusLabel } from '../lib/hazards'
import { balance } from '../lib/money'
import { RemittancesIssued } from '../components/Remittance'
import { FULL, QUICK } from './supervisorAnalysis/checks'
import { aboutOf, day, shows } from './supervisorDesk/common'
import { EvidencePacks, TransmissionsReceived } from './supervisorDesk/EntityRecords'

// The entity file (UI standard, 2026-10-16) — what a line supervisor opens: where the entity is in the process and its
// checks, four figures, its filings as chips, its position among peers as range bars, where its book sits and what
// threatens it as bars, and its records (transmissions, evidence packs, onward shares). Every figure is the entity's own
// engine result at the authority's basis; opening the file is written to the entity's audit trail.
interface Fw { framework: string; label: string; state: 'filed' | 'in_progress' | 'none'; state_label: string | null; status: string | null; period_label: string | null }
interface Pos { id: string; label: string; unit: string; value: number | null; flag: string; flag_label: string | null; percentile: number | null
  distribution: { n: number; min?: number; p25?: number; median?: number; p75?: number; max?: number } }
interface FileResp {
  entity: { org_id: string; name: string; sector_label: string | null; country_name: string | null; lei: string | null; legal_name: string | null }
  in_profile: boolean; has_intake?: boolean; sector: { label: string; book_noun: string } | null; notes: Message[]; about: Message
  submissions: { frameworks: Fw[]; filed: number; expected: number } | null
  book: { n_assets: number; value_eur: number; n_regions: number
    top_regions: { key: string; name: string; country_name: string | null; kind_label: string | null; n_sites: number; value_eur: number; max_score: number | null; worst_hazard: string | null }[]
    hazards: { hazard: string; n: number; value_eur: number }[] }
  peer_position: Pos[]; peers_in_sector: number | null; site_access: boolean
  my_recent_accesses: { label: string; at: string }[]
}
const STATE_TONE: Record<Fw['state'], 'good' | 'warn' | 'neutral'> = { filed: 'good', in_progress: 'warn', none: 'neutral' }
const FLAG_COLOR: Record<string, string> = { act: 'var(--color-bad)', watch: 'var(--color-warn)', ok: 'var(--color-good)', na: 'var(--color-faint)' }
const FLAG_TONE: Record<string, 'bad' | 'warn' | 'good' | 'neutral'> = { act: 'bad', watch: 'warn', ok: 'good', na: 'neutral' }
const fig = (p: Pos, v: number | null | undefined) => v == null ? '—' : p.unit === 'eur' ? balance(v) : `${v}%`
const hazardName = (h: string | null) => !h || h === 'unscored' ? 'Not scored' : hazardLabel(h)

// One measure among peers: the range across peers, the middle half shaded, the median a tick, this entity a marker.
function PeerBar({ p }: { p: Pos }) {
  const ds = p.distribution
  if (ds.n <= 1 || ds.min == null || ds.max == null) return <span className="text-[11.5px] text-[var(--color-faint)]">No peers yet</span>
  const span = ds.max - ds.min || 1, x = (v: number) => `${Math.max(0, Math.min(100, ((v - ds.min!) / span) * 100))}%`
  return (
    <div className="relative h-5 w-full rounded bg-[var(--color-panel-2)]" role="img" title={`Peers ${fig(p, ds.min)} to ${fig(p, ds.max)} · median ${fig(p, ds.median)}`}
      aria-label={`This entity ${fig(p, p.value)}; peers ${fig(p, ds.min)} to ${fig(p, ds.max)}, median ${fig(p, ds.median)}`}>
      {ds.p25 != null && ds.p75 != null && <div className="absolute top-0 h-full rounded bg-[var(--color-sky)]/25" style={{ left: x(ds.p25), width: `calc(${x(ds.p75)} - ${x(ds.p25)})` }} />}
      {ds.median != null && <div className="absolute top-0 h-full w-px bg-[var(--color-sky)]" style={{ left: x(ds.median) }} />}
      {p.value != null && <div className="absolute top-[2px] h-4 w-[4px] rounded-sm -translate-x-1/2" style={{ left: x(p.value), background: FLAG_COLOR[p.flag] ?? 'var(--color-ink)' }} />}
    </div>
  )
}

export default function EntityFile() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['entity-file', orgId], queryFn: () => api.get<FileResp>(`/v1/supervisor/entity/${orgId}/file`) })
  const wf = useQuery({ queryKey: ['supervisor-workflow'], queryFn: () => api.get<{ entities: { org_id: string; steps: Step[]; next: { label: string; to: string } }[] }>('/v1/supervisor/population/workflow') })
  const mine = wf.data?.entities.find(e => e.org_id === orgId)
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">Opening the entity file…</div>
  if (!d) return <div className="h-[60vh] grid place-items-center text-[var(--color-bad)] text-sm">This entity is not in your supervised population.</div>
  const sub = d.submissions
  const link = 'inline-flex items-center rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12.5px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition'
  return (
    <div className="fadeup space-y-6">
      <Link to="/supervised" className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Supervised population</Link>
      <PageHeader eyebrow={[d.entity.sector_label, d.entity.country_name].filter(Boolean).join(' · ')} title={d.entity.name}
        about={[...(d.entity.legal_name || d.entity.lei ? [shows(`${d.entity.legal_name ?? d.entity.name}${d.entity.lei ? ` · LEI ${d.entity.lei}` : ''}`)] : []), ...aboutOf(d.about)]} />
      <Card className="p-4 space-y-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {mine ? <StageStrip steps={mine.steps} /> : <span className="text-[12px] text-[var(--color-faint)]">Reading where this entity is in the process…</span>}
          {mine && <Link to={mine.next.to} className="text-[12.5px] font-medium text-[var(--color-sky)] hover:underline whitespace-nowrap">Next: {mine.next.label} →</Link>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {d.has_intake && <>
            <Link to={`/supervised/${orgId}/intake`} className={link}>Intake</Link>
            <Link to={`/supervised/${orgId}/plausibility`} className={link}>{QUICK}</Link>
            <Link to={`/supervised/${orgId}/lens`} className={link}>{FULL}</Link></>}
          {d.notes.map(m => <MessageLine key={m.code} m={m} className="text-[12.5px] text-[var(--color-warn)]" />)}
        </div>
      </Card>

      <StatGrid cols={4} items={[
        { label: d.sector?.book_noun ? d.sector.book_noun[0].toUpperCase() + d.sector.book_noun.slice(1) : 'Assets', value: d.book.n_assets.toLocaleString(), sub: balance(d.book.value_eur) },
        { label: 'Filings on record', value: sub ? `${sub.filed} of ${sub.expected}` : '—', sub: 'expected for the year' },
        { label: 'Regions with exposure', value: String(d.book.n_regions), sub: 'regions and grid cells' },
        { label: 'Site-level access', value: d.site_access ? 'Granted' : 'Not granted', accent: d.site_access ? 'var(--color-good)' : undefined, sub: d.site_access ? 'individual sites visible' : 'regional figures only' },
      ]} />

      {sub && sub.frameworks.length > 0 && <Card className="p-5">
        <SectionHead icon={ShieldCheck}>Filings</SectionHead>
        <div className="flex flex-wrap gap-2 mt-3">{sub.frameworks.map(f => (
          <span key={f.framework} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line)] px-2.5 py-1.5 text-[12.5px]"
            title={f.status ? `${statusLabel(f.status)}${f.period_label ? ` · ${f.period_label}` : ''}` : undefined}>
            <span className="text-[var(--color-ink)]">{f.label}</span><StatusChip label={f.state_label ?? undefined} value={f.state} tone={STATE_TONE[f.state]} /></span>))}</div>
      </Card>}

      {d.peer_position.length > 0 && <Card className="p-5">
        <SectionHead icon={Users} hint={d.peers_in_sector ? `among ${d.peers_in_sector} ${d.sector?.label.toLowerCase() ?? 'peers'}` : undefined}>Peer position</SectionHead>
        <div className="mt-3 divide-y divide-[var(--color-line)]">{d.peer_position.map(p => (
          <div key={p.id} className="py-2.5 grid sm:grid-cols-[14rem_1fr_7rem_8rem] items-center gap-x-4 gap-y-1.5 text-[12.5px]">
            <span className="text-[var(--color-ink)]">{p.label}</span>
            <PeerBar p={p} />
            <span className="tabular-nums text-right text-[var(--color-ink)]">{fig(p, p.value)}{p.percentile != null && p.distribution.n > 1 ? <span className="text-[var(--color-faint)]"> · {p.percentile}th</span> : null}</span>
            <span className="sm:text-right"><StatusChip label={p.flag_label ?? undefined} tone={FLAG_TONE[p.flag] ?? 'neutral'} /></span>
          </div>))}</div>
      </Card>}

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <SectionHead icon={MapPin} hint="largest regions by value">Where the book sits</SectionHead>
          <div className="mt-3"><HBar labelWidth="w-40" format={balance} data={d.book.top_regions.map(r => ({
            label: r.country_name && !r.name.includes(r.country_name) ? `${r.name} · ${r.country_name}` : r.name,
            value: r.value_eur, color: severityHex(r.max_score),
            sub: r.max_score != null ? `${Math.round(r.max_score)} · ${hazardName(r.worst_hazard)}` : 'Not scored' }))} /></div>
        </Card>
        <Card className="p-5">
          <SectionHead hint="value by its biggest threat">Headline hazards</SectionHead>
          <div className="mt-3"><HBar labelWidth="w-40" format={balance} data={d.book.hazards.map(h => ({ label: hazardName(h.hazard), value: h.value_eur, sub: `${h.n} assets` }))} /></div>
        </Card>
      </div>

      <Card className="p-5">
        <SectionHead hint="the entity sees it too">Your recent access</SectionHead>
        <ol className="mt-3 space-y-1.5 list-none p-0 m-0">{d.my_recent_accesses.map((a, i) => (
          <li key={i} className="flex items-center gap-3 text-[12.5px]"><span className="w-2 h-2 rounded-full bg-[var(--color-sky)]/60 shrink-0" />
            <span className="text-[var(--color-ink)] mr-auto">{a.label}</span><span className="text-[var(--color-faint)] tabular-nums">{day(a.at)}</span></li>))}</ol>
      </Card>
      <TransmissionsReceived orgId={orgId} />
      <EvidencePacks orgId={orgId} />
      <RemittancesIssued orgId={orgId} />
    </div>
  )
}
