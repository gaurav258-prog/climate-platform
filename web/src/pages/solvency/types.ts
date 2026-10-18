import type { Message } from '../../components/Details'

// What the catastrophe-capital page reads: /v1/insurance/solvency-scr (the standard formula and the modelled 1-in-200),
// /reinsurance/attested and /incurred-losses. Every explanation arrives as a catalogue message (codes solvency.*).

export type Peril = 'windstorm' | 'earthquake' | 'flood' | 'hail' | 'subsidence'
export const PERILS: Peril[] = ['windstorm', 'earthquake', 'flood', 'hail', 'subsidence']
export const PERIL_LABEL: Record<Peril, string> = { windstorm: 'Windstorm', earthquake: 'Earthquake', flood: 'Flood', hail: 'Hail', subsidence: 'Subsidence' }
export const PERIL_COLOR: Record<Peril, string> = { windstorm: '#7db8ff', earthquake: '#e0574a', flood: '#3f7fd6', hail: '#a78bfa', subsidence: '#f2b45a' }

export type Missing = Message & { uncharged_eur: number }
export interface SFRegion {
  region: string; region_name: string; n_policies: number; exposure_eur: number; specified_gross_loss_eur: number
  scenario: 'A' | 'B' | null; before_eur: number; after_eur: number
  method: 'exact_zonal' | 'grouped_art90b' | 'single_zone'; method_message: Message
}
export interface SFOther { exposure_eur: number; status: 'computed' | 'missing_input' | 'not_calculated'; premium_eur?: number; after_eur?: number; message: Message }
export interface PerilBlock {
  available: boolean; peril: Peril; citation?: string
  regions?: SFRegion[]; other_regions?: SFOther | null; not_charged_exposure_eur?: number
  before_eur?: number; after_eur?: number; diversification_after_eur?: number; complete?: boolean
}
export interface SF {
  available: boolean; version_name?: string; version_source?: string; reference_date?: string; treaty_basis?: 'attested' | 'none'
  treaty_message?: Message | null
  natcat_scr_eur?: number; natcat_scr_before_mitigation_eur?: number; diversification_between_perils_before_eur?: number
  perils?: Partial<Record<Peril, PerilBlock>>; complete?: boolean; missing?: Missing[]
  simplification_art_90b?: boolean; readings?: { subject: string; reading: string }[]
}
export interface ScrResp {
  available: boolean; gap?: string; reason?: string
  modelled_1_in_200_loss_eur?: number; mean_annual_loss_eur?: number; risk_load_eur?: number | null
  scr_pct_of_sum_insured?: number | null; standard_formula_natcat?: SF
}
export interface ReinResp {
  available: boolean; message?: Message; pml_return_period?: number; gross_pml_eur?: number
  one_in_200?: { gross_eur: number; reinsurance_eur: number; net_eur: number } | null
  net?: { net_pml_eur?: number }
}

interface LossRow { gross_incurred_loss_eur: number; net_incurred_loss_eur?: number | null; n_records: number }
export interface Incurred {
  status: 'not_yet_supplied' | 'supplied'; message?: Message
  n_records?: number; total_gross_incurred_loss_eur?: number; total_net_incurred_loss_eur?: number | null
  by_peril: (LossRow & { peril: string })[]; by_period: { period_start: string; period_end: string }[]
  by_region?: (LossRow & { region: string })[]; by_modelled?: (LossRow & { modelled: 'modelled' | 'non_modelled' })[]
  region_coverage?: Message | null; modelled_coverage?: Message | null; comparison?: Message
  modeled?: { total_expected_annual_loss_eur?: number | null } | null
}

// A region's short name: the country's name in English where the region is one country, else the Regulation's own.
const ALIAS: Record<string, string> = { UK: 'GB', HE: 'GR' }
let names: Intl.DisplayNames | null = null
export function regionName(code: string, official: string): string {
  try {
    names ??= new Intl.DisplayNames(['en'], { type: 'region' })
    const n = names.of(ALIAS[code] ?? code)
    if (n && n !== code && n !== ALIAS[code]) return n
  } catch { /* not a country code */ }
  return official.replace(/\s*\(.*\)\s*$/, '')
}
