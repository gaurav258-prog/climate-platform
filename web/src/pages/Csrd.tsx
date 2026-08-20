import { useQuery } from '@tanstack/react-query'
import { Download, Building2, Sprout, TrendingUp, ShieldCheck, Layers } from 'lucide-react'
import { api, download } from '../lib/api'
import { Card, Button, PageHeader, HeroStrip, HeroMetric, SectionHead } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

interface HazardBlock { hazard: string; label: string; class: string
  own_operations: { n_sites: number; asset_value_eur: number; bi_at_risk_eur: number; max_score: number } | null
  upstream: { n_commodities: number; spend_eur: number; cogs_at_risk_eur: number; max_score: number } | null }
interface Commodity { commodity: string; hazard: string; avg_hazard: number | null; spend_eur: number
  published: boolean; volume_at_risk_eur: number | null; volume_at_risk_low_eur: number | null
  volume_at_risk_high_eur: number | null; calibration: string | null; fit_r2: number | null; held_reason: string | null }
interface E1 {
  entity: { name: string | null; country: string | null; eori: string | null }
  standard: string; datapoint: string; reporting_basis: { scenario: string; horizon: string }
  material_hazards: HazardBlock[]
  own_operations: { n_sites: number; asset_value_eur: number; asset_value_at_risk_eur: number; throughput_eur: number; business_interruption_eur: number }
  upstream_sourcing: { ingredient_spend_eur: number; cogs_at_risk_published_eur: number; exposure_mapped_spend_eur: number; commodities: Commodity[] }
  financial_effects: { asset_value_at_risk_eur: number; business_interruption_eur: number; cogs_at_risk_published_eur: number; exposure_mapped_but_withheld_eur: number; note: string }
  projections: { hazard_type: string; time_horizon: string; avg_score: number }[]
  resilience: { hazard: string; label: string; actions: string[] }[]
  provenance: Record<string, string>
}

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : n >= 1e3 ? `€${(n / 1e3).toFixed(0)}k` : `€${n}`
const CLS: Record<string, string> = {
  acute: 'text-[var(--color-bad)] bg-[color-mix(in_oklab,var(--color-bad)_13%,transparent)]',
  chronic: 'text-[var(--color-warn)] bg-[color-mix(in_oklab,var(--color-warn)_13%,transparent)]',
}
const HORIZONS = ['current', '2030', '2050', '2100']

export default function Csrd() {
  const q = useQuery({ queryKey: ['csrd-e1'], queryFn: () => api.get<E1>('/v1/supply/csrd-e1') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const d = q.data
  const fe = d.financial_effects

  // pivot projections → hazard rows × horizon cols
  const hazards = [...new Set(d.projections.map(p => p.hazard_type))]
  const proj: Record<string, Record<string, number>> = {}
  d.projections.forEach(p => { (proj[p.hazard_type] ??= {})[p.time_horizon] = p.avg_score })

  return (
    <div className="fadeup space-y-7">
      <PageHeader eyebrow="Compliance · corporate sustainability reporting"
        title="CSRD (Corporate Sustainability Reporting Directive) · ESRS E1 physical risk"
        lead="The physical-climate-risk section your CSRD report must disclose (ESRS E1-9, anticipated financial effects), assembled from your own sites and your sourcing book on the golden source. A euro is shown as a firm loss only where the hazard→yield chain is validated; otherwise exposure is mapped and the € withheld."
        actions={
          <Button variant="ghost" onClick={() => download('/v1/supply/csrd-e1.xlsx', `tellumen-csrd-e1-${d.reporting_basis.scenario}.xlsx`)}>
            <Download size={15} /> Export (Excel)
          </Button>
        }>
        <p className="mono text-[11px] text-[var(--color-faint)] mt-2">
          {d.entity.name} · {d.entity.country}{d.entity.eori ? ` · EORI ${d.entity.eori}` : ''} · basis {d.reporting_basis.scenario}/{d.reporting_basis.horizon}
        </p>
      </PageHeader>

      {/* headline financial effects — the numbers a filing must carry */}
      <HeroStrip>
        <HeroMetric value={eur(fe.asset_value_at_risk_eur)} label="Asset value at material risk" tone="#E8853C" />
        <HeroMetric value={eur(fe.business_interruption_eur)} label="Business interruption (v0)" tone="#E8853C" />
        <HeroMetric value={eur(fe.cogs_at_risk_published_eur)} label="Sourcing COGS at risk (published)" tone="#E8853C" />
        <HeroMetric value={eur(fe.exposure_mapped_but_withheld_eur)} label="Exposure mapped · € withheld" />
      </HeroStrip>
      <p className="text-[12px] text-[var(--color-mute)] -mt-3">{fe.note}</p>

      {/* material hazards — acute/chronic, split own-ops vs upstream */}
      <section className="space-y-3">
        <SectionHead icon={Layers}>Material physical hazards</SectionHead>
        {d.material_hazards.length === 0 && <Card className="p-5 text-sm text-[var(--color-faint)]">No hazard reaches the materiality threshold on any site or commodity.</Card>}
        {d.material_hazards.map(h => (
          <Card key={h.hazard} className="p-4">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-2">
              <span className="text-[15px] font-semibold">{h.label}</span>
              <span className={`mono text-[9px] px-2 py-0.5 rounded-full uppercase tracking-wide ${CLS[h.class] ?? ''}`}>{h.class}</span>
            </div>
            <div className="grid sm:grid-cols-2 gap-3 text-[13px]">
              <div className="flex items-start gap-2">
                <Building2 size={15} className="text-[var(--color-blue)] mt-0.5 shrink-0" />
                {h.own_operations
                  ? <span className="text-[var(--color-mute)]">Own operations · <b className="text-[var(--color-ink)]">{h.own_operations.n_sites}</b> site(s) · {eur(h.own_operations.asset_value_eur)} asset value · BI {eur(h.own_operations.bi_at_risk_eur)} · peak score {h.own_operations.max_score}</span>
                  : <span className="text-[var(--color-faint)]">Own operations · not material</span>}
              </div>
              <div className="flex items-start gap-2">
                <Sprout size={15} className="text-[var(--color-good)] mt-0.5 shrink-0" />
                {h.upstream
                  ? <span className="text-[var(--color-mute)]">Upstream sourcing · <b className="text-[var(--color-ink)]">{h.upstream.n_commodities}</b> commodit(ies) · {eur(h.upstream.spend_eur)} spend · COGS {eur(h.upstream.cogs_at_risk_eur)} published · peak score {h.upstream.max_score}</span>
                  : <span className="text-[var(--color-faint)]">Upstream sourcing · not material</span>}
              </div>
            </div>
          </Card>
        ))}
      </section>

      {/* two exposure ledgers */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card className="p-5">
          <SectionHead icon={Building2} className="mb-3">Own operations</SectionHead>
          <div className="grid grid-cols-2 gap-y-2 text-[13px]">
            <span className="text-[var(--color-mute)]">Sites</span><span className="text-right font-medium">{d.own_operations.n_sites}</span>
            <span className="text-[var(--color-mute)]">Asset value</span><span className="text-right font-medium">{eur(d.own_operations.asset_value_eur)}</span>
            <span className="text-[var(--color-mute)]">…at material risk</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(d.own_operations.asset_value_at_risk_eur)}</span>
            <span className="text-[var(--color-mute)]">Annual throughput</span><span className="text-right font-medium">{eur(d.own_operations.throughput_eur)}</span>
            <span className="text-[var(--color-mute)]">Business interruption (v0)</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(d.own_operations.business_interruption_eur)}</span>
          </div>
        </Card>
        <Card className="p-5">
          <SectionHead icon={Sprout} className="mb-3">Upstream sourcing</SectionHead>
          <div className="grid grid-cols-2 gap-y-2 text-[13px]">
            <span className="text-[var(--color-mute)]">Ingredient spend</span><span className="text-right font-medium">{eur(d.upstream_sourcing.ingredient_spend_eur)}</span>
            <span className="text-[var(--color-mute)]">COGS at risk (published)</span><span className="text-right font-medium text-[var(--color-warn)]">{eur(d.upstream_sourcing.cogs_at_risk_published_eur)}</span>
            <span className="text-[var(--color-mute)]">Exposure mapped · € withheld</span><span className="text-right font-medium text-[var(--color-faint)]">{eur(d.upstream_sourcing.exposure_mapped_spend_eur)}</span>
          </div>
          <div className="mt-3 space-y-1.5">
            {d.upstream_sourcing.commodities.map(c => (
              <div key={c.commodity} className="flex items-center gap-2 text-[12px]">
                <span className="text-[var(--color-ink)]">{c.commodity}</span>
                <span className="text-[var(--color-faint)]">· {hazardLabel(c.hazard)} {c.avg_hazard ?? '—'}</span>
                <span className="ml-auto">{c.published
                  ? <span className="text-[var(--color-warn)] font-medium">{c.calibration === 'ranged' ? `${eur(c.volume_at_risk_low_eur)}–${eur(c.volume_at_risk_high_eur)}` : eur(c.volume_at_risk_eur)}{c.fit_r2 != null ? ` · r² ${c.fit_r2.toFixed(2)}` : ''}</span>
                  : <span className="mono text-[11px] text-[var(--color-faint)]" title={c.held_reason ?? ''}>€ withheld</span>}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* forward horizons */}
      {hazards.length > 0 && (
        <section className="space-y-3">
          <SectionHead icon={TrendingUp}>Forward trajectory (mean hazard score)</SectionHead>
          <Card className="p-0 overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
                <th className="py-2.5 px-4 font-medium">Hazard</th>
                {HORIZONS.map(h => <th key={h} className="py-2.5 px-4 font-medium text-right tabular-nums">{h}</th>)}
              </tr></thead>
              <tbody>
                {hazards.map(hz => (
                  <tr key={hz} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="py-2.5 px-4 capitalize">{hz.replace('_', ' ')}</td>
                    {HORIZONS.map(h => <td key={h} className="py-2.5 px-4 text-right tabular-nums">{proj[hz]?.[h] ?? '—'}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <p className="text-[11px] text-[var(--color-faint)]">Projections = parametric warming shift on the calibrated baseline (CMIP6 3-model ensemble where downscaled), not a re-forecast.</p>
        </section>
      )}

      {/* resilience / adaptation */}
      {d.resilience.length > 0 && (
        <section className="space-y-3">
          <SectionHead icon={ShieldCheck}>Resilience &amp; adaptation</SectionHead>
          <div className="grid sm:grid-cols-2 gap-3">
            {d.resilience.map(r => (
              <Card key={r.hazard} className="p-4">
                <div className="text-[14px] font-semibold mb-2">{r.label}</div>
                <ul className="space-y-1 text-[12.5px] text-[var(--color-mute)]">
                  {r.actions.map((m, i) => <li key={i} className="flex gap-2"><span className="text-[var(--color-good)]">›</span>{m}</li>)}
                </ul>
              </Card>
            ))}
          </div>
        </section>
      )}

      {/* provenance */}
      <section className="space-y-2">
        <SectionHead>Basis of preparation</SectionHead>
        <Card className="p-5 space-y-2 text-[12.5px] text-[var(--color-mute)]">
          {Object.entries(d.provenance).map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="mono text-[10.5px] uppercase tracking-wide text-[var(--color-faint)] shrink-0 w-28">{k.replace(/_/g, ' ')}</span>
              <span>{v}</span>
            </div>
          ))}
          <p className="text-[11px] text-[var(--color-faint)] pt-1">{d.standard} · {d.datapoint}. A defensible draft for your sustainability team to complete and sign — not a filing or legal advice.</p>
        </Card>
      </section>
    </div>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
