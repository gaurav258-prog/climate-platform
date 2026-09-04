import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Download, CloudRain, Droplets, Trees, ArrowRight, MinusCircle, Code2, Lock, History, ChevronRight, FileCode, CheckCircle2, XCircle, ShieldCheck } from 'lucide-react'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Button, Stat, PageHeader, SectionHead } from '../components/ui'
import ReportTabs from '../components/ReportTabs'

interface Topic {
  topic: string; title: string; standard?: string; material: boolean
  financial_effects?: { asset_value_at_risk_eur: number; business_interruption_eur: number; cogs_at_risk_published_eur: number; exposure_mapped_but_withheld_eur: number }
  own_operations?: { sites: number; sites_water_stressed: number; asset_value_exposed_eur: number }
  upstream?: { plots: number; plots_water_stressed: number; spend_exposed_eur: number; peak_score: number | null }
  eudr_covered_plots?: number; eudr_commodities?: number; deforestation_free?: number; non_compliant?: number
  geolocation_incomplete?: number; not_determined?: number; deforestation_free_pct_of_determined?: number | null; post_cutoff_forest_loss_ha?: number
  protected_areas?: {
    sites_in_protected: number; sites_total: number; site_value_in_protected_eur: number
    plots_in_protected: number; plots_total: number; plot_spend_in_protected_eur: number
    coverage: { loaded: { dataset: string; label: string; geography: string; cells: number }[]; authoritative_global_loaded: boolean; note: string }
    basis: string
  }
  basis?: string; detail_ref?: string; metric_kind?: string; e3_4_note?: string
}
interface Pack {
  entity: { name: string | null; country: string | null; eori: string | null }
  pack: string; reporting_basis: { scenario: string; horizon: string }
  topics: Topic[]
  out_of_scope: { topic: string; label: string; handled_by: string }[]
  provenance: Record<string, string>; note: string
}

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : n >= 1e3 ? `€${(n / 1e3).toFixed(0)}k` : `€${n}`
const ICON: Record<string, typeof CloudRain> = { E1: CloudRain, E3: Droplets, E4: Trees }
const materialPill = (m: boolean) => m
  ? 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_14%,transparent)]'
  : 'text-[var(--color-faint)] bg-[color-mix(in_oklab,var(--color-faint)_14%,transparent)]'

export default function EsrsPack() {
  const q = useQuery({ queryKey: ['esrs-pack'], queryFn: () => api.get<Pack>('/v1/supply/esrs-pack') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const d = q.data

  return (
    <div className="fadeup space-y-7">
      <ReportTabs />
      <PageHeader eyebrow="Compliance · corporate sustainability reporting"
        title="ESRS (European Sustainability Reporting Standards) Climate & Nature pack"
        lead="The ESRS topics driven by our physical-climate & deforestation engine — climate physical risk (E1), water (E3) and biodiversity — deforestation + protected areas (E4) — assembled filing-grade to slot into your wider CSRD statement. GHG accounting, social and governance stay with your other tools, by design."
        actions={<>
          <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.xlsx', `tellumen-esrs-climate-nature-${d.reporting_basis.scenario}.xlsx`)}>
            <Download size={15} /> Excel
          </Button>
          <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.xbrl', `tellumen-esrs-climate-nature-${d.reporting_basis.scenario}.xbrl`)}>
            <Code2 size={15} /> XBRL
          </Button>
          <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.ixbrl', `tellumen-esrs-climate-nature-${d.reporting_basis.scenario}.xhtml`)}>
            <FileCode size={15} /> iXBRL
          </Button>
        </>}>
        <p className="mono text-[11px] text-[var(--color-faint)] mt-2">
          {d.entity.name} · {d.entity.country}{d.entity.eori ? ` · EORI ${d.entity.eori}` : ''} · basis {d.reporting_basis.scenario}/{d.reporting_basis.horizon}
        </p>
      </PageHeader>

      {/* the topics we own */}
      <div className="grid lg:grid-cols-3 gap-4">
        {d.topics.map(t => {
          const Icon = ICON[t.topic] ?? CloudRain
          return (
            <Card key={t.topic} className="p-5 flex flex-col">
              <div className="flex items-center gap-2 mb-3">
                <Icon size={17} className="text-[var(--color-sky)]" />
                <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)]">{t.topic}</span>
                <span className="text-[14px] font-semibold">{t.title}</span>
                <span className={`ml-auto mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${materialPill(t.material)}`}>{t.material ? 'material' : 'not material'}</span>
              </div>

              {t.topic === 'E1' && t.financial_effects && (
                <div className="grid grid-cols-2 gap-y-2 text-[13px] flex-1">
                  <span className="text-[var(--color-mute)]">Asset value at risk</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(t.financial_effects.asset_value_at_risk_eur)}</span>
                  <span className="text-[var(--color-mute)]">Business interruption</span><span className="text-right font-medium">{eur(t.financial_effects.business_interruption_eur)}</span>
                  <span className="text-[var(--color-mute)]">COGS at risk (published)</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(t.financial_effects.cogs_at_risk_published_eur)}</span>
                  <span className="text-[var(--color-mute)]">Exposure mapped · withheld</span><span className="text-right font-medium text-[var(--color-faint)]">{eur(t.financial_effects.exposure_mapped_but_withheld_eur)}</span>
                </div>
              )}
              {t.topic === 'E3' && t.own_operations && t.upstream && (
                <div className="grid grid-cols-2 gap-y-2 text-[13px] flex-1">
                  <span className="text-[var(--color-mute)]">Sites water-stressed</span><span className="text-right font-medium">{t.own_operations.sites_water_stressed}/{t.own_operations.sites}</span>
                  <span className="text-[var(--color-mute)]">Asset value exposed</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(t.own_operations.asset_value_exposed_eur)}</span>
                  <span className="text-[var(--color-mute)]">Plots water-stressed</span><span className="text-right font-medium">{t.upstream.plots_water_stressed}/{t.upstream.plots}</span>
                  <span className="text-[var(--color-mute)]">Spend exposed</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(t.upstream.spend_exposed_eur)}</span>
                </div>
              )}
              {t.topic === 'E4' && (
                <div className="grid grid-cols-2 gap-y-2 text-[13px] flex-1">
                  <span className="text-[var(--color-mute)]">EUDR-covered plots</span><span className="text-right font-medium">{t.eudr_covered_plots}</span>
                  <span className="text-[var(--color-mute)]">Deforestation-free</span><span className="text-right font-medium text-[var(--color-good)]">{t.deforestation_free}{t.deforestation_free_pct_of_determined != null ? ` · ${t.deforestation_free_pct_of_determined}%` : ''}</span>
                  <span className="text-[var(--color-mute)]">Non-compliant</span><span className="text-right font-medium" style={{ color: t.non_compliant ? 'var(--color-bad)' : 'var(--color-ink)' }}>{t.non_compliant}</span>
                  <span className="text-[var(--color-mute)]">Post-cutoff forest loss</span><span className="text-right font-medium">{t.post_cutoff_forest_loss_ha} ha</span>
                  {t.protected_areas && (<>
                    <span className="col-span-2 mt-1.5 text-[11px] uppercase tracking-wide text-[var(--color-faint)]">Protected areas · E4-5</span>
                    <span className="text-[var(--color-mute)]">Sites in / near</span><span className="text-right font-medium" style={{ color: t.protected_areas.sites_in_protected ? 'var(--color-warn)' : 'var(--color-ink)' }}>{t.protected_areas.sites_in_protected}/{t.protected_areas.sites_total}{t.protected_areas.site_value_in_protected_eur ? ` · ${eur(t.protected_areas.site_value_in_protected_eur)}` : ''}</span>
                    <span className="text-[var(--color-mute)]">Plots in / near</span><span className="text-right font-medium" style={{ color: t.protected_areas.plots_in_protected ? 'var(--color-warn)' : 'var(--color-ink)' }}>{t.protected_areas.plots_in_protected}/{t.protected_areas.plots_total}{t.protected_areas.plot_spend_in_protected_eur ? ` · ${eur(t.protected_areas.plot_spend_in_protected_eur)}` : ''}</span>
                  </>)}
                </div>
              )}

              {t.e3_4_note && (
                <p className="text-[11px] text-[var(--color-warn)] mt-3 rounded-md border border-[color-mix(in_oklab,var(--color-warn)_35%,var(--color-line))] bg-[color-mix(in_oklab,var(--color-warn)_7%,transparent)] px-2.5 py-1.5 leading-relaxed">
                  <span className="font-semibold">Proxy — not the metered E3-4 figure.</span> {t.e3_4_note}
                </p>
              )}
              {t.basis && <p className="text-[11px] text-[var(--color-faint)] mt-3">{t.basis}</p>}
              {t.topic === 'E4' && t.protected_areas && (
                <p className="text-[11px] mt-2 leading-relaxed rounded-md px-2.5 py-1.5 border"
                   style={t.protected_areas.coverage.authoritative_global_loaded
                     ? { color: 'var(--color-faint)', borderColor: 'var(--color-line)' }
                     : { color: 'var(--color-warn)', borderColor: 'color-mix(in oklab, var(--color-warn) 35%, var(--color-line))', background: 'color-mix(in oklab, var(--color-warn) 7%, transparent)' }}>
                  <span className="font-semibold">Protected-area coverage:</span> {t.protected_areas.coverage.loaded.map(l => l.label).join(' · ') || 'none loaded'}. {t.protected_areas.coverage.note}
                </p>
              )}
              {t.topic === 'E1' && (
                <Link to="/csrd" className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline">
                  Full ESRS E1 report <ArrowRight size={14} />
                </Link>
              )}
              {t.topic === 'E4' && (
                <Link to="/disclosure" className="mt-3 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--color-sky)] hover:underline">
                  EUDR determinations & DDS <ArrowRight size={14} />
                </Link>
              )}
            </Card>
          )
        })}
      </div>

      <TaxonomyAdaptation />

      <FilingReadiness scenario={d.reporting_basis.scenario} />

      <FilingsHistory />

      {/* out of scope — by design */}
      <Card className="p-5">
        <SectionHead icon={MinusCircle} className="mb-1">Out of scope — by design</SectionHead>
        <p className="text-[12px] text-[var(--color-mute)] mb-3">These ESRS topics aren't driven by our engine — your carbon, EHS, HR and governance tools produce them, and everything combines into one CSRD statement. We say so rather than pretend to cover it.</p>
        <div className="grid sm:grid-cols-2 gap-x-8 gap-y-2 text-[13px]">
          {d.out_of_scope.map((o, i) => (
            <div key={i} className="flex items-center justify-between gap-3 border-b border-[var(--color-line)] pb-1.5">
              <span className="text-[var(--color-mute)]"><span className="mono text-[10px] text-[var(--color-faint)] mr-1.5">{o.topic}</span>{o.label}</span>
              <span className="text-[11px] text-[var(--color-faint)] text-right shrink-0">{o.handled_by}</span>
            </div>
          ))}
        </div>
      </Card>

      {/* provenance */}
      <Card className="p-5 space-y-2 text-[12.5px] text-[var(--color-mute)]">
        <SectionHead className="mb-1">Basis of preparation</SectionHead>
        {Object.entries(d.provenance).map(([k, v]) => (
          <div key={k} className="flex gap-2">
            <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] shrink-0 w-28">{k.replace(/_/g, ' ')}</span>
            <span>{v}</span>
          </div>
        ))}
        <p className="text-[11px] text-[var(--color-faint)] pt-1">{d.note}</p>
        <p className="text-[11px] text-[var(--color-faint)]"><b>XBRL export:</b> each figure is tagged to its ESRS disclosure requirement (E1-9, E3-4/5, E4-5) as a machine-readable, XBRL-shaped instance — ready to bind to the adopted EFRAG ESRS taxonomy in your filing tool. It's the tagged-data layer, not a validated ESEF filing.</p>
      </Card>
    </div>
  )
}
interface TaxAdapt {
  objective: string
  crva: { sites_total: number; sites_assessed: number; coverage_pct: number | null; asset_value_assessed_eur: number }
  physical_risk: { sites_materially_exposed: number; asset_value_exposed_eur: number; share_of_assets_exposed_pct: number | null; hazards: string[] }
  substantial_contribution: { adaptation_solutions_identified: boolean; candidate_contributing_value_eur: number }
  out_of_scope: { note: string; we_provide: string[]; you_provide: string[] }
}

function TaxonomyAdaptation() {
  const q = useQuery({ queryKey: ['taxonomy-adaptation'], queryFn: () => api.get<TaxAdapt>('/v1/supply/taxonomy-adaptation') })
  const d = q.data
  if (!d) return null
  return (
    <Card className="p-5">
      <SectionHead icon={Trees} className="mb-1">EU Taxonomy · Climate change adaptation (Art. 8)</SectionHead>
      <p className="text-[12px] text-[var(--color-mute)] mb-4 max-w-3xl">The mandated hard input for the adaptation objective is a robust <b>Climate Risk &amp; Vulnerability Assessment</b> and evidence that adaptation solutions address the material physical risks — that's ours. We provide the substantial-contribution evidence, not the turnover/capex/opex alignment %.</p>
      <div className="grid sm:grid-cols-4 gap-4 mb-4">
        <Stat big={`${d.crva.coverage_pct ?? 0}%`} label="CRVA coverage (sites assessed)" tone={d.crva.coverage_pct === 100 ? 'good' : 'warn'} />
        <Stat big={eur(d.crva.asset_value_assessed_eur)} label="asset value assessed" />
        <Stat big={`${d.physical_risk.share_of_assets_exposed_pct ?? 0}%`} label="of assets materially exposed" tone="warn" />
        <Stat big={eur(d.substantial_contribution.candidate_contributing_value_eur)} label="candidate adaptation-contributing value" tone="warn" />
      </div>
      <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5 text-[12.5px]">
        <div>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-good)] mb-1">We provide</div>
          {d.out_of_scope.we_provide.map((x, i) => <div key={i} className="text-[var(--color-mute)] flex gap-2"><span className="text-[var(--color-good)]">✓</span>{x}</div>)}
        </div>
        <div>
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Your reporting suite provides</div>
          {d.out_of_scope.you_provide.map((x, i) => <div key={i} className="text-[var(--color-faint)] flex gap-2"><span>·</span>{x}</div>)}
        </div>
      </div>
    </Card>
  )
}

interface ValCheck { name: string; ok: boolean; detail: string }
interface Validation { ok: boolean; profile: string; profile_status: string; is_ixbrl: boolean; facts: number; checks: ValCheck[]; errors: string[]; disclaimer: string }
interface Binding { profile: string; status: string; namespace: string; concepts_total: number; concepts_bound: number; concepts_unbound: string[]; note: string }

const CHECK_LABEL: Record<string, string> = {
  well_formed_xml: 'Well-formed XML', has_contexts: 'Reporting contexts', has_units: 'Units declared',
  schema_ref: 'Taxonomy schema reference', facts_complete: 'Every fact complete', concepts_bound: 'Concepts bound',
  arelle_available: 'Full ESEF conformance (filing tool)',
}

function FilingReadiness({ scenario }: { scenario: string }) {
  const v = useQuery({ queryKey: ['esrs-validate'], queryFn: () => api.get<Validation>('/v1/supply/esrs-pack.validate?form=ixbrl') })
  const b = useQuery({ queryKey: ['taxonomy-binding'], queryFn: () => api.get<Binding>('/v1/supply/taxonomy-binding') })
  const d = v.data
  return (
    <Card className="p-5">
      <SectionHead icon={ShieldCheck} className="mb-1">Filing readiness — Inline XBRL (ESEF)</SectionHead>
      <p className="text-[12px] text-[var(--color-mute)] mb-4 max-w-3xl">
        The pack is emitted as <b>Inline XBRL</b> — one document a person reads and a machine parses, the shape ESEF filings take. We validate it structurally here; full taxonomy conformance runs in the filing tool once bound to the adopted EFRAG taxonomy.
      </p>

      {d && (
        <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5 mb-4">
          {d.checks.filter(c => c.name !== 'concepts_bound').map(c => (
            <div key={c.name} className="flex items-start gap-2 text-[13px]">
              {c.ok ? <CheckCircle2 size={15} className="text-[var(--color-good)] mt-px shrink-0" /> : <XCircle size={15} className="text-[var(--color-faint)] mt-px shrink-0" />}
              <span className={c.ok ? 'text-[var(--color-mute)]' : 'text-[var(--color-faint)]'}>{CHECK_LABEL[c.name] ?? c.name} <span className="text-[var(--color-faint)]">— {c.detail}</span></span>
            </div>
          ))}
        </div>
      )}

      {b.data && (
        <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3.5 text-[12.5px]">
          <div className="flex items-center justify-between gap-3 mb-1">
            <span className="font-medium text-[var(--color-ink)]">Taxonomy binding</span>
            <span className="mono text-[10px] px-2 py-0.5 rounded-full uppercase tracking-wide"
              style={{ color: b.data.status === 'adopted' ? 'var(--color-good)' : 'var(--color-warn)',
                       background: `color-mix(in oklab, ${b.data.status === 'adopted' ? 'var(--color-good)' : 'var(--color-warn)'} 14%, transparent)` }}>
              {b.data.profile} · {b.data.status.replace(/_/g, ' ')}
            </span>
          </div>
          <div className="text-[var(--color-mute)]">{b.data.concepts_bound}/{b.data.concepts_total} concepts bound · {b.data.note}</div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 mt-4">
        <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.ixbrl', `tellumen-esrs-climate-nature-${scenario}.xhtml`)}><FileCode size={14} /> Download iXBRL</Button>
        {d && <span className="inline-flex items-center gap-1.5 text-[12.5px]" style={{ color: d.ok ? 'var(--color-good)' : 'var(--color-bad)' }}>
          {d.ok ? <CheckCircle2 size={14} /> : <XCircle size={14} />}{d.ok ? `Structurally valid · ${d.facts} tagged facts` : 'Validation failed'}</span>}
      </div>
    </Card>
  )
}

interface Basis { scenario: string; horizon: string; materiality_threshold: number; reporting_period_end: string }
interface Snapshot { snapshot_id: string; report_type: string; label: string; version: number; reporting_basis: Basis; note: string | null; created_at: string; created_by: string | null }

function FilingsHistory() {
  const { profile } = useAuth()
  const canPublish = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['report-snapshots'], queryFn: () => api.get<{ snapshots: Snapshot[] }>('/v1/supply/report-snapshots') })
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [open, setOpen] = useState<string | null>(null)
  const snaps = q.data?.snapshots ?? []

  const freeze = async (report_type: string) => {
    setBusy(report_type)
    try { await api.post('/v1/supply/report-snapshots', { report_type, note: note.trim() || null }); setNote(''); await q.refetch() }
    finally { setBusy(null) }
  }

  return (
    <Card className="p-5">
      <SectionHead icon={Lock} className="mb-1">Filed versions — frozen &amp; immutable</SectionHead>
      <p className="text-[12px] text-[var(--color-mute)] mb-4 max-w-3xl">
        Freeze a filing and its exact figures, reporting basis and golden-source state are captured as an immutable, versioned record — reproducible for the board or an assurer even after the live engine moves on. A correction is a new version; nothing is ever overwritten.
      </p>

      {canPublish && (
        <div className="flex flex-wrap items-center gap-2 mb-4">
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Optional note (e.g. FY2025 board sign-off)"
            className="flex-1 min-w-[220px] bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
          <Button variant="ghost" disabled={busy !== null} onClick={() => freeze('esrs_pack')}><Lock size={14} /> {busy === 'esrs_pack' ? 'Freezing…' : 'Freeze this pack'}</Button>
          <Button variant="ghost" disabled={busy !== null} onClick={() => freeze('csrd_e1')}><Lock size={14} /> {busy === 'csrd_e1' ? 'Freezing…' : 'Freeze ESRS E1'}</Button>
        </div>
      )}

      {snaps.length === 0 ? (
        <div className="flex items-center gap-2 text-[12.5px] text-[var(--color-faint)] py-2"><History size={14} /> No filings frozen yet.</div>
      ) : (
        <div className="space-y-1.5">
          {snaps.map(s => (
            <div key={s.snapshot_id} className="border border-[var(--color-line)] rounded-lg">
              <button onClick={() => setOpen(open === s.snapshot_id ? null : s.snapshot_id)}
                className="w-full flex items-center gap-3 px-3 py-2.5 text-left hover:bg-[var(--color-panel-2)] rounded-lg transition">
                <ChevronRight size={14} className={`text-[var(--color-faint)] transition-transform ${open === s.snapshot_id ? 'rotate-90' : ''}`} />
                <span className="mono text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-mute)] shrink-0">v{s.version}</span>
                <span className="text-[13px] font-medium">{s.label}</span>
                <span className="text-[11px] text-[var(--color-faint)] ml-auto text-right">{s.created_at.slice(0, 10)} · {s.created_by ?? '—'}</span>
              </button>
              {open === s.snapshot_id && <FrozenDetail snapshotId={s.snapshot_id} note={s.note} basis={s.reporting_basis} version={s.version} reportType={s.report_type} />}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

interface FrozenPayload {
  topics?: Topic[]
  financial_effects?: { asset_value_at_risk_eur: number; business_interruption_eur: number; cogs_at_risk_published_eur: number; exposure_mapped_but_withheld_eur: number }
  material_hazards?: { hazard: string; label: string }[]
}

function FrozenDetail({ snapshotId, note, basis, version, reportType }: { snapshotId: string; note: string | null; basis: Basis; version: number; reportType: string }) {
  const q = useQuery({ queryKey: ['report-snapshot', snapshotId], queryFn: () => api.get<{ payload: FrozenPayload }>(`/v1/supply/report-snapshots/${snapshotId}`) })
  const p = q.data?.payload
  // esrs_pack carries topics; csrd_e1 carries financial_effects at the top level
  const topics = p?.topics
  const e1 = topics?.find(t => t.topic === 'E1'), e3 = topics?.find(t => t.topic === 'E3'), e4 = topics?.find(t => t.topic === 'E4')
  const fe = e1?.financial_effects ?? p?.financial_effects
  return (
    <div className="px-3 pb-3 pt-1 border-t border-[var(--color-line)] text-[12px]">
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-[var(--color-faint)] mb-2 mono">
        <span>PERIOD {basis.reporting_period_end}</span><span>SCENARIO {basis.scenario}</span>
        <span>HORIZON {basis.horizon}</span><span>MATERIALITY ≥ {basis.materiality_threshold}</span>
      </div>
      {note && <p className="text-[12px] text-[var(--color-mute)] mb-2 italic">“{note}”</p>}
      {!p ? <div className="text-[var(--color-faint)]">loading frozen figures…</div> : (
        <div className="grid sm:grid-cols-3 gap-x-6 gap-y-1 text-[var(--color-mute)]">
          {fe && <div className="flex justify-between gap-2"><span>Asset value at risk</span><span className="font-medium text-[var(--color-ink)]">{eur(fe.asset_value_at_risk_eur)}</span></div>}
          {fe && <div className="flex justify-between gap-2"><span>COGS at risk (published)</span><span className="font-medium text-[var(--color-ink)]">{eur(fe.cogs_at_risk_published_eur)}</span></div>}
          {fe && <div className="flex justify-between gap-2"><span>Exposure mapped · withheld</span><span className="font-medium text-[var(--color-faint)]">{eur(fe.exposure_mapped_but_withheld_eur)}</span></div>}
          {e3?.upstream && <div className="flex justify-between gap-2"><span>E3 plots water-stressed</span><span className="font-medium text-[var(--color-ink)]">{e3.upstream.plots_water_stressed}/{e3.upstream.plots}</span></div>}
          {e4 && <div className="flex justify-between gap-2"><span>E4 EUDR-covered plots</span><span className="font-medium text-[var(--color-ink)]">{e4.eudr_covered_plots}</span></div>}
          {e4 && <div className="flex justify-between gap-2"><span>E4 deforestation-free</span><span className="font-medium text-[var(--color-good)]">{e4.deforestation_free}</span></div>}
          {e4?.protected_areas && <div className="flex justify-between gap-2"><span>E4 sites/plots in protected areas</span><span className="font-medium text-[var(--color-ink)]">{e4.protected_areas.sites_in_protected + e4.protected_areas.plots_in_protected}</span></div>}
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5">
        <button onClick={() => download(`/v1/supply/report-snapshots/${snapshotId}/assurance-pack`, `assurance-pack-${reportType}-v${version}.zip`)}
          className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline">
          <ShieldCheck size={13} /> Assurance pack (ZIP)
        </button>
        {reportType === 'esrs_pack' && <>
          <button onClick={() => download(`/v1/supply/report-snapshots/${snapshotId}.ixbrl`, `tellumen-esrs-v${version}.xhtml`)}
            className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline">
            <FileCode size={13} /> iXBRL (from this snapshot)
          </button>
          <button onClick={() => download(`/v1/supply/report-snapshots/${snapshotId}.xbrl`, `tellumen-esrs-v${version}.xbrl`)}
            className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)] hover:underline">
            <Code2 size={13} /> XBRL
          </button>
        </>}
      </div>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
