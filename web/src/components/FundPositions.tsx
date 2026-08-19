import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, X, Factory } from 'lucide-react'
import { api } from '../lib/api'
import { Card, SectionHead } from './ui'
import { hazardLabel, sevColor } from '../lib/hazards'

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
  error?: string
  issuer?: { issuer_id: string; lei: string | null; name: string; issuer_type: string | null; country: string | null; sector: string | null; nace_code: string | null }
  physical?: { headline_score?: number | null; headline_bucket?: string | null; headline_hazard?: string | null; per_hazard?: Record<string, { score: number; bucket: string }>; n_facilities?: number; n_scored_facilities?: number }
  transition?: { transition_risk_score: number | null; carbon_intensity_tco2e_per_meur: number | null } | null
  emissions?: { reporting_year: number; scope1: number | null; scope2: number | null; scope3: number | null; source: string } | null
  facilities?: Facility[]
}

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
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
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
          <SectionHead>Issuer</SectionHead>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>
        {!d ? <div className="p-8 text-[13px] text-[var(--color-faint)]">loading…</div>
          : d.error || !iss ? <div className="p-8 text-[13px] text-[var(--color-bad)]">{d.error ?? 'Issuer not found.'}</div>
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
      </div>
    </div>
  )
}
