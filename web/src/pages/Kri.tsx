import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight, ShieldCheck, ArrowUpRight, Upload, SlidersHorizontal } from 'lucide-react'
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import { useResizableWidth } from '../lib/resizable'
import { Eyebrow, Card, Lens } from '../components/ui'
import { HBar } from '../components/Charts'
import { hazardLabel, sevColor } from '../lib/hazards'
import { filingLink } from '../lib/links'
import { toast } from '../lib/toast'
import AssetDrawer, { type DrawerCfg } from '../components/AssetDrawer'

// the asset-detail config per bank/REIT framework — lets a KRI exposure row open the full asset drawer
const DRAWER_CFG: Record<string, DrawerCfg> = {
  bank_tcfd:  { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  bank_p3esg: { prefix: 'bank', itemKey: 'asset', nameKey: 'asset_name', valueKey: 'value_eur', typeKey: 'asset_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
  reit_tcfd:  { prefix: 'realestate', itemKey: 'property', nameKey: 'property_name', valueKey: 'property_value_eur', typeKey: 'property_type', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation' },
}

// Key Regulatory Indicator dashboard — the regulator's-eye consolidated view of the book's physical-risk
// KRIs, with the same headline figures across the org's filed history so the trend is visible.

interface Kpi { key: string; label: string; value: number | null; fmt: string; tone: string | null; hint: string | null; status?: 'ok' | 'amber' | 'red' | null; amber?: number | null; red?: number | null; direction?: string | null; breached?: boolean; reg?: string; reg_tier?: string; integrated?: boolean; integrated_note?: string | null; kind?: 'computed' | 'integrated' }
interface Regulator { authority: string; disclosure: string; legal_basis: string; form_url: string | null }
interface Readiness { core: number; covered: number; integrated: string[]; gaps: string[] }
interface Haz { hazard: string; value: number; score: number }
interface Hist { label: string; filing_id: string | null; total_value: number | null; value_at_risk: number | null; pct_at_risk: number | null }
interface Resp { framework: string; supported: boolean; label: string; kpis: Kpi[]; by_hazard: Haz[]; history: Hist[]; note?: string; message?: string; breaches?: number; scope_note?: string; regulator?: Regulator; readiness?: Readiness }
const RAG: Record<string, string> = { ok: 'var(--color-good)', amber: '#f0a860', red: '#fb7185' }
// the appetite band in words, in the KRI's own unit
const bandNote = (k: Kpi) => {
  if (k.amber == null && k.red == null) return null
  const u = k.fmt === 'pct' ? '%' : k.fmt === 'ha' ? ' ha' : ''
  const cmp = k.direction === 'lower_worse' ? '≤' : '≥'
  const parts: string[] = []
  if (k.amber != null) parts.push(`warn ${cmp}${k.amber}${u}`)
  if (k.red != null) parts.push(`breach ${cmp}${k.red}${u}`)
  return parts.join(' · ')
}
interface Ent { name: string; value: number | null; h3_cell: string | null; country: string | null; score: number | null }
interface HazDrill { supported: boolean; hazard: string; noun: string; entities: Ent[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const fmt = (k: Kpi) => k.value == null ? '—' : k.fmt === 'eur' ? eur(k.value) : k.fmt === 'pct' ? `${k.value}%` : k.fmt === 'ha' ? `${k.value} ha` : k.fmt === 'dec' ? String(k.value) : Math.round(k.value).toLocaleString('en-GB')
const FRAMEWORKS: Record<string, string> = { bank: 'bank_tcfd', asset_manager: 'sfdr_pai', reit: 'reit_tcfd', insurer: 'insurer_climate', manufacturer: 'esrs_pack' }
interface Fw { framework: string; label: string }

export default function Kri() {
  const { profile } = useAuth()
  const nav = useNavigate()
  // an org can report on several frameworks (e.g. a bank owes TCFD *and* Pillar 3 ESG) — pick which to view.
  const fwq = useQuery({ queryKey: ['kri-frameworks'], queryFn: () => api.get<{ frameworks: Fw[] }>('/v1/reg-tasks/kri/frameworks') })
  const frameworks = fwq.data?.frameworks ?? []
  const [picked, setPicked] = useState<string | null>(null)
  const framework = picked ?? frameworks[0]?.framework ?? FRAMEWORKS[profile?.org?.type ?? ''] ?? 'bank_tcfd'
  // Analytics is the forward (scenario) lens — offered only where it serves this book (bank / AM / REIT).
  const hasAnalytics = ['bank', 'asset_manager', 'reit'].includes(profile?.org?.type ?? '')
  const [drill, setDrill] = useState<string | null>(null)
  const [detail, setDetail] = useState<string | null>(null)  // clicked KRI tile → its drill drawer
  // provenance filter — show all KRIs, only those Tellumen computes, or only those you/your vendor provide.
  const [prov, setProv] = useState<'all' | 'computed' | 'integrated'>('all')
  const q = useQuery({ queryKey: ['kri', framework], queryFn: () => api.get<Resp>(`/v1/reg-tasks/kri?framework=${framework}`) })
  const d = q.data
  const kindOf = (k: Kpi): 'computed' | 'integrated' => k.kind ?? (k.integrated ? 'integrated' : 'computed')
  const nComputed = d?.kpis?.filter(k => kindOf(k) === 'computed').length ?? 0
  const nIntegrated = d?.kpis?.filter(k => kindOf(k) === 'integrated').length ?? 0

  return (
    <div className="fadeup space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Eyebrow>Regulatory intelligence</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">KRI dashboard</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">A regulator's-eye view of the book's key risk indicators — identify emerging risk early, drill into a hazard, and track the trend across filings.</p>
        </div>
        <Lens kind="governance" className="mt-1 shrink-0" />
      </div>

      {/* framework picker — shown when the org reports on more than one (e.g. a bank: TCFD + Pillar 3 ESG) */}
      {frameworks.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {frameworks.map(f => (
            <button key={f.framework} onClick={() => setPicked(f.framework)}
              className={`px-3 py-1.5 rounded-lg text-[12px] border transition ${framework === f.framework ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{f.label}</button>
          ))}
        </div>
      )}

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
        : !d || !d.supported ? <Card className="p-10 text-[13px] text-[var(--color-mute)]">{d?.message ?? 'No KRI dashboard for this sector yet.'}</Card>
        : (
        <>
          {d.note && <div className="text-[12.5px] text-[var(--color-warn)]">{d.note}</div>}
          {/* regulator framing — what the supervisor expects to see before you file, and how ready you are */}
          {d.regulator && (
            <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-3">
              <div className="flex items-center gap-2 flex-wrap">
                <ShieldCheck size={15} className="text-[var(--color-sky)]" />
                <span className="text-[12.5px] text-[var(--color-ink)]">What your regulator expects before you file — <b>{d.regulator.authority}</b></span>
                {d.readiness && (
                  <span className="ml-auto mono text-[10.5px]" style={{ color: d.readiness.covered >= d.readiness.core ? 'var(--color-good)' : 'var(--color-warn)' }}>
                    {d.readiness.covered}/{d.readiness.core} regulator datapoints covered
                  </span>
                )}
              </div>
              <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">{d.regulator.disclosure}{d.regulator.form_url ? <> · <a href={d.regulator.form_url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">official form ↗</a></> : ''}</div>
              {d.readiness && d.readiness.integrated.length > 0 && <div className="mono text-[10px] text-[var(--color-faint)] mt-1">needs your input: {d.readiness.integrated.join(' · ')}</div>}
              {d.readiness && d.readiness.gaps.length > 0 && <div className="mono text-[10px] text-[var(--color-warn)] mt-1">awaiting data: {d.readiness.gaps.join(' · ')}</div>}
            </div>
          )}
          {d.scope_note && <div className="mono text-[10.5px] text-[var(--color-faint)]">{d.scope_note}</div>}
          {(d.breaches ?? 0) > 0 && (
            <div className="flex items-center gap-2 rounded-lg px-3.5 py-2.5" style={{ background: 'color-mix(in oklab, #fb7185 12%, transparent)', border: '1px solid color-mix(in oklab, #fb7185 30%, transparent)' }}>
              <span className="w-2 h-2 rounded-full" style={{ background: '#fb7185' }} />
              <span className="text-[12.5px] text-[var(--color-ink)]"><b>{d.breaches}</b> indicator{d.breaches === 1 ? '' : 's'} outside appetite</span>
              <span className="mono text-[10px] text-[var(--color-faint)] ml-auto">bands set in Settings → KRI appetite</span>
            </div>
          )}
          {/* provenance legend + filter — labels the dot on every KRI and lets you isolate what Tellumen
              computes vs what you/your vendor provide. Standard across every sector's dashboard. */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mr-0.5">Data source</span>
            <button onClick={() => setProv(p => p === 'computed' ? 'all' : 'computed')}
              className={`inline-flex items-center gap-1.5 rounded-full pl-2 pr-2.5 py-1 text-[11px] border transition ${prov === 'computed' ? 'border-[var(--color-blue)] bg-[color-mix(in_oklab,var(--color-blue)_10%,transparent)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-blue)]'}`}
              title="Produced by Tellumen's engine (from our feeds and your processed uploads)">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: 'var(--color-blue)' }} />
              Computed by Tellumen <b className="tabular-nums text-[var(--color-ink)]">{nComputed}</b>
            </button>
            <button disabled={nIntegrated === 0} onClick={() => setProv(p => p === 'integrated' ? 'all' : 'integrated')}
              className={`inline-flex items-center gap-1.5 rounded-full pl-2 pr-2.5 py-1 text-[11px] border transition disabled:opacity-45 disabled:cursor-default ${prov === 'integrated' ? 'border-[var(--color-slate)] bg-[color-mix(in_oklab,var(--color-slate)_12%,transparent)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] enabled:hover:border-[var(--color-slate)]'}`}
              title="A pre-calculated value you or your vendor provide; Tellumen reconciles it (bring-your-own-number)">
              <span className="w-2 h-2 rounded-full shrink-0 box-border" style={{ border: '1.5px solid var(--color-slate)' }} />
              Integrated · you provide <b className="tabular-nums text-[var(--color-ink)]">{nIntegrated}</b>
            </button>
            {prov !== 'all' && <button onClick={() => setProv('all')} className="mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline ml-0.5">show all</button>}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {d.kpis.filter(k => prov === 'all' || kindOf(k) === prov).map(k => {
              const rag = k.status ? RAG[k.status] : null
              const note = bandNote(k)
              const integrated = kindOf(k) === 'integrated'
              return (
                <Card key={k.key} onClick={() => setDetail(k.key)} className="px-4 py-3.5 relative cursor-pointer hover:border-[var(--color-line-2)] transition group">
                  {k.status && <span className="absolute top-3 right-3 w-2 h-2 rounded-full" style={{ background: rag! }} title={k.status === 'ok' ? 'within appetite' : k.status === 'amber' ? 'warning' : 'breach'} />}
                  <ArrowUpRight size={13} className="absolute bottom-3 right-3 text-[var(--color-faint)] opacity-0 group-hover:opacity-100 transition" />

                  {k.integrated && k.value == null && <span className="absolute top-3 right-3 mono text-[7.5px] uppercase tracking-wide px-1 py-0.5 rounded text-[var(--color-faint)] border border-[var(--color-line-2)]" title={k.hint ?? undefined}>{k.integrated_note ?? 'integrated'}</span>}
                  <div className="display text-[22px] leading-none" style={{ color: rag ?? k.tone ?? undefined }}>{k.integrated && k.value == null ? <span className="text-[15px] text-[var(--color-faint)] italic">—</span> : fmt(k)}</div>
                  <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-2 flex items-start gap-1.5" title={k.hint ?? undefined}>
                    <span className="w-1.5 h-1.5 rounded-full shrink-0 mt-[3px] box-border" style={integrated ? { border: '1.5px solid var(--color-slate)' } : { background: 'var(--color-blue)' }}
                      title={integrated ? 'Integrated — you or your vendor provide this; Tellumen reconciles it' : 'Computed by Tellumen'} />
                    <span>{k.label}{k.hint ? ' ⓘ' : ''}</span>
                  </div>
                  {k.reg && <div className="text-[8.5px] text-[var(--color-faint)] mt-1 truncate leading-tight" title={k.reg}>{k.reg_tier === 'core' && <span style={{ color: 'var(--color-sky)' }}>▸ </span>}{k.reg}</div>}
                  {note && <div className="mono text-[8.5px] text-[var(--color-faint)] mt-1" style={k.breached ? { color: rag! } : undefined}>{note}</div>}
                </Card>
              )
            })}
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            {d.by_hazard.length > 0 && (
              <div>
                <div className="flex items-center mb-2">
                  <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Value at risk by hazard</div>
                  {hasAnalytics && (
                    <button onClick={() => nav('/analytics')} className="ml-auto inline-flex items-center gap-1 mono text-[9.5px] uppercase tracking-wide text-[var(--color-sky)] hover:underline" title="See how this exposure moves as the world warms">
                      explore forward <ChevronRight size={11} />
                    </button>
                  )}
                </div>
                <Card className="p-4">
                  <HBar data={d.by_hazard.map(h => ({ label: hazardLabel(h.hazard), value: h.value, color: sevColor(h.score) }))} format={eur} onBar={i => setDrill(d.by_hazard[i].hazard)} />
                  <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2">click a hazard to see what's driving it{hasAnalytics ? ' · then project it forward in Analytics' : ''}</div>
                </Card>
              </div>
            )}
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Historical perspective · across filings</div>
              <Card className="p-0 overflow-hidden">
                {d.history.length === 0 ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No filed history yet.</div>
                  : <div className="divide-y divide-[var(--color-line)]">
                      {d.history.map((h, i) => (
                        <button key={i} onClick={() => h.filing_id && nav(filingLink(profile?.org?.type, h.filing_id))}
                          className="w-full text-left px-5 py-3 flex items-center gap-4 hover:bg-[var(--color-panel)] transition" title="Open this filing">
                          <div className="flex-1 mono text-[12px] text-[var(--color-mute)]">{h.label}</div>
                          <div className="text-right"><div className="mono text-[12.5px] tabular-nums">{eur(h.total_value)}</div><div className="mono text-[9.5px] text-[var(--color-faint)]">book value</div></div>
                          {h.value_at_risk != null && <div className="text-right w-24"><div className="mono text-[12.5px] tabular-nums" style={{ color: '#fb7185' }}>{eur(h.value_at_risk)}</div><div className="mono text-[9.5px] text-[var(--color-faint)]">at risk</div></div>}
                          <ChevronRight size={14} className="text-[var(--color-faint)] shrink-0" />
                        </button>
                      ))}
                    </div>}
              </Card>
            </div>
          </div>
        </>
      )}

      {drill && <HazardDrill framework={framework} hazard={drill} hasAnalytics={hasAnalytics} onClose={() => setDrill(null)} />}
      {detail && <KriDetail framework={framework} kriKey={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

function HazardDrill({ framework, hazard, hasAnalytics, onClose }: { framework: string; hazard: string; hasAnalytics: boolean; onClose: () => void }) {
  const nav = useNavigate()
  const { width, setWidth, startResize } = useResizableWidth('tellumen.drawerw', 460, 360, 860, 'right')
  const q = useQuery({ queryKey: ['kri-hazard', framework, hazard], queryFn: () => api.get<HazDrill>(`/v1/reg-tasks/kri/hazard?framework=${framework}&hazard=${hazard}`) })
  const d = q.data
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div style={{ width, maxWidth: '96vw' }} className="relative w-full h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div onMouseDown={startResize} onTouchStart={startResize} onDoubleClick={() => setWidth(460)} title="Drag to resize · double-click to reset" className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize hover:bg-[color-mix(in_oklab,var(--color-sky)_45%,transparent)] active:bg-[var(--color-sky)] transition z-30" />
        <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-center justify-between">
          <div><div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Driving {hazardLabel(hazard)}</div></div>
          <div className="flex items-center gap-3">
            {hasAnalytics && (
              <button onClick={() => nav(`/analytics?hazard=${hazard}`)} className="inline-flex items-center gap-1 mono text-[9.5px] uppercase tracking-wide text-[var(--color-sky)] hover:underline" title="Project this hazard forward across warming pathways">
                explore forward <ChevronRight size={11} />
              </button>
            )}
            <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><ChevronRight size={17} className="rotate-180" /></button>
          </div>
        </div>
        {!d ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</div>
          : !d.supported ? <div className="p-6 text-[13px] text-[var(--color-mute)]">Entity-level drill isn't available for this sector's report.</div>
          : (
          <div className="p-5">
            <div className="mono text-[11px] text-[var(--color-faint)] mb-3">{d.entities.length} {d.noun} exposed at High+ · biggest first</div>
            <div className="space-y-2">
              {d.entities.map((e, i) => (
                <div key={i} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-2.5 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] text-[var(--color-ink)] truncate">{e.name}{e.country ? <span className="text-[var(--color-faint)]"> · {e.country}</span> : null}</div>
                    <div className="mono text-[9.5px] text-[var(--color-faint)]">cell {e.h3_cell ? e.h3_cell.slice(0, 10) + '…' : '—'}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="mono text-[12px] tabular-nums text-[var(--color-mute)]">{eur(e.value)}</div>
                    <div className="mono text-[10px]" style={{ color: sevColor(e.score ?? 0) }}>{e.score != null ? Math.round(e.score) : '—'}/100</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// The drill behind one KRI tile — methodology, trend across filings, and the real composition (by hazard /
// scope / scored-unscored / eligible-not), plus contextual actions. All from /kri/detail; nothing fabricated.
interface Comp { type: 'hazard' | 'scope' | 'coverage' | 'taxonomy' | 'sector' | 'horizon'; unit: 'eur' | 'num' | 'pct'; items: { label: string; value: number; score?: number }[] }
interface Driver { id?: string | null; name: string; sector?: string | null; country?: string | null; nace?: string | null; value: number; hazard?: string | null; bucket?: string | null; score?: number | null }
interface Drivers { unit: 'eur' | 'num'; total_count: number; items: Driver[] }
interface Detail { supported: boolean; message?: string; framework: string; kpi: Kpi; regulator?: Regulator; methodology?: string | null; trend: { points: { label: string; value: number | null }[]; fmt: string }; composition?: Comp | null; drivers?: Drivers | null; actions: { analytics: boolean; provide: boolean } }

function KriDetail({ framework, kriKey, onClose }: { framework: string; kriKey: string; onClose: () => void }) {
  const nav = useNavigate()
  const { profile } = useAuth()
  const canSetAppetite = (profile?.permissions ?? []).includes('admin.approval_policy.manage')
  const { width, setWidth, startResize } = useResizableWidth('tellumen.drawerw', 460, 360, 860, 'right')
  const q = useQuery({ queryKey: ['kri-detail', framework, kriKey], queryFn: () => api.get<Detail>(`/v1/reg-tasks/kri/detail?framework=${framework}&kri=${encodeURIComponent(kriKey)}`) })
  const d = q.data
  const [editBand, setEditBand] = useState(false)
  const [band, setBand] = useState<{ amber?: number; red?: number; direction?: string }>({})
  const [savingBand, setSavingBand] = useState(false)
  const startBand = () => { const k = d?.kpi; setBand({ amber: k?.amber ?? undefined, red: k?.red ?? undefined, direction: k?.direction ?? 'higher_worse' }); setEditBand(true) }
  // land Analytics scoped to the factors that drive THIS indicator, not the generic page: acute/chronic KRIs
  // scope to their peril subset; the forward KRI pre-selects the forward pathway; all carry a context label.
  const analyticsHref = (key: string, label: string) => {
    const p = new URLSearchParams({ from: label })
    if (key === 'acute_share') p.set('perils', 'acute')
    else if (key === 'chronic_share') p.set('perils', 'chronic')
    else if (key === 'forward_share') p.set('scenario', 'disorderly_2c')
    return `/analytics?${p.toString()}`
  }
  // drill state: a clicked composition bar scopes the exposures list to that segment; a clicked exposure
  // opens the full asset drawer (the deepest level).
  const [seg, setSeg] = useState<{ type: string; value: string; label: string } | null>(null)
  const [assetId, setAssetId] = useState<string | null>(null)
  const segQ = useQuery({
    queryKey: ['kri-drivers-seg', framework, seg?.type, seg?.value],
    enabled: !!seg,
    queryFn: () => api.get<Drivers>(`/v1/reg-tasks/kri/drivers?framework=${framework}&kri=${encodeURIComponent(kriKey)}&seg_type=${seg!.type}&seg_value=${encodeURIComponent(seg!.value)}`),
  })
  // map a composition bar to a drill segment; horizon/coverage/taxonomy bars aren't asset-decomposable
  const segFor = (type: string, item: { label: string }, i: number): { type: string; value: string; label: string } | null => {
    if (type === 'scope') return { type: 'scope', value: String(i + 1), label: `Scope ${i + 1}` }
    if (type === 'sector') return { type: 'sector', value: item.label.split(' · ')[0].trim(), label: item.label }
    if (type === 'hazard') return { type: 'hazard', value: item.label, label: hazardLabel(item.label) }
    return null
  }
  const drawerCfg = DRAWER_CFG[framework]
  const saveBand = async () => {
    setSavingBand(true)
    try {
      await api.patch('/v1/admin/kri-appetite', { kri_key: kriKey, framework, amber: band.amber, red: band.red, direction: band.direction })
      await q.refetch(); setEditBand(false); toast.success('Appetite band updated.')
    } catch { toast.error('Could not update the appetite band.') } finally { setSavingBand(false) }
  }
  const uf = (v: number, unit?: string) => unit === 'eur' ? eur(v) : unit === 'pct' ? `${v}%` : Math.round(v).toLocaleString('en-GB')
  const tf = (v: number) => d?.trend.fmt === 'eur' ? eur(v) : d?.trend.fmt === 'pct' ? `${v}%` : Math.round(v).toLocaleString('en-GB')
  const compTitle: Record<string, string> = { hazard: 'Exposure by hazard', scope: 'Emissions by scope', coverage: 'Scored vs unscored', taxonomy: 'Eligible vs not eligible', sector: 'Concentration by NACE sector', horizon: 'Projected trajectory by horizon' }
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div style={{ width, maxWidth: '96vw' }} className="relative w-full h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div onMouseDown={startResize} onTouchStart={startResize} onDoubleClick={() => setWidth(460)} title="Drag to resize · double-click to reset" className="absolute top-0 left-0 h-full w-1.5 cursor-col-resize hover:bg-[color-mix(in_oklab,var(--color-sky)_45%,transparent)] active:bg-[var(--color-sky)] transition z-30" />
        {!d ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</div>
          : !d.supported ? <div className="p-6 text-[13px] text-[var(--color-mute)]">{d.message ?? 'No detail for this KRI.'}</div>
          : (() => {
            const k = d.kpi
            const integrated = k.kind === 'integrated' || k.integrated
            const value = k.integrated && k.value == null ? '—' : fmt(k)
            return (<>
              <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full box-border shrink-0" style={integrated ? { border: '1.5px solid var(--color-slate)' } : { background: 'var(--color-blue)' }} />
                    {integrated ? 'Integrated · you provide' : 'Computed by Tellumen'}
                  </div>
                  <div className="display text-[26px] leading-none mt-1.5" style={{ color: k.status ? RAG[k.status] : k.tone ?? undefined }}>{value}</div>
                  <div className="text-[13px] text-[var(--color-mute)] mt-1">{k.label}</div>
                </div>
                <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)] shrink-0"><ChevronRight size={17} className="rotate-180" /></button>
              </div>
              <div className="p-5 space-y-5">
                {(d.regulator || k.reg) && (
                  <div className="space-y-1">
                    {d.regulator && <div className="text-[11.5px] text-[var(--color-mute)]">{d.regulator.authority} · {d.regulator.disclosure}</div>}
                    {k.reg && <div className="text-[11px] text-[var(--color-faint)]">{k.reg_tier === 'core' && <span style={{ color: 'var(--color-sky)' }}>▸ </span>}{k.reg}</div>}
                  </div>
                )}
                {(d.methodology || k.hint) && (
                  <div>
                    <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5">How it's computed</div>
                    <p className="text-[12.5px] text-[var(--color-mute)] leading-relaxed">{d.methodology ?? k.hint}</p>
                  </div>
                )}
                {(k.status || (canSetAppetite && (k.fmt === 'pct' || k.fmt === 'eur' || k.fmt === 'num'))) && (
                  <div className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-[12px]">
                    <div className="flex items-center gap-2">
                      {k.status && <span className="w-2 h-2 rounded-full shrink-0" style={{ background: RAG[k.status] }} />}
                      <span className="text-[var(--color-mute)]">{!k.status ? 'No appetite band set' : k.status === 'ok' ? 'Within appetite' : k.status === 'amber' ? 'Warning — approaching breach' : 'Outside appetite (breach)'}</span>
                      {!editBand && (k.amber != null || k.red != null) && <span className="mono text-[10px] text-[var(--color-faint)] ml-auto">warn {k.amber} · breach {k.red}</span>}
                      {!editBand && canSetAppetite && <button onClick={startBand} className={`mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline ${(k.amber != null || k.red != null) ? 'ml-2' : 'ml-auto'}`}>{(k.amber != null || k.red != null) ? 'adjust' : 'set band'}</button>}
                    </div>
                    {editBand && (
                      <div className="mt-2 pt-2 border-t border-[var(--color-line-2)] flex flex-wrap items-end gap-2">
                        <label className="block"><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-0.5">Warn ≥</div>
                          <input type="number" value={band.amber ?? ''} onChange={e => setBand(b => ({ ...b, amber: e.target.value === '' ? undefined : Number(e.target.value) }))} className="w-20 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" /></label>
                        <label className="block"><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-0.5">Breach ≥</div>
                          <input type="number" value={band.red ?? ''} onChange={e => setBand(b => ({ ...b, red: e.target.value === '' ? undefined : Number(e.target.value) }))} className="w-20 rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]" /></label>
                        <label className="block"><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-0.5">Direction</div>
                          <select value={band.direction ?? 'higher_worse'} onChange={e => setBand(b => ({ ...b, direction: e.target.value }))} className="rounded border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1 text-[12px]">
                            <option value="higher_worse">higher is worse</option><option value="lower_worse">lower is worse</option></select></label>
                        <div className="flex gap-1.5 ml-auto">
                          <button onClick={saveBand} disabled={savingBand} className="rounded-lg bg-[var(--color-sky)] text-white px-3 py-1.5 text-[12px] disabled:opacity-50">{savingBand ? 'Saving…' : 'Save'}</button>
                          <button onClick={() => setEditBand(false)} className="rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)]">Cancel</button>
                        </div>
                        <p className="w-full mono text-[9.5px] text-[var(--color-faint)]">Sets your organisation's appetite band on this KRI ({k.label}) — the same control as Settings → KRI appetite, applied here in context.</p>
                      </div>
                    )}
                  </div>
                )}
                <div>
                  <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5">Trend across filings</div>
                  {d.trend.points.length >= 2 ? (
                    <div className="h-40">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={d.trend.points} margin={{ top: 6, right: 12, bottom: 2, left: 4 }}>
                          <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="2 5" vertical={false} />
                          <XAxis dataKey="label" tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={{ stroke: 'var(--color-line)' }} tickLine={false} />
                          <YAxis tick={{ fill: 'var(--color-faint)', fontSize: 10 }} axisLine={false} tickLine={false} width={46} tickFormatter={tf} />
                          <Tooltip formatter={(v) => tf(Number(v))} contentStyle={{ background: 'var(--color-panel)', border: '1px solid var(--color-line)', borderRadius: 8, fontSize: 12 }} />
                          <Line type="monotone" dataKey="value" stroke="var(--color-sky)" strokeWidth={2} dot={{ r: 3, fill: 'var(--color-sky)' }} isAnimationActive={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : <p className="text-[12px] text-[var(--color-faint)] leading-relaxed">This metric's trend appears once you have two or more filed reports (filed history currently tracks book value, value-at-risk and share-at-risk).</p>}
                </div>
                {d.composition && d.composition.items.length > 0 && (() => {
                  const comp = d.composition
                  const drillable = comp.type === 'scope' || comp.type === 'sector' || comp.type === 'hazard'
                  return (
                    <div>
                      <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5 flex items-center gap-1.5">
                        {compTitle[comp.type] ?? 'Composition'}
                        {drillable && <span className="text-[var(--color-faint)] normal-case tracking-normal">· click a bar to drill</span>}
                      </div>
                      <HBar
                        data={comp.items.map(it => ({ label: comp.type === 'hazard' ? hazardLabel(it.label) : it.label, value: it.value, color: comp.type === 'hazard' ? sevColor(it.score ?? 0) : 'var(--color-sky)' }))}
                        format={n => uf(n, comp.unit)}
                        {...(drillable ? { onBar: (i: number) => { const s = segFor(comp.type, comp.items[i], i); if (s) setSeg(s) } } : {})}
                      />
                    </div>
                  )
                })()}
                {(() => {
                  const dr = seg ? segQ.data : d.drivers
                  if (!dr || dr.items.length === 0) return seg ? (
                    <div className="text-[12px] text-[var(--color-faint)]"><button onClick={() => setSeg(null)} className="mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline">‹ back</button> · no exposures in this slice.</div>
                  ) : null
                  return (
                    <div>
                      <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5 flex items-center gap-1.5 flex-wrap">
                        {seg
                          ? <><button onClick={() => setSeg(null)} className="text-[var(--color-sky)] hover:underline">{k.label}</button><span className="text-[var(--color-faint)]">›</span><span className="text-[var(--color-ink)]">{seg.label}</span></>
                          : <span>Top exposures behind this indicator</span>}
                        <span className="text-[var(--color-faint)] normal-case tracking-normal">· {dr.total_count} in total · click a row for the asset</span>
                      </div>
                      <div className="rounded-lg border border-[var(--color-line)] overflow-hidden">
                        <table className="w-full text-[11.5px]">
                          <tbody>
                            {dr.items.map((it, i) => (
                              <tr key={i} onClick={() => it.id && drawerCfg && setAssetId(it.id)} className={`border-b border-[var(--color-line-2)] last:border-0 ${it.id && drawerCfg ? 'cursor-pointer hover:bg-[var(--color-bg-2)]' : ''}`}>
                                <td className="px-3 py-1.5 text-[var(--color-ink)] truncate max-w-[180px]" title={it.name}>{it.name}</td>
                                <td className="px-2 py-1.5 text-[var(--color-faint)] mono text-[10px] whitespace-nowrap">{[it.nace, it.country].filter(Boolean).join(' · ')}</td>
                                <td className="px-2 py-1.5 text-right">{it.hazard && <span className="mono text-[10px]" style={{ color: sevColor(it.score ?? 0) }}>{hazardLabel(it.hazard)}{it.bucket ? ` · ${it.bucket}` : ''}</span>}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums text-[var(--color-ink)] whitespace-nowrap">{uf(it.value, dr.unit)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      {d.actions.analytics && dr.total_count > dr.items.length && (
                        <button onClick={() => nav('/portfolio')} className="mt-1.5 mono text-[10px] uppercase tracking-wide text-[var(--color-sky)] hover:underline">See all {dr.total_count} in Portfolio →</button>
                      )}
                    </div>
                  )
                })()}
                <div className="flex flex-wrap gap-2 pt-1">
                  {d.actions.analytics && <button onClick={() => nav(analyticsHref(kriKey, k.label))} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-ink)] transition"><ArrowUpRight size={13} /> Explore forward in Analytics</button>}
                  {d.actions.provide && <button onClick={() => nav('/compliance')} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-slate)] hover:text-[var(--color-ink)] transition"><Upload size={13} /> Provide this figure</button>}
                  {canSetAppetite && !editBand && <button onClick={startBand} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)] transition"><SlidersHorizontal size={13} /> Set appetite</button>}
                </div>
              </div>
            </>)
          })()}
      </div>
      {assetId && drawerCfg && <AssetDrawer cfg={drawerCfg} id={assetId} onClose={() => setAssetId(null)} onChanged={() => segQ.refetch()} />}
    </div>
  )
}
