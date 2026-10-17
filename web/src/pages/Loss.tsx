import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Calculator, FlaskConical, Layers, ListX, Play } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { balance, flow } from '../lib/money'
import { toast } from '../lib/toast'
import { arrivedRun } from '../lib/runWait'
import { PageHeader, Card, StatGrid, SectionHead, Button } from '../components/ui'
import { HBar } from '../components/Charts'
import ReviewTabs from '../components/ReviewTabs'

// Loss from the hazard itself (E171): a money figure per asset and peril, read off a damage curve the institution
// adopted at the hazard's physical intensity (flood depth in metres, wind in m/s) by return period — always a range
// with the standing the curve's test gave it (published · held · untested), or a named gap. Figures of different
// standing are never added together; a refused curve family is shown with why, never offered.

type Standing = 'published' | 'held' | 'untested'
interface Curve { key: string; occupancy: string; region: string | null; countries: string[]; sd?: number[][] | null; spread?: string | null; test?: FamilyTest | null }
interface FamilyTest { passed: boolean; band_coverage?: number; events_tested?: number; events_within_tolerance?: number; median_abs_error?: number; passed_band?: boolean; passed_event_total?: boolean; protocol?: string }
interface Family { family: string; kind: 'published' | 'measured'; peril: string; metric: string; unit: string; damage_basis: string | null; source: { authors?: string; title?: string; year?: number; url?: string } | null; curves: Curve[]; test: FamilyTest | null; derivation: { claims_used?: number } | null; regions_basis?: string | null; absent?: string[] | null; not_carried?: Record<string, string> | null }
interface Families { families: Family[]; refused: { family: string; reasons: string[] }[]; adopted: Record<string, string | null>; dependence: Record<string, string | null>; headline: Record<string, 'defended' | 'undefended' | null> }
interface Skill { rho: number; auc_share_gt_2pct: number }
interface Layer { key: string; peril: string; metric: string; unit: string; version: string; source: string; resolution_m: number | null; return_periods: number[]; licence: string | null; licence_status: string | null; status: string | null; replaces?: string | null; coverage_countries?: string | null; caution?: string | null; test: { passed: boolean; pooled?: { m90?: Skill; m30?: Skill; global?: Skill; europe?: Skill } } | null; decision?: { date: string; outcome: string; basis: string } | null; present_day_check?: Projection['present_day_check'] | null; use?: { role: string; compared_with: string } | null; building_scale_test?: { verdict: string; csi_difference_90pct_interval: [number, number]; pooled: { pixels: number; m90: { csi: number }; m30: { csi: number } } } | null; sampled: { places: number; outside_coverage: number; maps?: number } }
interface ProtectionLayer { key: string; version: string; source: string; resolution_m: number; coverage: string; licence: string; sampled: { places: number; with_a_level?: number; no_value?: number; outside_coverage?: number } }
interface RunRow { run_id: string; book: string; scenario: string; time_horizon: string; as_of: string; n_assets: number; n_gaps: number; created_at: string; families_adopted: Record<string, string | null> }
interface Projection { source: string; citation: string; licence: string; periods: Record<string, string>; models: string[]; flood: { scenario: string; horizon: string; gap: string | null }[]; storm: string | null; present_day_check?: { against_observed: { pooled: { aqueduct: { rho: number; auc_share_gt_2pct: number }; jrc: { rho: number; auc_share_gt_2pct: number } } }; agreement_at_assets: { agree_share: number; locations: number } } }
interface Band { low: number; central: number; high: number }
interface Result { asset_id: string; asset_name: string | null; country: string | null; peril: string; exposed_value_eur: number | null; occupancy: string | null; curve_key: string | null; eal_eur: number | null; eal_low_eur: number | null; eal_high_eur: number | null; standing: Standing | null; loss_at_rp: Record<string, Band> | null; gap: string | null; eal_same_source_today_eur: number | null; model_eal: Record<string, number> | null; flood_layer: string | null; protection_rp_years: number | null; protection_basis: string | null; caution: string | null; eal_defended_eur: number | null; eal_defended_low_eur: number | null; eal_defended_high_eur: number | null }
interface ProjectionInputs { key: string; pathway: string; period: string; models: string[] }
interface RunDetail { run: RunRow & { inputs: { layers?: { flood?: ProjectionInputs | { key: string } } } }; totals: Total[]; gaps: { reason: string; count: number }[]; results: Result[]; book_curve: { peril: string; rp_years: number; loss_eur: number }[] }

interface Total { peril: string; standing: Standing; results: number; eal_low_eur: number; eal_eur: number; eal_high_eur: number; eal_same_source_today_eur: number | null; defended_results: number; eal_defended_low_eur: number; eal_defended_eur: number; eal_defended_high_eur: number; eal_undefended_same_results_eur: number; protection_unknown_results: number; eal_protection_unknown_eur: number }
const FLOOD_MAP: Record<string, string> = { jrc_river_flood: 'JRC global maps', jrc_river_flood_europe: 'JRC European maps', aqueduct_river_flood: 'WRI Aqueduct' }
const LAYER_STATUS: Record<string, string> = { in_use: 'in use', candidate: 'candidate — not used', refused: 'refused — not used' }

const BOOKS: Record<string, { key: string; label: string }[]> = {
  bank: [{ key: 'banking', label: 'Loan book' }],
  insurer: [{ key: 'insurance', label: 'Insured properties' }, { key: 'insurer_investments', label: 'Investments' }],
  asset_manager: [{ key: 'assetmgmt', label: 'Holdings' }],
  reit: [{ key: 'realestate', label: 'Properties' }],
  manufacturer: [{ key: 'company_sites', label: 'Own sites' }],
}
const STANDING: Record<Standing, { label: string; hint: string; color: string }> = {
  published: { label: 'Published', hint: 'the curve passed both tests on losses it was not built from', color: 'var(--color-good)' },
  held: { label: 'Held', hint: 'the curve was tested and failed — shown with its test, not for use', color: 'var(--color-warn)' },
  untested: { label: 'Untested', hint: 'no observed losses to test the curve where the asset is', color: 'var(--color-slate)' },
}
const PERIL: Record<string, string> = { flood: 'River flood', storm: 'Tropical cyclone' }
const SCENARIO: Record<string, string> = { baseline: 'Today', disorderly_2c: 'Disorderly 2 °C', hot_house_3_5c: 'Hot house 3.5 °C', orderly_1_5c: 'Orderly 1.5 °C' }
const HORIZONS = ['2030', '2050', '2080', '2100']
const PATHWAY: Record<string, string> = { rcp4p5: 'RCP4.5', rcp8p5: 'RCP8.5' }
const runLabel = (r: RunRow) => r.scenario === 'baseline' ? 'Today' : `${SCENARIO[r.scenario] ?? r.scenario} · ${r.time_horizon}`
const change = (now: number | null, then: number | null) => now == null || !then ? '—' : `${now >= then ? '+' : ''}${(((now - then) / then) * 100).toFixed(0)}%`

function StandingChip({ s }: { s: Standing }) {
  const v = STANDING[s]
  return <span title={v.hint} className="mono text-[10.5px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
    style={{ color: v.color, background: `color-mix(in oklab, ${v.color} 14%, transparent)` }}>{v.label}</span>
}

export default function Loss() {
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const books = BOOKS[type] ?? []
  const canRun = (profile?.permissions ?? []).includes('reports.publish')
  const fams = useQuery({ queryKey: ['loss-families'], queryFn: () => api.get<Families>('/v1/loss/families') })
  const layers = useQuery({ queryKey: ['loss-layers'], queryFn: () => api.get<{ layers: Layer[]; protection_layers: ProtectionLayer[] }>('/v1/loss/layers') })
  const proj = useQuery({ queryKey: ['loss-projection'], queryFn: () => api.get<Projection>('/v1/loss/projection') })
  const [book, setBook] = useState(books[0]?.key ?? '')
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState('2050')
  const projGap = scenario === 'baseline' ? null : proj.data?.flood.find(c => c.scenario === scenario && c.horizon === horizon)?.gap ?? null
  const [waiting, setWaiting] = useState(0)
  const runs = useQuery({
    queryKey: ['loss-runs', book], enabled: !!book,
    queryFn: () => api.get<{ runs: RunRow[] }>(`/v1/loss/runs?book=${book}&limit=20`),
    refetchInterval: waiting ? 3000 : false,
    refetchIntervalInBackground: true,           // a run started here lands even if the tab is out of sight
  })
  const [runId, setRunId] = useState<string | null>(null)
  const [before, setBefore] = useState<string | null>(null)          // the newest run when this one was started
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

  return (
    <div className="space-y-6">
      <ReviewTabs />
      <PageHeader eyebrow="Assess · Loss" title="Loss from the hazard itself"
        lead="Each asset's loss is read off a damage curve at the hazard's physical intensity — flood depth in metres, cyclone wind in metres per second — at each return period. Every figure is a range with the standing its curve earned on observed losses; anything missing is named, never a zero." />
      <Families q={fams.data} loading={fams.isLoading} />
      <Card className="p-5 space-y-4">
        <SectionHead icon={Calculator} hint="every asset and peril, recorded and never edited">Loss runs</SectionHead>
        {books.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">Your sector holds no book of physical assets to run losses over.</div> : (
          <div className="flex flex-wrap items-center gap-3">
            <select value={book} onChange={e => { setBook(e.target.value); setRunId(null) }} aria-label="Book"
              className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
              {books.map(b => <option key={b.key} value={b.key}>{b.label}</option>)}
            </select>
            <select value={scenario} onChange={e => setScenario(e.target.value)} aria-label="Climate"
              className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
              {Object.entries(SCENARIO).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            {scenario !== 'baseline' && (
              <select value={horizon} onChange={e => setHorizon(e.target.value)} aria-label="Year"
                className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
                {HORIZONS.map(h => <option key={h} value={h}>{h}{proj.data?.periods[h] ? ` (${proj.data.periods[h]})` : ''}</option>)}
              </select>
            )}
            {canRun && <Button onClick={start} disabled={!!waiting || !!projGap}><Play size={14} className="inline -mt-0.5 mr-1" />{waiting ? 'Running…' : 'Run losses now'}</Button>}
            {(runs.data?.runs.length ?? 0) > 0 && (
              <select value={shown ?? ''} onChange={e => setRunId(e.target.value)} aria-label="Run"
                className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
                {runs.data!.runs.map(r => <option key={r.run_id} value={r.run_id}>{runLabel(r)} · {new Date(r.created_at).toLocaleString()} · {r.n_assets} assets</option>)}
              </select>
            )}
          </div>
        )}
        {projGap && <div className="text-[12px] text-[var(--color-warn)]">Not available: {projGap}.</div>}
        {shown ? <RunView runId={shown} headline={fams.data?.headline?.flood ?? null} /> : books.length > 0 && !runs.isLoading &&
          <div className="text-[12.5px] text-[var(--color-faint)]">No loss run yet for this book.</div>}
      </Card>
      <LayersView layers={layers.data?.layers ?? []} protection={layers.data?.protection_layers ?? []} />
    </div>
  )
}

function Families({ q, loading }: { q?: Families; loading: boolean }) {
  if (loading || !q) return <Card className="p-5 text-[12.5px] text-[var(--color-faint)]">Loading curve families…</Card>
  return (
    <Card className="p-5 space-y-4">
      <SectionHead icon={FlaskConical} hint="adopted in Settings → Methodology (audited, 4-eyes where required)">Damage-curve families</SectionHead>
      <div className="grid gap-3 md:grid-cols-2">
        {(['flood', 'storm'] as const).map(p => (
          <div key={p} className="rounded-lg border border-[var(--color-line-2)] px-3.5 py-3">
            <div className="text-[12px] text-[var(--color-mute)]">{PERIL[p]} · adopted</div>
            <div className="text-[14px] font-semibold text-[var(--color-ink)] mt-0.5">{q.adopted[p] ?? 'None — every loss for this peril is a named gap'}</div>
            {p === 'flood' && <div className="text-[11.5px] text-[var(--color-mute)] mt-1">Book exceedance curve: {q.dependence.flood ? `assets combined ${q.dependence.flood}` : 'not stated — no book curve, each asset stands alone'}</div>}
            {p === 'flood' && <div className="text-[11.5px] text-[var(--color-mute)] mt-0.5">Leads with: {q.headline?.flood ? `the ${q.headline.flood} figure` : 'not stated — defended and undefended shown side by side'}</div>}
          </div>
        ))}
      </div>
      {q.families.map(f => (
        <div key={f.family} className="border-t border-[var(--color-line)] pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-semibold text-[var(--color-ink)]">{f.family}</span>
            <span className="mono text-[10.5px] text-[var(--color-mute)]">{f.kind} · {PERIL[f.peril] ?? f.peril} · {f.metric} ({f.unit})</span>
            {f.test && <StandingChip s={f.test.passed ? 'published' : 'held'} />}
          </div>
          <div className="text-[12px] text-[var(--color-mute)] mt-1">
            {f.source?.authors}{f.source?.year ? ` (${f.source.year})` : ''}{f.source?.title ? ` — ${f.source.title}` : ''}
            {f.derivation?.claims_used ? ` · built from ${f.derivation.claims_used.toLocaleString()} claims` : ''}
            {' · '}{f.curves.length} curve{f.curves.length === 1 ? '' : 's'} for {(() => { const cs = Array.from(new Set(f.curves.flatMap(c => c.countries))); return cs.length <= 10 ? cs.join(', ') : `${cs.length} countries` })()}
          </div>
          {f.kind === 'published' && (
            <div className="text-[12px] text-[var(--color-mute)] mt-1.5 space-y-1">
              <div>{f.curves.length} curves ({Array.from(new Set(f.curves.map(c => c.occupancy))).join(', ')}) by region{f.regions_basis ? ' — regions are the UN M49 groupings' : ''}; {f.curves.filter(c => c.sd).length} with a published range (± one standard deviation), {f.curves.filter(c => c.spread === 'none published').length} with none published.</div>
              {f.curves.filter(c => c.test).map(c => (
                <div key={c.key} className="text-[var(--color-ink)] flex flex-wrap items-center gap-2">
                  <span className="mono text-[10.5px]">{c.occupancy} · {c.region}</span>
                  <StandingChip s={c.test!.passed ? 'published' : 'held'} />
                  <span>tested on {c.test!.events_tested} US flood events: totals within ±30% in {c.test!.events_within_tolerance}; range holds {((c.test!.band_coverage ?? 0) * 100).toFixed(0)}% of claims</span>
                </div>
              ))}
              <div>Every other curve is <StandingChip s="untested" /> — no observed losses to test it against.</div>
              {(f.absent ?? []).length > 0 && <div>Not in the source: {f.absent!.join('; ')}.</div>}
            </div>
          )}
          {f.test && (
            <div className="text-[12px] text-[var(--color-ink)] mt-1.5 flex flex-wrap gap-x-5 gap-y-1">
              {f.test.band_coverage != null && <span>Range holds {(f.test.band_coverage * 100).toFixed(1)}% of held-out claims (75–85% needed) — {f.test.passed_band ? 'pass' : 'fail'}</span>}
              {f.test.events_tested != null && <span>Event totals within ±30%: {f.test.events_within_tolerance} of {f.test.events_tested} (two thirds needed) — {f.test.passed_event_total ? 'pass' : 'fail'}</span>}
            </div>
          )}
        </div>
      ))}
      {q.refused.length > 0 && (
        <div className="border-t border-[var(--color-line)] pt-3">
          <div className="text-[12px] font-semibold text-[var(--color-ink)] mb-1">Registered but not usable</div>
          {q.refused.map(r => <div key={r.family} className="text-[12px] text-[var(--color-mute)]"><span className="mono text-[var(--color-ink)]">{r.family}</span> — {r.reasons.join('; ')}</div>)}
        </div>
      )}
    </Card>
  )
}

function FloodTotal({ t, headline }: { t: Total; headline: 'defended' | 'undefended' | null }) {
  const lead = (k: 'defended' | 'undefended') => headline === k && <span className="mono text-[9.5px] ml-1.5 px-1.5 py-0.5 rounded-full border border-[var(--color-sky)] text-[var(--color-ink)]">leads</span>
  return (
    <div className="grid grid-cols-2 gap-3 mt-1.5">
      <div>
        <div className="text-[10.5px] text-[var(--color-mute)]">Undefended{lead('undefended')}</div>
        <div className="display text-[18px] tabular-nums">{flow(t.eal_eur)}</div>
        <div className="text-[10.5px] text-[var(--color-mute)] tabular-nums">{flow(t.eal_low_eur)} – {flow(t.eal_high_eur)} · {t.results} assets</div>
      </div>
      <div>
        <div className="text-[10.5px] text-[var(--color-mute)]">Defended{lead('defended')}</div>
        <div className="display text-[18px] tabular-nums">{t.defended_results ? flow(t.eal_defended_eur) : '—'}</div>
        <div className="text-[10.5px] text-[var(--color-mute)] tabular-nums">{t.defended_results ? `${flow(t.eal_defended_low_eur)} – ${flow(t.eal_defended_high_eur)} · ${t.defended_results} assets (undefended ${flow(t.eal_undefended_same_results_eur)})` : 'no protection level known'}</div>
      </div>
      {t.protection_unknown_results > 0 && <div className="col-span-2 text-[10.5px] text-[var(--color-warn)]">Protection unknown at {t.protection_unknown_results} asset{t.protection_unknown_results === 1 ? '' : 's'}: {flow(t.eal_protection_unknown_eur)} undefended, not in the defended sum.</div>}
    </div>
  )
}

function RunView({ runId, headline }: { runId: string; headline: 'defended' | 'undefended' | null }) {
  const q = useQuery({ queryKey: ['loss-run', runId], queryFn: () => api.get<RunDetail>(`/v1/loss/runs/${runId}`) })
  const [peril, setPeril] = useState<'all' | string>('all')
  const rows = useMemo(() => (q.data?.results ?? []).filter(r => peril === 'all' || r.peril === peril), [q.data, peril])
  if (q.isLoading || !q.data) return <div className="text-[12.5px] text-[var(--color-faint)]">Loading the run…</div>
  const d = q.data
  const withFigure = d.results.filter(r => !r.gap)
  const fl = d.run.inputs.layers?.flood as ProjectionInputs | undefined
  const projected = d.run.scenario !== 'baseline'
  return (
    <div className="space-y-5">
      {projected && fl?.pathway && (
        <div className="rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 text-[12.5px] text-[var(--color-ink)]">
          <span className="font-semibold">{SCENARIO[d.run.scenario]} · {d.run.time_horizon}</span>: flood depth from WRI Aqueduct Floods, {PATHWAY[fl.pathway] ?? fl.pathway}, period {fl.period}, five climate models. The central figure is the middle model; the range spans the lowest and highest. Each figure is compared only with Aqueduct's own present day, never with today's run (which reads the JRC maps).
        </div>
      )}
      <StatGrid cols={4} items={[
        { label: 'Assets', value: d.run.n_assets.toLocaleString(), sub: `as of ${d.run.as_of}` },
        { label: 'Asset–peril figures', value: withFigure.length.toLocaleString(), sub: 'a range each, with its standing' },
        { label: 'Named gaps', value: d.gaps.reduce((a, g) => a + g.count, 0).toLocaleString(), sub: `${d.gaps.length} reason${d.gaps.length === 1 ? '' : 's'}`, accent: d.gaps.length ? 'var(--color-warn)' : undefined },
        { label: 'Assets with no figure', value: d.run.n_gaps.toLocaleString(), sub: 'for any peril' },
      ]} />
      {d.totals.length > 0 && (
        <div>
          <div className="text-[12px] font-semibold text-[var(--color-ink)] mb-2">Expected annual loss, by peril and standing — never added across standing</div>
          <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3">
            {d.totals.map(t => (
              <div key={`${t.peril}:${t.standing}`} className={`rounded-lg border border-[var(--color-line-2)] px-3.5 py-3 ${t.peril === 'flood' && !projected ? 'sm:col-span-2' : ''}`}>
                <div className="flex items-center justify-between gap-2"><span className="text-[12px] text-[var(--color-ink)]">{PERIL[t.peril] ?? t.peril}</span><StandingChip s={t.standing} /></div>
                {t.peril === 'flood' && !projected ? <FloodTotal t={t} headline={headline} /> : (<>
                <div className="display text-[20px] tabular-nums mt-1.5">{flow(t.eal_eur)}</div>
                <div className="text-[11px] text-[var(--color-mute)] mt-1 tabular-nums">range {flow(t.eal_low_eur)} – {flow(t.eal_high_eur)} · {t.results} asset{t.results === 1 ? '' : 's'}</div></>)}
                {t.eal_same_source_today_eur != null && <div className="text-[11px] text-[var(--color-mute)] mt-0.5 tabular-nums">same source today {flow(t.eal_same_source_today_eur)} · change {change(t.eal_eur, t.eal_same_source_today_eur)}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
      {d.gaps.length > 0 && (
        <div>
          <SectionHead icon={ListX} hint="what would turn each into a figure" className="mb-2">Why figures are missing</SectionHead>
          <HBar data={d.gaps.map(g => ({ label: g.reason, value: g.count }))} format={n => `${n}`} />
        </div>
      )}
      <div>
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span className="text-[12px] font-semibold text-[var(--color-ink)]">Per asset</span>
          {['all', 'flood', 'storm'].map(p => (
            <button key={p} onClick={() => setPeril(p)} className={`px-2.5 py-1 text-[11.5px] rounded-full border ${peril === p ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>{p === 'all' ? 'All perils' : PERIL[p]}</button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] tabular-nums">
            <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
              <th className="py-1.5 pr-3 font-medium">Asset</th><th className="pr-3 font-medium">Peril</th><th className="pr-3 font-medium text-right" title="The value the curve's ratio is taken of — for a building curve, the building's own value (land excluded) as your book states it">Building value</th>
              <th className="pr-3 font-medium">Use · curve</th><th className="pr-3 font-medium">Standing</th>
              <th className="pr-3 font-medium text-right">Expected annual loss (range){!projected && ' — undefended'}</th>
              {!projected && <th className="pr-3 font-medium text-right" title="Losses from floods more frequent than the local protection level set to zero (JRC map of European protection standards)">Defended (protection level)</th>}
              {projected && <th className="pr-3 font-medium text-right" title="The same asset in the projection source's own present-day map — the only figure a projected loss is compared with">Same source today</th>}
              <th className="font-medium text-right">1-in-100 loss</th>
            </tr></thead>
            <tbody>
              {rows.slice(0, 200).map(r => (
                <tr key={`${r.asset_id}:${r.peril}`} className="border-b border-[var(--color-line)] align-top">
                  <td className="py-1.5 pr-3 text-[var(--color-ink)]">{r.asset_name ?? r.asset_id.slice(0, 8)}<span className="text-[var(--color-faint)]"> {r.country}</span></td>
                  <td className="pr-3">{PERIL[r.peril] ?? r.peril}</td>
                  <td className="pr-3 text-right">{r.exposed_value_eur ? balance(r.exposed_value_eur) : '—'}</td>
                  {r.gap ? <td colSpan={5} className="pr-3 text-[var(--color-warn)]">{r.gap}</td> : (<>
                    <td className="pr-3 text-[var(--color-mute)]">{r.occupancy} · <span className="mono text-[10.5px]">{r.curve_key}</span>{r.flood_layer && <div className="text-[10.5px] text-[var(--color-faint)]">{FLOOD_MAP[r.flood_layer] ?? r.flood_layer}</div>}</td>
                    <td className="pr-3">{r.standing && <StandingChip s={r.standing} />}</td>
                    <td className="pr-3 text-right">{flow(r.eal_eur)} <span className="text-[var(--color-faint)]">({flow(r.eal_low_eur)} – {flow(r.eal_high_eur)})</span>{r.caution && <div className="text-[10.5px] text-[var(--color-warn)]" title={r.caution}>publisher's caution: depths here may be spurious</div>}</td>
                    {!projected && <td className="pr-3 text-right" title={r.protection_basis ?? undefined}>{r.peril !== 'flood' ? '—' : r.eal_defended_eur != null ? <>{flow(r.eal_defended_eur)} <span className="text-[var(--color-faint)]">(1-in-{r.protection_rp_years})</span></> : <span className="text-[var(--color-warn)]">protection unknown</span>}</td>}
                    {projected && <td className="pr-3 text-right" title={r.model_eal ? Object.entries(r.model_eal).map(([m, v]) => `${m.replace(/^0+/, '')}: ${flow(v)}`).join('\n') : undefined}>{flow(r.eal_same_source_today_eur)} <span className="text-[var(--color-faint)]">{change(r.eal_eur, r.eal_same_source_today_eur)}</span></td>}
                    <td className="text-right">{r.loss_at_rp?.['100'] ? balance(r.loss_at_rp['100'].central) : '—'}</td>
                  </>)}
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length > 200 && <div className="text-[11.5px] text-[var(--color-faint)] mt-2">Showing the first 200 of {rows.length}, largest expected loss first.</div>}
        </div>
      </div>
      {d.book_curve.length > 0 && (
        <div className="text-[12px] text-[var(--color-ink)]">
          <span className="font-semibold">Book flood loss by return period</span> (published figures, assets combined as stated): {d.book_curve.map(p => `1-in-${p.rp_years}: ${balance(p.loss_eur)}`).join(' · ')}
        </div>
      )}
    </div>
  )
}

function LayersView({ layers, protection }: { layers: Layer[]; protection: ProtectionLayer[] }) {
  if (!layers.length) return null
  return (
    <Card className="p-5">
      <SectionHead icon={Layers} hint="physical units by return period, sampled at every asset location" className="mb-3">Hazard intensity layers</SectionHead>
      <div className="divide-y divide-[var(--color-line)]">
        {layers.map(L => (
          <div key={L.key} className="py-2.5 text-[12px]">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-[var(--color-ink)]">{L.key}</span>
              <span className="mono text-[10.5px] text-[var(--color-mute)]">{L.version} · {L.metric} ({L.unit}){L.resolution_m ? ` · ${L.resolution_m} m` : ''} · 1-in-{L.return_periods.join(', ')} years</span>
              {L.status && <span className="mono text-[10.5px] px-2 py-0.5 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)]">{LAYER_STATUS[L.status] ?? L.status}</span>}
            </div>
            <div className="text-[var(--color-mute)] mt-0.5">{L.source}</div>
            <div className="text-[var(--color-mute)] mt-0.5">Sampled at {L.sampled.places.toLocaleString()} places{(L.sampled.maps ?? 1) > 1 ? ` on ${L.sampled.maps} maps` : ''}{L.sampled.outside_coverage ? ` (${L.sampled.outside_coverage.toLocaleString()} outside its coverage)` : ''} · licence: {L.licence ?? L.licence_status ?? 'not recorded'}</div>
            {L.test?.pooled?.m30 && L.test.pooled.m90 && (
              <div className="text-[var(--color-ink)] mt-0.5">Test against observed flood extents (0.1° areas): rank correlation {L.test.pooled.m30.rho.toFixed(3)} vs {L.test.pooled.m90.rho.toFixed(3)} for the 90 m maps; AUC {L.test.pooled.m30.auc_share_gt_2pct.toFixed(3)} vs {L.test.pooled.m90.auc_share_gt_2pct.toFixed(3)}{L.status === 'in_use' ? ' — in use' : ' — not in use'}</div>
            )}
            {L.replaces && <div className="text-[var(--color-ink)] mt-0.5">Replaces {FLOOD_MAP[L.replaces] ?? L.replaces} for assets in: {L.coverage_countries}{L.status !== 'in_use' && ' — once its check lets it into use'}.</div>}
            {L.test?.pooled?.europe && L.test.pooled.global && (
              <div className="text-[var(--color-ink)] mt-0.5">Check on six observed floods: rank correlation {L.test.pooled.europe.rho.toFixed(3)} vs {L.test.pooled.global.rho.toFixed(3)} for the global maps; AUC {L.test.pooled.europe.auc_share_gt_2pct.toFixed(3)} vs {L.test.pooled.global.auc_share_gt_2pct.toFixed(3)} — {L.test.passed ? 'not worse: in use' : 'worse: refused'}</div>
            )}
            {L.caution && <div className="text-[var(--color-mute)] mt-0.5">Publisher's caution: {L.caution}</div>}
            {L.use && <div className="text-[var(--color-ink)] mt-0.5"><span className="font-semibold">Use:</span> {L.use.role}; {L.use.compared_with}.</div>}
            {L.present_day_check && (
              <div className="text-[var(--color-ink)] mt-0.5">Present-day check on six observed floods: rank correlation {L.present_day_check.against_observed.pooled.aqueduct.rho.toFixed(2)} vs {L.present_day_check.against_observed.pooled.jrc.rho.toFixed(2)} for the JRC maps, AUC {L.present_day_check.against_observed.pooled.aqueduct.auc_share_gt_2pct.toFixed(2)} vs {L.present_day_check.against_observed.pooled.jrc.auc_share_gt_2pct.toFixed(2)}; agrees with the JRC maps on wet or dry at {(L.present_day_check.agreement_at_assets.agree_share * 100).toFixed(0)}% of {L.present_day_check.agreement_at_assets.locations.toLocaleString()} asset locations. Reported, not a gate: a future cannot be tested.</div>
            )}
            {L.decision && (
              <div className="text-[var(--color-ink)] mt-0.5"><span className="font-semibold">Decision ({L.decision.date}):</span> {L.decision.outcome} — {L.decision.basis}.</div>
            )}
            {L.building_scale_test && (
              <div className="text-[var(--color-ink)] mt-0.5">Building-scale test ({L.building_scale_test.pooled.pixels.toLocaleString()} pixels of 30 m): flood maps' success index {L.building_scale_test.pooled.m30.csi.toFixed(3)} vs {L.building_scale_test.pooled.m90.csi.toFixed(3)} for the 90 m maps; the difference lies within {L.building_scale_test.csi_difference_90pct_interval[0].toFixed(3)} to {L.building_scale_test.csi_difference_90pct_interval[1].toFixed(3)} — {L.building_scale_test.verdict === 'better' ? 'better' : L.building_scale_test.verdict === 'worse' ? 'worse' : 'the test cannot tell them apart'}</div>
            )}
          </div>
        ))}
      </div>
      {protection.map(P => (
        <div key={P.key} className="pt-2.5 mt-1 border-t border-[var(--color-line)] text-[12px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-semibold text-[var(--color-ink)]">{P.key}</span>
            <span className="mono text-[10.5px] text-[var(--color-mute)]">{P.version} · flood protection standard (design return period, years) · {P.resolution_m} m</span>
          </div>
          <div className="text-[var(--color-mute)] mt-0.5">{P.source}</div>
          <div className="text-[var(--color-mute)] mt-0.5">Sampled at {P.sampled.places.toLocaleString()} places: {(P.sampled.with_a_level ?? 0).toLocaleString()} with a level, {(P.sampled.no_value ?? 0).toLocaleString()} where the map holds none, {(P.sampled.outside_coverage ?? 0).toLocaleString()} outside it · coverage: {P.coverage} · licence: {P.licence}</div>
        </div>
      ))}
      <div className="text-[11.5px] text-[var(--color-faint)] mt-2">Adopt a damage-curve family in <Link to="/admin" className="underline">Settings → Methodology</Link>.</div>
    </Card>
  )
}
