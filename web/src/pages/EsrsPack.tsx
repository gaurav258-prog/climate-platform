import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Download, CloudRain, Droplets, Trees, ArrowRight, MinusCircle, Code2 } from 'lucide-react'
import { api, download } from '../lib/api'
import { Eyebrow, Card, Button, Stat } from '../components/ui'

interface Topic {
  topic: string; title: string; standard?: string; material: boolean
  financial_effects?: { asset_value_at_risk_eur: number; business_interruption_eur: number; cogs_at_risk_published_eur: number; exposure_mapped_but_withheld_eur: number }
  own_operations?: { sites: number; sites_water_stressed: number; asset_value_exposed_eur: number }
  upstream?: { plots: number; plots_water_stressed: number; spend_exposed_eur: number; peak_score: number | null }
  eudr_covered_plots?: number; eudr_commodities?: number; deforestation_free?: number; non_compliant?: number
  geolocation_incomplete?: number; not_determined?: number; deforestation_free_pct_of_determined?: number | null; post_cutoff_forest_loss_ha?: number
  basis?: string; detail_ref?: string
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
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <Eyebrow>Compliance · corporate sustainability reporting</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">ESRS Climate &amp; Nature pack</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">
            The ESRS topics driven by our physical-climate &amp; deforestation engine — climate physical risk (E1),
            water (E3) and biodiversity/deforestation (E4) — assembled filing-grade to slot into your wider CSRD
            statement. GHG accounting, social and governance stay with your other tools, by design.
          </p>
          <p className="mono text-[11px] text-[var(--color-faint)] mt-2">
            {d.entity.name} · {d.entity.country}{d.entity.eori ? ` · EORI ${d.entity.eori}` : ''} · basis {d.reporting_basis.scenario}/{d.reporting_basis.horizon}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.xlsx', `tellumen-esrs-climate-nature-${d.reporting_basis.scenario}.xlsx`)}>
            <Download size={15} /> Excel
          </Button>
          <Button variant="ghost" onClick={() => download('/v1/supply/esrs-pack.xbrl', `tellumen-esrs-climate-nature-${d.reporting_basis.scenario}.xbrl`)}>
            <Code2 size={15} /> XBRL
          </Button>
        </div>
      </div>

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
                </div>
              )}

              {t.basis && <p className="text-[11px] text-[var(--color-faint)] mt-3">{t.basis}</p>}
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

      {/* out of scope — by design */}
      <Card className="p-5">
        <div className="flex items-center gap-2 mb-1"><MinusCircle size={15} className="text-[var(--color-faint)]" /><h3 className="font-semibold">Out of scope — by design</h3></div>
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
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-1">Basis of preparation</div>
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
      <div className="flex items-center gap-2 mb-1"><Trees size={15} className="text-[var(--color-sky)]" /><h3 className="font-semibold">EU Taxonomy · Climate change adaptation (Art. 8)</h3></div>
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

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
