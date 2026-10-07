import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Calculator, FlaskConical, Layers, ListX, Play } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { useAuth } from '../lib/auth'
import { balance, flow } from '../lib/money'
import { toast } from '../lib/toast'
import { PageHeader, Card, StatGrid, SectionHead, Button } from '../components/ui'
import { HBar } from '../components/Charts'
import ReviewTabs from '../components/ReviewTabs'

// Loss from the hazard itself (E171): a money figure per asset and peril, read off a damage curve the institution
// adopted at the hazard's physical intensity (flood depth in metres, wind in m/s) by return period — always a range
// with the standing the curve's test gave it (published · held · untested), or a named gap. Figures of different
// standing are never added together; a refused curve family is shown with why, never offered.

type Standing = 'published' | 'held' | 'untested'
interface Curve { key: string; occupancy: string; region: string | null; countries: string[] }
interface FamilyTest { passed: boolean; band_coverage?: number; events_tested?: number; events_within_tolerance?: number; median_abs_error?: number; passed_band?: boolean; passed_event_total?: boolean; protocol?: string }
interface Family { family: string; kind: 'published' | 'measured'; peril: string; metric: string; unit: string; damage_basis: string | null; source: { authors?: string; title?: string; year?: number; url?: string } | null; curves: Curve[]; test: FamilyTest | null; derivation: { claims_used?: number } | null }
interface Families { families: Family[]; refused: { family: string; reasons: string[] }[]; adopted: Record<string, string | null>; dependence: Record<string, string | null> }
interface Layer { key: string; peril: string; metric: string; unit: string; version: string; source: string; resolution_m: number | null; return_periods: number[]; licence: string | null; licence_status: string | null; status: string | null; test: { passed: boolean; pooled?: { m90: { rho: number; auc_share_gt_2pct: number }; m30: { rho: number; auc_share_gt_2pct: number } } } | null; decision?: { date: string; outcome: string; basis: string } | null; building_scale_test?: { verdict: string; csi_difference_90pct_interval: [number, number]; pooled: { pixels: number; m90: { csi: number }; m30: { csi: number } } } | null; sampled: { places: number; outside_coverage: number } }
interface RunRow { run_id: string; book: string; as_of: string; n_assets: number; n_gaps: number; created_at: string; families_adopted: Record<string, string | null> }
interface Band { low: number; central: number; high: number }
interface Result { asset_id: string; asset_name: string | null; country: string | null; peril: string; exposed_value_eur: number | null; occupancy: string | null; curve_key: string | null; eal_eur: number | null; eal_low_eur: number | null; eal_high_eur: number | null; standing: Standing | null; loss_at_rp: Record<string, Band> | null; gap: string | null }
interface RunDetail { run: RunRow & { inputs: Record<string, unknown> }; totals: { peril: string; standing: Standing; results: number; eal_low_eur: number; eal_eur: number; eal_high_eur: number }[]; gaps: { reason: string; count: number }[]; results: Result[]; book_curve: { peril: string; rp_years: number; loss_eur: number }[] }

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
  const layers = useQuery({ queryKey: ['loss-layers'], queryFn: () => api.get<{ layers: Layer[] }>('/v1/loss/layers') })
  const [book, setBook] = useState(books[0]?.key ?? '')
  const [waiting, setWaiting] = useState(0)
  const runs = useQuery({
    queryKey: ['loss-runs', book], enabled: !!book,
    queryFn: () => api.get<{ runs: RunRow[] }>(`/v1/loss/runs?book=${book}&limit=20`),
    refetchInterval: waiting ? 3000 : false,
  })
  const [runId, setRunId] = useState<string | null>(null)
  const latest = runs.data?.runs[0]?.run_id ?? null
  useEffect(() => { if (waiting && latest && latest !== runId) { setWaiting(0); setRunId(latest); toast.success('Loss run recorded.') } }, [latest, waiting, runId])
  useEffect(() => { if (waiting && Date.now() - waiting > 120000) setWaiting(0) }, [runs.dataUpdatedAt, waiting])
  const shown = runId ?? latest

  const start = async () => {
    try {
      await api.post('/v1/loss/runs', { book })
      setRunId(null); setWaiting(Date.now()); toast.info('Loss run started.')
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
            {canRun && <Button onClick={start} disabled={!!waiting}><Play size={14} className="inline -mt-0.5 mr-1" />{waiting ? 'Running…' : 'Run losses now'}</Button>}
            {(runs.data?.runs.length ?? 0) > 0 && (
              <select value={shown ?? ''} onChange={e => setRunId(e.target.value)} aria-label="Run"
                className="rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]">
                {runs.data!.runs.map(r => <option key={r.run_id} value={r.run_id}>{new Date(r.created_at).toLocaleString()} · {r.n_assets} assets</option>)}
              </select>
            )}
          </div>
        )}
        {shown ? <RunView runId={shown} /> : books.length > 0 && !runs.isLoading &&
          <div className="text-[12.5px] text-[var(--color-faint)]">No loss run yet for this book.</div>}
      </Card>
      <LayersView layers={layers.data?.layers ?? []} />
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
            {' · '}{f.curves.length} curve{f.curves.length === 1 ? '' : 's'} for {Array.from(new Set(f.curves.flatMap(c => c.countries))).join(', ')}
          </div>
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

function RunView({ runId }: { runId: string }) {
  const q = useQuery({ queryKey: ['loss-run', runId], queryFn: () => api.get<RunDetail>(`/v1/loss/runs/${runId}`) })
  const [peril, setPeril] = useState<'all' | string>('all')
  const rows = useMemo(() => (q.data?.results ?? []).filter(r => peril === 'all' || r.peril === peril), [q.data, peril])
  if (q.isLoading || !q.data) return <div className="text-[12.5px] text-[var(--color-faint)]">Loading the run…</div>
  const d = q.data
  const withFigure = d.results.filter(r => !r.gap)
  return (
    <div className="space-y-5">
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
              <div key={`${t.peril}:${t.standing}`} className="rounded-lg border border-[var(--color-line-2)] px-3.5 py-3">
                <div className="flex items-center justify-between gap-2"><span className="text-[12px] text-[var(--color-ink)]">{PERIL[t.peril] ?? t.peril}</span><StandingChip s={t.standing} /></div>
                <div className="display text-[20px] tabular-nums mt-1.5">{flow(t.eal_eur)}</div>
                <div className="text-[11px] text-[var(--color-mute)] mt-1 tabular-nums">range {flow(t.eal_low_eur)} – {flow(t.eal_high_eur)} · {t.results} asset{t.results === 1 ? '' : 's'}</div>
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
              <th className="pr-3 font-medium text-right">Expected annual loss (range)</th><th className="font-medium text-right">1-in-100 loss</th>
            </tr></thead>
            <tbody>
              {rows.slice(0, 200).map(r => (
                <tr key={`${r.asset_id}:${r.peril}`} className="border-b border-[var(--color-line)] align-top">
                  <td className="py-1.5 pr-3 text-[var(--color-ink)]">{r.asset_name ?? r.asset_id.slice(0, 8)}<span className="text-[var(--color-faint)]"> {r.country}</span></td>
                  <td className="pr-3">{PERIL[r.peril] ?? r.peril}</td>
                  <td className="pr-3 text-right">{r.exposed_value_eur ? balance(r.exposed_value_eur) : '—'}</td>
                  {r.gap ? <td colSpan={4} className="pr-3 text-[var(--color-warn)]">{r.gap}</td> : (<>
                    <td className="pr-3 text-[var(--color-mute)]">{r.occupancy} · <span className="mono text-[10.5px]">{r.curve_key}</span></td>
                    <td className="pr-3">{r.standing && <StandingChip s={r.standing} />}</td>
                    <td className="pr-3 text-right">{flow(r.eal_eur)} <span className="text-[var(--color-faint)]">({flow(r.eal_low_eur)} – {flow(r.eal_high_eur)})</span></td>
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

function LayersView({ layers }: { layers: Layer[] }) {
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
              {L.status && <span className="mono text-[10.5px] px-2 py-0.5 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)]">{L.status === 'in_use' ? 'in use' : 'candidate — not used'}</span>}
            </div>
            <div className="text-[var(--color-mute)] mt-0.5">{L.source}</div>
            <div className="text-[var(--color-mute)] mt-0.5">Sampled at {L.sampled.places.toLocaleString()} places{L.sampled.outside_coverage ? ` (${L.sampled.outside_coverage.toLocaleString()} outside its coverage)` : ''} · licence: {L.licence ?? L.licence_status ?? 'not recorded'}</div>
            {L.test?.pooled && (
              <div className="text-[var(--color-ink)] mt-0.5">Test against observed flood extents (0.1° areas): rank correlation {L.test.pooled.m30.rho.toFixed(3)} vs {L.test.pooled.m90.rho.toFixed(3)} for the 90 m maps; AUC {L.test.pooled.m30.auc_share_gt_2pct.toFixed(3)} vs {L.test.pooled.m90.auc_share_gt_2pct.toFixed(3)}{L.status === 'in_use' ? ' — in use' : ' — not in use'}</div>
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
      <div className="text-[11.5px] text-[var(--color-faint)] mt-2">Adopt a damage-curve family in <Link to="/admin" className="underline">Settings → Methodology</Link>.</div>
    </Card>
  )
}
