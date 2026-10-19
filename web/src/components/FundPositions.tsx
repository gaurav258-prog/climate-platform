import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Factory, Layers } from 'lucide-react'
import { api, apiMessage, apiDetail } from '../lib/api'
import { toast } from '../lib/toast'
import { money } from '../lib/money'
import { Button, Card, SectionHead } from './ui'
import { hazardLabel, sevColor } from '../lib/hazards'
import { HEADING, InfoButton, MessageLine } from './Details'
import { StatusChip } from './StatusChip'
import { Meter, SidePanel, num } from './sfdr/visuals'
import { BAND, OWN_DATA } from './sfdr/words'

// The fund's holdings, each drilling to the issuer's physical footprint (a score per site) — the look-through from a
// fund position to the assets on the ground that drive its climate risk.

interface Pos {
  position_id: string; isin: string; security_name: string; asset_class?: string
  issuer_id: string | null; issuer_name: string | null; country: string | null; sector: string | null
  market_value_eur: number | null; weight_pct: number | null
  physical: { headline_score: number | null; headline_bucket: string | null; headline_hazard: string | null } | null
}
interface Facility { facility_id: string; name: string; facility_type: string | null; country: string | null; region: string | null
  scores: { hazard: string; score: number; bucket: string }[] }
interface Issuer {
  issuer?: { issuer_id: string; lei: string | null; name: string; country: string | null; sector: string | null }
  physical?: { per_hazard?: Record<string, { score: number; bucket: string }>; n_facilities?: number; n_scored_facilities?: number }
  transition?: { transition_risk_score: number | null; carbon_intensity_tco2e_per_meur: number | null } | null
  emissions?: { reporting_year: number; scope1: number | null; scope2: number | null; scope3: number | null; source: string } | null
  facilities?: Facility[]
  own_data?: Record<string, number>     // rows of the organisation's own data about the issuer, per store
}

const eur = (n?: number | null) => money(n, 'EUR')   // fund positions are held in euro, as the statement reports them
// where an issuer's emissions come from (issuer_emissions source)
const SOURCE: Record<string, string> = {
  disclosed: 'Reported by the company', client: 'Your data', cdp: 'Reported to CDP', vendor: 'Your data vendor',
  estimated: 'Estimated from its sector and revenue',
}
const SITE: Record<string, string> = { hq: 'Head office', office: 'Office', plant: 'Plant', warehouse: 'Warehouse' }

export default function FundPositions({ fundId }: { fundId: string }) {
  const q = useQuery({ queryKey: ['fund-positions', fundId], queryFn: () => api.get<{ positions: Pos[] }>(`/v1/funds/${fundId}/positions`) })
  const [issuer, setIssuer] = useState<string | null>(null)
  const positions = q.data?.positions ?? []
  if (!q.isLoading && positions.length === 0) return null
  const maxW = Math.max(1, ...positions.map(p => p.weight_pct ?? 0))

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center gap-2 flex-wrap">
        <SectionHead icon={Layers}>Holdings</SectionHead>
        <StatusChip tone="neutral" label={`${positions.length} holding${positions.length === 1 ? '' : 's'}`} />
        <InfoButton compact details={{ title: 'Holdings', sections: [{ heading: HEADING.read, body: 'Highest physical risk first. Open a holding to see its issuer\'s sites and the score of each.' }] }} />
      </div>
      {q.isLoading ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">Loading…</div>
        : <div className="divide-y divide-[var(--color-line)]">
            {positions.map(p => {
              const sc = p.physical?.headline_score
              return (
                <button key={p.position_id} onClick={() => p.issuer_id && setIssuer(p.issuer_id)} disabled={!p.issuer_id}
                  className="w-full text-left px-5 py-3 grid grid-cols-[1fr_auto] md:grid-cols-[1fr_9rem_13rem_1rem] gap-x-4 gap-y-1 items-center hover:bg-[var(--color-bg-2)] transition disabled:cursor-default">
                  <div className="min-w-0">
                    <div className="text-[13.5px] text-[var(--color-ink)] truncate">{p.security_name || p.issuer_name || p.isin}</div>
                    <div className="text-[11.5px] text-[var(--color-faint)] truncate">{[p.isin, p.sector, p.country].filter(Boolean).join(' · ')}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[12.5px] tabular-nums text-[var(--color-mute)]">{eur(p.market_value_eur)}</div>
                    <div className="h-1 rounded-full mt-1 ml-auto" style={{ width: `${Math.max(4, ((p.weight_pct ?? 0) / maxW) * 100)}%`, background: 'var(--color-sky)', opacity: 0.6 }} title={`${num(p.weight_pct, 1)}% of the fund`} />
                  </div>
                  <div className="hidden md:flex items-center gap-2 justify-end">
                    {sc == null ? <span className="text-[12px] text-[var(--color-faint)]">Not scored</span>
                      : <><Meter value={sc} tone={sevColor(sc)} width="w-14" score />{p.physical?.headline_hazard && <span className="text-[11px] text-[var(--color-faint)] truncate max-w-[8rem]">{hazardLabel(p.physical.headline_hazard)}</span>}</>}
                  </div>
                  {p.issuer_id ? <ChevronRight size={14} className="text-[var(--color-faint)] hidden md:block" /> : <span className="hidden md:block" />}
                </button>
              )
            })}
          </div>}
      {issuer && <IssuerPanel issuerId={issuer} onClose={() => setIssuer(null)} />}
    </Card>
  )
}

function IssuerPanel({ issuerId, onClose }: { issuerId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['issuer', issuerId], queryFn: () => api.get<Issuer>(`/v1/issuers/${issuerId}`) })
  const d = q.data
  const iss = d?.issuer
  const perHaz = d?.physical?.per_hazard ? Object.entries(d.physical.per_hazard).sort((a, b) => b[1].score - a[1].score) : []
  const e = d?.emissions
  const scopes = e ? ([['Scope 1', e.scope1], ['Scope 2', e.scope2], ['Scope 3', e.scope3]] as const) : []
  const maxScope = Math.max(1, ...scopes.map(([, v]) => v ?? 0))
  return (
    <SidePanel title={iss?.name ?? 'Issuer'} onClose={onClose}>
      {q.isError ? <MessageLine m={{ label: apiMessage(q.error, 'Issuer not found.'), detail: apiDetail(q.error) }} className="text-[13px] text-[var(--color-bad)]" />
        : !d || !iss ? <div className="text-[13px] text-[var(--color-faint)]">Loading…</div>
        : (
        <div className="space-y-6">
          <div className="flex flex-wrap gap-1.5">
            {iss.sector && <StatusChip tone="neutral" label={iss.sector} />}
            {iss.country && <StatusChip tone="neutral" label={iss.country} />}
            {iss.lei && <StatusChip tone="neutral" label={`LEI ${iss.lei}`} />}
          </div>

          {perHaz.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[13px] font-medium text-[var(--color-ink)]">Physical risk</span>
                {d.physical?.n_scored_facilities != null && <StatusChip tone="neutral" label={`${d.physical.n_scored_facilities} of ${d.physical.n_facilities} sites scored`} />}
                <InfoButton compact details={{ title: 'Physical risk', sections: [{ heading: HEADING.read, body: 'Each hazard\'s score out of 100, weighted across the issuer\'s sites by how much each matters to it.' }] }} />
              </div>
              <div className="space-y-1.5">
                {perHaz.map(([h, v]) => (
                  <div key={h} className="grid grid-cols-[11rem_1fr_4.5rem] items-center gap-3 text-[12.5px]">
                    <span className="text-[var(--color-mute)] truncate">{hazardLabel(h)}</span>
                    <Meter value={v.score} tone={sevColor(v.score)} width="w-full" score />
                    <span className="text-[11.5px] text-right" style={{ color: sevColor(v.score) }}>{BAND[v.bucket] ?? '—'}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {e && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[13px] font-medium text-[var(--color-ink)]">Emissions</span>
                <StatusChip tone="neutral" label={String(e.reporting_year)} />
                <InfoButton compact details={{ title: 'Emissions', sections: [{ heading: HEADING.sources, body: SOURCE[e.source] ?? 'A published figure' }] }} />
              </div>
              <div className="space-y-1.5">
                {scopes.map(([name, v]) => (
                  <div key={name} className="grid grid-cols-[4.5rem_1fr_6rem] items-center gap-3 text-[12.5px]">
                    <span className="text-[var(--color-mute)]">{name}</span>
                    <span className="h-1.5 rounded-full" style={{ width: `${v == null ? 0 : Math.max(2, (v / maxScope) * 100)}%`, background: 'var(--color-sky)' }} />
                    <span className="text-right tabular-nums text-[var(--color-ink)]">{v == null ? '—' : `${num(v, 0)} t`}</span>
                  </div>))}
              </div>
            </div>
          )}

          {d.own_data && Object.keys(d.own_data).length > 0 && <OwnData issuerId={issuerId} name={iss.name} own={d.own_data} />}

          {(d.facilities?.length ?? 0) > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[13px] font-medium text-[var(--color-ink)]">Sites</span>
                <StatusChip tone="neutral" label={String(d.facilities!.length)} />
              </div>
              <div className="space-y-2">
                {d.facilities!.map(f => {
                  const worst = f.scores?.length ? f.scores.reduce((a, b) => b.score > a.score ? b : a) : null
                  return (
                    <div key={f.facility_id} className="rounded-lg border border-[var(--color-line)] px-3 py-2 flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-[12.5px] text-[var(--color-ink)] truncate flex items-center gap-1.5"><Factory size={12} className="text-[var(--color-faint)]" />{f.name}</div>
                        <div className="text-[11.5px] text-[var(--color-faint)]">{[SITE[f.facility_type ?? ''] ?? null, f.region, f.country].filter(Boolean).join(' · ')}</div>
                      </div>
                      {worst && <span className="inline-flex items-center gap-2 shrink-0"><span className="text-[11.5px] text-[var(--color-mute)]">{hazardLabel(worst.hazard)}</span><Meter value={worst.score} tone={sevColor(worst.score)} width="w-12" score /></span>}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </SidePanel>
  )
}

// the data the organisation stated about this issuer — withdrawable (uploaded in error), kept on record with the reason
function OwnData({ issuerId, name, own }: { issuerId: string; name: string; own: Record<string, number> }) {
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const withdraw = async () => {
    setBusy(true)
    try {
      await api.post(`/v1/issuers/${issuerId}/client-data/withdraw`, { reason: reason.trim() })
      toast.success(`Your data on ${name} was withdrawn.`)
      setOpen(false); setReason('')
      qc.invalidateQueries({ queryKey: ['issuer', issuerId] }); qc.invalidateQueries({ queryKey: ['fund'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not withdraw the data.')) }
    finally { setBusy(false) }
  }
  return (
    <div className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[13px] font-medium text-[var(--color-ink)]">Your data on this issuer</span>
        {Object.entries(own).map(([t, n]) => <StatusChip key={t} tone="neutral" label={`${n} ${OWN_DATA[t] ?? 'figures'}`} />)}
      </div>
      {!open ? <Button variant="ghost" onClick={() => setOpen(true)}>Withdraw this data</Button> : (
        <div className="space-y-2">
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} aria-label="Why it is withdrawn"
            placeholder="Why it is withdrawn — for example, uploaded for the wrong company"
            className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]" />
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={withdraw} disabled={busy || reason.trim().length < 10}>Withdraw</Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <InfoButton compact details={{ title: 'Withdraw your data', sections: [{ heading: HEADING.read, body: 'Only your own figures go, and the reason is kept on record. Published and shared reference data stay, and a filing already frozen keeps what it printed.' }] }} />
          </div>
        </div>
      )}
    </div>
  )
}
