import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from 'recharts'
import { Satellite, ShieldCheck, FileCheck2, AlertTriangle, Loader2, Percent } from 'lucide-react'
import { api } from '../lib/api'
import { Card, Button, StatusPill, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import Lineage from '../components/Lineage'
import RealizedExposure from '../components/RealizedExposure'
import ReportTabs from '../components/ReportTabs'

interface Disc {
  rollup: { volume_at_risk_eur: number; pct_cogs_at_risk: number; ingredient_spend_eur: number; total_cogs_eur: number }
  csrd: { commodity: string; volume_at_risk_eur: number | null; status: string; calibration: string | null; avg_hazard: number | null; spend_eur: number }[]
  eudr: { summary: Record<string, number>; plots: EudrPlot[] }
}
interface EudrPlot {
  plot_id: string; plot: string; commodity: string; country: string | null; eudr_covered: boolean
  eudr_declared: string | null; eudr_determination: string | null; first_loss_year: number | null; loss_ha: number | null
}
interface Dds {
  dds_id: string; status: string; ready: boolean; reason: string; covered_plots: number; fileable_plots: number
  items: { commodity: string; hs_code: string; trade_name: string; scientific_name: string | null; description: string; plot_count: number; countries_of_production: string[] }[]
  blockers: { plot: string; commodity: string; determination: string; reason: string }[]
  operator_completes: string[]
  reference_number?: string | null; reference_captured_at?: string | null
}

interface Resourcing {
  available: boolean; reallocation_cap_pct: number; total_current_cogs_at_risk_eur: number
  total_avoidable_eur: number; avoidable_pct_of_current: number; n_opportunities: number
  opportunities: { commodity: string; avoidable_eur: number; avoidable_pct: number; shift_spend_eur: number
    from_origin: string; from_yield_shock_pct: number; to_origin: string; to_yield_shock_pct: number }[]
  single_origin_commodities: { commodity: string; origin: string }[]
}

const eur = (n?: number | null) => n == null ? '—' : `€${(n / 1e6).toFixed(1)}m`
const eurk = (n?: number | null) => n == null ? '—' : Math.abs(n) >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

export default function Disclosure() {
  const qc = useQueryClient()
  const disc = useQuery({ queryKey: ['disclosure'], queryFn: () => api.get<Disc>('/v1/supply/disclosure') })
  const rs = useQuery({ queryKey: ['resourcing'], queryFn: () => api.get<Resourcing>('/v1/supply/resourcing') })
  const [dds, setDds] = useState<Dds | null>(null)

  const determine = useMutation({
    mutationFn: () => api.post('/v1/supply/eudr/determine'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['disclosure'] }),
  })
  const assemble = useMutation({
    mutationFn: () => api.post<Dds>('/v1/supply/eudr/dds'),
    onSuccess: (d) => setDds(d),
  })
  const [ref, setRef] = useState('')
  const [ver, setVer] = useState('')
  const capture = useMutation({
    mutationFn: () => api.put<{ reference_number: string; reference_captured_at: string }>(
      `/v1/supply/eudr/dds/${dds!.dds_id}/reference`, { reference_number: ref.trim(), verification_number: ver.trim() || null }),
    onSuccess: (r) => setDds(prev => prev ? { ...prev, status: 'filed', reference_number: r.reference_number, reference_captured_at: r.reference_captured_at } : prev),
  })
  const [prep, setPrep] = useState<{ status: string; internal_reference?: string; note?: string } | null>(null)
  const prepare = useMutation({
    mutationFn: () => api.post<{ status: string; internal_reference?: string; note?: string }>('/v1/supply/eudr/submit'),
    onSuccess: (r) => setPrep(r),
  })

  if (disc.isLoading) return <Center>loading disclosure…</Center>
  if (disc.error || !disc.data) return <Center>Could not load. Is the API running on :8001?</Center>
  const d = disc.data
  const s = d.eudr.summary
  const covered = d.eudr.plots.filter(p => p.eudr_covered)
  const chart = d.csrd.filter(c => (c.volume_at_risk_eur ?? 0) > 0).map(c => ({ name: c.commodity, v: (c.volume_at_risk_eur ?? 0) / 1e6 }))

  return (
    <div className="fadeup space-y-7">
      <ReportTabs />
      <PageHeader eyebrow="Agriculture · Sense → Score → Act"
        title="Disclosure & EUDR (EU Deforestation Regulation)"
        lead="Physical volume-at-risk from your sourcing book, and the EUDR deforestation-free determination per plot — computed from satellite data, traceable end to end." />

      {/* stat row — lead with the answer */}
      <HeroBanner
        eyebrow="Disclosure & EUDR"
        title={(s.covered_plots ?? 0) > 0 && (s.deforestation_free ?? 0) === (s.covered_plots ?? 0)
          ? 'Every covered plot is deforestation-free.'
          : `${s.deforestation_free ?? 0} of ${s.covered_plots ?? 0} plots deforestation-free.`}
        lead="Physical volume-at-risk from your sourcing book and the EUDR determination per plot — computed from satellite data, traceable end to end."
        stat={[
          { label: 'Volume at risk (physical)', value: eur(d.rollup.volume_at_risk_eur), icon: AlertTriangle, tone: '#E8853C' },
          { label: 'of COGS', value: `${(d.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`, icon: Percent, tone: 'var(--color-sky)' },
          { label: 'EUDR-covered plots', value: s.covered_plots ?? 0, icon: Satellite, tone: 'var(--color-sky)' },
          { label: 'Deforestation-free', value: s.deforestation_free ?? 0, icon: ShieldCheck, tone: '#4FA46E' },
        ]} />

      {/* realized exposure — the real yield shocks that have ALREADY hit this buyer's origins (observed hook) */}
      <RealizedExposure />

      {/* re-sourcing / origin substitution — cut COGS-at-risk by shifting to a lower-risk origin you already source */}
      <ResourcingCard rs={rs.data} />

      {/* chart + eudr run */}
      <div className="grid lg:grid-cols-[1.3fr_1fr] gap-4">
        <Card className="p-5">
          <SectionHead hint="€m, physical" className="mb-3">Volume-at-risk by commodity</SectionHead>
          <div className="h-[240px]">
            {chart.length === 0 ? <Empty>No published € yet — commodities still validating.</Empty> :
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ left: -18, right: 8, top: 6 }}>
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#1e2a40' }} tickLine={false} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: '#16223a55' }} contentStyle={{ background: '#111a2c', border: '1px solid #1e2a40', borderRadius: 10, fontSize: 12 }}
                    formatter={(v) => [`€${Number(v).toFixed(2)}m`, 'at risk']} />
                  <Bar dataKey="v" radius={[5, 5, 0, 0]}>
                    {chart.map((_, i) => <Cell key={i} fill="#38bdf8" />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>}
          </div>
        </Card>

        <Card className="p-5 flex flex-col">
          <SectionHead icon={Satellite} className="mb-1">EUDR satellite check</SectionHead>
          <p className="text-[12.5px] text-[var(--color-mute)] mb-4">Run the deforestation-free determination across your covered plots against Hansen forest-loss (post-2020 cutoff).</p>
          <div className="grid grid-cols-2 gap-2 mb-4">
            <Mini n={s.deforestation_free ?? 0} label="deforestation-free" tone="good" />
            <Mini n={s.non_compliant ?? 0} label="non-compliant" tone="bad" />
            <Mini n={s.geolocation_incomplete ?? 0} label="needs polygon" tone="warn" />
            <Mini n={s.insufficient ?? 0} label="insufficient" tone="slate" />
          </div>
          <Button onClick={() => determine.mutate()} disabled={determine.isPending} className="mt-auto justify-center">
            {determine.isPending ? <><Loader2 size={15} className="animate-spin" /> Checking…</> : <><ShieldCheck size={15} /> Run EUDR check</>}
          </Button>
        </Card>
      </div>

      {/* per-plot: declared vs computed */}
      <Card className="p-5">
        <SectionHead className="mb-3">Per plot — declared vs. our satellite determination</SectionHead>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th>
                <th className="font-normal pr-3">Country</th><th className="font-normal pr-3">Declared</th>
                <th className="font-normal pr-3">Our determination</th><th className="font-normal">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {covered.map(p => (
                <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                  <td className="py-2.5 pr-3 text-[var(--color-ink)]">{p.plot}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 mono text-[12px] text-[var(--color-mute)]">{p.country ?? '—'}</td>
                  <td className="pr-3"><span className="mono text-[11px] text-[var(--color-faint)]">{p.eudr_declared ?? '—'}</span></td>
                  <td className="pr-3"><StatusPill status={p.eudr_determination} /></td>
                  <td className="text-[12px] text-[var(--color-mute)]">{p.first_loss_year ? `loss ${p.first_loss_year} · ${p.loss_ha ?? 0} ha` : (p.eudr_determination === 'deforestation_free' ? 'no post-2020 loss' : '—')}</td>
                </tr>
              ))}
              {covered.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-[var(--color-faint)]">No EUDR-covered plots in this book.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {/* DDS */}
      <Card className="p-5">
        <div className="flex items-center justify-between mb-3">
          <SectionHead icon={FileCheck2}>EUDR Due Diligence Statement</SectionHead>
          <Button variant="ghost" onClick={() => assemble.mutate()} disabled={assemble.isPending}>
            {assemble.isPending ? <><Loader2 size={14} className="animate-spin" /> Assembling…</> : 'Assemble DDS'}
          </Button>
        </div>
        {!dds ? <p className="text-[12.5px] text-[var(--color-mute)]">Build a submission-ready statement from the deforestation-free plots. Blockers and operator to-dos are listed honestly.</p> :
          <div className="space-y-4">
            <div className={`flex items-center gap-2 text-[13px] ${dds.ready ? 'text-[var(--color-good)]' : 'text-[var(--color-warn)]'}`}>
              {dds.ready ? <FileCheck2 size={15} /> : <AlertTriangle size={15} />}{dds.reason}
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-2">Statement items ({dds.fileable_plots} fileable plots)</div>
                {dds.items.map(it => (
                  <div key={it.commodity} className="flex items-start justify-between text-[13px] py-1.5 border-b border-[var(--color-line)]">
                    <span>
                      {it.commodity} <span className="mono text-[11px] text-[var(--color-faint)]">HS {it.hs_code}</span>
                      <span className="block text-[11px] text-[var(--color-faint)] italic">
                        {it.scientific_name || <span className="not-italic">scientific name — operator supplies</span>}
                      </span>
                    </span>
                    <span className="text-[var(--color-mute)] text-[12px] text-right shrink-0 pl-3">{it.plot_count} plots · {it.countries_of_production.join(', ') || '—'}</span>
                  </div>
                ))}
                {dds.items.length === 0 && <div className="text-[12px] text-[var(--color-faint)]">No fileable plots yet.</div>}
              </div>
              <div>
                {dds.blockers.length > 0 && <>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-warn)] mb-2">Blockers ({dds.blockers.length})</div>
                  {dds.blockers.slice(0, 5).map((b, i) => (
                    <div key={i} className="text-[12px] text-[var(--color-mute)] py-1"><span className="text-[var(--color-ink)]">{b.plot}</span> — {b.reason}</div>
                  ))}
                </>}
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mt-3 mb-2">Operator completes in TRACES</div>
                {dds.operator_completes.map((c, i) => <div key={i} className="text-[12px] text-[var(--color-mute)] py-0.5">— {c}</div>)}
              </div>
            </div>

            {/* file & capture the TRACES reference */}
            {dds.status === 'filed' ? (
              <div className="rounded-lg border border-[color-mix(in_oklab,var(--color-good)_45%,var(--color-line))] bg-[color-mix(in_oklab,var(--color-good)_9%,transparent)] px-4 py-3">
                <div className="flex items-center gap-2 text-[13px] text-[var(--color-good)]"><FileCheck2 size={15} /> Filed to EU TRACES</div>
                <div className="mono text-[12px] text-[var(--color-ink)] mt-1.5">ref {dds.reference_number}
                  <span className="text-[var(--color-faint)]"> · captured {dds.reference_captured_at ? new Date(dds.reference_captured_at).toLocaleString() : ''}</span></div>
              </div>
            ) : dds.ready ? (
              <div className="space-y-3">
              {/* Tier 2 — direct TRACES submission (prepared by default; live needs operator registration) */}
              <div className="rounded-lg border border-[color-mix(in_oklab,var(--color-sky)_40%,var(--color-line))] bg-[color-mix(in_oklab,var(--color-sky)_7%,transparent)] px-4 py-3">
                <div className="flex items-center justify-between gap-3 mb-2">
                  <div className="text-[12.5px] font-medium text-[var(--color-ink)]">Direct submission (Tier 2)</div>
                  <Button variant="ghost" onClick={() => prepare.mutate()} disabled={prepare.isPending}>
                    {prepare.isPending ? <><Loader2 size={14} className="animate-spin" /> Preparing…</> : 'Prepare TRACES submission'}
                  </Button>
                </div>
                <div className="text-[12px] text-[var(--color-mute)]">Builds &amp; validates the exact submission envelope the client would file. Live submission flips on once the operator is registered in the EU Information System and API credentials are configured — nothing is filed until then.</div>
                {prep && (
                  <div className="mt-2.5 rounded-md border border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-2">
                    <div className="mono text-[12px]"><span className="text-[var(--color-faint)]">status</span> <span className="text-[var(--color-sky)]">{prep.status}</span>
                      {prep.internal_reference && <span className="text-[var(--color-ink)]"> · {prep.internal_reference}</span>}</div>
                    {prep.note && <div className="text-[11px] text-[var(--color-faint)] mt-1">{prep.note}</div>}
                  </div>
                )}
              </div>
              {/* Tier 1 — manual reference capture */}
              <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-4 py-3">
                <div className="text-[12.5px] text-[var(--color-mute)] mb-3">Or file the statement in EU TRACES yourself, then paste the reference number it returns to close the loop — an immutable, audited filing record.</div>
                <div className="flex flex-wrap gap-2 items-end">
                  <div>
                    <label className="block mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">TRACES reference *</label>
                    <input value={ref} onChange={e => setRef(e.target.value)} placeholder="e.g. 25NLABCD1234567"
                      className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)] w-[220px]" />
                  </div>
                  <div>
                    <label className="block mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Verification (optional)</label>
                    <input value={ver} onChange={e => setVer(e.target.value)} placeholder="verification no."
                      className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-sm outline-none focus:border-[var(--color-sky)] w-[180px]" />
                  </div>
                  <Button onClick={() => capture.mutate()} disabled={capture.isPending || !ref.trim()}>
                    {capture.isPending ? <><Loader2 size={14} className="animate-spin" /> Recording…</> : 'Mark filed'}
                  </Button>
                </div>
                {capture.error ? <div className="text-[12px] text-[var(--color-bad)] mt-2">Could not record the reference. Re-assemble and try again.</div> : null}
              </div>
              </div>
            ) : null}
          </div>}
      </Card>

      {/* lineage */}
      <Lineage />
    </div>
  )
}

function Mini({ n, label, tone }: { n: number; label: string; tone: 'good' | 'bad' | 'warn' | 'slate' }) {
  const c = { good: 'var(--color-good)', bad: 'var(--color-bad)', warn: 'var(--color-warn)', slate: 'var(--color-slate)' }[tone]
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-3 py-2">
      <div className="text-lg font-semibold" style={{ color: c }}>{n}</div>
      <div className="text-[10.5px] text-[var(--color-mute)]">{label}</div>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
const Empty = ({ children }: { children: React.ReactNode }) => <div className="h-full grid place-items-center text-[var(--color-faint)] text-[12px]">{children}</div>

function ResourcingCard({ rs }: { rs?: Resourcing }) {
  if (!rs || !rs.available || (rs.n_opportunities === 0 && rs.single_origin_commodities.length === 0)) return null
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 mb-3">
        <div className="text-[13px] font-semibold">Re-sourcing opportunities</div>
        <span className="text-[12px] text-[var(--color-mute)]">cut COGS-at-risk by shifting to a lower-risk origin you already source</span>
        {rs.total_avoidable_eur > 0 && (
          <span className="mono text-[11px] ml-auto" style={{ color: 'var(--color-good)' }}>
            up to {eurk(rs.total_avoidable_eur)} avoidable ({rs.avoidable_pct_of_current}%) · ≤{rs.reallocation_cap_pct}% reallocation
          </span>
        )}
      </div>
      {rs.opportunities.length > 0 ? (
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {rs.opportunities.map(o => (
            <div key={o.commodity} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-[12.5px]">
              <span className="font-semibold text-[var(--color-ink)] w-24">{o.commodity}</span>
              <span className="text-[var(--color-mute)]">
                shift {eurk(o.shift_spend_eur)} from <b className="text-[var(--color-ink)]">{o.from_origin}</b> ({o.from_yield_shock_pct}% shock) → <b className="text-[var(--color-ink)]">{o.to_origin}</b> ({o.to_yield_shock_pct}%)
              </span>
              <span className="mono text-[11px] ml-auto" style={{ color: 'var(--color-good)' }}>avoid {eurk(o.avoidable_eur)} ({o.avoidable_pct}%)</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-[12.5px] text-[var(--color-mute)] py-2">No in-book reallocation available — the opportunities below need a genuinely new origin.</div>
      )}
      {rs.single_origin_commodities.length > 0 && (
        <div className="mt-3 text-[11.5px] text-[var(--color-faint)]">
          <span className="mono uppercase tracking-wide text-[10px]">Single-origin — diversification needs a new supplier region:</span>{' '}
          {rs.single_origin_commodities.map(c => `${c.commodity} (${c.origin})`).join(' · ')}
        </div>
      )}
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-3">
        Reallocates a bounded share (≤{rs.reallocation_cap_pct}%) of each commodity's spend from its highest- to its lowest-risk EXISTING origin; avoided COGS-at-risk = shift × the yield-shock gap. Only origins you already source — a single-origin commodity is flagged, never given a fabricated alternative.
      </div>
    </Card>
  )
}
