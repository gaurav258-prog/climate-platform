import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Building2, ShieldCheck, Layers, ChevronRight, FileClock } from 'lucide-react'
import MoneyDeclaration from '../components/MoneyDeclaration'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Button, SectionHead, PageHeader, HeroBanner, StatGrid } from '../components/ui'
import { HBar } from '../components/Charts'
import { HAZARD_LABEL, hazardLabel } from '../lib/hazards'

// Solvency II capital for a property insurer — the catastrophe SCR on TWO labelled bases:
//  · internal-model: our common-shock cat engine's 1-in-200 (99.5% VaR), gross & net of reinsurance
//  · standard formula: EIOPA's prescribed per-region factors (Del. Reg. 2015/35, Art. 120-125), all five
//    nat-cat perils + the Art. 120 aggregation — a cited regulatory calc, not our hazard model.

interface PerRegion { region: string; region_name: string; sum_insured_eur: number; n_policies: number; risk_factor_q: number; scr_region_eur: number }
interface PerilBlock {
  available: boolean; peril: string; scr_eur?: number; citation?: string
  per_region?: PerRegion[]; other_regions_sum_insured_eur?: number
  undiversified_scr_eur?: number; regional_diversification_benefit_eur?: number; reason?: string
}
interface SF {
  available: boolean; regulation?: string; natcat_scr_eur?: number; undiversified_sum_eur?: number
  cross_peril_diversification_benefit_eur?: number; scr_by_peril_eur?: Record<string, number>
  perils?: Record<string, PerilBlock>; aggregation?: string; note?: string
}
interface ScrResp {
  available: boolean; reason?: string; scr_basis?: string
  natcat_scr_eur?: number; aep_1_in_200_eur?: number; oep_1_in_200_eur?: number
  mean_annual_loss_eur?: number; risk_load_eur?: number; gross_sum_insured_eur?: number
  scr_pct_of_sum_insured?: number | null; note?: string; standard_formula_natcat?: SF
}
interface ReinResp {
  available: boolean; gross_pml_eur?: number; gross_oep_1_in_200_eur?: number
  net?: { net_pml_eur?: number; net_aep_eur?: Record<string, number>; ceded_pml_eur?: number; cession_ratio_pct?: number }
  program?: Record<string, number>
}

const eur = (v?: number | null) => (typeof v === 'number' ? `€${Math.round(v).toLocaleString()}` : '—')
const eurM = (v?: number | null) => (typeof v === 'number' ? `€${(v / 1e6).toFixed(1)}m` : '—')
const PERIL_LABEL: Record<string, string> = { windstorm: 'Windstorm', earthquake: 'Earthquake', flood: 'Flood', hail: 'Hail', subsidence: 'Subsidence' }
const PERIL_COLOR: Record<string, string> = { windstorm: '#7db8ff', earthquake: '#e0574a', flood: '#3f7fd6', hail: '#a78bfa', subsidence: '#f2b45a' }

// IFRS S2 ¶16(a) — actual incurred losses for the reporting period, alongside the ¶16(c)-(d) modelled figures.
interface PerilLossRow { peril: string; gross_incurred_loss_eur: number; net_incurred_loss_eur?: number | null; n_records: number }
interface PeriodLossRow { period_start: string; period_end: string; gross_incurred_loss_eur: number; net_incurred_loss_eur?: number | null; perils: string[] }
// SASB FN-IN-450a.2 disaggregation (via IFRS S2 ¶29) — geography and modelled/non-modelled catastrophe.
interface RegionLossRow { region: string; gross_incurred_loss_eur: number; net_incurred_loss_eur?: number | null; n_records: number }
interface ModelledLossRow { modelled: 'modelled' | 'non_modelled'; gross_incurred_loss_eur: number; net_incurred_loss_eur?: number | null; n_records: number }
interface ModeledFigures {
  available?: boolean; scenario?: string; horizon?: string
  total_expected_annual_loss_eur?: number | null
  internal_model_natcat_scr_1_in_200_eur?: number | null
  standard_formula_natcat_scr_eur?: number | null
}
interface IncurredSummary {
  status: 'not_yet_supplied' | 'supplied'; regulation: string; note?: string
  n_records?: number; total_gross_incurred_loss_eur?: number; total_net_incurred_loss_eur?: number | null
  by_peril: PerilLossRow[]; by_period: PeriodLossRow[]; modeled?: ModeledFigures | null; comparison_note?: string
  by_region?: RegionLossRow[]; by_modelled?: ModelledLossRow[]
  region_coverage_note?: string | null; modelled_coverage_note?: string | null
}

export default function Solvency() {
  const scr = useQuery({ queryKey: ['ins-scr'], queryFn: () => api.get<ScrResp>('/v1/insurance/solvency-scr?scenario=baseline&horizon=current') })
  const reins = useQuery({ queryKey: ['ins-reins'], queryFn: () => api.get<ReinResp>('/v1/insurance/reinsurance?scenario=baseline&horizon=current') })
  const incurred = useQuery({ queryKey: ['ins-incurred'], queryFn: () => api.get<IncurredSummary>('/v1/insurance/incurred-losses?scenario=baseline&horizon=current') })
  const d = scr.data
  const sf = d?.standard_formula_natcat

  if (scr.isLoading) return <div className="fadeup"><PageHeader eyebrow="Assess · Solvency II" title="Catastrophe capital" /><Card><div className="p-6 mono text-[12px] text-[var(--color-faint)]">loading the catastrophe SCR…</div></Card></div>
  if (!d?.available) return <div className="fadeup"><PageHeader eyebrow="Assess · Solvency II" title="Catastrophe capital" /><Card><div className="p-6 text-[13px] text-[var(--color-mute)]">{d?.reason ?? 'No scored policies yet — upload your Statement of Values under “Your data”.'}</div></Card></div>

  const im = d.natcat_scr_eur
  const imNet = ((reins.data?.net?.net_aep_eur) || {}).rp_200 ?? reins.data?.net?.net_pml_eur
  const heroStats: { label: string; value: string; tone?: string }[] = [
    { label: 'Standard formula · NatCat SCR', value: eurM(sf?.natcat_scr_eur), tone: 'sky' },
    { label: 'Internal model · 1-in-200 gross', value: eurM(im) },
    { label: 'Net of reinsurance', value: eurM(imNet) },
    { label: 'SCR / sum insured', value: `${d.scr_pct_of_sum_insured ?? '—'}%` },
  ]

  const perilBars = sf?.scr_by_peril_eur
    ? Object.entries(sf.scr_by_peril_eur).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
        .map(([k, v]) => ({ label: PERIL_LABEL[k] ?? k, value: v, color: PERIL_COLOR[k], sub: eur(v) }))
    : []

  return (
    <div className="fadeup space-y-5 max-w-5xl">
      <PageHeader eyebrow="Assess · Solvency II" title="Catastrophe capital"
        lead="Your natural-catastrophe SCR on two labelled bases — our internal-model 1-in-200, and the prescribed EIOPA standard formula (Del. Reg. 2015/35, Art. 120-125). Every number is computed from your book; the standard-formula factors are the regulator’s own, cited." />

      <HeroBanner eyebrow="Disclose · catastrophe SCR" title="What you must hold against a bad cat year."
        lead={sf?.available ? 'The standard-formula NatCat SCR combines five prescribed perils; the internal model is shown beside it.' : 'Internal-model catastrophe SCR (standard-formula factors pending).'}
        stat={heroStats} />

      <div className="grid md:grid-cols-2 gap-4">
        {/* internal model */}
        <Card>
          <SectionHead icon={Building2} hint="99.5% VaR · our common-shock cat engine">Internal model</SectionHead>
          <div className="mt-3">
            <StatGrid cols={2} items={[
              { label: 'NatCat SCR — gross (1-in-200)', value: eur(im), accent: 'var(--color-ink)' },
              { label: 'Net of reinsurance', value: eur(imNet) },
              { label: 'Mean annual cat loss', value: eur(d.mean_annual_loss_eur) },
              { label: 'Risk load (SCR − mean)', value: eur(d.risk_load_eur) },
            ]} />
          </div>
          {reins.data?.available && (
            <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3.5 py-2.5 text-[12px] text-[var(--color-mute)]">
              Reinsurance cedes <b className="text-[var(--color-ink)]">{eur(reins.data?.net?.ceded_pml_eur)}</b> of the single-event PML — gross {eur(reins.data?.gross_pml_eur)} → net {eur(reins.data?.net?.net_pml_eur)}.
            </div>
          )}
        </Card>

        {/* standard formula */}
        <Card>
          <SectionHead icon={ShieldCheck} hint="EIOPA prescribed factors — cited, not modelled">Standard formula</SectionHead>
          {sf?.available ? (
            <div className="mt-3">
              <StatGrid cols={2} items={[
                { label: 'NatCat SCR (√Σ SCR_peril²)', value: eur(sf.natcat_scr_eur), accent: 'var(--color-sky)' },
                { label: 'Undiversified (Σ perils)', value: eur(sf.undiversified_sum_eur) },
                { label: 'Cross-peril diversification', value: eur(sf.cross_peril_diversification_benefit_eur) },
                { label: 'Basis', value: 'gross of reinsurance' },
              ]} />
              <div className="mt-3">
                <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">SCR by peril</div>
                <HBar data={perilBars} format={eurM} />
              </div>
            </div>
          ) : <div className="mt-3 text-[12.5px] text-[var(--color-mute)]">Standard-formula factors not loaded.</div>}
        </Card>
      </div>

      {/* per-peril regional detail */}
      {sf?.available && <PerilDetail sf={sf} />}

      {/* IFRS S2 ¶16(a) — actual incurred losses for the reporting period, alongside ¶16(c)-(d) modelled figures */}
      <IncurredLosses data={incurred.data} loading={incurred.isLoading} onSaved={() => incurred.refetch()} />

      <Card>
        <div className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">
          <b className="text-[var(--color-ink)]">How to read this.</b> The two bases have different scope. The <b className="text-[var(--color-ink)]">internal model</b> is our 1-in-200 across <i>every</i> climate hazard your book is scored on (flood, heat, convective, windstorm…) at the modelled severity. The <b className="text-[var(--color-ink)]">standard formula</b> is the prescribed EIOPA charge for the five nat-cat perils only, at the regulator’s fixed per-region factors — so the two can differ materially, and comparing them is itself a useful calibration check.
          {sf?.available && <> The standard formula is a country-level approximation: the region factors and inter-region correlation are the exact Annex values, but the intra-country CRESTA-zone weights/diversification and the flood/hail motor component are not applied — an approximation of the exact zonal figure. Man-made catastrophe is out of climate scope.</>}
        </div>
      </Card>
    </div>
  )
}

function PerilDetail({ sf }: { sf: SF }) {
  const [open, setOpen] = useState<string | null>('earthquake')
  const perils = ['windstorm', 'earthquake', 'flood', 'hail'].map(k => ({ k, b: sf.perils?.[k] })).filter(x => x.b?.available && x.b.per_region?.length)
  if (!perils.length) return null
  return (
    <Card>
      <SectionHead icon={Layers} hint="prescribed Annex factors × your sums insured">SCR by peril &amp; region</SectionHead>
      <div className="mt-3 space-y-2">
        {perils.map(({ k, b }) => {
          const isOpen = open === k
          return (
            <div key={k} className="rounded-lg border border-[var(--color-line)] overflow-hidden">
              <button onClick={() => setOpen(isOpen ? null : k)}
                className="w-full flex items-center gap-2.5 px-3.5 py-2.5 hover:bg-[var(--color-bg-2)] transition">
                <ChevronRight size={14} className={`text-[var(--color-faint)] transition ${isOpen ? 'rotate-90' : ''}`} />
                <span className="w-2 h-2 rounded-full" style={{ background: PERIL_COLOR[k] }} />
                <span className="text-[13px] font-medium text-[var(--color-ink)]">{PERIL_LABEL[k]}</span>
                <span className="mono text-[10px] text-[var(--color-faint)] ml-1">{b!.citation}</span>
                <span className="ml-auto mono text-[12.5px] text-[var(--color-ink)]">{eur(b!.scr_eur)}</span>
              </button>
              {isOpen && (
                <div className="border-t border-[var(--color-line)]">
                  <div className="px-3.5 pt-3 pb-1">
                    <div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">SCR by region</div>
                    <HBar data={b!.per_region!.map(r => ({ label: r.region, value: r.scr_region_eur, sub: `Q ${(r.risk_factor_q * 100).toFixed(1)}%`, color: PERIL_COLOR[k] }))} format={eurM} height={14} />
                  </div>
                  <table className="w-full text-[12px]">
                    <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase">
                      <th className="text-left font-normal px-3.5 py-1.5">Region</th>
                      <th className="text-right font-normal px-3.5 py-1.5">Sum insured</th>
                      <th className="text-right font-normal px-3.5 py-1.5">Factor Q</th>
                      <th className="text-right font-normal px-3.5 py-1.5">SCR</th>
                    </tr></thead>
                    <tbody>
                      {b!.per_region!.map(r => (
                        <tr key={r.region} className="border-t border-[var(--color-line-2)]">
                          <td className="px-3.5 py-1.5 text-[var(--color-ink)]">{r.region} · <span className="text-[var(--color-mute)]">{r.region_name}</span></td>
                          <td className="px-3.5 py-1.5 text-right mono text-[var(--color-mute)]">{eur(r.sum_insured_eur)}</td>
                          <td className="px-3.5 py-1.5 text-right mono text-[var(--color-mute)]">{(r.risk_factor_q * 100).toFixed(2)}%</td>
                          <td className="px-3.5 py-1.5 text-right mono text-[var(--color-ink)]">{eur(r.scr_region_eur)}</td>
                        </tr>
                      ))}
                      {b!.other_regions_sum_insured_eur ? (
                        <tr className="border-t border-[var(--color-line-2)]">
                          <td className="px-3.5 py-1.5 text-[var(--color-faint)] italic" colSpan={3}>outside Annex regions (not in the charge)</td>
                          <td className="px-3.5 py-1.5 text-right mono text-[var(--color-faint)]">{eur(b!.other_regions_sum_insured_eur)} SI</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                  {(b!.regional_diversification_benefit_eur ?? 0) > 0 && (
                    <div className="px-3.5 py-2 border-t border-[var(--color-line-2)] mono text-[10.5px] text-[var(--color-faint)]">
                      regional diversification benefit {eur(b!.regional_diversification_benefit_eur)} · undiversified {eur(b!.undiversified_scr_eur)}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

const apiErrText = (e: unknown, fb: string) => {
  const b = (e as { body?: unknown })?.body as { message?: string; error?: { message?: string } } | string | undefined
  if (typeof b === 'string') return b
  return b?.message ?? b?.error?.message ?? fb
}

// IFRS S2 ¶16(a): actual, incurred NatCat losses for the reporting period — customer-supplied, shown alongside
// the ¶16(c)-(d) modelled figures (EAL, standard-formula/internal-model SCR) that already appear above. Never a
// silent zero: an honest "not yet supplied" state when nothing has been submitted.
function IncurredLosses({ data, loading, onSaved }: { data?: IncurredSummary; loading: boolean; onSaved: () => void }) {
  const { profile } = useAuth()
  const canSubmit = (profile?.permissions ?? []).includes('pricing.approve')

  return (
    <Card>
      <SectionHead icon={FileClock} hint="IFRS S2 ¶16(a) · actual, for the reporting period">Incurred NatCat losses</SectionHead>
      <div className="mt-2 text-[11.5px] text-[var(--color-mute)] leading-relaxed">
        What the SCR and expected annual loss above model as <i>anticipated</i> (¶16(c)-(d)); this is what your book
        actually <i>incurred</i> — real claims for a stated reporting period, customer-supplied since the platform
        cannot observe your claims ledger itself.
      </div>

      {loading ? (
        <div className="mt-3 mono text-[12px] text-[var(--color-faint)]">loading…</div>
      ) : !data || data.status === 'not_yet_supplied' ? (
        <div className="mt-3 rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3.5 py-2.5 text-[12.5px] text-[var(--color-mute)]">
          No incurred losses submitted for any reporting period yet — not yet supplied.
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <StatGrid cols={2} items={[
            { label: 'Total gross incurred', value: eur(data.total_gross_incurred_loss_eur), accent: 'var(--color-ink)' },
            { label: 'Total net (after reinsurance)', value: data.total_net_incurred_loss_eur != null ? eur(data.total_net_incurred_loss_eur) : 'not supplied' },
            { label: 'Modelled EAL — pricing model (¶16(c)-(d))', value: eur(data.modeled?.total_expected_annual_loss_eur),
              sub: 'Per-policy pricing-model sum — a different methodology from "Mean annual cat loss" on the Internal model card above (Monte-Carlo simulation mean). Both are anticipated/¶16(c)-(d); they are not expected to match exactly.' },
            { label: 'Standard-formula SCR (¶16(c)-(d))', value: eur(data.modeled?.standard_formula_natcat_scr_eur) },
          ]} />
          <table className="w-full text-[12px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase">
              <th className="text-left font-normal px-2 py-1.5">Peril</th>
              <th className="text-right font-normal px-2 py-1.5">Gross incurred</th>
              <th className="text-right font-normal px-2 py-1.5">Net incurred</th>
              <th className="text-right font-normal px-2 py-1.5">Records</th>
            </tr></thead>
            <tbody>
              {data.by_peril.map(p => (
                <tr key={p.peril} className="border-t border-[var(--color-line-2)]">
                  <td className="px-2 py-1.5 text-[var(--color-ink)]">{hazardLabel(p.peril) ?? p.peril}</td>
                  <td className="px-2 py-1.5 text-right mono text-[var(--color-ink)]">{eur(p.gross_incurred_loss_eur)}</td>
                  <td className="px-2 py-1.5 text-right mono text-[var(--color-mute)]">{p.net_incurred_loss_eur != null ? eur(p.net_incurred_loss_eur) : '—'}</td>
                  <td className="px-2 py-1.5 text-right mono text-[var(--color-faint)]">{p.n_records}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(!!data.by_region?.length || !!data.by_modelled?.length) && (
            <div className="grid md:grid-cols-2 gap-3">
              {!!data.by_region?.length && (
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">By region</div>
                  <table className="w-full text-[12px]">
                    <tbody>
                      {data.by_region.map(r => (
                        <tr key={r.region} className="border-t border-[var(--color-line-2)]">
                          <td className="px-2 py-1.5 text-[var(--color-ink)]">{r.region}</td>
                          <td className="px-2 py-1.5 text-right mono text-[var(--color-ink)]">{eur(r.gross_incurred_loss_eur)}</td>
                          <td className="px-2 py-1.5 text-right mono text-[var(--color-faint)]">{r.n_records}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {!!data.by_modelled?.length && (
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Modelled vs non-modelled</div>
                  <table className="w-full text-[12px]">
                    <tbody>
                      {data.by_modelled.map(m => (
                        <tr key={m.modelled} className="border-t border-[var(--color-line-2)]">
                          <td className="px-2 py-1.5 text-[var(--color-ink)]">{m.modelled === 'modelled' ? 'Modelled catastrophe' : 'Non-modelled catastrophe'}</td>
                          <td className="px-2 py-1.5 text-right mono text-[var(--color-ink)]">{eur(m.gross_incurred_loss_eur)}</td>
                          <td className="px-2 py-1.5 text-right mono text-[var(--color-faint)]">{m.n_records}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
          {(data.region_coverage_note || data.modelled_coverage_note) && (
            <div className="mono text-[10.5px] text-[var(--color-faint)] leading-relaxed space-y-0.5">
              {data.region_coverage_note && <div>{data.region_coverage_note}</div>}
              {data.modelled_coverage_note && <div>{data.modelled_coverage_note}</div>}
            </div>
          )}
          {data.comparison_note && <div className="mono text-[10.5px] text-[var(--color-faint)] leading-relaxed">{data.comparison_note}</div>}
        </div>
      )}

      {canSubmit ? <IncurredLossForm onSaved={onSaved} /> : (
        <div className="mt-3 pt-3 border-t border-[var(--color-line)] text-[11.5px] text-[var(--color-faint)]">
          Submitting an incurred loss needs the <span className="mono">pricing.approve</span> permission.
        </div>
      )}
    </Card>
  )
}

function IncurredLossForm({ onSaved }: { onSaved: () => void }) {
  const perils = Object.keys(HAZARD_LABEL)
  const [peril, setPeril] = useState(perils[0] ?? 'flood')
  // default: the last FULL calendar year — a period must have ended to have incurred losses (and a rate)
  const [periodStart, setPeriodStart] = useState(`${new Date().getFullYear() - 1}-01-01`)
  const [periodEnd, setPeriodEnd] = useState(`${new Date().getFullYear() - 1}-12-31`)
  const [ccy, setCcy] = useState('')
  const [gross, setGross] = useState('')
  const [net, setNet] = useState('')
  const [region, setRegion] = useState('')
  const [modelled, setModelled] = useState('')   // '' = not specified, 'true' / 'false'
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const submit = async () => {
    setErr(null)
    if (!gross || Number(gross) < 0) { setErr('Enter the gross incurred loss.'); return }
    if (!ccy) { setErr('Choose the currency of the losses.'); return }
    if (periodEnd < periodStart) { setErr('The period end cannot be before the period start.'); return }
    setBusy(true)
    try {
      await api.post('/v1/insurance/incurred-losses', {
        period_start: periodStart, period_end: periodEnd, peril,
        gross_incurred_loss_eur: Number(gross),
        net_incurred_loss_eur: net ? Number(net) : undefined, currency: ccy,
        source: 'client',
        region: region || undefined,
        modelled: modelled === '' ? undefined : modelled === 'true',
      })
      setGross(''); setNet(''); setRegion(''); setModelled(''); onSaved()
    } catch (e) { setErr(apiErrText(e, 'Could not save the incurred loss.')) } finally { setBusy(false) }
  }

  return (
    <div className="mt-3 pt-3 border-t border-[var(--color-line)] space-y-2">
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Submit an incurred loss</div>
      {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
      <MoneyDeclaration currency={ccy} setCurrency={setCcy} withDate={false}
        note="Losses are a flow over the period: converted to EUR at the average rate from the period start to its end." />
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <select value={peril} onChange={e => setPeril(e.target.value)}
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
          {perils.map(p => <option key={p} value={p}>{HAZARD_LABEL[p] ?? p}</option>)}
        </select>
        <input type="date" value={periodStart} onChange={e => setPeriodStart(e.target.value)}
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <input type="date" value={periodEnd} onChange={e => setPeriodEnd(e.target.value)}
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <input type="number" min={0} placeholder="Gross loss" value={gross} onChange={e => setGross(e.target.value)}
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <input type="number" min={0} placeholder="Net loss (optional)" value={net} onChange={e => setNet(e.target.value)}
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <input type="text" placeholder="Region (optional)" value={region} onChange={e => setRegion(e.target.value)}
          title="SASB FN-IN-450a.2 geographic-segment disaggregation, e.g. 'Germany'"
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
        <select value={modelled} onChange={e => setModelled(e.target.value)}
          title="SASB FN-IN-450a.2 modelled-vs-non-modelled catastrophe disaggregation"
          className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]">
          <option value="">Modelled? (optional)</option>
          <option value="true">Modelled catastrophe</option>
          <option value="false">Non-modelled catastrophe</option>
        </select>
      </div>
      <Button variant="primary" onClick={submit} disabled={busy}><FileClock size={14} /> Submit incurred loss</Button>
    </div>
  )
}
