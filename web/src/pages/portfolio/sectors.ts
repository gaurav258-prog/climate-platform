import { balance, flow } from '../../lib/money'

// The only thing that differs between the four financial books: the endpoints, the keys of a row and the headline
// figures. Every number is read from the book's own endpoint; nothing is invented.

export type Kpi = { label: string; field?: string; num?: string; den?: string; fmt: 'eur' | 'pct' | 'frac'; flow?: boolean; tone?: string }
export interface Cfg {
  prefix: string; listKey: string; noun: string
  idKey: string; nameKey: string; typeKey: string; valueKey: string
  uploadNoun: string     // what a CSV row is, for the import ("loan tape", "Statement of Values", …)
  itemKey: string        // the detail / override path: /v1/{prefix}/{itemKey}/{id}
  valuationKey?: string  // where the valuation block sits in the detail payload
  auditKey: string       // where the audit trail sits in the detail payload
  overrideMode: 'valuation' | 'trigger'   // an insurer sets a parametric trigger; the others override a discount
  kpis: Kpi[]
}

const RISK = 'var(--color-warn)'
export const SECTORS: Record<string, Cfg> = {
  bank: {
    prefix: 'bank', listKey: 'assets', noun: 'financed assets', uploadNoun: 'loan tape',
    idKey: 'asset_id', nameKey: 'asset_name', typeKey: 'asset_type', valueKey: 'value_eur',
    itemKey: 'asset', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Total book value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Money at material risk', field: 'value_at_risk_eur', fmt: 'eur', tone: RISK },
      { label: 'Share of book at material risk', field: 'pct_value_at_risk', fmt: 'pct' },
      { label: 'Assets analysed', num: 'n_scored', den: 'n_assets', fmt: 'frac' },
    ],
  },
  insurer: {
    prefix: 'insurance', listKey: 'policies', noun: 'insured locations', uploadNoun: 'Statement of Values',
    idKey: 'policy_id', nameKey: 'policy_name', typeKey: 'policy_type', valueKey: 'sum_insured_eur',
    itemKey: 'policy', auditKey: 'audit', overrideMode: 'trigger',
    kpis: [
      { label: 'Total sum insured', field: 'total_sum_insured_eur', fmt: 'eur' },
      { label: 'Likely yearly loss', field: 'total_expected_annual_loss_eur', fmt: 'eur', flow: true, tone: RISK },
      { label: 'Sum insured at material risk', field: 'value_at_risk_eur', fmt: 'eur' },
      { label: 'Locations priced', num: 'n_priced', den: 'n_policies', fmt: 'frac' },
    ],
  },
  asset_manager: {
    prefix: 'assetmgmt', listKey: 'holdings', noun: 'holdings', uploadNoun: 'holdings book',
    idKey: 'holding_id', nameKey: 'holding_name', typeKey: 'sector', valueKey: 'position_value_eur',
    itemKey: 'holding', valuationKey: 'climate_var', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Portfolio value', field: 'total_portfolio_value_eur', fmt: 'eur' },
      { label: 'Money at climate risk', field: 'total_climate_var_eur', fmt: 'eur', tone: RISK },
      { label: 'Share at climate risk', field: 'portfolio_climate_var_pct', fmt: 'pct' },
      { label: 'Holdings analysed', num: 'n_scored', den: 'n_holdings', fmt: 'frac' },
    ],
  },
  reit: {
    prefix: 'realestate', listKey: 'properties', noun: 'properties', uploadNoun: 'property schedule',
    idKey: 'property_id', nameKey: 'property_name', typeKey: 'property_type', valueKey: 'property_value_eur',
    itemKey: 'property', valuationKey: 'valuation', auditKey: 'valuation_audit', overrideMode: 'valuation',
    kpis: [
      { label: 'Portfolio value', field: 'total_value_eur', fmt: 'eur' },
      { label: 'Yearly rental income', field: 'total_annual_noi_eur', fmt: 'eur', flow: true },
      { label: 'Hit to rental income', field: 'portfolio_noi_impact_pct', fmt: 'pct', tone: RISK },
      { label: 'Properties analysed', num: 'n_scored', den: 'n_properties', fmt: 'frac' },
    ],
  },
}

// upload / template paths share one shape: /v1/{prefix}/{listKey}/{upload|template.xlsx}
export const uploadPath = (c: Cfg) => `/v1/${c.prefix}/${c.listKey}/upload`
export const templatePath = (c: Cfg) => `/v1/${c.prefix}/${c.listKey}/template.xlsx`

export function kpiValue(k: Kpi, r: Record<string, unknown> | undefined): string {
  if (!r) return '—'
  if (k.fmt === 'frac') return `${(r[k.num!] as number) ?? 0}/${(r[k.den!] as number) ?? 0}`
  const v = r[k.field!] as number | undefined
  if (v == null) return '—'
  return k.fmt === 'pct' ? `${v}%` : k.flow ? flow(v) : balance(v)
}

// The page offers today and one warming pathway; the forward view always reads a pathway (today has no projection).
export const SCENARIOS = ['baseline', 'disorderly_2c'] as const
export const FORWARD_DEFAULT = 'disorderly_2c'
// each pathway's own hue (index.css --scn-*), so a scenario reads the same on every chart
export const SCENARIO_COLOR: Record<string, string> = {
  baseline: 'var(--scn-baseline)', orderly_1_5c: 'var(--scn-orderly)', disorderly_2c: 'var(--scn-disorderly)', hot_house_3_5c: 'var(--scn-hot)',
}
