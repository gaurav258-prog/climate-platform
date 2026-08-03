import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { api, download } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'
import FilingCockpit from '../components/FilingCockpit'

// The financial-sector compliance surface behind the globe — the regulatory read of the book. Sector-
// adaptive: bank / asset-manager / REIT show the physical-risk-by-hazard + EU-Taxonomy disclosure the
// /disclosure endpoint assembles (bank adds financed emissions); the insurer shows its parametric-trigger
// monitoring. Every number is the real projected book — nothing invented, "—" where absent.

interface HazardBlock { exposed_value_eur: number; n_exposed: number; max_score: number; model_version?: string; scored_at?: string }
interface TaxBlock { count: number; value_eur: number }
interface DisclosureResp {
  scenario: string; horizon: string
  by_hazard: Record<string, HazardBlock>
  taxonomy: Record<string, TaxBlock>
  financed_emissions_tco2e?: { scope1: number; scope2: number; scope3: number }
}
interface TriggerBlock { hazard_type: string; attachment_score: number; exhaustion_score: number; current_score: number | null; is_triggered: boolean; payout_pct: number; payout_eur: number }
interface TriggerRow { policy_id: string; policy_name: string; region?: string; sum_insured_eur?: number; trigger: TriggerBlock }
interface TriggersResp {
  rollup: { n_configured: number; n_triggered_now: number; total_payout_if_triggered_eur: number }
  configured: TriggerRow[]; triggered_now: TriggerRow[]
}

const CFG: Record<string, { mode: 'disclosure' | 'triggers'; prefix: string; title: string; blurb: string; emissions?: boolean; xlsx?: boolean }> = {
  bank:          { mode: 'disclosure', prefix: 'bank',       title: 'TCFD · EU Taxonomy', blurb: 'Physical-risk exposure of the loan book by hazard, EU-Taxonomy eligibility and financed emissions — the TCFD / EU-Taxonomy disclosure assembled from the projected book.', emissions: true, xlsx: true },
  asset_manager: { mode: 'disclosure', prefix: 'assetmgmt',  title: 'Physical-risk exposure · EU Taxonomy', blurb: 'Physical-risk exposure of the holdings by hazard and EU-Taxonomy eligibility, from the projected book.' },
  reit:          { mode: 'disclosure', prefix: 'realestate', title: 'Physical-risk exposure · EU Taxonomy', blurb: 'Physical-risk exposure of the property book by hazard and EU-Taxonomy eligibility, from the projected book.' },
  insurer:       { mode: 'triggers',   prefix: 'insurance',  title: 'Parametric triggers', blurb: 'Parametric cover monitoring — configured triggers and any that have breached now, with the payout on the line.' },
}

const HORIZONS = ['current', '2030', '2050', '2100'] as const
const SCENARIOS: [string, string][] = [['baseline', 'Today'], ['disorderly_2c', 'Disorderly 2°C']]
const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const num = (n?: number | null) => n == null ? '—' : Math.round(n).toLocaleString('en-GB')
function col(l: number): [number, number, number] { return l < 28 ? [95, 185, 140] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59] }

export default function Compliance() {
  const { profile } = useAuth()
  const cfg = CFG[profile?.org?.type ?? '']
  const [scenario, setScenario] = useState('baseline')
  const [horizon, setHorizon] = useState<string>('current')

  if (!cfg) return (
    <div className="fadeup"><Eyebrow>Compliance</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">This workspace has no financial compliance surface here.</Card>
    </div>
  )

  return (
    <div className="fadeup space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>{profile?.org?.name} · compliance</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">{cfg.title}</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">{cfg.blurb}</p>
        </div>
        {cfg.mode === 'disclosure' && (
          <div className="flex flex-col gap-2 items-end">
            <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
              {SCENARIOS.map(([k, lbl]) => <button key={k} onClick={() => setScenario(k)} className={`px-3 py-1.5 rounded-md text-[12px] transition ${scenario === k ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>)}
            </div>
            <div className="flex gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
              {HORIZONS.map(h => <button key={h} onClick={() => setHorizon(h)} className={`px-3 py-1.5 rounded-md text-[12px] transition ${horizon === h ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{h === 'current' ? 'Now' : h}</button>)}
            </div>
          </div>
        )}
      </div>

      {/* the reporting cockpit — filing calendar, register and lifecycle (hidden for sectors with no
          frameworks wired yet). Sits above the live read of the book, which is its underlying data. */}
      <FilingCockpit />

      <div className="pt-2">
        <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)] mb-3">Live read of the book · the data behind a new filing</div>
        {cfg.mode === 'disclosure'
          ? <DisclosureView prefix={cfg.prefix} scenario={scenario} horizon={horizon} emissions={!!cfg.emissions} xlsx={!!cfg.xlsx} />
          : <TriggersView />}
      </div>
    </div>
  )
}

function DisclosureView({ prefix, scenario, horizon, emissions, xlsx }: { prefix: string; scenario: string; horizon: string; emissions: boolean; xlsx: boolean }) {
  const q = useQuery({ queryKey: ['fin-disclosure', prefix, scenario, horizon], queryFn: () => api.get<DisclosureResp>(`/v1/${prefix}/disclosure?scenario=${scenario}&horizon=${horizon}`) })
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading the disclosure…</Card>
  if (q.isError || !q.data) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the disclosure — reload, or sign in again.</div>

  const hazards = Object.entries(q.data.by_hazard).sort((a, b) => b[1].exposed_value_eur - a[1].exposed_value_eur)
  const tax = q.data.taxonomy
  const em = q.data.financed_emissions_tco2e

  return (
    <div className="space-y-6">
      {/* physical risk by hazard */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]">
          <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Physical risk by hazard · value exposed at High+</div>
          {xlsx && <button className="inline-flex items-center gap-1.5 mono text-[11px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"
            onClick={() => download(`/v1/${prefix}/disclosure.xlsx?scenario=${scenario}&horizon=${horizon}`, `${prefix}-disclosure.xlsx`).catch(() => alert('Could not download the export.'))}><Download size={13} /> Export .xlsx</button>}
        </div>
        <div className="divide-y divide-[var(--color-line)]">
          {hazards.map(([hz, b]) => { const [r, g, bl] = col(b.max_score); return (
            <div key={hz} className="px-5 py-3 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <div className="text-[14px] text-[var(--color-ink)] capitalize">{hz.replace(/_/g, ' ')}</div>
                <div className="mono text-[11px] text-[var(--color-faint)]">{b.n_exposed} exposed{b.model_version ? ` · ${b.model_version}` : ''}</div>
              </div>
              <div className="mono text-[13px] tabular-nums text-[var(--color-mute)] w-28 text-right">{eur(b.exposed_value_eur)}</div>
              <div className="w-24 text-right"><span className="inline-flex items-center gap-1.5 mono text-[12px]" style={{ color: `rgb(${r},${g},${bl})` }}><span className="w-1.5 h-1.5 rounded-full" style={{ background: `rgb(${r},${g},${bl})` }} />{Math.round(b.max_score)}/100</span></div>
            </div>) })}
        </div>
      </Card>

      <div className="grid md:grid-cols-2 gap-6">
        {/* EU taxonomy */}
        <Card className="p-5">
          <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)] mb-3">EU Taxonomy eligibility</div>
          <div className="space-y-3">
            {(['eligible', 'not_eligible'] as const).map(k => tax[k] && (
              <div key={k} className="flex items-center justify-between">
                <div className="text-[14px] text-[var(--color-ink)] capitalize">{k.replace('_', '-')}</div>
                <div className="text-right">
                  <div className="mono text-[14px] tabular-nums">{eur(tax[k].value_eur)}</div>
                  <div className="mono text-[11px] text-[var(--color-faint)]">{tax[k].count} position{tax[k].count !== 1 ? 's' : ''}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-4 leading-relaxed">Eligibility only — a full aligned % needs DNSH + minimum-safeguards + financial tagging from your books.</div>
        </Card>

        {/* financed emissions (bank) */}
        {emissions && em && (
          <Card className="p-5">
            <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)] mb-3">Financed emissions · tCO₂e</div>
            <div className="space-y-2.5">
              {([['scope1', 'Scope 1'], ['scope2', 'Scope 2'], ['scope3', 'Scope 3']] as const).map(([k, lbl]) => (
                <div key={k} className="flex items-center justify-between">
                  <div className="text-[14px] text-[var(--color-mute)]">{lbl}</div>
                  <div className="mono text-[14px] tabular-nums">{num(em[k])}</div>
                </div>
              ))}
              <div className="flex items-center justify-between border-t border-[var(--color-line)] pt-2.5 mt-1">
                <div className="text-[14px] text-[var(--color-ink)]">Total</div>
                <div className="mono text-[15px] tabular-nums text-[var(--color-ink)]">{num(em.scope1 + em.scope2 + em.scope3)}</div>
              </div>
            </div>
            <div className="mono text-[10.5px] text-[var(--color-faint)] mt-4 leading-relaxed">PCAF attribution over the financed book; scope-3 is the estimated upstream/downstream tail.</div>
          </Card>
        )}
      </div>
    </div>
  )
}

function TriggersView() {
  const q = useQuery({ queryKey: ['ins-triggers'], queryFn: () => api.get<TriggersResp>('/v1/insurance/triggers') })
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading triggers…</Card>
  if (q.isError || !q.data) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load triggers — reload, or sign in again.</div>
  const r = q.data.rollup
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-3">
        <Kpi label="configured triggers" value={String(r.n_configured)} />
        <Kpi label="breached now" value={String(r.n_triggered_now)} tone={r.n_triggered_now > 0 ? '#E9744A' : undefined} />
        <Kpi label="payout if breached" value={eur(r.total_payout_if_triggered_eur)} />
      </div>
      {q.data.configured.length === 0
        ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">No parametric triggers configured yet. Configure index-based cover on a policy to monitor breaches here.</Card>
        : <div className="space-y-6">
            {q.data.triggered_now.length > 0 && <TriggerTable title="Breached now · payout on the line" rows={q.data.triggered_now} breached />}
            {(() => { const armed = q.data.configured.filter(t => !t.trigger.is_triggered); return armed.length > 0
              ? <TriggerTable title="Armed · monitoring" rows={armed} /> : null })()}
          </div>}
    </div>
  )
}

function TriggerTable({ title, rows, breached }: { title: string; rows: TriggerRow[]; breached?: boolean }) {
  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">{title}</div>
      <div className="divide-y divide-[var(--color-line)]">
        {rows.map(p => { const t = p.trigger; const [r, g, b] = col(t.current_score ?? 0); return (
          <div key={p.policy_id} className="px-5 py-3 flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="text-[14px] text-[var(--color-ink)] truncate">{p.policy_name}</div>
              <div className="mono text-[11px] text-[var(--color-faint)] truncate">{[p.region, t.hazard_type.replace(/_/g, ' ')].filter(Boolean).join(' · ')} · band {Math.round(t.attachment_score)}–{Math.round(t.exhaustion_score)}</div>
            </div>
            <div className="w-20 text-right"><span className="mono text-[12px]" style={{ color: `rgb(${r},${g},${b})` }}>{t.current_score != null ? `${Math.round(t.current_score)}/100` : '—'}</span></div>
            {breached
              ? <div className="w-32 text-right">
                  <div className="mono text-[13px] tabular-nums text-[var(--color-bad)]">{eur(t.payout_eur)}</div>
                  <div className="mono text-[10.5px] text-[var(--color-faint)]">{t.payout_pct}% payout</div>
                </div>
              : <div className="w-32 text-right mono text-[11.5px] text-[var(--color-faint)]">{Math.max(0, Math.round(t.attachment_score - (t.current_score ?? 0)))} pts to attach</div>}
          </div>) })}
      </div>
    </Card>
  )
}

function Kpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="display text-[26px] leading-none" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="mono text-[10.5px] tracking-[0.14em] uppercase text-[var(--color-faint)] mt-2">{label}</div>
    </Card>
  )
}
