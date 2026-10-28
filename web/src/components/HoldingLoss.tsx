import { useQuery } from '@tanstack/react-query'
import { Factory } from 'lucide-react'
import { api } from '../lib/api'
import { flow } from '../lib/money'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Meter } from './sfdr/visuals'

// The holdings look-through of the loss engine (decided 2026-10-22): each holding's yearly loss, looked through to its
// issuer's sites — the share of the issuer's physical value lost (tested damage curves only), and euros on the holding
// where the issuer's physical value and enterprise value are provided. Every missing part is named, never estimated.

type Why = Message & { code: string }
interface Hazard { peril: string; share: number | null; low: number | null; high: number | null; why: Why | null }
interface Site { facility_id: string; name: string | null; facility_type: string | null; country: string | null; region: string | null
  weight: number; weight_basis: string; counts: boolean; why: Why | null; hazards: Hazard[] }
export interface IssuerLoss { share: number | null; share_low: number | null; share_high: number | null; covered: number | null
  why: Why | null; sites: Site[]; hazards: Record<string, { share: number; covered: number }> }
export interface HoldingLossRow { position_id: string; issuer_id: string; mv: number; share: number | null; eur: number | null
  eur_low: number | null; eur_high: number | null; holding_share: number | null; why: Why | null
  physical_value_eur: number | null; physical_value_year: number | null; evic_eur: number | null; evic_year: number | null }
export interface FundLoss { as_of: string | null; positions: HoldingLossRow[]; issuers: Record<string, IssuerLoss>
  value_eur: number; covered_value_eur: number; eur: number | null; eur_low: number | null; eur_high: number | null
  why: (Why & { count: number })[]; accepted_bases: { basis: string; name: string }[]; headline: string | null }

const PERIL: Record<string, string> = { flood: 'River flood', coastal_flood: 'Coastal flood', storm: 'Tropical cyclone', windstorm: 'European windstorm' }
const SITE: Record<string, string> = { hq: 'Head office', office: 'Office', plant: 'Plant', warehouse: 'Warehouse' }
const BASIS: Record<string, string> = { assets: 'Assets', revenue: 'Revenue', production_capacity: 'Capacity', headcount: 'Headcount', equal: 'Equal shares' }

/** A share of value lost per year, as a percentage — small shares keep two significant figures. */
export function share(v: number | null | undefined): string {
  if (v == null) return '—'
  const p = v * 100
  if (p === 0) return '0%'
  if (p < 0.0001) return '<0.0001%'
  return `${p.toLocaleString('en-GB', { maximumSignificantDigits: 2 })}%`
}

export const ABOUT = [
  { heading: HEADING.shows, body: 'Each holding’s expected yearly loss from river flood and tropical cyclone, looked through to the sites of the company it is invested in: first as a share of the company’s physical value, then in euros on the holding.' },
  { heading: HEADING.read, body: 'The share is the sum over the company’s sites of each site’s share of the company’s value times the share of that site’s value lost a year. Euros on the holding are that share times the company’s physical asset value times the holding’s part of the company: its value divided by the company’s enterprise value.' },
  { heading: HEADING.sources, body: 'Only losses whose damage curve passed its test on observed losses, and gives a share of the site’s whole physical value. A site counts when its weight is measured on the company’s assets, or on another basis your organisation accepts in Methodology. The company’s physical asset value and enterprise value are yours, from the holdings upload.' },
  { heading: HEADING.limits, body: 'Where any part is missing, the reason is shown — never a zero or an estimate. A company located only by its registered address has no physical site located. Today’s climate only.' },
]

export function useFundLoss(fundId: string) {
  return useQuery({ queryKey: ['fund-loss', fundId], queryFn: () => api.get<FundLoss>(`/v1/funds/${fundId}/loss-lookthrough`) })
}

/** The fund's yearly loss on its holdings and the share of its value that figure covers; why the rest is missing, each
 * reason with how many holdings it stops, one click away. */
export function FundLossChip({ d }: { d?: FundLoss }) {
  if (!d) return null
  const cov = d.value_eur ? (100 * d.covered_value_eur) / d.value_eur : 0
  const missing = d.why.reduce((a, w) => a + w.count, 0)
  return (
    <span className="inline-flex items-center gap-2 text-[12px] text-[var(--color-mute)]">
      <span>Yearly loss</span>
      {d.eur != null
        ? <><span className="text-[var(--color-ink)] tabular-nums">{flow(d.eur)}</span><Meter value={cov} width="w-14" label="Share of the fund's value with a figure" /></>
        : <span className="text-[var(--color-warn)]">Missing</span>}
      {missing > 0 && <InfoButton compact details={{ title: `Missing for ${missing} holding${missing === 1 ? '' : 's'}`,
        sections: d.why.map(w => ({ heading: w.label, body: `${w.count} holding${w.count === 1 ? '' : 's'}. ${w.detail?.what ?? ''}` })) }} />}
      <InfoButton compact details={{ title: 'Yearly loss on holdings', sections: ABOUT }} />
    </span>
  )
}

/** One holding's cell: euros a year, else the share of the company's value, else why (detail in the issuer panel). */
export function LossCell({ r }: { r?: HoldingLossRow }) {
  if (!r) return <span className="text-[12px] text-[var(--color-faint)]">—</span>
  if (r.eur != null) return (
    <span className="text-right">
      <span className="block text-[12.5px] tabular-nums text-[var(--color-ink)]">{flow(r.eur)}</span>
      <span className="block text-[11px] tabular-nums text-[var(--color-faint)]">{share(r.share)} of company</span>
    </span>)
  if (r.share != null) return (
    <span className="text-right">
      <span className="block text-[12.5px] tabular-nums text-[var(--color-ink)]">{share(r.share)}</span>
      <span className="block text-[11px] text-[var(--color-warn)] truncate">{r.why?.label}</span>
    </span>)
  return <span className="text-[11.5px] text-[var(--color-faint)] truncate text-right" title={r.why?.label}>{r.why?.label ?? '—'}</span>
}

/** The issuer panel's loss section: the share lost, euros on the holding, and each site with each hazard. */
export function IssuerLossSection({ a, h }: { a?: IssuerLoss; h?: HoldingLossRow }) {
  if (!a) return null
  const counted = a.sites.filter(s => s.counts)
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[13px] font-medium text-[var(--color-ink)]">Yearly loss</span>
        <InfoButton compact details={{ title: 'Yearly loss', sections: ABOUT }} />
      </div>
      {a.share == null && a.why ? <MessageLine m={a.why} className="text-[12.5px] text-[var(--color-warn)]" /> : (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-[var(--color-line)] p-3">
            <div className="text-[11.5px] text-[var(--color-faint)]">Share of the company’s physical value</div>
            <div className="display text-[22px] tabular-nums text-[var(--color-ink)]">{share(a.share)}</div>
            <div className="text-[11px] tabular-nums text-[var(--color-faint)]">{share(a.share_low)} – {share(a.share_high)} a year</div>
            <div className="flex items-center justify-between gap-2 mt-2 text-[11.5px] text-[var(--color-mute)]">
              <span>Value with a tested loss</span><Meter value={(a.covered ?? 0) * 100} width="w-14" />
            </div>
          </div>
          <div className="rounded-lg border border-[var(--color-line)] p-3">
            <div className="text-[11.5px] text-[var(--color-faint)]">On this holding</div>
            {h?.eur != null ? <>
              <div className="display text-[22px] tabular-nums text-[var(--color-ink)]">{flow(h.eur)}</div>
              <div className="text-[11px] tabular-nums text-[var(--color-faint)]">{flow(h.eur_low)} – {flow(h.eur_high)} a year</div>
              <div className="text-[11px] tabular-nums text-[var(--color-faint)] mt-2">{share(h.holding_share)} of the company</div>
            </> : h?.why ? <MessageLine m={h.why} className="text-[12px] text-[var(--color-warn)] mt-1" /> : <span>—</span>}
          </div>
        </div>
      )}
      {a.sites.length > 0 && (
        <div className="space-y-2 mt-3">
          {a.sites.map(s => (
            <div key={s.facility_id} className="rounded-lg border border-[var(--color-line)] px-3 py-2 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-[12.5px] text-[var(--color-ink)] truncate flex items-center gap-1.5"><Factory size={12} className="text-[var(--color-faint)]" />{s.name ?? 'Site'}</div>
                  <div className="text-[11.5px] text-[var(--color-faint)]">{[SITE[s.facility_type ?? ''] ?? null, s.region, s.country].filter(Boolean).join(' · ')}</div>
                </div>
                <span className="inline-flex items-center gap-2 shrink-0" title="The site's share of the company">
                  <StatusChip tone={s.counts ? 'neutral' : 'warn'} label={BASIS[s.weight_basis] ?? 'Weight'} />
                  <Meter value={s.weight * 100} width="w-12" />
                </span>
              </div>
              {s.why ? <MessageLine m={s.why} className="text-[11.5px] text-[var(--color-warn)]" /> : s.hazards.map(z => (
                <div key={z.peril} className="flex items-center justify-between gap-2 text-[11.5px]">
                  <span className="text-[var(--color-mute)]">{PERIL[z.peril] ?? 'Hazard'}</span>
                  {z.share != null ? <span className="tabular-nums text-[var(--color-ink)]">{share(z.share)} of its value a year</span>
                    : z.why ? <MessageLine m={z.why} className="text-[var(--color-faint)]" /> : <span>—</span>}
                </div>))}
            </div>))}
          {counted.length === 0 && a.sites.length > 0 && !a.why && <div className="text-[11.5px] text-[var(--color-faint)]">No site weighted by value.</div>}
        </div>
      )}
    </div>
  )
}
