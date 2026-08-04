import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileCheck2, CheckCircle2, AlertTriangle, Clock } from 'lucide-react'
import { api, ApiError, download } from '../lib/api'
import { Eyebrow, Card, Button } from '../components/ui'
import { SfdrBadge } from './Funds'
import FundPositions from '../components/FundPositions'
import { OnboardHoldings, VoluntaryPai } from '../components/FundOnboard'

// One fund's full picture: the physical + transition climate report, and the SFDR PAI statement (the 14
// mandatory indicators + taxonomy + narratives) ready to download or freeze as the official filing.

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const num = (n?: number | null, d = 0) => n == null ? '—' : Number(n).toLocaleString('en-GB', { maximumFractionDigits: d })
const pct = (n?: number | null) => n == null ? '—' : `${Math.round(n)}%`

interface Summary { fund: { fund_id: string; name: string; fund_type: string; sfdr_classification: string | null; org_name?: string }
  total_value_eur: number; positions: number
  physical?: { value_weighted_score: number | null; coverage_pct: number | null; value_at_high_plus_eur: number | null; pct_at_high_plus: number | null }
  transition?: { value_weighted_score: number | null; coverage_pct: number | null; value_at_high_plus_eur: number | null; pct_at_high_plus: number | null }
  pai?: { pcaf_data_quality_score: number | null; emissions_coverage_pct: number | null; financed_emissions_coverage_pct: number | null
    pai: { pai_3_waci_tco2e_per_meur: number | null; pai_4_fossil_fuel_exposure_pct: number | null
      pai_1_financed_emissions_tco2e: { total: number } | null; pai_2_carbon_footprint_tco2e_per_meur: number | null } } }

type IndVal = number | { scope_1?: number; scope_2?: number; scope_3?: number; total?: number; note?: string } | null
interface Indicator { number: number | string; area: string; metric: string; unit: string; value: IndVal; coverage_pct: number | null; source?: string; method: string; input_required?: string }
interface Statement { error?: string; message?: string
  entity?: { fund_name: string; manager_legal_name?: string; manager_lei?: string; reference_period?: string }
  summary?: { reference_period: string; reference_year: number; declaration?: string }
  filing_readiness?: { ready_to_file: boolean; missing: string[]; note?: string }
  indicators?: Indicator[]; real_estate_indicators?: Indicator[]; sovereign_indicators?: Indicator[]
  taxonomy?: { taxonomy_eligible_pct?: number; taxonomy_aligned_pct?: number; alignment_coverage_pct?: number; alignment_note?: string }
  narratives?: { policies?: string; actions?: string; engagement?: string; standards?: string; missing?: string[] }
  additional_indicators?: { selected?: string[] }
  coverage_summary?: { mandatory_indicators: number; computed: number; partial: number; not_available: number; emissions_coverage_pct?: number } }
interface Filing { reference_year: number; filed_at: string; filed_by: string; status: string }

const METHOD: Record<string, { c: string; label: string }> = {
  computed: { c: '#34d399', label: 'computed' }, partial: { c: '#e8b24c', label: 'partial' },
  estimated: { c: '#5cc8ff', label: 'estimated' }, not_available: { c: '#fb7185', label: 'not available' },
  not_applicable: { c: '#64748b', label: 'n/a' },
}

function renderIndVal(v: IndVal, unit: string): string {
  if (v == null) return '—'
  if (typeof v === 'number') return unit?.includes('%') ? pct(v) : num(v, 2)
  if (typeof v === 'object') {
    if (v.total != null) return num(v.total, 1)
    const parts = [v.scope_1, v.scope_2, v.scope_3].filter(x => x != null).map(x => num(x, 0))
    return parts.length ? parts.join(' / ') : (v.note ?? '—')
  }
  return '—'
}

export default function FundDetail() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const sum = useQuery({ queryKey: ['fund', id], queryFn: () => api.get<Summary>(`/v1/funds/${id}`) })
  const stmt = useQuery({ queryKey: ['fund-sfdr', id], queryFn: () => api.get<Statement>(`/v1/funds/${id}/sfdr-statement`) })
  const filings = useQuery({ queryKey: ['fund-filings', id], queryFn: () => api.get<{ filings: Filing[] }>(`/v1/funds/${id}/sfdr-filings`) })
  const s = sum.data
  const st = stmt.data
  const [busy, setBusy] = useState(false); const [msg, setMsg] = useState<{ t: string; ok: boolean } | null>(null)
  const refreshAll = () => { sum.refetch(); stmt.refetch(); qc.invalidateQueries({ queryKey: ['fund-positions', id] }); qc.invalidateQueries({ queryKey: ['funds'] }) }

  const fileStatement = async () => {
    setBusy(true); setMsg(null)
    try {
      const r = await api.post<{ ok?: boolean; reference_year?: number; error?: string }>(`/v1/funds/${id}/sfdr-statement/file`, {})
      if (r.error) setMsg({ t: r.error, ok: false })
      else { setMsg({ t: `Filed as the official SFDR statement for ${r.reference_year}.`, ok: true }); qc.invalidateQueries({ queryKey: ['fund-filings', id] }); stmt.refetch() }
    } catch (e) { setMsg({ t: e instanceof ApiError ? String(e.body ?? e.message) : 'Could not file.', ok: false }) }
    finally { setBusy(false) }
  }

  if (sum.isLoading) return <div className="p-10 text-[13px] text-[var(--color-faint)]">loading…</div>
  if (!s || !s.fund) return <div className="p-10 text-[13px] text-[var(--color-bad)]">Fund not found.</div>

  const ready = st?.filing_readiness?.ready_to_file
  const inds = st?.indicators ?? []
  const cov = st?.coverage_summary

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Asset management · SFDR · fund</Eyebrow>
        <div className="flex items-center gap-3 mt-2 mb-1">
          <h1 className="display text-3xl font-semibold">{s.fund.name}</h1>
          <SfdrBadge c={s.fund.sfdr_classification} />
        </div>
        <p className="mono text-[11px] text-[var(--color-faint)]">{eur(s.total_value_eur)} · {s.positions} position{s.positions === 1 ? '' : 's'} · {s.fund.fund_type?.replace(/_/g, ' ')}</p>
      </div>

      {/* climate report */}
      {s.positions === 0
        ? <Card className="p-8 text-center text-[13px] text-[var(--color-mute)]">This fund has no holdings yet — onboard holdings by ISIN to compute its climate report and SFDR statement.</Card>
        : <div className="grid md:grid-cols-3 gap-3">
            <RiskCard title="Physical risk" d={s.physical} />
            <RiskCard title="Transition risk" d={s.transition} />
            <Card className="p-4">
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Emissions (PAI)</div>
              <div className="display text-[22px] leading-none">{num(s.pai?.pai?.pai_3_waci_tco2e_per_meur, 0)}</div>
              <div className="mono text-[10px] text-[var(--color-faint)] mt-1">WACI · tCO₂e / €m revenue</div>
              <div className="mt-3 space-y-1 text-[11.5px] text-[var(--color-mute)]">
                <div className="flex justify-between"><span>Financed emissions</span><span className="mono">{num(s.pai?.pai?.pai_1_financed_emissions_tco2e?.total, 0)} tCO₂e</span></div>
                <div className="flex justify-between"><span>Emissions coverage</span><span className="mono">{pct(s.pai?.emissions_coverage_pct)}</span></div>
                <div className="flex justify-between"><span>PCAF data quality</span><span className="mono">{s.pai?.pcaf_data_quality_score != null ? `${s.pai.pcaf_data_quality_score}/5` : '—'}</span></div>
              </div>
            </Card>
          </div>}

      {/* onboard holdings by ISIN — the data-in path */}
      <OnboardHoldings fundId={id} onDone={refreshAll} />

      {/* SFDR PAI statement */}
      {st && !st.error && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-3">
            <div>
              <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">SFDR PAI statement</div>
              <div className="mono text-[11px] text-[var(--color-faint)] mt-0.5">{st.summary?.reference_period ?? st.entity?.reference_period} · {cov ? `${cov.computed}/${cov.mandatory_indicators} indicators computed` : ''}</div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={() => download(`/v1/funds/${id}/sfdr-statement.xlsx`, `SFDR_PAI_${s.fund.name.replace(/\s+/g, '_')}.xlsx`).catch(() => alert('Could not download.'))}
                className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={13} /> xlsx</button>
              <button onClick={() => download(`/v1/funds/${id}/sfdr-statement.xbrl`, `SFDR_PAI_${s.fund.name.replace(/\s+/g, '_')}.xbrl`).catch(() => alert('Could not download.'))}
                className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={13} /> xbrl</button>
            </div>
          </div>

          {/* filing readiness */}
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 text-[12.5px]">
              {ready ? <CheckCircle2 size={15} className="text-[var(--color-good)]" /> : <AlertTriangle size={15} className="text-[var(--color-warn)]" />}
              <span className="text-[var(--color-ink)]">{ready ? 'Ready to file' : 'Not ready to file'}</span>
              {!ready && (st.filing_readiness?.missing?.length ?? 0) > 0 && <span className="text-[var(--color-mute)]">— {st.filing_readiness!.missing.join(' · ')}</span>}
            </div>
            <div className="flex items-center gap-3">
              {msg && <span className={`mono text-[10.5px] ${msg.ok ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`}>{msg.t}</span>}
              <Button variant="primary" onClick={fileStatement} disabled={busy || !ready}><FileCheck2 size={14} /> File statement</Button>
            </div>
          </div>

          {/* indicators table */}
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[9.5px] uppercase tracking-wide border-b border-[var(--color-line)]">
                <th className="text-left px-5 py-2 font-normal">#</th><th className="text-left py-2 font-normal">Indicator</th>
                <th className="text-right py-2 font-normal">Value</th><th className="text-right py-2 font-normal">Coverage</th><th className="text-right px-5 py-2 font-normal">Method</th>
              </tr></thead>
              <tbody>
                {inds.map((r, i) => { const m = METHOD[r.method] ?? { c: 'var(--color-faint)', label: r.method }; return (
                  <tr key={i} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="px-5 py-2 mono text-[var(--color-faint)]">{r.number}</td>
                    <td className="py-2"><span className="text-[var(--color-ink)]">{r.metric}</span>{r.unit ? <span className="text-[var(--color-faint)] mono text-[10px] ml-1.5">{r.unit}</span> : null}</td>
                    <td className="py-2 text-right mono tabular-nums text-[var(--color-mute)]">{renderIndVal(r.value, r.unit)}</td>
                    <td className="py-2 text-right mono text-[var(--color-faint)]">{r.coverage_pct != null ? pct(r.coverage_pct) : '—'}</td>
                    <td className="px-5 py-2 text-right"><span className="mono text-[10px]" style={{ color: m.c }}>{m.label}</span></td>
                  </tr>) })}
              </tbody>
            </table>
          </div>

          {/* taxonomy + narratives */}
          <div className="grid md:grid-cols-2 gap-0 border-t border-[var(--color-line)]">
            <div className="p-5 md:border-r border-[var(--color-line)]">
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">EU Taxonomy alignment</div>
              <div className="space-y-1 text-[12.5px] text-[var(--color-mute)]">
                <div className="flex justify-between"><span>Eligible</span><span className="mono">{pct(st.taxonomy?.taxonomy_eligible_pct)}</span></div>
                <div className="flex justify-between"><span>Aligned</span><span className="mono">{pct(st.taxonomy?.taxonomy_aligned_pct)}</span></div>
                <div className="flex justify-between"><span>Alignment coverage</span><span className="mono">{pct(st.taxonomy?.alignment_coverage_pct)}</span></div>
              </div>
              {st.taxonomy?.alignment_note && <div className="text-[10.5px] text-[var(--color-faint)] mt-2">{st.taxonomy.alignment_note}</div>}
            </div>
            <div className="p-5">
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Narratives</div>
              {(['policies', 'actions', 'engagement', 'standards'] as const).map(k => (
                <div key={k} className="text-[12px] mb-1.5">
                  <span className="capitalize text-[var(--color-mute)]">{k}: </span>
                  <span className={st.narratives?.[k] ? 'text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}>{st.narratives?.[k] ? st.narratives[k] : 'not set — required to file'}</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
      {st?.error && <Card className="p-6 text-[13px] text-[var(--color-mute)]">{st.error === 'fund has no positions to report on' ? 'No positions to report on yet.' : st.error}</Card>}

      {/* voluntary PAI selection */}
      {st && !st.error && <VoluntaryPai fundId={id} selected={st.additional_indicators?.selected ?? []} onDone={refreshAll} />}

      {/* holdings with issuer drill */}
      <FundPositions fundId={id} />

      {/* prior filings */}
      {(filings.data?.filings?.length ?? 0) > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Filing history</div>
          <div className="divide-y divide-[var(--color-line)]">
            {filings.data!.filings.map((f, i) => (
              <div key={i} className="px-5 py-3 flex items-center gap-3 text-[12.5px]">
                <Clock size={13} className="text-[var(--color-faint)]" />
                <span className="text-[var(--color-ink)]">SFDR {f.reference_year}</span>
                <span className="mono text-[10.5px] text-[var(--color-faint)]">filed {new Date(f.filed_at).toLocaleDateString('en-GB')} · {f.filed_by}</span>
                <span className="ml-auto mono text-[10px] px-1.5 py-0.5 rounded" style={{ color: '#34d399', background: '#34d39922' }}>{f.status}</span>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}

function RiskCard({ title, d }: { title: string; d?: { value_weighted_score: number | null; coverage_pct: number | null; value_at_high_plus_eur: number | null; pct_at_high_plus: number | null } }) {
  const s = d?.value_weighted_score
  const c = s == null ? 'var(--color-faint)' : s < 28 ? '#34d399' : s < 50 ? '#e8b24c' : s < 75 ? '#f0a860' : '#fb7185'
  return (
    <Card className="p-4">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">{title}</div>
      <div className="display text-[22px] leading-none" style={{ color: c }}>{s == null ? '—' : `${Math.round(s)}/100`}</div>
      <div className="mono text-[10px] text-[var(--color-faint)] mt-1">value-weighted score</div>
      <div className="mt-3 space-y-1 text-[11.5px] text-[var(--color-mute)]">
        <div className="flex justify-between"><span>At high+ risk</span><span className="mono">{eur(d?.value_at_high_plus_eur)}{d?.pct_at_high_plus != null ? ` · ${Math.round(d.pct_at_high_plus)}%` : ''}</span></div>
        <div className="flex justify-between"><span>Coverage</span><span className="mono">{pct(d?.coverage_pct)}</span></div>
      </div>
    </Card>
  )
}
