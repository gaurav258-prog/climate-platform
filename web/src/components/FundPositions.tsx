import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Factory } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { money } from '../lib/money'
import { Button, Card, SectionHead } from './ui'
import { hazardLabel, sevColor } from '../lib/hazards'
import { CloseButton } from './Dialog'
import { Drawer } from './Drawer'

// The fund's holdings, each drilling to the issuer's full physical footprint (per-facility scores) — the
// look-through from a fund position to the real assets on the ground that drive its climate risk.

interface Pos {
  position_id: string; isin: string; security_name: string; asset_class?: string
  issuer_id: string | null; issuer_name: string | null; country: string | null; sector: string | null
  market_value_eur: number | null; weight_pct: number | null
  physical: { headline_score: number | null; headline_bucket: string | null; headline_hazard: string | null } | null
  transition: { transition_risk_score: number | null } | null
}
interface Facility { facility_id: string; name: string; facility_type: string | null; country: string | null; region: string | null
  lat: number | null; lon: number | null; materiality_weight: number | null; scores: { hazard: string; score: number; bucket: string }[] }
interface Issuer {
  issuer?: { issuer_id: string; lei: string | null; name: string; issuer_type: string | null; country: string | null; sector: string | null; nace_code: string | null }
  physical?: { headline_score?: number | null; headline_bucket?: string | null; headline_hazard?: string | null; per_hazard?: Record<string, { score: number; bucket: string }>; n_facilities?: number; n_scored_facilities?: number }
  transition?: { transition_risk_score: number | null; carbon_intensity_tco2e_per_meur: number | null } | null
  emissions?: { reporting_year: number; scope1: number | null; scope2: number | null; scope3: number | null; source: string } | null
  facilities?: Facility[]
  own_data?: Record<string, number>     // rows of the organisation's own data about the issuer, per store
}

const eur = (n?: number | null) => money(n, 'EUR')   // fund positions are held in EUR, as the SFDR statement reports them
const BUCKET: Record<string, string> = { VH: 'severe', H: 'high', M: 'elevated', L: 'low' }

export default function FundPositions({ fundId }: { fundId: string }) {
  const q = useQuery({ queryKey: ['fund-positions', fundId], queryFn: () => api.get<{ positions: Pos[] }>(`/v1/funds/${fundId}/positions`) })
  const [issuer, setIssuer] = useState<string | null>(null)
  const positions = q.data?.positions ?? []
  if (!q.isLoading && positions.length === 0) return null

  return (
    <Card className="p-0 overflow-hidden">
      <SectionHead className="px-5 py-3 border-b border-[var(--color-line)]" hint={<>{positions.length} position{positions.length === 1 ? '' : 's'} · biggest physical risk first</>}>Holdings</SectionHead>
      {q.isLoading ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</div>
        : <div className="divide-y divide-[var(--color-line)]">
            {positions.map(p => {
              const sc = p.physical?.headline_score
              return (
                <button key={p.position_id} onClick={() => p.issuer_id && setIssuer(p.issuer_id)} disabled={!p.issuer_id}
                  className="w-full text-left px-5 py-3 flex items-center gap-4 hover:bg-[var(--color-bg-2)] transition disabled:cursor-default">
                  <div className="min-w-0 flex-1">
                    <div className="text-[13.5px] text-[var(--color-ink)] truncate">{p.security_name || p.issuer_name || p.isin}</div>
                    <div className="mono text-[10.5px] text-[var(--color-faint)] truncate">{[p.isin, p.sector, p.country].filter(Boolean).join(' · ')}</div>
                  </div>
                  <div className="text-right w-24 shrink-0"><div className="mono text-[12.5px] tabular-nums text-[var(--color-mute)]">{eur(p.market_value_eur)}</div><div className="mono text-[9px] text-[var(--color-faint)]">{p.weight_pct != null ? `${p.weight_pct.toFixed(1)}%` : ''}</div></div>
                  <div className="w-28 text-right shrink-0">
                    {sc == null ? <span className="mono text-[12px] text-[var(--color-faint)]">—</span>
                      : <span className="mono text-[12px]" style={{ color: sevColor(sc) }}>{Math.round(sc)}/100{p.physical?.headline_hazard ? ` · ${hazardLabel(p.physical.headline_hazard)}` : ''}</span>}
                  </div>
                  {p.issuer_id ? <ChevronRight size={14} className="text-[var(--color-faint)] shrink-0" /> : <span className="w-3.5 shrink-0" />}
                </button>
              )
            })}
          </div>}
      {issuer && <IssuerDrawer issuerId={issuer} onClose={() => setIssuer(null)} />}
    </Card>
  )
}

function IssuerDrawer({ issuerId, onClose }: { issuerId: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['issuer', issuerId], queryFn: () => api.get<Issuer>(`/v1/issuers/${issuerId}`) })
  const d = q.data
  const iss = d?.issuer
  const perHaz = d?.physical?.per_hazard ? Object.entries(d.physical.per_hazard).sort((a, b) => b[1].score - a[1].score) : []
  return (
    <Drawer label="Issuer" onClose={onClose} backdropClassName="bg-black/50" className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] shadow-2xl">
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
          <SectionHead>Issuer</SectionHead>
          <CloseButton onClick={onClose} />
        </div>
        {q.isError ? <div className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Issuer not found.')}</div>
          : !d ? <div className="p-8 text-[13px] text-[var(--color-faint)]">loading…</div>
          : !iss ? <div className="p-8 text-[13px] text-[var(--color-bad)]">Issuer not found.</div>
          : (
          <div className="p-6 space-y-6">
            <div>
              <h2 className="display text-xl font-semibold">{iss.name}</h2>
              <div className="mono text-[11px] text-[var(--color-faint)] mt-1 flex flex-wrap gap-x-2">
                {iss.issuer_type && <span>{iss.issuer_type}</span>}{iss.sector && <span>· {iss.sector}</span>}{iss.country && <span>· {iss.country}</span>}{iss.lei && <span>· LEI {iss.lei}</span>}
              </div>
            </div>

            {perHaz.length > 0 && (
              <div>
                <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Physical risk · value-weighted across facilities{d.physical?.n_scored_facilities != null ? ` (${d.physical.n_scored_facilities}/${d.physical.n_facilities} scored)` : ''}</div>
                <Card className="p-4"><div className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5">
                  {perHaz.map(([h, v]) => (
                    <div key={h} className="flex items-center justify-between gap-3 text-[12.5px] border-b border-[var(--color-line)] py-1">
                      <span className="text-[var(--color-mute)] capitalize truncate">{hazardLabel(h)}</span>
                      <span className="mono tabular-nums shrink-0" style={{ color: sevColor(v.score) }}>{Math.round(v.score)}/100 · {BUCKET[v.bucket] ?? v.bucket}</span>
                    </div>
                  ))}
                </div></Card>
              </div>
            )}

            {d.emissions && (
              <div className="text-[12px] text-[var(--color-mute)]">
                <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] block mb-1">Emissions ({d.emissions.reporting_year} · {d.emissions.source})</span>
                Scope 1 <b>{d.emissions.scope1 ?? '—'}</b> · Scope 2 <b>{d.emissions.scope2 ?? '—'}</b> · Scope 3 <b>{d.emissions.scope3 ?? '—'}</b> tCO₂e
              </div>
            )}

            {d.own_data && Object.keys(d.own_data).length > 0 && <OwnData issuerId={issuerId} name={iss.name} own={d.own_data} />}

            {(d.facilities?.length ?? 0) > 0 && (
              <div>
                <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Facilities · the assets on the ground</div>
                <div className="space-y-2">
                  {d.facilities!.map(f => {
                    const worst = f.scores?.length ? f.scores.reduce((a, b) => b.score > a.score ? b : a) : null
                    return (
                      <div key={f.facility_id} className="rounded-lg border border-[var(--color-line)] p-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="min-w-0"><div className="text-[12.5px] text-[var(--color-ink)] truncate flex items-center gap-1.5"><Factory size={12} className="text-[var(--color-faint)]" />{f.name}</div>
                            <div className="mono text-[10px] text-[var(--color-faint)]">{[f.facility_type, f.region, f.country].filter(Boolean).join(' · ')}{f.lat != null && f.lon != null ? ` · ${Math.abs(f.lat).toFixed(1)}°${f.lat >= 0 ? 'N' : 'S'}` : ''}</div>
                          </div>
                          {worst && <span className="mono text-[11px] shrink-0" style={{ color: sevColor(worst.score) }}>{hazardLabel(worst.hazard)} {Math.round(worst.score)}</span>}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )}
    </Drawer>
  )
}

const STORE: Record<string, string> = {
  issuer_emissions: 'emissions', issuer_esg_metrics: 'ESG metrics', issuer_taxonomy_kpi: 'Taxonomy KPIs',
  issuer_voluntary_pai: 'additional PAI values', issuer_data_confirmations: 'plausibility confirmations',
}

// the data the organisation stated about this issuer — withdrawable (uploaded in error), audited with the reason (E146)
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
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Your organisation's data on this issuer</div>
      <div className="text-[12px] text-[var(--color-mute)]">
        {Object.entries(own).map(([t, n]) => `${n} ${STORE[t] ?? t}`).join(' · ')}
      </div>
      {!open ? <Button variant="ghost" onClick={() => setOpen(true)}>Withdraw this data</Button> : (
        <div className="space-y-2">
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2}
            placeholder="Why it is withdrawn (kept in the audit record) — e.g. uploaded for the wrong company"
            className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]" />
          <div className="text-[11px] text-[var(--color-faint)]">Only your own figures go; published and shared reference data stay, and a filing already frozen keeps what it printed.</div>
          <div className="flex gap-2">
            <Button variant="primary" onClick={withdraw} disabled={busy || reason.trim().length < 10}>Withdraw</Button>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}
    </div>
  )
}
