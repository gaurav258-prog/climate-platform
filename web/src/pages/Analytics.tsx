import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, ArrowDownRight, Minus } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

// Analytics — the forward-looking read that does NOT belong on a point-in-time filing: how the book's climate
// exposure changes as you move the two parameters (climate scenario × horizon). Pick a BASE and a COMPARE
// setting and see every figure side-by-side with the delta. This is where the 2030/2050/2100 and 2°C
// projections live now. Every number is the projected book from the golden source — nothing invented.

interface HazardBlock { exposed_value_eur: number; n_exposed: number; max_score: number }
interface TaxBlock { count: number; value_eur: number }
interface DisclosureResp {
  by_hazard: Record<string, HazardBlock>
  taxonomy: Record<string, TaxBlock>
  financed_emissions_tco2e?: { scope1: number; scope2: number; scope3: number }
}

const PREFIX: Record<string, string> = { bank: 'bank', asset_manager: 'assetmgmt', reit: 'realestate' }
const SCENARIOS: [string, string][] = [['baseline', 'Today'], ['orderly_1_5c', 'Orderly 1.5°C'], ['disorderly_2c', 'Disorderly 2°C'], ['hot_house_3_5c', 'Hot-house 3.5°C']]
const HORIZONS: [string, string][] = [['current', 'Now'], ['2030', '2030'], ['2050', '2050'], ['2100', '2100']]
const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const num = (n?: number | null) => n == null ? '—' : Math.round(n).toLocaleString('en-GB')

export default function Analytics() {
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const prefix = PREFIX[type]
  const [base, setBase] = useState({ scenario: 'baseline', horizon: 'current' })
  const [cmp, setCmp] = useState({ scenario: 'disorderly_2c', horizon: '2050' })

  const bq = useQuery({ queryKey: ['analytics', prefix, base], enabled: !!prefix, queryFn: () => api.get<DisclosureResp>(`/v1/${prefix}/disclosure?scenario=${base.scenario}&horizon=${base.horizon}`) })
  const cq = useQuery({ queryKey: ['analytics', prefix, cmp], enabled: !!prefix, queryFn: () => api.get<DisclosureResp>(`/v1/${prefix}/disclosure?scenario=${cmp.scenario}&horizon=${cmp.horizon}`) })

  if (!prefix) return (
    <div className="fadeup"><Eyebrow>Analytics</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">Forward-looking exposure analytics are available for the loan / holdings / property book. This workspace has no such book here.</Card>
    </div>
  )

  const b = bq.data, c = cq.data
  const hazTotB = b ? Object.values(b.by_hazard).reduce((s, v) => s + (v.exposed_value_eur || 0), 0) : 0
  const hazTotC = c ? Object.values(c.by_hazard).reduce((s, v) => s + (v.exposed_value_eur || 0), 0) : 0
  const hazKeys = useMemo(() => {
    const keys = new Set([...Object.keys(b?.by_hazard ?? {}), ...Object.keys(c?.by_hazard ?? {})])
    return [...keys].sort((x, y) => ((c?.by_hazard[y]?.exposed_value_eur ?? b?.by_hazard[y]?.exposed_value_eur ?? 0) - (c?.by_hazard[x]?.exposed_value_eur ?? b?.by_hazard[x]?.exposed_value_eur ?? 0)))
  }, [b, c])

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>{profile?.org?.name} · analytics</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Forward-looking analytics</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">How the book's climate exposure changes as you move the parameters — climate scenario and time horizon. Pick two settings and compare figure by figure.</p>
      </div>

      {/* the two parameter columns */}
      <div className="grid md:grid-cols-2 gap-4">
        <ParamCard title="Base" tone="var(--color-mute)" value={base} onChange={setBase} loading={bq.isLoading} />
        <ParamCard title="Compare" tone="var(--color-sky)" value={cmp} onChange={setCmp} loading={cq.isLoading} />
      </div>

      {(bq.isError || cq.isError) && <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the projection — reload, or sign in again.</div>}

      {/* headline: total value exposed at High+ */}
      <div className="grid sm:grid-cols-3 gap-3">
        <BigDelta label="Value exposed at High+" base={hazTotB} cmp={hazTotC} fmt={eur} worseUp />
        <BigDelta label="Taxonomy-eligible value" base={b?.taxonomy?.eligible?.value_eur} cmp={c?.taxonomy?.eligible?.value_eur} fmt={eur} />
        {b?.financed_emissions_tco2e && (
          <BigDelta label="Total financed emissions" base={sumEm(b)} cmp={sumEm(c)} fmt={num} unit="tCO₂e" worseUp />
        )}
      </div>

      {/* exposure by hazard */}
      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-3 border-b border-[var(--color-line)] mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Exposure by hazard · value at High+</div>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead><tr className="text-left">
              <th className="px-5 py-2 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium">Hazard</th>
              <th className="px-5 py-2 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium text-right">Base</th>
              <th className="px-5 py-2 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium text-right">Compare</th>
              <th className="px-5 py-2 mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] font-medium text-right">Change</th>
            </tr></thead>
            <tbody>
              {hazKeys.map(h => {
                const bv = b?.by_hazard[h]?.exposed_value_eur ?? 0
                const cv = c?.by_hazard[h]?.exposed_value_eur ?? 0
                if (bv === 0 && cv === 0) return null
                return (
                  <tr key={h} className="border-t border-[var(--color-line)]">
                    <td className="px-5 py-2.5 text-[var(--color-ink)] capitalize">{hazardLabel(h)}</td>
                    <td className="px-5 py-2.5 text-right mono tabular-nums text-[var(--color-mute)]">{eur(bv)}</td>
                    <td className="px-5 py-2.5 text-right mono tabular-nums text-[var(--color-ink)]">{eur(cv)}</td>
                    <td className="px-5 py-2.5 text-right"><Delta base={bv} cmp={cv} fmt={eur} worseUp /></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* EU-Taxonomy eligibility change */}
      {b?.taxonomy && (
        <Card className="p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-[var(--color-line)] mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">EU-Taxonomy eligibility</div>
          <div className="divide-y divide-[var(--color-line)]">
            {(['eligible', 'not_eligible'] as const).map(k => (
              <div key={k} className="px-5 py-3 flex items-center gap-4">
                <div className="flex-1 text-[13px] text-[var(--color-ink)]">{k === 'eligible' ? 'Taxonomy-eligible' : 'Not eligible'}</div>
                <div className="w-28 text-right mono text-[12.5px] text-[var(--color-mute)]">{eur(b.taxonomy[k]?.value_eur)}</div>
                <div className="w-28 text-right mono text-[12.5px] text-[var(--color-ink)]">{eur(c?.taxonomy[k]?.value_eur)}</div>
                <div className="w-28 text-right"><Delta base={b.taxonomy[k]?.value_eur ?? 0} cmp={c?.taxonomy[k]?.value_eur ?? 0} fmt={eur} /></div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="mono text-[10px] text-[var(--color-faint)] leading-relaxed">Projections apply a parametric warming shift to the climate-physical hazard scores at the chosen scenario / horizon. They exclude non-climate drivers (policy, fuel, labour). The <span className="text-[var(--color-mute)]">Base</span> figures at Today / Now are the same current-basis figures a filing freezes.</div>
    </div>
  )
}

const sumEm = (d?: DisclosureResp) => d?.financed_emissions_tco2e ? d.financed_emissions_tco2e.scope1 + d.financed_emissions_tco2e.scope2 + d.financed_emissions_tco2e.scope3 : undefined

function ParamCard({ title, tone, value, onChange, loading }: { title: string; tone: string; value: { scenario: string; horizon: string }; onChange: (v: { scenario: string; horizon: string }) => void; loading: boolean }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="mono text-[10px] uppercase tracking-widest" style={{ color: tone }}>{title}</span>
        {loading && <span className="mono text-[10px] text-[var(--color-faint)]">loading…</span>}
      </div>
      <div className="space-y-2.5">
        <Seg label="Scenario" options={SCENARIOS} val={value.scenario} onPick={v => onChange({ ...value, scenario: v })} />
        <Seg label="Horizon" options={HORIZONS} val={value.horizon} onPick={v => onChange({ ...value, horizon: v })} />
      </div>
    </Card>
  )
}

function Seg({ label, options, val, onPick }: { label: string; options: [string, string][]; val: string; onPick: (v: string) => void }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-16 text-[11.5px] text-[var(--color-mute)]">{label}</span>
      <div className="flex flex-wrap gap-1">
        {options.map(([k, lbl]) => (
          <button key={k} onClick={() => onPick(k)} className={`px-2.5 py-1 rounded-md text-[11.5px] transition ${val === k ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)]' : 'border border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{lbl}</button>
        ))}
      </div>
    </div>
  )
}

// direction-aware delta chip. worseUp = an increase is bad (more exposure / more emissions) → red.
function tone(base: number, cmp: number, worseUp: boolean): string {
  if (cmp === base) return 'var(--color-mute)'
  const up = cmp > base
  return (up === worseUp) ? 'var(--color-bad)' : 'var(--color-good)'
}
function Delta({ base, cmp, fmt, worseUp = false }: { base: number; cmp: number; fmt: (n?: number | null) => string; worseUp?: boolean }) {
  const d = cmp - base
  const pct = base ? (d / base) * 100 : null
  const t = tone(base, cmp, worseUp)
  const Icon = d > 0 ? ArrowUpRight : d < 0 ? ArrowDownRight : Minus
  return (
    <span className="inline-flex items-center gap-1 mono text-[12px] tabular-nums" style={{ color: t }}>
      <Icon size={13} />{d === 0 ? '—' : `${d > 0 ? '+' : '−'}${fmt(Math.abs(d))}`}{pct != null && d !== 0 && <span className="text-[10.5px]">({d > 0 ? '+' : '−'}{Math.abs(pct).toFixed(0)}%)</span>}
    </span>
  )
}

function BigDelta({ label, base, cmp, fmt, unit, worseUp = false }: { label: string; base?: number; cmp?: number; fmt: (n?: number | null) => string; unit?: string; worseUp?: boolean }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">{label}</div>
      <div className="display text-[26px] leading-none mt-2">{fmt(cmp)}{unit && <span className="text-[13px] text-[var(--color-faint)] ml-1">{unit}</span>}</div>
      <div className="mt-2 flex items-center justify-between">
        <span className="mono text-[10.5px] text-[var(--color-faint)]">base {fmt(base)}</span>
        {base != null && cmp != null && <Delta base={base} cmp={cmp} fmt={fmt} worseUp={worseUp} />}
      </div>
    </Card>
  )
}
