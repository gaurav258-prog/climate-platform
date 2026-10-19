import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, ChevronRight, Clock, Gauge, CheckCircle2, AlertTriangle, ShieldAlert, ShieldCheck, ListPlus } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import { Card, Lens, ExportButton, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import { HEADING, InfoButton, MessageLine, messageDetails } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import ReviewTabs from '../components/ReviewTabs'
import DetectionLag from '../components/DetectionLag'
import RegNotifications from '../components/RegNotifications'
import KriTemplateRows from '../components/KriTemplateRows'
import { HBar } from '../components/Charts'
import { downloadCsv } from '../lib/export'
import { hazardLabel } from '../lib/labels'
import { sevColor } from '../lib/hazards'
import { filingLink } from '../lib/links'
import { balance } from '../lib/money'
import AppetiteBar from './kri/AppetiteBar'
import { HazardDrill, KriDetail, Provenance, raiseTask } from './kri/KriDrawer'
import { RAG, STATUS_WORD, bandWords, kindOf, value, type Framework, type Kpi, type KriSet } from './kri/model'
import { heroTitle } from './kri/words'

// Key risk indicators, to the UI standard (2026-10-16): how each indicator of a report sits against the organisation's
// appetite, as figures and bars; everything else — how a figure is computed, the facts behind it, its trend, what drives
// it and where it is reported — opens from the indicator (kri/KriDrawer.tsx). The server sends numbers, names and
// catalogue messages (services/governance/kri*.py).

const ABOUT = [
  { heading: HEADING.shows, body: 'The key risk indicators of the report you choose, each graded against the appetite band your organisation sets: within appetite, warning or breach.' },
  { heading: HEADING.read, body: 'Each tile shows the figure and, where a band is set, where it sits in the band. Open a tile for how it is computed, the facts behind it, its trend across filings and the exposures that drive it. A filled dot marks a figure the platform computes; a ring marks one you provide.' },
  { heading: HEADING.sources, body: 'Your uploaded book, scored on the platform’s hazard data; the figures you provide; and the filings you have made, for the trend.' },
  { heading: HEADING.limits, body: 'The tiles are recomputed from today’s book each time you open the page. They are not necessarily what you last filed: the trend shows what each filing printed.' },
]
// the report a sector reports on first, until the list of its reports arrives
const FIRST: Record<string, string> = { bank: 'bank_tcfd', asset_manager: 'sfdr_pai', reit: 'reit_taxonomy', insurer: 'insurer_solvency', manufacturer: 'esrs_pack' }
const chip = (on: boolean) => `px-3 py-1.5 rounded-lg text-[12px] border transition ${on ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`

export default function Kri() {
  const { profile } = useAuth()
  const orgType = profile?.org?.type ?? ''
  // an organisation can report on several frameworks (a bank: the EU Taxonomy report and Pillar 3 ESG) — pick one
  const fwq = useQuery({ queryKey: ['kri-frameworks'], queryFn: () => api.get<{ frameworks: Framework[] }>('/v1/reg-tasks/kri/frameworks') })
  const frameworks = fwq.data?.frameworks ?? []
  const [picked, setPicked] = useState<string | null>(null)
  const framework = picked ?? frameworks[0]?.framework ?? FIRST[orgType] ?? 'bank_tcfd'
  // the forward (scenario) view serves the books it models: bank, asset manager, property
  const hasAnalytics = ['bank', 'asset_manager', 'reit'].includes(orgType)
  const [drill, setDrill] = useState<string | null>(null)
  const [detail, setDetail] = useState<string | null>(null)
  const [prov, setProv] = useState<'all' | 'computed' | 'integrated'>('all')
  const [onlyBreaches, setOnlyBreaches] = useState(false)
  const [entity, setEntity] = useState<string | null>(null)          // the undertaking an ESRS set is for
  const eq = entity && framework === 'esrs_pack' ? `&entity_id=${entity}` : ''
  const q = useQuery({ queryKey: ['kri', framework, eq], queryFn: () => api.get<KriSet>(`/v1/reg-tasks/kri?framework=${framework}${eq}`) })
  const d = q.data
  const undertakings = d?.undertakings ?? []
  const tiles = d?.kpis?.filter(k => !k.group) ?? []          // a grouped set (the sector rows) is picked by row below
  const n = (s: string) => tiles.filter(k => k.status === s).length
  const nRed = n('red'), nAmber = n('amber'), nOk = n('ok')
  const nComputed = tiles.filter(k => kindOf(k) === 'computed').length
  const nProvided = tiles.length - nComputed
  const canRaise = profile?.permissions?.includes('approvals.create') ?? false

  const exportKri = () => {
    if (!d?.kpis?.length) return
    downloadCsv(`tellumen-kri-${framework}`,
      [{ key: 'label', label: 'Indicator' }, { key: 'value', label: 'Value' }, { key: 'status', label: 'Appetite' },
       { key: 'band', label: 'Appetite band' }, { key: 'datapoint', label: 'Regulatory datapoint' }, { key: 'source', label: 'Source' }],
      d.kpis.map(k => ({
        label: k.label, value: value(k), status: k.status ? STATUS_WORD[k.status] : '', band: k.amber != null || k.red != null ? bandWords(k) : '',
        datapoint: k.reg ?? '', source: kindOf(k) === 'integrated' ? 'You provide' : 'Computed by Tellumen',
      })),
      { title: `Key risk indicators · ${d.label}`, org: profile?.org?.name, basis: { framework: d.label } })
  }

  return (
    <div className="fadeup space-y-5">
      <ReviewTabs />
      <PageHeader eyebrow="Govern · Key risk indicators" title="Are we within appetite?" about={ABOUT}
        lead="Your indicators against appetite, and how they move."
        actions={<>{d?.supported && !!d.kpis?.length && <ExportButton onExport={exportKri} />}<Lens kind="governance" /></>} />

      {frameworks.length > 1 && (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Report">
          {frameworks.map(f => <button key={f.framework} onClick={() => setPicked(f.framework)} className={chip(framework === f.framework)}>{f.label}</button>)}
        </div>
      )}
      {framework === 'esrs_pack' && undertakings.length > 1 && (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Undertaking">
          {undertakings.map(u => (
            <button key={u.entity_id ?? 'org'} onClick={() => setEntity(u.entity_id)} className={chip((d?.undertaking?.entity_id ?? null) === u.entity_id)}>
              {u.name}{u.role === 'consolidated' ? ' (group)' : ''}</button>
          ))}
        </div>
      )}

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">Loading…</Card>
        : !d || !d.supported || !d.kpis.length ? <Unavailable d={d} framework={framework} />
        : (<>
          <HeroBanner eyebrow={d.label}
            title={heroTitle({ red: nRed, amber: nAmber, ok: nOk })}
            stat={[
              { label: 'Indicators', value: tiles.length, icon: Gauge, tone: 'var(--color-sky)' },
              { label: 'Within appetite', value: nOk, icon: CheckCircle2, tone: nOk > 0 ? 'var(--color-good)' : undefined },
              { label: 'Warning', value: nAmber, icon: AlertTriangle, tone: nAmber > 0 ? 'var(--color-warn)' : undefined },
              { label: 'In breach', value: nRed, icon: ShieldAlert, tone: nRed > 0 ? 'var(--color-bad)' : 'var(--color-good)', pulse: nRed > 0, onClick: nRed > 0 ? () => setOnlyBreaches(v => !v) : undefined },
            ]} />
          <Basis d={d} />

          <div className="flex items-center gap-2 flex-wrap">
            <ProvButton on={prov === 'computed'} onClick={() => setProv(p => p === 'computed' ? 'all' : 'computed')} n={nComputed} provided={false} />
            <ProvButton on={prov === 'integrated'} onClick={() => setProv(p => p === 'integrated' ? 'all' : 'integrated')} n={nProvided} provided disabled={nProvided === 0} />
            {nRed > 0 && (
              <button onClick={() => setOnlyBreaches(v => !v)} className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] border transition ${onlyBreaches ? 'border-[var(--color-bad)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-bad)]'}`}>
                <span className="w-2 h-2 rounded-full" style={{ background: RAG.red }} />{onlyBreaches ? 'Show all' : `Only the ${nRed} in breach`}
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3">
            {tiles.filter(k => (prov === 'all' || kindOf(k) === prov) && (!onlyBreaches || k.status === 'red')).map(k => (
              <Tile key={k.key} k={k} onOpen={() => setDetail(k.key)} onRaise={canRaise && k.status === 'red' ? () => raiseTask(framework, k) : undefined} />
            ))}
          </div>

          <Reference d={d} hasAnalytics={hasAnalytics} orgType={orgType} setDrill={setDrill} setDetail={setDetail} />
          {/* how long breaches sat before action, and the regulatory-notification clock a breach may start */}
          <DetectionLag framework={framework} />
          <RegNotifications framework={framework} />
        </>)}

      {drill && <HazardDrill framework={framework} entityQ={eq} hazard={drill} hasAnalytics={hasAnalytics} onClose={() => setDrill(null)} />}
      {detail && <KriDetail framework={framework} entityQ={eq} kriKey={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

function Unavailable({ d, framework }: { d?: KriSet; framework: string }) {
  const nav = useNavigate()
  return (
    <Card className="p-8 text-[13px] text-[var(--color-mute)] flex flex-wrap items-center gap-3">
      {d?.notice ? <MessageLine m={d.notice} /> : <span>No indicators for this report yet.</span>}
      {framework === 'esrs_pack' && <button onClick={() => nav('/esrs')} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Open the ESRS statement <ArrowUpRight size={12} /></button>}
    </Card>
  )
}

// live, not filed: the tiles are recomputed from today's book; the last filing is one click away
function Basis({ d }: { d: KriSet }) {
  const nav = useNavigate()
  const { profile } = useAuth()
  if (!d.basis) return null
  const last = d.basis.last_filed
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px] text-[var(--color-mute)]">
      <span className="inline-flex items-center gap-1.5"><Clock size={13} className="text-[var(--color-sky)]" /><MessageLine m={d.basis.message} /></span>
      {last && (last.filing_id
        ? <button onClick={() => nav(filingLink(profile?.org?.type, last.filing_id!))} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Last filed: {last.period_label}<ChevronRight size={12} /></button>
        : <span>Last filed: {last.period_label}</span>)}
    </div>
  )
}

function ProvButton({ on, onClick, n, provided, disabled }: { on: boolean; onClick: () => void; n: number; provided: boolean; disabled?: boolean }) {
  const c = provided ? 'var(--color-slate)' : 'var(--color-blue)'
  return (
    <button disabled={disabled} onClick={onClick} aria-pressed={on}
      className={`inline-flex items-center gap-1.5 rounded-full pl-2 pr-2.5 py-1 text-[12px] border transition disabled:opacity-45 disabled:cursor-default ${on ? 'text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}
      style={on ? { borderColor: c, background: `color-mix(in oklab, ${c} 12%, transparent)` } : undefined}>
      <span className="w-2 h-2 rounded-full shrink-0 box-border" style={provided ? { border: `1.5px solid ${c}` } : { background: c }} />
      {provided ? 'You provide' : 'Computed by Tellumen'} <b className="tabular-nums text-[var(--color-ink)]">{n}</b>
    </button>
  )
}

// one indicator: the figure, its name, where it sits in its band, and what it is waiting for
function Tile({ k, onOpen, onRaise }: { k: Kpi; onOpen: () => void; onRaise?: () => void }) {
  const waiting = k.needs ?? (k.gap ? { label: 'Needs your input' } : null) ?? k.missing
  return (
    <Card onClick={onOpen} className="px-4 py-3.5 cursor-pointer hover:border-[var(--color-line-2)] transition group flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="display text-[22px] leading-none tabular-nums" style={{ color: k.status ? RAG[k.status] : k.tone ?? undefined }}>{value(k)}</div>
        {k.status && <span className="w-2.5 h-2.5 rounded-full shrink-0 mt-1" style={{ background: RAG[k.status] }} title={STATUS_WORD[k.status]} />}
      </div>
      <div className="text-[12.5px] leading-snug text-[var(--color-ink)]">{k.label}</div>
      <AppetiteBar k={k} />
      <div className="mt-auto flex items-center justify-between gap-2 pt-0.5">
        <Provenance k={k} compact />
        <ArrowUpRight size={13} className="text-[var(--color-faint)] opacity-0 group-hover:opacity-100 transition" />
      </div>
      {waiting && <StatusChip label={waiting.label} tone="warn" className="self-start max-w-full truncate" />}
      {onRaise && (
        <button onClick={e => { e.stopPropagation(); onRaise() }} className="self-start inline-flex items-center gap-1 text-[12px] text-[var(--color-bad)] hover:underline">
          <ListPlus size={12} /> Raise a task
        </button>
      )}
    </Card>
  )
}

// the set's context behind tabs: by sector row, by hazard, the trend across filings and the regulator's view
function Reference({ d, hasAnalytics, orgType, setDrill, setDetail }: {
  d: KriSet; hasAnalytics: boolean; orgType: string; setDrill: (h: string) => void; setDetail: (k: string) => void
}) {
  const nav = useNavigate()
  const rowKpis = d.kpis.filter(k => k.group)
  const tabs = [
    ...(rowKpis.length ? [{ k: 'rows', label: 'By sector row' }] : []),
    ...(d.by_hazard.length ? [{ k: 'hazard', label: 'By hazard' }] : []),
    { k: 'trend', label: 'Filed trend' },
    ...(d.regulator ? [{ k: 'reg', label: 'Regulator' }] : []),
  ]
  const [tab, setTab] = useState(tabs[0].k)
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex gap-1 px-2.5 py-2 border-b border-[var(--color-line)] bg-[var(--color-bg-2)] flex-wrap" role="tablist">
        {tabs.map(t => (
          <button key={t.k} role="tab" aria-selected={tab === t.k} onClick={() => setTab(t.k)}
            className={`text-[12.5px] px-3 py-1.5 rounded-md transition ${tab === t.k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{t.label}</button>
        ))}
      </div>
      <div className="p-4">
        {tab === 'rows' && <KriTemplateRows kpis={rowKpis} history={d.history} onOpen={setDetail} />}
        {tab === 'hazard' && (
          <div>
            <div className="flex items-center mb-3 gap-2">
              <SectionHead>Value at risk by hazard</SectionHead>
              {hasAnalytics && <button onClick={() => nav('/analytics')} className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">Explore forward <ChevronRight size={12} /></button>}
            </div>
            <HBar labelWidth="w-44" data={d.by_hazard.map(h => ({ label: hazardLabel(h.hazard), value: h.value, color: sevColor(h.score) }))} format={balance} onBar={i => setDrill(d.by_hazard[i].hazard)} />
          </div>
        )}
        {tab === 'trend' && <FiledTrend d={d} orgType={orgType} />}
        {tab === 'reg' && d.regulator && <RegulatorView d={d} />}
      </div>
    </Card>
  )
}

// what each filing printed, figure by figure: a bar per filing, newest last; a bar opens its filing
function FiledTrend({ d, orgType }: { d: KriSet; orgType: string }) {
  const nav = useNavigate()
  if (!d.history.length) return <div className="py-4 text-[13px] text-[var(--color-faint)]">No filing yet.</div>
  const series = d.history.some(h => h.figures)
    ? [...new Map(d.history.flatMap(h => (h.figures ?? []).filter(f => !f.group).map(f => [f.key, { key: f.key, label: f.label, fmt: f.fmt }]))).values()]
    : [{ key: 'total_value', label: 'Book value', fmt: 'eur' }, { key: 'value_at_risk', label: 'Value at risk', fmt: 'eur' }]
  const at = (h: KriSet['history'][number], key: string) => h.figures
    ? h.figures.find(f => f.key === key)?.value ?? null
    : (h as unknown as Record<string, number | null>)[key] ?? null
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {series.map(s => {
        const vals = d.history.map(h => at(h, s.key))
        const max = Math.max(1, ...vals.map(v => Math.abs(v ?? 0)))
        return (
          <div key={s.key} className="rounded-xl border border-[var(--color-line)] p-3">
            <div className="text-[12.5px] text-[var(--color-ink)] mb-2">{s.label}</div>
            <div className="flex items-end gap-1 h-20">
              {d.history.map((h, i) => {
                const v = vals[i]
                return (
                  <button key={i} disabled={!h.filing_id} onClick={() => h.filing_id && nav(filingLink(orgType, h.filing_id))} title={`${h.label}: ${value({ value: v, fmt: s.fmt as Kpi['fmt'] })}`}
                    className="flex-1 min-w-0 h-full flex flex-col justify-end group">
                    <span className="block w-full rounded-t transition group-hover:brightness-125" style={{ height: v == null ? 2 : `${Math.max(4, 100 * Math.abs(v) / max)}%`, background: v == null ? 'var(--color-line-2)' : 'var(--color-sky)', opacity: v == null ? 1 : 0.8 }} />
                  </button>
                )
              })}
            </div>
            <div className="flex justify-between text-[11px] text-[var(--color-faint)] mt-1.5 tabular-nums">
              <span>{d.history[0].label}</span><span className="text-[var(--color-ink)]">{value({ value: vals[vals.length - 1], fmt: s.fmt as Kpi['fmt'] })}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

// what the regulator expects: the authority and disclosure, and how many of its headline datapoints carry a value
function RegulatorView({ d }: { d: KriSet }) {
  const reg = d.regulator!
  const r = d.readiness
  const pct = r && r.core ? Math.round(100 * r.covered / r.core) : null
  return (
    <div className="grid gap-5 md:grid-cols-[1fr_1.2fr]">
      <div className="space-y-2">
        <div className="flex items-center gap-2"><ShieldCheck size={16} className="text-[var(--color-sky)]" /><span className="text-[14px] font-semibold text-[var(--color-ink)]">{reg.authority}</span></div>
        <div className="text-[12.5px] text-[var(--color-mute)]">{reg.disclosure}</div>
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <InfoButton label="Legal basis" details={{ title: reg.disclosure, sections: [{ heading: 'Legal basis', body: reg.legal_basis }] }} />
          {reg.form_url && <a href={reg.form_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[12.5px] text-[var(--color-sky)] hover:underline">Official text <ArrowUpRight size={12} /></a>}
          {d.scope && <InfoButton label="Scope of these figures" details={messageDetails(d.scope)} />}
        </div>
      </div>
      {r && r.core > 0 && (
        <div className="space-y-2.5">
          <div className="flex items-baseline justify-between">
            <span className="text-[12.5px] text-[var(--color-mute)]">Headline datapoints with a value</span>
            <span className="display text-[20px] tabular-nums" style={{ color: r.covered >= r.core ? 'var(--color-good)' : 'var(--color-warn)' }}>{r.covered} of {r.core}</span>
          </div>
          <div className="h-2 rounded-full bg-[var(--color-panel-2)] overflow-hidden"><div className="h-full rounded-full" style={{ width: `${pct}%`, background: r.covered >= r.core ? 'var(--color-good)' : 'var(--color-warn)' }} /></div>
          {(r.integrated.length > 0 || r.gaps.length > 0) && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {r.integrated.length > 0 && <StatusChip label={`${r.integrated.length} you provide`} tone="neutral" />}
              {r.gaps.length > 0 && <StatusChip label={`${r.gaps.length} awaiting data`} tone="warn" />}
              <InfoButton compact details={{ title: 'Datapoints without a value', sections: [
                ...(r.integrated.length ? [{ heading: 'You provide', body: r.integrated.join(', ') }] : []),
                ...(r.gaps.length ? [{ heading: 'Awaiting data', body: r.gaps.join(', ') }] : []),
              ] }} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
