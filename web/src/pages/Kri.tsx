import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'
import { HBar } from '../components/Charts'
import { hazardLabel, sevColor } from '../lib/hazards'
import { filingLink } from '../lib/links'

// Key Regulatory Indicator dashboard — the regulator's-eye consolidated view of the book's physical-risk
// KRIs, with the same headline figures across the org's filed history so the trend is visible.

interface Kpi { key: string; label: string; value: number | null; fmt: string; tone: string | null; hint: string | null }
interface Haz { hazard: string; value: number; score: number }
interface Hist { label: string; filing_id: string | null; total_value: number | null; value_at_risk: number | null; pct_at_risk: number | null }
interface Resp { framework: string; supported: boolean; label: string; kpis: Kpi[]; by_hazard: Haz[]; history: Hist[]; note?: string; message?: string }
interface Ent { name: string; value: number | null; h3_cell: string | null; country: string | null; score: number | null }
interface HazDrill { supported: boolean; hazard: string; noun: string; entities: Ent[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const fmt = (k: Kpi) => k.value == null ? '—' : k.fmt === 'eur' ? eur(k.value) : k.fmt === 'pct' ? `${k.value}%` : Math.round(k.value).toLocaleString('en-GB')
const FRAMEWORKS: Record<string, string> = { bank: 'bank_tcfd', asset_manager: 'sfdr_pai', reit: 'reit_tcfd', insurer: 'insurer_climate', manufacturer: 'csrd_e1' }

export default function Kri() {
  const { profile } = useAuth()
  const nav = useNavigate()
  const fw = FRAMEWORKS[profile?.org?.type ?? ''] ?? 'bank_tcfd'
  const [framework] = useState(fw)
  const [drill, setDrill] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['kri', framework], queryFn: () => api.get<Resp>(`/v1/reg-tasks/kri?framework=${framework}`) })
  const d = q.data

  return (
    <div className="fadeup space-y-5">
      <div>
        <Eyebrow>Regulatory intelligence</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">KRI dashboard</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">A regulator's-eye view of the book's key risk indicators — identify emerging risk early, drill into a hazard, and track the trend across filings.</p>
      </div>

      {q.isLoading ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
        : !d || !d.supported ? <Card className="p-10 text-[13px] text-[var(--color-mute)]">{d?.message ?? 'No KRI dashboard for this sector yet.'}</Card>
        : (
        <>
          {d.note && <div className="text-[12.5px] text-[var(--color-warn)]">{d.note}</div>}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {d.kpis.map(k => (
              <Card key={k.key} className="px-4 py-3.5" >
                <div className="display text-[22px] leading-none" style={k.tone ? { color: k.tone } : undefined}>{fmt(k)}</div>
                <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-2" title={k.hint ?? undefined}>{k.label}{k.hint ? ' ⓘ' : ''}</div>
              </Card>
            ))}
          </div>

          <div className="grid lg:grid-cols-2 gap-5">
            {d.by_hazard.length > 0 && (
              <div>
                <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Value at risk by hazard</div>
                <Card className="p-4">
                  <HBar data={d.by_hazard.map(h => ({ label: hazardLabel(h.hazard), value: h.value, color: sevColor(h.score) }))} format={eur} onBar={i => setDrill(d.by_hazard[i].hazard)} />
                  <div className="mono text-[9.5px] text-[var(--color-faint)] mt-2">click a hazard to see what's driving it</div>
                </Card>
              </div>
            )}
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Historical perspective · across filings</div>
              <Card className="p-0 overflow-hidden">
                {d.history.length === 0 ? <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">No filed history yet.</div>
                  : <div className="divide-y divide-[var(--color-line)]">
                      {d.history.map((h, i) => (
                        <button key={i} onClick={() => h.filing_id && nav(filingLink(profile?.org?.type, h.filing_id))}
                          className="w-full text-left px-5 py-3 flex items-center gap-4 hover:bg-[var(--color-panel)] transition" title="Open this filing">
                          <div className="flex-1 mono text-[12px] text-[var(--color-mute)]">{h.label}</div>
                          <div className="text-right"><div className="mono text-[12.5px] tabular-nums">{eur(h.total_value)}</div><div className="mono text-[9.5px] text-[var(--color-faint)]">book value</div></div>
                          {h.value_at_risk != null && <div className="text-right w-24"><div className="mono text-[12.5px] tabular-nums" style={{ color: '#fb7185' }}>{eur(h.value_at_risk)}</div><div className="mono text-[9.5px] text-[var(--color-faint)]">at risk</div></div>}
                          <ChevronRight size={14} className="text-[var(--color-faint)] shrink-0" />
                        </button>
                      ))}
                    </div>}
              </Card>
            </div>
          </div>
        </>
      )}

      {drill && <HazardDrill framework={framework} hazard={drill} onClose={() => setDrill(null)} />}
    </div>
  )
}

function HazardDrill({ framework, hazard, onClose }: { framework: string; hazard: string; onClose: () => void }) {
  const q = useQuery({ queryKey: ['kri-hazard', framework, hazard], queryFn: () => api.get<HazDrill>(`/v1/reg-tasks/kri/hazard?framework=${framework}&hazard=${hazard}`) })
  const d = q.data
  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-full max-w-md h-full bg-[var(--color-bg-2)] border-l border-[var(--color-line)] overflow-y-auto" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] px-5 py-3 flex items-center justify-between">
          <div><div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Driving {hazardLabel(hazard)}</div></div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><ChevronRight size={17} className="rotate-180" /></button>
        </div>
        {!d ? <div className="p-8 text-center text-[var(--color-faint)] text-sm">loading…</div>
          : !d.supported ? <div className="p-6 text-[13px] text-[var(--color-mute)]">Entity-level drill isn't available for this sector's report.</div>
          : (
          <div className="p-5">
            <div className="mono text-[11px] text-[var(--color-faint)] mb-3">{d.entities.length} {d.noun} exposed at High+ · biggest first</div>
            <div className="space-y-2">
              {d.entities.map((e, i) => (
                <div key={i} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-2.5 flex items-center gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="text-[12.5px] text-[var(--color-ink)] truncate">{e.name}{e.country ? <span className="text-[var(--color-faint)]"> · {e.country}</span> : null}</div>
                    <div className="mono text-[9.5px] text-[var(--color-faint)]">cell {e.h3_cell ? e.h3_cell.slice(0, 10) + '…' : '—'}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="mono text-[12px] tabular-nums text-[var(--color-mute)]">{eur(e.value)}</div>
                    <div className="mono text-[10px]" style={{ color: sevColor(e.score ?? 0) }}>{e.score != null ? Math.round(e.score) : '—'}/100</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
