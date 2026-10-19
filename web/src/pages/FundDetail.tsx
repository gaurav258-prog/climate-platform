import { useState } from 'react'
import { money } from '../lib/money'
import { useParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileCheck2, Flame, Thermometer, Factory, BarChart3, History } from 'lucide-react'
import { api, apiMessage, apiDetail, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead, PageHeader } from '../components/ui'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import { SfdrBadge } from './Funds'
import FundPositions from '../components/FundPositions'
import ShareClasses from '../components/ShareClasses'
import { OnboardHoldings, VoluntaryPai } from '../components/FundOnboard'
import SfdrDocument from '../components/SfdrDocument'
import MethodGap from '../components/MethodGap'
import { Meter, Ring, Stack, num, pct, TONE } from '../components/sfdr/visuals'
import { FUND_TYPE, METHOD, fmtDate, scoreTone } from '../components/sfdr/words'

// One fund's picture: its physical and transition climate risk, and its adverse-impact figures (the mandatory indicators
// and the EU Taxonomy share computed over the fund's holdings) — analytics, not a filing: the statement is the manager's
// (Funds page); a fund discloses how it considers adverse impacts in its product documents, below.

interface Base { currency: string; as_of: string; available?: boolean; total_value?: number; physical_value_at_risk?: number | null; transition_value_at_risk?: number | null }
const eur = (n?: number | null) => money(n, 'EUR')
// fund values in the fund's own base currency; the adverse-impact figures stay in euro as the Regulation defines them
const inBase = (eurValue: number | null | undefined, baseValue: number | undefined | null, b?: Base | null) =>
  b && b.currency !== 'EUR' && b.available !== false && baseValue != null ? money(baseValue, b.currency) : eur(eurValue)

type ScopeCov = { scope_1: number; scope_2: number; scope_3: number; total: number }
interface RiskBlock { value_weighted_score: number | null; coverage_pct: number | null; value_at_risk_eur: number | null; pct_at_risk: number | null }
interface Summary {
  fund: { fund_id: string; name: string; fund_type: string; sfdr_classification: string | null }
  total_value_eur: number; positions: number; base?: Base | null; physical?: RiskBlock; transition?: RiskBlock; gap?: string
  pai?: { pcaf_data_quality_score: number | null
    pai: { pai_3_waci_tco2e_per_meur: number | null; pai_3_coverage_pct?: number | null
      pai_1_financed_emissions_tco2e: { total: number | null } | null; pai_1_investee_emissions_tco2e?: { coverage_pct?: ScopeCov } } }
}
type IndVal = number | { scope_1?: number; scope_2?: number; scope_3?: number; total?: number } | null
interface Indicator { number: number | string; metric: string; unit: string; value: IndVal; coverage_pct: number | null; method: string }
interface Statement {
  error?: string; view?: { error?: Message; readiness: Message[]; needs: Record<string, Message>; taxonomy: { turnover: Message; capex: Message } | null }
  summary?: { reference_period: string; reference_year: number | null }
  filing_readiness?: { ready_to_file: boolean }
  filing_status?: 'filed' | 'draft_not_yet_filed'
  indicators?: Indicator[]; sovereign_indicators?: Indicator[]; real_estate_indicators?: Indicator[]
  taxonomy?: { taxonomy_eligible_pct?: number | null; taxonomy_aligned_turnover_pct?: number | null; turnover_alignment_coverage_pct?: number | null
    taxonomy_aligned_capex_pct?: number | null; capex_alignment_coverage_pct?: number | null }
  additional_indicators?: { selected?: string[] }
}
interface Filing { reference_year: number; filed_at: string; filed_by: string; status: string }

function figure(v: IndVal, unit: string): string {
  if (v == null) return '—'
  if (typeof v === 'number') return unit?.includes('%') ? pct(v) : num(v, 2)
  if (v.total != null) return num(v.total, 1)
  const parts = [v.scope_1, v.scope_2, v.scope_3].filter(x => x != null).map(x => num(x, 0))
  return parts.length ? parts.join(' / ') : '—'
}

export default function FundDetail() {
  const { id = '' } = useParams()
  const qc = useQueryClient()
  const sum = useQuery({ queryKey: ['fund', id], queryFn: () => api.get<Summary>(`/v1/funds/${id}`) })
  const stmt = useQuery({ queryKey: ['fund-sfdr', id], queryFn: () => api.get<Statement>(`/v1/funds/${id}/sfdr-statement`) })
  const filings = useQuery({ queryKey: ['fund-filings', id], queryFn: () => api.get<{ filings: Filing[] }>(`/v1/funds/${id}/sfdr-filings`) })
  const s = sum.data
  const st = stmt.data
  const [busy, setBusy] = useState(false)
  const refreshAll = () => { sum.refetch(); stmt.refetch(); qc.invalidateQueries({ queryKey: ['fund-positions', id] }); qc.invalidateQueries({ queryKey: ['funds'] }) }

  const keepYear = async () => {
    setBusy(true)
    try {
      const r = await api.post<{ msg: Message }>(`/v1/funds/${id}/sfdr-statement/file`, {})
      toast.success(r.msg.label); qc.invalidateQueries({ queryKey: ['fund-filings', id] }); stmt.refetch()
    } catch (e) { toast.error(apiMessage(e, 'Could not keep the year as a record.')) }
    finally { setBusy(false) }
  }

  if (sum.isLoading) return <div className="p-10 text-[13px] text-[var(--color-faint)]">Loading…</div>
  if (!s || !s.fund) return <div className="p-10"><MessageLine m={{ label: apiMessage(sum.error, 'Fund not found.'), detail: apiDetail(sum.error) }} className="text-[13px] text-[var(--color-bad)]" /></div>

  const inds = [...(st?.indicators ?? []), ...(st?.sovereign_indicators ?? []), ...(st?.real_estate_indicators ?? [])]
  const count = (m: string) => inds.filter(i => i.method === m).length
  const v = st?.view
  const scopeCov = s.pai?.pai?.pai_1_investee_emissions_tco2e?.coverage_pct
  const dq = s.pai?.pcaf_data_quality_score

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Asset management · fund"
        title={<span className="inline-flex items-center gap-3 flex-wrap">{s.fund.name}<SfdrBadge c={s.fund.sfdr_classification} /></span>}>
        <p className="text-[12.5px] text-[var(--color-faint)] mt-1">{inBase(s.total_value_eur, s.base?.total_value, s.base)} · {s.positions} holding{s.positions === 1 ? '' : 's'} · {FUND_TYPE[s.fund.fund_type] ?? 'Fund'}</p>
      </PageHeader>

      {s.gap && <MethodGap gap={s.gap} what="Fund climate report" />}
      {s.positions === 0
        ? <Card className="p-8 text-center text-[13px] text-[var(--color-mute)]">No holdings yet — add them below to compute the fund's climate risk and adverse-impact figures.</Card>
        : <div className="grid md:grid-cols-3 gap-3">
            <RiskCard title="Physical risk" icon={Thermometer} atRisk="Held at or above your at-risk level" d={s.physical} base={s.base} baseHigh={s.base?.physical_value_at_risk} />
            <RiskCard title="Transition risk" icon={Flame} atRisk="Value times your stated stranded share" d={s.transition} base={s.base} baseHigh={s.base?.transition_value_at_risk} />
            <Card className="p-4 space-y-3">
              <div className="flex items-center gap-2">
                <SectionHead icon={Factory}>Emissions</SectionHead>
                <InfoButton compact details={{ title: 'Emissions', sections: [
                  { heading: HEADING.shows, body: 'Carbon intensity: tonnes of CO₂e per million euro of revenue, weighted by value (WACI). Financed emissions: the fund\'s share of its investees\' emissions.' },
                  { heading: HEADING.read, body: 'The financed total and the carbon footprint count only investees stating all three scopes and their enterprise value; the intensity, those stating all three and their revenue.' },
                  { heading: HEADING.sources, body: 'The investees\' reported emissions, or your figures from the holdings upload. Data quality is the PCAF score, 1 (reported, verified) to 5 (estimated from sector averages).' }] }} />
              </div>
              <div>
                <div className="display text-[26px] leading-none tabular-nums">{num(s.pai?.pai?.pai_3_waci_tco2e_per_meur, 0)}</div>
                <div className="text-[11.5px] text-[var(--color-faint)] mt-1">t CO₂e per €m revenue</div>
              </div>
              <div className="space-y-1.5 text-[12px] text-[var(--color-mute)]">
                <div className="flex justify-between gap-2"><span>Financed</span><span className="tabular-nums">{num(s.pai?.pai?.pai_1_financed_emissions_tco2e?.total, 0)} t</span></div>
                {scopeCov && (['scope_1', 'scope_2', 'scope_3'] as const).map((k, i) => (
                  <div key={k} className="flex justify-between items-center gap-2"><span>Scope {i + 1} stated</span><Meter value={scopeCov[k]} width="w-20" /></div>))}
                <div className="flex justify-between items-center gap-2"><span>Data quality</span>
                  <span className="inline-flex items-center gap-0.5" title={dq != null ? `PCAF score ${num(dq, 1)} (1 best, 5 weakest)` : 'No score'}>
                    {[1, 2, 3, 4, 5].map(n => <span key={n} className="w-2.5 h-2.5 rounded-sm" style={{ background: dq != null && n <= Math.round(6 - dq) ? (dq <= 2 ? TONE.good : dq <= 3.5 ? TONE.warn : TONE.bad) : 'var(--color-panel-2)' }} />)}
                  </span></div>
              </div>
            </Card>
          </div>}

      <OnboardHoldings fundId={id} onDone={refreshAll} />

      {/* the fund's adverse-impact figures — analytics, not a filing */}
      {st && !st.error && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <SectionHead icon={BarChart3}>Adverse-impact figures</SectionHead>
              <InfoButton compact details={{ title: 'Adverse-impact figures', sections: [
                { heading: HEADING.shows, body: 'The mandatory adverse-impact indicators and the EU Taxonomy share, computed over this fund\'s holdings. These are analytics, not a filing.' },
                { heading: HEADING.read, body: 'The statement you file is the manager\'s, on the Funds page. A fund shows how it considers adverse impacts in its product documents.' },
                { heading: 'Legal basis', body: 'Delegated Regulation (EU) 2022/1288: Annex I, Table 1 (the indicators); Articles 5 to 10 (the manager\'s statement).' }] }} />
              <StatusChip tone="neutral" label={st.summary?.reference_year ? String(st.summary.reference_year) : 'No year yet'} />
              {st.filing_status === 'filed' ? <StatusChip tone="good" label="Kept as the year's record" /> : <StatusChip tone="neutral" label="Live" />}
            </div>
            <div className="flex items-center gap-3">
              <button onClick={() => download(`/v1/funds/${id}/sfdr-statement.xlsx`, `SFDR_PAI_${s.fund.name.replace(/\s+/g, '_')}.xlsx`).catch(() => toast.error('Could not download.'))}
                className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={13} /> Excel</button>
              <Button variant="primary" onClick={keepYear} disabled={busy || !st.filing_readiness?.ready_to_file}><FileCheck2 size={14} /> Keep year as record</Button>
            </div>
          </div>

          <div className="px-5 py-4 border-b border-[var(--color-line)] grid gap-4 md:grid-cols-[1fr_auto] items-center">
            <Stack parts={[
              { n: count('computed'), tone: TONE.good, label: 'computed' }, { n: count('partial'), tone: TONE.warn, label: 'partial' },
              { n: count('estimated'), tone: TONE.sky, label: 'estimated' }, { n: count('not_available'), tone: TONE.bad, label: 'not available' },
              { n: count('not_applicable'), tone: TONE.faint, label: 'do not apply' }]} />
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {(v?.readiness ?? []).map((m, i) => <MessageLine key={i} m={m} className="text-[12px] text-[var(--color-warn)]" />)}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px] min-w-[560px]">
              <thead><tr className="text-[11px] text-[var(--color-faint)] border-b border-[var(--color-line)]">
                <th className="text-left px-5 py-2 font-normal w-10">No.</th><th className="text-left py-2 font-normal">Indicator</th>
                <th className="text-right py-2 font-normal">Value</th><th className="text-left py-2 pl-6 font-normal">Coverage</th><th className="text-left px-5 py-2 font-normal">Status</th>
              </tr></thead>
              <tbody>
                {inds.map((r, i) => { const m = METHOD[r.method] ?? METHOD.not_available; const need = v?.needs[String(r.number)]; return (
                  <tr key={i} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="px-5 py-2 text-[var(--color-faint)] tabular-nums">{r.number}</td>
                    <td className="py-2 text-[var(--color-ink)]">{r.metric}<span className="text-[var(--color-faint)] text-[11px] ml-1.5">{r.unit}</span></td>
                    <td className="py-2 text-right tabular-nums text-[var(--color-mute)]">{figure(r.value, r.unit)}</td>
                    <td className="py-2 pl-6">{r.coverage_pct != null ? <Meter value={r.coverage_pct} width="w-16" /> : <span className="text-[var(--color-faint)]">—</span>}</td>
                    <td className="px-5 py-2"><span className="inline-flex items-center gap-1">
                      <StatusChip label={m.label} tone={r.method === 'computed' ? 'good' : r.method === 'partial' ? 'warn' : r.method === 'not_available' ? 'bad' : 'neutral'} />
                      {need && <InfoButton compact details={messageDetails(need)} />}</span></td>
                  </tr>) })}
              </tbody>
            </table>
          </div>

          {st.taxonomy && (
            <div className="px-5 py-4 border-t border-[var(--color-line)] space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-[var(--color-ink)]">EU Taxonomy</span>
                <StatusChip tone="neutral" label={`${pct(st.taxonomy.taxonomy_eligible_pct)} eligible`} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {([['Aligned by turnover', st.taxonomy.taxonomy_aligned_turnover_pct, st.taxonomy.turnover_alignment_coverage_pct, v?.taxonomy?.turnover],
                  ['Aligned by CapEx', st.taxonomy.taxonomy_aligned_capex_pct, st.taxonomy.capex_alignment_coverage_pct, v?.taxonomy?.capex]] as const).map(([name, aligned, cov, m]) => (
                  <div key={name} className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2 text-[12.5px]">
                      <span className="text-[var(--color-ink)] inline-flex items-center gap-1">{name}{m && <InfoButton compact details={messageDetails(m)} />}</span>
                      <span className="display text-[20px] tabular-nums">{pct(aligned)}</span>
                    </div>
                    <div className="flex items-center justify-between text-[11.5px] text-[var(--color-faint)]"><span>Investees reporting it</span><Meter value={cov} width="w-20" /></div>
                  </div>))}
              </div>
            </div>)}
        </Card>
      )}
      {v?.error && <Card className="p-6"><MessageLine m={v.error} className="text-[13px] text-[var(--color-mute)]" /></Card>}

      {st && !st.error && <VoluntaryPai fundId={id} selected={st.additional_indicators?.selected ?? []} onDone={refreshAll} />}

      {(s.fund.sfdr_classification === 'article_8' || s.fund.sfdr_classification === 'article_9') && (
        <SfdrDocument fundId={id} fundName={s.fund.name} />
      )}

      <ShareClasses fundId={id} />
      <FundPositions fundId={id} />

      {(filings.data?.filings?.length ?? 0) > 0 && (
        <Card className="p-4">
          <SectionHead icon={History} className="mb-3">Years kept as records</SectionHead>
          <div className="flex flex-wrap gap-2">
            {filings.data!.filings.map(f => (
              <span key={f.reference_year} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line)] px-3 py-1.5 text-[12.5px]">
                <span className="text-[var(--color-ink)] tabular-nums">{f.reference_year}</span>
                <InfoButton compact details={{ title: `${f.reference_year} record`, sections: [{ heading: 'Kept', body: `${fmtDate(f.filed_at)} by ${f.filed_by}` }] }} />
              </span>))}
          </div>
        </Card>
      )}
    </div>
  )
}

function RiskCard({ title, icon, atRisk, d, base, baseHigh }: { title: string; icon: typeof Flame; atRisk: string; d?: RiskBlock; base?: Base | null; baseHigh?: number | null }) {
  const s = d?.value_weighted_score
  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <SectionHead icon={icon}>{title}</SectionHead>
        <InfoButton compact details={{ title, sections: [
          { heading: HEADING.shows, body: 'The fund\'s score out of 100, weighted by the value of each holding, and the value at risk.' },
          { heading: HEADING.read, body: `Value at risk: ${atRisk.toLowerCase()}. Coverage is the share of the fund's value with a score.` }] }} />
      </div>
      <div className="flex items-center gap-4">
        <Ring value={s ?? 0} tone={scoreTone(s)} size={60}>{s == null ? '—' : Math.round(s)}</Ring>
        <div className="space-y-1.5 text-[12px] text-[var(--color-mute)] min-w-0">
          <div>Value at risk</div>
          <div className="text-[15px] text-[var(--color-ink)] tabular-nums">{d?.value_at_risk_eur == null ? 'Not stated' : inBase(d.value_at_risk_eur, baseHigh, base)}
            {d?.pct_at_risk != null && <span className="text-[12px] text-[var(--color-faint)]"> · {pct(d.pct_at_risk)}</span>}</div>
        </div>
      </div>
      <div className="flex items-center justify-between text-[12px] text-[var(--color-mute)]"><span>Coverage</span><Meter value={d?.coverage_pct} width="w-20" /></div>
    </Card>
  )
}
