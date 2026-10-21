import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { BookOpen, Calculator, ListX, Play, ShieldCheck, TriangleAlert } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { balance, flow } from '../lib/money'
import { changeVs } from '../lib/change'
import { toast } from '../lib/toast'
import { arrivedRun } from '../lib/runWait'
import { PageHeader, Card, StatGrid, SectionHead, Button } from '../components/ui'
import { HBar } from '../components/Charts'
import { Dialog, CloseButton } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'

// Loss from the hazard itself (E171), to the UI standard (2026-10-16): the main screen is figures and charts — the
// expected yearly loss, undefended and defended, why figures are missing, and each asset; every explanation (the
// method, the sources, a figure's basis) is one click away, in customer words from the server's message catalogue.

type Standing = 'published' | 'held' | 'untested'
interface Family { family: string; name: string; kind: 'published' | 'measured'; peril: string; source: { authors?: string; title?: string; year?: number } | null; curves: { key: string; occupancy: string; region: string | null; test?: { passed: boolean; events_tested?: number; events_within_tolerance?: number } | null }[]; test: { passed: boolean } | null }
interface Families { families: Family[]; refused: { family: string; name: string }[]; adopted: Record<string, string | null>; headline: Record<string, 'defended' | 'undefended' | null> }
interface Skill { rho: number; auc_share_gt_2pct: number }
interface Layer { key: string; name: string; peril: string; resolution_m: number | null; return_periods: number[]; status: string | null; licence: string | null; test: { passed: boolean; pooled?: { m90?: Skill; m30?: Skill; global?: Skill; europe?: Skill } } | null; sampled: { places: number } }
interface ProtectionLayer { key: string; name: string; resolution_m: number; licence: string; citation?: string; sampled: { places: number; with_a_level?: number; no_value?: number; outside_coverage?: number } }
interface RunRow { run_id: string; book: string; scenario: string; time_horizon: string; as_of: string; n_assets: number; n_gaps: number; created_at: string }
interface Band { low: number; central: number; high: number }
interface Result { asset_id: string; asset_name: string | null; country_name: string | null; peril: string; exposed_value_eur: number | null; occupancy: string | null; curve_name: string | null; flood_layer: string | null; eal_eur: number | null; eal_low_eur: number | null; eal_high_eur: number | null; standing: Standing | null; loss_at_rp: Record<string, Band> | null; gap: string | null; gap_message: Message | null; eal_same_source_today_eur: number | null; protection_rp_years: number | null; protection_message: Message | null; caution_message: Message | null; eal_defended_eur: number | null; eal_defended_low_eur: number | null; eal_defended_high_eur: number | null }
interface Total { peril: string; standing: Standing; results: number; eal_low_eur: number; eal_eur: number; eal_high_eur: number; eal_same_source_today_eur: number | null; defended_results: number; eal_defended_eur: number; eal_defended_low_eur: number; eal_defended_high_eur: number; eal_undefended_same_results_eur: number; protection_unknown_results: number; eal_protection_unknown_eur: number }
interface Gap { code: string | null; reason: string; detail: Message['detail']; count: number }
interface RunDetail { run: RunRow & { inputs: { layers?: { flood?: { pathway?: string; period?: string } } } }; totals: Total[]; gaps: Gap[]; results: Result[]; book_curve: { peril: string; rp_years: number; loss_eur: number }[] }
interface Projection { periods: Record<string, string>; flood: { scenario: string; horizon: string; gap: Message | null }[] }

const BOOKS: Record<string, { key: string; label: string }[]> = {
  bank: [{ key: 'banking', label: 'Loan book' }],
  insurer: [{ key: 'insurance', label: 'Insured properties' }, { key: 'insurer_investments', label: 'Investments' }],
  asset_manager: [{ key: 'assetmgmt', label: 'Holdings' }],
  reit: [{ key: 'realestate', label: 'Properties' }],
  manufacturer: [{ key: 'company_sites', label: 'Own sites' }],
}
const STANDING: Record<Standing, { label: string; tone: 'good' | 'warn' | 'neutral'; what: string }> = {
  published: { label: 'Tested', tone: 'good', what: 'The damage curve passed both tests on observed losses it was not built from.' },
  held: { label: 'Failed its test', tone: 'warn', what: 'The damage curve was tested on observed losses and failed; the figure is shown for reference, not for use.' },
  untested: { label: 'Untested', tone: 'neutral', what: 'There are no observed losses to test the damage curve against where this asset is.' },
}
const PERIL: Record<string, string> = { flood: 'River flood', storm: 'Tropical cyclone' }
const SCENARIO: Record<string, string> = { baseline: 'Today', disorderly_2c: 'Disorderly 2 °C', hot_house_3_5c: 'Hot house 3.5 °C', orderly_1_5c: 'Orderly 1.5 °C' }
const HORIZONS = ['2030', '2050', '2080', '2100']
const LAYER_STATUS: Record<string, string> = { in_use: 'in_use', candidate: 'candidate', refused: 'refused' }
const runLabel = (r: RunRow) => r.scenario === 'baseline' ? 'Today' : `${SCENARIO[r.scenario] ?? 'Projection'} · ${r.time_horizon}`

function StandingChip({ s }: { s: Standing }) {
  const v = STANDING[s]
  return <StatusChip label={v.label} tone={v.tone} />
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Each asset’s expected yearly loss from river flood and tropical cyclone, read off the damage curve your organisation chose at the hazard’s physical strength — flood depth in metres, wind speed in metres per second — at each return period.' },
  { heading: HEADING.read, body: 'Every figure is a range. Flood losses appear twice: undefended, as the flood maps show the hazard, and defended, with losses from floods more frequent than the local protection level set to zero. Each figure carries the standing its damage curve earned on observed losses: tested, failed its test, or untested.' },
  { heading: HEADING.sources, body: 'Flood depth: JRC river-flood maps (European maps in Europe, global maps elsewhere). Flood protection: JRC map of estimated flood-protection standards in Europe. Cyclone wind: STORM. Damage curves: the family your organisation chose. Details under Methods and data sources.' },
  { heading: HEADING.limits, body: 'A figure that cannot be computed is shown as missing, with its reason — never as zero. Flood maps show river floods only; coastal and surface-water flooding are separate hazards.' },
]

export default function Loss() {
  const { profile } = useAuth()
  const books = BOOKS[profile?.org?.type ?? ''] ?? []
  const canRun = (profile?.permissions ?? []).includes('reports.publish')
  const fams = useQuery({ queryKey: ['loss-families'], queryFn: () => api.get<Families>('/v1/loss/families') })
  const proj = useQuery({ queryKey: ['loss-projection'], queryFn: () => api.get<Projection>('/v1/loss/projection') })
  const [book, setBook] = useState(books[0]?.key ?? '')
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('2050')
  const [methods, setMethods] = useState(false)
  const projGap = scenario === 'baseline' ? null : proj.data?.flood.find(c => c.scenario === scenario && c.horizon === horizon)?.gap ?? null
  const [waiting, setWaiting] = useState(0)
  const runs = useQuery({
    queryKey: ['loss-runs', book], enabled: !!book,
    queryFn: () => api.get<{ runs: RunRow[] }>(`/v1/loss/runs?book=${book}&limit=20`),
    refetchInterval: waiting ? 3000 : false, refetchIntervalInBackground: true,
  })
  const [runId, setRunId] = useState<string | null>(null)
  const [before, setBefore] = useState<string | null>(null)
  const latest = runs.data?.runs[0]?.run_id ?? null
  useEffect(() => {
    const got = arrivedRun(latest, before, !!waiting)
    if (got) { setWaiting(0); setRunId(got); toast.success('Loss run recorded.') }
  }, [latest, waiting, before])
  useEffect(() => { if (waiting && Date.now() - waiting > 120000) setWaiting(0) }, [runs.dataUpdatedAt, waiting])
  const shown = runId ?? latest
  const start = async () => {
    try {
      await api.post('/v1/loss/runs', scenario === 'baseline' ? { book } : { book, scenario, horizon })
      setBefore(latest); setWaiting(Date.now()); toast.info('Loss run started.')
    } catch (e) { toast.error(apiMessage(e, 'Could not start the loss run.')) }
  }
  const select = 'rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]'
  const adopted = fams.data?.families.find(f => f.family === fams.data?.adopted.flood)

  return (
    <div className="space-y-6">
      <ReviewTabs />
      <PageHeader eyebrow="Assess · Loss" title="Loss from hazards" lead="Expected yearly loss to your buildings, with and without flood defences." about={ABOUT}
        actions={<Button variant="ghost" onClick={() => setMethods(true)}><BookOpen size={14} className="inline -mt-0.5 mr-1" />Methods and data sources</Button>} />
      <Card className="p-5 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <SectionHead icon={Calculator}>Loss runs</SectionHead>
          {fams.data && <span className="text-[12px] text-[var(--color-mute)]">Flood curves: <span className="text-[var(--color-ink)]">{adopted?.name ?? 'none chosen'}</span></span>}
        </div>
        {books.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">Your sector holds no book of physical assets.</div> : (
          <div className="flex flex-wrap items-center gap-3">
            <select value={book} onChange={e => { setBook(e.target.value); setRunId(null) }} aria-label="Book" className={select}>
              {books.map(b => <option key={b.key} value={b.key}>{b.label}</option>)}
            </select>
            <select value={scenario} onChange={e => setScenario(e.target.value)} aria-label="Climate" className={select}>
              {Object.entries(SCENARIO).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            {scenario !== 'baseline' && (
              <select value={horizon} onChange={e => setHorizon(e.target.value)} aria-label="Year" className={select}>
                {HORIZONS.map(h => <option key={h} value={h}>{h}</option>)}
              </select>
            )}
            {canRun && <Button onClick={start} disabled={!!waiting || !!projGap}><Play size={14} className="inline -mt-0.5 mr-1" />{waiting ? 'Running…' : 'Run losses now'}</Button>}
            {(runs.data?.runs.length ?? 0) > 0 && (
              <select value={shown ?? ''} onChange={e => setRunId(e.target.value)} aria-label="Run" className={select}>
                {runs.data!.runs.map(r => <option key={r.run_id} value={r.run_id}>{runLabel(r)} · {new Date(r.created_at).toLocaleString()}</option>)}
              </select>
            )}
          </div>
        )}
        {projGap && <div className="text-[12.5px] text-[var(--color-warn)]"><MessageLine m={projGap} /></div>}
      </Card>
      {shown ? <RunView runId={shown} headline={fams.data?.headline?.flood ?? null} /> : books.length > 0 && !runs.isLoading &&
        <div className="text-[12.5px] text-[var(--color-faint)]">No loss run yet for this book.</div>}
      {methods && <Methods families={fams.data} onClose={() => setMethods(false)} />}
    </div>
  )
}

// Two bars on one scale: the undefended and the defended expected yearly loss.
function Compare({ t, headline }: { t: Total; headline: 'defended' | 'undefended' | null }) {
  const max = Math.max(1, t.eal_eur)
  const rows: { k: 'undefended' | 'defended'; label: string; v: number | null; lo: number; hi: number; n: number; tone: string }[] = [
    { k: 'undefended', label: 'Undefended', v: t.eal_eur, lo: t.eal_low_eur, hi: t.eal_high_eur, n: t.results, tone: 'var(--color-warn)' },
    { k: 'defended', label: 'Defended', v: t.defended_results ? t.eal_defended_eur : null, lo: t.eal_defended_low_eur, hi: t.eal_defended_high_eur, n: t.defended_results, tone: 'var(--color-good)' },
  ]
  return (
    <div className="space-y-3 mt-3">
      {rows.map(r => (
        <div key={r.k}>
          <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
            <span className="text-[var(--color-ink)]">{r.label}{headline === r.k && <StatusChip label="Leads" tone="neutral" className="ml-2" />}</span>
            <span className="display text-[20px] tabular-nums">{r.v == null ? '—' : flow(r.v)}</span>
          </div>
          <div className="h-3 rounded-full bg-[var(--color-panel-2)] mt-1 relative overflow-hidden">
            {r.v != null && <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${Math.max(1.5, (r.v / max) * 100)}%`, background: r.tone }} />}
          </div>
          <div className="text-[11px] text-[var(--color-faint)] mt-1 tabular-nums">{r.v == null ? 'No protection level known' : `${flow(r.lo)} – ${flow(r.hi)} · ${r.n} assets`}</div>
        </div>
      ))}
      {t.protection_unknown_results > 0 && (
        <div className="text-[12px] text-[var(--color-warn)] flex items-center gap-1.5">
          <ShieldCheck size={13} /> Protection unknown at {t.protection_unknown_results} assets · {flow(t.eal_protection_unknown_eur)}
          <InfoButton compact details={{ title: 'Protection unknown', sections: [{ heading: HEADING.shows, body: `These ${t.protection_unknown_results} assets lie where the flood-protection map holds no level, so only their undefended loss exists. It is not part of the defended sum.` }] }} />
        </div>
      )}
    </div>
  )
}

function RunView({ runId, headline }: { runId: string; headline: 'defended' | 'undefended' | null }) {
  const q = useQuery({ queryKey: ['loss-run', runId], queryFn: () => api.get<RunDetail>(`/v1/loss/runs/${runId}`) })
  const [peril, setPeril] = useState<'all' | string>('all')
  const [asset, setAsset] = useState<Result | null>(null)
  const [reason, setReason] = useState<Gap | null>(null)
  const rows = useMemo(() => (q.data?.results ?? []).filter(r => peril === 'all' || r.peril === peril), [q.data, peril])
  if (q.isLoading || !q.data) return <div className="text-[12.5px] text-[var(--color-faint)]">Loading the run…</div>
  const d = q.data
  const projected = d.run.scenario !== 'baseline'
  const missing = d.gaps.reduce((a, g) => a + g.count, 0)
  const top = Math.max(1, ...rows.map(r => r.eal_eur ?? 0))
  return (
    <div className="space-y-6">
      <StatGrid cols={3} items={[
        { label: 'Assets', value: d.run.n_assets.toLocaleString(), sub: runLabel(d.run) },
        { label: 'Figures', value: (d.results.length - missing).toLocaleString(), sub: 'one per asset and hazard' },
        { label: 'Missing figures', value: missing.toLocaleString(), sub: `${d.gaps.length} reasons`, accent: missing ? 'var(--color-warn)' : undefined },
      ]} />
      {d.totals.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {d.totals.map(t => (
            <Card key={`${t.peril}:${t.standing}`} className="p-5">
              <div className="flex items-center justify-between gap-2">
                <SectionHead>{PERIL[t.peril] ?? 'Hazard'} · expected yearly loss</SectionHead>
                <StandingChip s={t.standing} />
              </div>
              {t.peril === 'flood' && !projected ? <Compare t={t} headline={headline} /> : (
                <div className="mt-3">
                  <div className="display text-[26px] tabular-nums">{flow(t.eal_eur)}</div>
                  <div className="text-[11px] text-[var(--color-faint)] mt-1 tabular-nums">{flow(t.eal_low_eur)} – {flow(t.eal_high_eur)} · {t.results} assets</div>
                  {changeVs(t.eal_eur, t.eal_same_source_today_eur) && <StatusChip className="mt-2" label={`${changeVs(t.eal_eur, t.eal_same_source_today_eur)} vs today`} tone="warn" />}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
      {d.gaps.length > 0 && (
        <Card className="p-5">
          <SectionHead icon={ListX} className="mb-3">Why figures are missing</SectionHead>
          <HBar data={d.gaps.map(g => ({ label: g.reason, value: g.count }))} format={n => `${n}`} onBar={i => setReason(d.gaps[i])} labelWidth="w-60" />
        </Card>
      )}
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <SectionHead>Assets</SectionHead>
          {['all', 'flood', 'storm'].map(p => (
            <button key={p} onClick={() => setPeril(p)} className={`px-2.5 py-1 text-[11.5px] rounded-full border ${peril === p ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>{p === 'all' ? 'All hazards' : PERIL[p]}</button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px] tabular-nums">
            <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
              <th className="py-1.5 pr-3 font-medium">Asset</th><th className="pr-3 font-medium">Hazard</th>
              <th className="pr-3 font-medium text-right">Building value</th><th className="pr-3 font-medium">Expected yearly loss</th>
              {!projected && <th className="pr-3 font-medium text-right">Defended</th>}<th className="font-medium">Standing</th>
            </tr></thead>
            <tbody>
              {rows.slice(0, 100).map(r => (
                <tr key={`${r.asset_id}:${r.peril}`} onClick={() => !r.gap && setAsset(r)}
                  className={`border-b border-[var(--color-line)] ${r.gap ? '' : 'cursor-pointer hover:bg-[var(--color-panel-2)]'}`}>
                  <td className="py-1.5 pr-3 text-[var(--color-ink)]">{r.asset_name ?? 'Asset'}<span className="text-[var(--color-faint)]"> · {r.country_name ?? '—'}</span></td>
                  <td className="pr-3">{PERIL[r.peril] ?? 'Hazard'}</td>
                  <td className="pr-3 text-right">{r.exposed_value_eur ? balance(r.exposed_value_eur) : '—'}</td>
                  {r.gap_message ? <td colSpan={projected ? 2 : 3} className="pr-3 text-[var(--color-warn)]"><MessageLine m={r.gap_message} /></td> : (<>
                    <td className="pr-3 min-w-[180px]">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 rounded-full bg-[var(--color-panel-2)] relative"><div className="absolute inset-y-0 left-0 rounded-full bg-[var(--color-warn)]" style={{ width: `${Math.max(1.5, ((r.eal_eur ?? 0) / top) * 100)}%` }} /></div>
                        <span className="w-16 text-right">{flow(r.eal_eur)}</span>
                        {r.caution_message && <span title={r.caution_message.label}><TriangleAlert size={13} className="text-[var(--color-warn)]" /></span>}
                      </div>
                    </td>
                    {!projected && <td className="pr-3 text-right">{r.peril !== 'flood' ? '—' : r.eal_defended_eur != null ? flow(r.eal_defended_eur) : <span className="text-[var(--color-faint)]">unknown</span>}</td>}
                    <td>{r.standing && <StandingChip s={r.standing} />}</td>
                  </>)}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 100 && <div className="text-[11.5px] text-[var(--color-faint)] mt-2">The 100 largest of {rows.length}.</div>}
        </div>
      </Card>
      {d.book_curve.length > 0 && <BookCurve points={d.book_curve} />}
      {asset && <AssetDetail r={asset} projected={projected} onClose={() => setAsset(null)} />}
      {reason && <Dialog title={reason.reason} onClose={() => setReason(null)} className="max-w-xl">
        <div className="text-[12.5px] text-[var(--color-mute)] mb-3">{reason.count} figures</div>
        <InfoBody m={{ label: reason.reason, detail: reason.detail }} />
      </Dialog>}
    </div>
  )
}

function InfoBody({ m }: { m: Message }) {
  const { sections } = messageDetails(m)
  return <div className="space-y-4">{sections.map((s, i) => <section key={i}><h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-1.5">{s.heading}</h4><div className="text-[13.5px] leading-relaxed">{s.body}</div></section>)}</div>
}

function BookCurve({ points }: { points: { rp_years: number; loss_eur: number }[] }) {
  const max = Math.max(1, ...points.map(p => p.loss_eur))
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3"><SectionHead>Book loss by return period</SectionHead>
        <InfoButton compact details={{ title: 'Book loss by return period', sections: [{ heading: HEADING.read, body: 'Each bar adds every tested asset’s loss at that return period, on the way your organisation states that assets flood together.' }] }} /></div>
      <div className="flex items-end gap-3 h-36">
        {points.map(p => (
          <div key={p.rp_years} className="flex-1 flex flex-col items-center justify-end h-full">
            <span className="text-[11px] tabular-nums text-[var(--color-mute)] mb-1">{balance(p.loss_eur)}</span>
            <div className="w-full rounded-t bg-[var(--color-warn)]" style={{ height: `${Math.max(2, (p.loss_eur / max) * 100)}%` }} />
            <span className="text-[11px] text-[var(--color-faint)] mt-1">1-in-{p.rp_years}</span>
          </div>
        ))}
      </div>
    </Card>
  )
}

function AssetDetail({ r, projected, onClose }: { r: Result; projected: boolean; onClose: () => void }) {
  const rps = Object.entries(r.loss_at_rp ?? {}).sort((a, b) => +a[0] - +b[0])
  const max = Math.max(1, ...rps.map(([, v]) => v.high))
  const fact = (label: string, value: React.ReactNode) => <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]"><span className="text-[var(--color-mute)]">{label}</span><span className="text-right text-[var(--color-ink)]">{value}</span></div>
  return (
    <Drawer label={r.asset_name ?? 'Asset'} onClose={onClose} className="w-full max-w-md h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div><div className="text-[16px] font-semibold text-[var(--color-ink)]">{r.asset_name ?? 'Asset'}</div><div className="text-[12px] text-[var(--color-mute)]">{r.country_name} · {PERIL[r.peril]}</div></div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="text-[12px] text-[var(--color-mute)] mb-2">Loss at each return period</div>
      <div className="space-y-1.5 mb-5">
        {rps.map(([rp, v]) => {
          const protectedRp = !projected && r.protection_rp_years != null && +rp < r.protection_rp_years
          return (
            <div key={rp} className="flex items-center gap-2 text-[11.5px]">
              <span className="w-14 text-[var(--color-faint)]">1-in-{rp}</span>
              <div className="flex-1 h-2.5 rounded bg-[var(--color-panel-2)] relative">
                <div className="absolute inset-y-0 rounded bg-[var(--color-warn)]/25" style={{ left: `${(v.low / max) * 100}%`, width: `${Math.max(0.5, ((v.high - v.low) / max) * 100)}%` }} />
                <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.max(1, (v.central / max) * 100)}%`, background: protectedRp ? 'var(--color-good)' : 'var(--color-warn)', opacity: protectedRp ? 0.5 : 1 }} />
              </div>
              <span className="w-16 text-right tabular-nums">{balance(v.central)}</span>
            </div>
          )
        })}
      </div>
      {fact('Expected yearly loss', `${flow(r.eal_eur)} (${flow(r.eal_low_eur)} – ${flow(r.eal_high_eur)})`)}
      {!projected && r.peril === 'flood' && fact('Defended', r.eal_defended_eur != null ? flow(r.eal_defended_eur) : '—')}
      {fact('Building value', r.exposed_value_eur ? balance(r.exposed_value_eur) : '—')}
      {fact('Building use', r.occupancy ?? '—')}
      {fact('Damage curve', r.curve_name ?? '—')}
      {r.standing && fact('Standing', <span className="inline-flex items-center gap-1.5"><StandingChip s={r.standing} /><InfoButton compact details={{ title: STANDING[r.standing].label, sections: [{ heading: HEADING.shows, body: STANDING[r.standing].what }] }} /></span>)}
      {r.protection_message && fact('Flood defences', <MessageLine m={r.protection_message} />)}
      {r.caution_message && fact('Caution', <MessageLine m={r.caution_message} />)}
      {!projected && r.protection_rp_years != null && <div className="text-[11px] text-[var(--color-faint)] mt-2">Green bars: floods more frequent than the defence level — set to zero in the defended figure.</div>}
    </Drawer>
  )
}

function Methods({ families, onClose }: { families?: Families; onClose: () => void }) {
  const layers = useQuery({ queryKey: ['loss-layers'], queryFn: () => api.get<{ layers: Layer[]; protection_layers: ProtectionLayer[] }>('/v1/loss/layers') })
  const h = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-5 mb-2">{t}</h4>
  const skill = (L: Layer) => {
    const p = L.test?.pooled
    const a = p?.europe ?? p?.m30, b = p?.global ?? p?.m90
    return a && b ? `Check on six observed floods — ranking agreement ${a.rho.toFixed(2)} (current maps ${b.rho.toFixed(2)}), hit rate ${a.auc_share_gt_2pct.toFixed(2)} (${b.auc_share_gt_2pct.toFixed(2)})` : null
  }
  return (
    <Drawer label="Methods and data sources" onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-center justify-between"><div className="text-[16px] font-semibold text-[var(--color-ink)]">Methods and data sources</div><CloseButton onClick={onClose} /></div>
      {h('Damage curves')}
      <div className="space-y-3 text-[13px]">
        {(['flood', 'storm'] as const).map(p => {
          const k = families?.adopted[p]
          const f = families?.families.find(x => x.family === k)
          return <div key={p}><span className="text-[var(--color-mute)]">{PERIL[p]}: </span>{f ? f.name : <>none chosen · <Link to="/admin?tab=Methodology" className="text-[var(--color-sky)]">choose in Methodology</Link></>}</div>
        })}
        {families?.families.map(f => (
          <div key={f.family} className="rounded-lg border border-[var(--color-line-2)] p-3">
            <div className="font-semibold text-[var(--color-ink)]">{f.name}</div>
            <div className="text-[12px] text-[var(--color-mute)] mt-0.5">{f.kind === 'measured' ? 'Built from observed claims' : 'Published'}{f.source?.authors ? ` · ${f.source.authors}${f.source.year ? ` (${f.source.year})` : ''}` : ''} · {f.curves.length} curves</div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {f.test ? <StatusChip label={f.test.passed ? 'Tested' : 'Failed its test'} tone={f.test.passed ? 'good' : 'warn'} /> : (() => {
                const failed = f.curves.filter(c => c.test && !c.test.passed).length
                return <>
                  <StatusChip label={`${f.curves.filter(c => c.test).length} of ${f.curves.length} tested`} tone="neutral" />
                  {failed > 0 && <StatusChip label={failed === 1 ? '1 failed its test' : `${failed} failed their test`} tone="warn" />}
                </>
              })()}
            </div>
          </div>
        ))}
        {(families?.refused.length ?? 0) > 0 && <div className="text-[12px] text-[var(--color-mute)]">Not usable yet: {families!.refused.map(r => r.name).join(', ')} — not yet compatible with the platform’s hazard data.</div>}
      </div>
      {h('Hazard maps')}
      <div className="space-y-3 text-[13px]">
        {(layers.data?.layers ?? []).map(L => (
          <div key={L.key} className="rounded-lg border border-[var(--color-line-2)] p-3">
            <div className="flex items-center justify-between gap-2"><span className="font-semibold text-[var(--color-ink)]">{L.name}</span>{L.status && <StatusChip value={LAYER_STATUS[L.status] ?? 'candidate'} label={L.status === 'in_use' ? 'In use' : L.status === 'refused' ? 'Not used' : 'Candidate'} />}</div>
            <div className="text-[12px] text-[var(--color-mute)] mt-0.5">{PERIL[L.peril]}{L.resolution_m ? ` · ${L.resolution_m} m` : ''} · 1-in-{L.return_periods.join(', ')} years · read at {L.sampled.places.toLocaleString()} places</div>
            {skill(L) && <div className="text-[12px] text-[var(--color-ink)] mt-1.5">{skill(L)}</div>}
          </div>
        ))}
      </div>
      {h('Flood protection')}
      {(layers.data?.protection_layers ?? []).map(P => (
        <div key={P.key} className="rounded-lg border border-[var(--color-line-2)] p-3 text-[13px]">
          <div className="font-semibold text-[var(--color-ink)]">{P.name}</div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">{P.resolution_m} m · a level at {(P.sampled.with_a_level ?? 0).toLocaleString()} places, unknown at {((P.sampled.no_value ?? 0) + (P.sampled.outside_coverage ?? 0)).toLocaleString()}</div>
          <div className="text-[12px] text-[var(--color-mute)] mt-1">Licence: {P.licence.split(' (')[0]}</div>
        </div>
      ))}
    </Drawer>
  )
}
