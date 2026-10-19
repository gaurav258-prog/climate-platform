import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, ChevronRight, ListPlus, SlidersHorizontal, Upload } from 'lucide-react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ComposedChart, Area, ReferenceLine, ReferenceArea } from 'recharts'
import { useAuth } from '../../lib/auth'
import { api, apiMessage } from '../../lib/api'
import { useResizableWidth } from '../../lib/resizable'
import { hazardLabel, bucketLabel } from '../../lib/labels'
import { sevColor } from '../../lib/hazards'
import { filingLink } from '../../lib/links'
import { toast } from '../../lib/toast'
import { balance } from '../../lib/money'
import { pressable } from '../../lib/pressable'
import { HBar } from '../../components/Charts'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import MethodGap from '../../components/MethodGap'
import { StatusChip } from '../../components/StatusChip'
import { InfoButton, MessageLine, messageDetails, type Message } from '../../components/Details'
import AssetDrawer, { type DrawerCfg } from '../../components/AssetDrawer'
import AppetiteBar from './AppetiteBar'
import { RAG, STATUS_WORD, bandWords, factValue, kindOf, value, type Kpi, type Regulator } from './model'
import { bandSaved } from './words'

// The drawers behind the KRI dashboard (UI standard, 2026-10-16): one indicator — its explanation, its band, the facts
// behind it, its trend, its make-up and the exposures that drive it, and where it is reported — and one hazard's
// exposures. Every word the server sends is a catalogue message; the regulatory reference sits here, one click away.

// the asset detail per bank / property framework — an exposure row opens the full asset drawer
const DRAWER_CFG: Record<string, DrawerCfg> = {
  bank_tcfd: { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  bank_p3esg: { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  reit_taxonomy: { prefix: 'realestate', itemKey: 'property', nameKey: 'property_name', valueKey: 'property_value_eur', typeKey: 'property_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
}
const W = 'w-full h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto'
const tipStyle = { background: 'var(--color-panel)', border: '1px solid var(--color-line)', borderRadius: 8, fontSize: 12 }

export async function raiseTask(framework: string, k: Kpi) {
  try {
    await api.post('/v1/reg-tasks/kri/spin-task', { framework, key: k.key, label: k.label, detail: bandWords(k) })
    toast.success(`Task raised for “${k.label}”.`)
  } catch (e) {
    toast.error(apiMessage(e, 'Could not raise the task.'))
  }
}

function Section({ title, info, children }: { title: string; info?: Message | null; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2">
        <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0">{title}</h4>
        {info && <InfoButton compact details={messageDetails(info)} />}
      </div>
      {children}
    </section>
  )
}

// who the figure comes from: a filled dot, computed by the platform; a ring, a figure you provide (compact: the dot alone,
// its words for assistive technology and on hover — the legend above the grid names both)
export function Provenance({ k, compact }: { k: Kpi; compact?: boolean }) {
  const provided = kindOf(k) === 'integrated'
  const word = provided ? 'You provide' : 'Computed by Tellumen'
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]" title={compact ? word : undefined}>
      <span className="w-2 h-2 rounded-full box-border shrink-0" style={provided ? { border: '1.5px solid var(--color-slate)' } : { background: 'var(--color-blue)' }} />
      {compact ? <span className="sr-only">{word}</span> : word}
    </span>
  )
}

interface Comp { type: 'hazard' | 'scope' | 'coverage' | 'taxonomy' | 'sector' | 'horizon'; unit: 'eur' | 'num' | 'pct'; items: { key: string; label: string; value: number; score?: number }[] }
interface Driver { id?: string | null; name: string; country?: string | null; sector_name?: string | null; value: number; hazard?: string | null; bucket?: string | null; score?: number | null }
interface Drivers { unit: 'eur' | 'num'; total_count: number; items: Driver[] }
interface Projection { points: { horizon: string; value: number; lo: number; hi: number }[]; unit: 'eur' | 'pct'; warn?: number | null; breach?: number | null; scenario_name: string; message: Message }
interface Detail {
  supported: boolean; notice?: Message; framework: string; kpi: Kpi; regulator?: Regulator
  trend: { points: { label: string; value: number | null; filing_id?: string }[]; fmt: string; flow?: boolean }
  projection?: Projection | null; composition?: Comp | null; drivers?: Drivers | null; actions: { analytics: boolean; provide: boolean }
}
const COMP_TITLE: Record<Comp['type'], string> = {
  hazard: 'By hazard', scope: 'By emissions scope', coverage: 'Scored and not scored', taxonomy: 'Eligible and not eligible',
  sector: 'By high-climate-impact sector', horizon: 'By future year',
}
const DRILLABLE = new Set<Comp['type']>(['scope', 'sector', 'hazard'])
const amount = (v: number, unit?: string) => unit === 'eur' ? balance(v) : unit === 'pct' ? `${v}%` : Math.round(v).toLocaleString('en-GB')

export function KriDetail({ framework, entityQ, kriKey, onClose }: { framework: string; entityQ: string; kriKey: string; onClose: () => void }) {
  const nav = useNavigate()
  const { profile } = useAuth()
  const perms = profile?.permissions ?? []
  const canSetAppetite = perms.includes('admin.approval_policy.manage')
  const canRaise = perms.includes('approvals.create')
  const [raising, setRaising] = useState(false)
  const { width, setWidth, startResize } = useResizableWidth('tellumen.drawerw', 480, 360, 860, 'right')
  const q = useQuery({ queryKey: ['kri-detail', framework, kriKey, entityQ], queryFn: () => api.get<Detail>(`/v1/reg-tasks/kri/detail?framework=${framework}&kri=${encodeURIComponent(kriKey)}${entityQ}`) })
  const d = q.data
  // a clicked composition bar narrows the exposures to that part; a clicked exposure opens the asset itself
  const [seg, setSeg] = useState<{ type: string; value: string; label: string } | null>(null)
  const [assetId, setAssetId] = useState<string | null>(null)
  const segQ = useQuery({
    queryKey: ['kri-drivers-seg', framework, kriKey, seg?.type, seg?.value], enabled: !!seg,
    queryFn: () => api.get<Drivers>(`/v1/reg-tasks/kri/drivers?framework=${framework}&kri=${encodeURIComponent(kriKey)}&seg_type=${seg!.type}&seg_value=${encodeURIComponent(seg!.value)}`),
  })
  const drawerCfg = DRAWER_CFG[framework]
  // Analytics opens scoped to what drives this indicator: its peril group, or the forward pathway
  const analyticsHref = (key: string, label: string) => {
    const p = new URLSearchParams({ from: label })
    if (key === 'acute_share') p.set('perils', 'acute')
    else if (key === 'chronic_share') p.set('perils', 'chronic')
    else if (key === 'forward_share') p.set('scenario', 'disorderly_2c')
    return `/analytics?${p.toString()}`
  }
  return (
    <Drawer label="Indicator" onClose={onClose} style={{ width, maxWidth: '96vw' }} resize={{ start: startResize, reset: () => setWidth(480) }} className={W}>
      {!d ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Loading…</div>
        : !d.supported ? (
          <div className="p-6 flex items-start justify-between gap-3 text-[13px] text-[var(--color-mute)]">
            {d.notice ? <MessageLine m={d.notice} /> : <span>No detail for this indicator.</span>}
            <CloseButton onClick={onClose} size={17} icon="back" />
          </div>
        ) : (() => {
          const k = d.kpi
          // how it is computed: the catalogue's 'what', then its note ('why'); what to do about a gap is MethodGap's
          const about = [
            ...(k.about?.detail?.what ? [{ heading: '', body: k.about.detail.what }] : []),
            ...(k.about?.detail?.why ? [{ heading: 'Note', body: k.about.detail.why }] : []),
          ]
          return (<>
            <div className="sticky top-0 z-10 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3.5 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Provenance k={k} />
                <div className="display text-[28px] leading-none mt-2 tabular-nums" style={{ color: k.status ? RAG[k.status] : k.tone ?? undefined }}>{value(k)}</div>
                <div className="text-[13.5px] text-[var(--color-ink)] mt-1.5">{k.label}</div>
                {k.status && <StatusChip className="mt-2" label={STATUS_WORD[k.status]} tone={k.status === 'ok' ? 'good' : k.status === 'amber' ? 'warn' : 'bad'} />}
              </div>
              <CloseButton onClick={onClose} size={17} icon="back" />
            </div>
            <div className="p-5 space-y-6">
              {(k.gap || k.missing || k.needs) && (
                <div className="space-y-2">
                  <MethodGap gap={k.gap} what={k.label} />
                  {k.missing && <div className="text-[12.5px] text-[var(--color-warn)]"><MessageLine m={k.missing} /></div>}
                  {k.needs && <div className="text-[12.5px] text-[var(--color-mute)]"><MessageLine m={k.needs} /></div>}
                </div>
              )}
              <Appetite k={k} framework={framework} canSet={canSetAppetite} onSaved={() => q.refetch()} />
              {about.length > 0 && (
                <Section title="How it is computed">
                  <div className="space-y-2.5 text-[13px] leading-relaxed text-[var(--color-ink)]">
                    {about.map((x, i) => <div key={i}>{x.heading && <div className="text-[12px] font-medium text-[var(--color-mute)] mb-0.5">{x.heading}</div>}{x.body}</div>)}
                  </div>
                </Section>
              )}
              {k.facts.length > 0 && (
                <Section title="Behind the figure">
                  <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1.5 text-[12.5px] m-0">
                    {k.facts.map(f => <div key={f.key} className="contents"><dt className="text-[var(--color-mute)]">{f.label}</dt><dd className="m-0 text-right tabular-nums text-[var(--color-ink)]">{factValue(f)}</dd></div>)}
                  </dl>
                </Section>
              )}
              {d.projection && d.projection.points.length >= 2 && <ProjectionChart pr={d.projection} />}
              <Section title="Trend across filings">
                {d.trend.points.length >= 2 ? <TrendChart d={d} onOpen={fid => nav(filingLink(profile?.org?.type, fid))} />
                  : <div className="text-[12.5px] text-[var(--color-mute)]">{k.filed && k.live_only ? <MessageLine m={k.filed} /> : 'Shown once two filings print it.'}</div>}
              </Section>
              {d.composition && d.composition.items.length > 0 && (() => {
                const comp = d.composition
                const drill = DRILLABLE.has(comp.type)
                const total = comp.items.reduce((s, it) => s + it.value, 0)
                let cum = 0
                return (
                  <Section title={COMP_TITLE[comp.type]}>
                    <HBar labelWidth="w-40" format={n => amount(n, comp.unit)}
                      data={comp.items.map(it => {
                        cum += it.value
                        return { label: it.label, value: it.value, color: comp.type === 'hazard' ? sevColor(it.score ?? 0) : 'var(--color-sky)', ...(comp.type === 'sector' && total ? { sub: `${Math.round(100 * cum / total)}% cumulative` } : {}) }
                      })}
                      {...(drill ? { onBar: (i: number) => { const it = comp.items[i]; setSeg({ type: comp.type, value: it.key, label: it.label }) } } : {})} />
                  </Section>
                )
              })()}
              <Exposures d={d} k={k} seg={seg} segData={segQ.data} clearSeg={() => setSeg(null)} openAsset={drawerCfg ? setAssetId : null} />
              <Reported k={k} regulator={d.regulator} />
              <div className="flex flex-wrap gap-2 pt-1">
                {k.status === 'red' && canRaise && (
                  <button disabled={raising} onClick={async () => { setRaising(true); await raiseTask(framework, k); setRaising(false) }}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] hover:brightness-110 transition disabled:opacity-50">
                    <ListPlus size={13} /> {raising ? 'Raising…' : 'Raise a task to fix it'}
                  </button>
                )}
                {d.actions.analytics && <button onClick={() => nav(analyticsHref(kriKey, k.label))} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-ink)] transition"><ArrowUpRight size={13} /> Explore forward</button>}
                {d.actions.provide && <button onClick={() => nav('/compliance')} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-slate)] hover:text-[var(--color-ink)] transition"><Upload size={13} /> Provide this figure</button>}
              </div>
            </div>
          </>)
        })()}
      {assetId && drawerCfg && <AssetDrawer cfg={drawerCfg} id={assetId} onClose={() => setAssetId(null)} onChanged={() => { segQ.refetch(); q.refetch() }} />}
    </Drawer>
  )
}

// the appetite band: where the value sits, and — for an administrator — the band itself, set here in context
function Appetite({ k, framework, canSet, onSaved }: { k: Kpi; framework: string; canSet: boolean; onSaved: () => void }) {
  const [edit, setEdit] = useState(false)
  const [band, setBand] = useState<{ amber?: number; red?: number; direction?: string }>({})
  const [saving, setSaving] = useState(false)
  const gradeable = k.fmt === 'pct' || k.fmt === 'eur' || k.fmt === 'num'
  if (!k.status && !(canSet && gradeable)) return null
  const hasBand = k.amber != null || k.red != null
  const start = () => { setBand({ amber: k.amber ?? undefined, red: k.red ?? undefined, direction: k.direction ?? 'higher_worse' }); setEdit(true) }
  const save = async () => {
    setSaving(true)
    try {
      const r = await api.patch<{ status?: string }>('/v1/admin/kri-appetite', { kri_key: k.key, framework, amber: band.amber, red: band.red, direction: band.direction })
      // a change that needs a second person's approval is sent for it; the band changes once approved
      toast.success(bandSaved(r.status))
      setEdit(false); onSaved()
    } catch (e) { toast.error(apiMessage(e, 'Could not update the appetite band.')) } finally { setSaving(false) }
  }
  const worse = (band.direction ?? 'higher_worse') === 'lower_worse' ? '≤' : '≥'
  const unit = k.fmt === 'eur' ? ' (EUR)' : k.fmt === 'pct' ? ' (%)' : ''
  const inp = 'w-24 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12.5px] tabular-nums'
  return (
    <Section title="Appetite">
      <div className="rounded-xl border border-[var(--color-line)] px-3.5 py-3 space-y-2.5">
        {hasBand ? <AppetiteBar k={k} showLevels /> : <div className="text-[12.5px] text-[var(--color-mute)]">No appetite band set.</div>}
        {canSet && !edit && (
          <button onClick={start} className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline">
            <SlidersHorizontal size={12} /> {hasBand ? 'Adjust the band' : 'Set a band'}
          </button>
        )}
        {edit && (
          <div className="pt-2.5 border-t border-[var(--color-line-2)] flex flex-wrap items-end gap-2.5">
            <label className="block text-[11.5px] text-[var(--color-mute)]">Worse when
              <select value={band.direction ?? 'higher_worse'} onChange={e => setBand(b => ({ ...b, direction: e.target.value }))} className="block mt-1 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12.5px]">
                <option value="higher_worse">higher</option><option value="lower_worse">lower</option></select></label>
            <label className="block text-[11.5px] text-[var(--color-mute)]">Warning {worse}{unit}
              <input type="number" value={band.amber ?? ''} onChange={e => setBand(b => ({ ...b, amber: e.target.value === '' ? undefined : Number(e.target.value) }))} className={`block mt-1 ${inp}`} /></label>
            <label className="block text-[11.5px] text-[var(--color-mute)]">Breach {worse}{unit}
              <input type="number" value={band.red ?? ''} onChange={e => setBand(b => ({ ...b, red: e.target.value === '' ? undefined : Number(e.target.value) }))} className={`block mt-1 ${inp}`} /></label>
            <div className="flex gap-1.5 ml-auto">
              <button onClick={save} disabled={saving} className="rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] px-3 py-1.5 text-[12px] disabled:opacity-50">{saving ? 'Saving…' : 'Save'}</button>
              <button onClick={() => setEdit(false)} className="rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)]">Cancel</button>
            </div>
          </div>
        )}
      </div>
    </Section>
  )
}

function ProjectionChart({ pr }: { pr: Projection }) {
  const pf = (v: number) => pr.unit === 'eur' ? balance(v) : `${Math.round(v)}%`
  // the climate models' range as one band behind the line (as on Portfolio's forward view)
  const rows = pr.points.map(p => ({ ...p, band: [p.lo, p.hi] as [number, number] }))
  const tip = (v: unknown, n: unknown) => Array.isArray(v) ? [`${pf(Number(v[0]))} – ${pf(Number(v[1]))}`, 'Range across climate models'] : [pf(Number(v)), n === 'value' ? 'Central estimate' : String(n)]
  return (
    <Section title={`Projected · ${pr.scenario_name}`} info={pr.message}>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 6, right: 12, bottom: 2, left: 4 }}>
            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 5" vertical={false} />
            <XAxis dataKey="horizon" tickFormatter={h => h === 'current' ? 'Today' : h} tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={{ stroke: 'var(--color-line)' }} tickLine={false} />
            <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={pf} />
            <Tooltip formatter={tip as never} labelFormatter={h => h === 'current' ? 'Today' : h} contentStyle={tipStyle} />
            {pr.breach != null && <ReferenceArea y1={pr.breach} y2={100000000000} fill="var(--color-bad)" fillOpacity={0.06} />}
            {pr.warn != null && pr.breach != null && <ReferenceArea y1={pr.warn} y2={pr.breach} fill="var(--color-warn)" fillOpacity={0.06} />}
            <Area type="monotone" dataKey="band" stroke="none" fill="var(--color-sky)" fillOpacity={0.16} isAnimationActive={false} activeDot={false} />
            {pr.warn != null && <ReferenceLine y={pr.warn} stroke="var(--color-warn)" strokeDasharray="5 4" strokeWidth={1} />}
            {pr.breach != null && <ReferenceLine y={pr.breach} stroke="var(--color-bad)" strokeDasharray="5 4" strokeWidth={1} />}
            <Line type="monotone" dataKey="value" stroke="var(--color-sky)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-sky)' }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Section>
  )
}

function TrendChart({ d, onOpen }: { d: Detail; onOpen: (filingId: string) => void }) {
  const tf = (v: number) => value({ value: v, fmt: d.trend.fmt as Kpi['fmt'], flow: d.trend.flow })
  return (
    <div className="h-40">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={d.trend.points} margin={{ top: 6, right: 12, bottom: 2, left: 4 }}>
          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 5" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={{ stroke: 'var(--color-line)' }} tickLine={false} />
          <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={false} tickLine={false} width={48} tickFormatter={tf} />
          <Tooltip formatter={v => tf(Number(v))} contentStyle={tipStyle} />
          <Line type="monotone" dataKey="value" stroke="var(--color-sky)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-sky)' }} isAnimationActive={false} style={{ cursor: 'pointer' }}
            activeDot={{ r: 5, style: { cursor: 'pointer' }, onClick: (props: unknown) => { const fid = (props as { payload?: { filing_id?: string } })?.payload?.filing_id; if (fid) onOpen(fid) } }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

function Exposures({ d, k, seg, segData, clearSeg, openAsset }: {
  d: Detail; k: Kpi; seg: { label: string } | null; segData?: Drivers; clearSeg: () => void; openAsset: ((id: string) => void) | null
}) {
  const nav = useNavigate()
  const dr = seg ? segData : d.drivers
  if (!dr || dr.items.length === 0) return seg ? (
    <div className="text-[12.5px] text-[var(--color-mute)] flex items-center gap-2">
      <button onClick={clearSeg} className="text-[var(--color-sky)] hover:underline">‹ {k.label}</button><span>No exposures in this part.</span>
    </div>
  ) : null
  const max = Math.max(1, ...dr.items.map(i => i.value))
  return (
    <Section title={seg ? `Exposures · ${seg.label}` : 'Largest exposures behind it'}>
      {seg && <button onClick={clearSeg} className="mb-2 text-[12px] text-[var(--color-sky)] hover:underline">‹ Back to {k.label}</button>}
      <div className="rounded-xl border border-[var(--color-line)] divide-y divide-[var(--color-line-2)] overflow-hidden">
        {dr.items.map((it, i) => (
          <div key={i} {...pressable(it.id && openAsset ? () => openAsset(it.id!) : undefined, { row: true })}
            className={`px-3 py-2 ${it.id && openAsset ? 'cursor-pointer hover:bg-[var(--color-panel)]' : ''}`}>
            <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
              <span className="truncate text-[var(--color-ink)]" title={it.name}>{it.name}</span>
              <span className="tabular-nums text-[var(--color-ink)] shrink-0">{amount(it.value, dr.unit)}</span>
            </div>
            <div className="mt-1 h-1 rounded-full bg-[var(--color-panel-2)]"><div className="h-full rounded-full" style={{ width: `${Math.max(2, 100 * it.value / max)}%`, background: it.hazard ? sevColor(it.score ?? 0) : 'var(--color-sky)' }} /></div>
            <div className="mt-1 text-[11px] text-[var(--color-faint)] truncate">
              {[it.sector_name, it.country, it.hazard ? `${hazardLabel(it.hazard)}${it.bucket ? ` · ${bucketLabel(it.bucket)}` : ''}` : null].filter(Boolean).join(' · ')}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex items-center justify-between text-[11.5px] text-[var(--color-faint)]">
        <span>{dr.items.length} of {dr.total_count}</span>
        {d.actions.analytics && dr.total_count > dr.items.length && <button onClick={() => nav('/portfolio')} className="inline-flex items-center gap-0.5 text-[var(--color-sky)] hover:underline">All in Portfolio <ChevronRight size={12} /></button>}
      </div>
    </Section>
  )
}

// where the figure is reported: the regulator, the datapoint it feeds and whether a filing prints it — references the
// main screen leaves out (legal citations sit one click away, UI standard 2026-10-18)
function Reported({ k, regulator }: { k: Kpi; regulator?: Regulator }) {
  const printed = k.filed && k.live_only === false          // live only is said with the trend above
  if (!regulator && !k.reg && !printed) return null
  return (
    <Section title="Where it is reported">
      <div className="space-y-1.5 text-[12.5px]">
        {regulator && <div className="text-[var(--color-ink)]">{regulator.authority}</div>}
        {k.reg && <div className="text-[var(--color-mute)]">{k.reg}{k.reg_tier === 'core' && <StatusChip className="ml-2" label="Headline datapoint" tone="neutral" />}</div>}
        {printed && <div className="text-[var(--color-mute)]"><MessageLine m={k.filed!} /></div>}
      </div>
    </Section>
  )
}

// ── one hazard's exposures (the drill under a hazard bar) ────────────────────────────────────────────────────────
interface Ent { name: string; value: number | null; country: string | null; score: number | null }
interface HazDrill { supported: boolean; hazard: string; noun: string; entities: Ent[]; method_gap?: string }

export function HazardDrill({ framework, entityQ, hazard, hasAnalytics, onClose }: { framework: string; entityQ: string; hazard: string; hasAnalytics: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const { width, setWidth, startResize } = useResizableWidth('tellumen.drawerw', 460, 360, 860, 'right')
  const q = useQuery({ queryKey: ['kri-hazard', framework, hazard, entityQ], queryFn: () => api.get<HazDrill>(`/v1/reg-tasks/kri/hazard?framework=${framework}&hazard=${hazard}${entityQ}`) })
  const d = q.data
  const max = Math.max(1, ...(d?.entities ?? []).map(e => e.value ?? 0))
  return (
    <Drawer label={hazardLabel(hazard)} onClose={onClose} style={{ width, maxWidth: '96vw' }} resize={{ start: startResize, reset: () => setWidth(460) }} className={W}>
      <div className="sticky top-0 z-10 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3.5 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[15px] font-semibold text-[var(--color-ink)]">{hazardLabel(hazard)}</div>
          {d?.supported && !d.method_gap && <div className="text-[12px] text-[var(--color-mute)] mt-0.5">{d.entities.length} {d.noun} at or above your at-risk level</div>}
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {hasAnalytics && <button onClick={() => nav(`/analytics?hazard=${hazard}`)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">Explore forward <ChevronRight size={12} /></button>}
          <CloseButton onClick={onClose} size={17} icon="back" />
        </div>
      </div>
      {!d ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Loading…</div>
        : !d.supported ? <div className="p-6 text-[13px] text-[var(--color-mute)]">This report does not break a hazard down by exposure.</div>
        : d.method_gap ? <div className="p-5"><MethodGap gap={d.method_gap} what="Exposures at risk" /></div>
        : (
          <div className="p-5 space-y-2">
            {d.entities.map((e, i) => (
              <div key={i} className="rounded-xl border border-[var(--color-line)] px-3 py-2.5">
                <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
                  <span className="truncate text-[var(--color-ink)]" title={e.name}>{e.name}{e.country && <span className="text-[var(--color-faint)]"> · {e.country}</span>}</span>
                  <span className="tabular-nums text-[var(--color-ink)] shrink-0">{balance(e.value)}</span>
                </div>
                <div className="mt-1.5 flex items-center gap-2">
                  <div className="flex-1 h-1 rounded-full bg-[var(--color-panel-2)]"><div className="h-full rounded-full" style={{ width: `${Math.max(2, 100 * (e.value ?? 0) / max)}%`, background: sevColor(e.score ?? 0) }} /></div>
                  <span className="text-[11px] tabular-nums" style={{ color: sevColor(e.score ?? 0) }}>{e.score != null ? `${Math.round(e.score)} / 100` : '—'}</span>
                </div>
              </div>
            ))}
          </div>
        )}
    </Drawer>
  )
}
