import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, ShieldAlert, History, Check, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, Button } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

// Act — the decision surface. The projection flags exposures that cross from below-High today into High+ by a
// chosen scenario/horizon; here an officer records what to do about each — reprice, engage, disclose, keep
// monitoring, or formally accept — with a rationale. Every call is written to the audit log. Sense → Score →
// Project → ACT.

const FIN = ['bank', 'insurer', 'asset_manager', 'reit']
const SCEN: [string, string][] = [['orderly_1_5c', 'Orderly 1.5°C'], ['disorderly_2c', 'Disorderly 2°C'], ['hot_house_3_5c', 'Hot-house 3.5°C']]
const HZ = ['2030', '2050', '2100']
const ACTIONS: { key: string; label: string; tone: string }[] = [
  { key: 'reprice', label: 'Reprice', tone: 'var(--scn-disorderly)' },
  { key: 'engage', label: 'Engage', tone: 'var(--scn-baseline)' },
  { key: 'disclose', label: 'Disclose', tone: 'var(--scn-orderly)' },
  { key: 'monitor', label: 'Monitor', tone: 'var(--color-mute)' },
  { key: 'accept', label: 'Accept', tone: 'var(--color-faint)' },
]
const actionMeta = (k?: string | null) => ACTIONS.find(a => a.key === k)

interface Decision { action: string; rationale: string | null; status: string; by: string | null; at: string }
interface Crossing { entity_id: string; entity_name: string; value_eur: number | null; country: string | null; region: string | null; driver: string; current_score: number | null; future_score: number | null; delta: number; decision: Decision | null }
interface LogRow { entity_name: string | null; scenario: string; horizon: string; action: string; rationale: string | null; status: string; by: string | null; at: string }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const scLabel = (k: string) => SCEN.find(s => s[0] === k)?.[1] ?? k

export default function Decisions() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const isFin = FIN.includes(profile?.org?.type ?? '')
  const canAct = (profile?.permissions ?? []).includes('approvals.create')
  const [scenario, setScenario] = useState('disorderly_2c')
  const [horizon, setHorizon] = useState('2050')

  const cq = useQuery({
    queryKey: ['decision-crossings', scenario, horizon],
    enabled: isFin,
    queryFn: () => api.get<{ n: number; at_risk_threshold: number; crossings: Crossing[] }>(`/v1/decisions/crossings?scenario=${scenario}&horizon=${horizon}`),
  })
  const lq = useQuery({ queryKey: ['decision-log'], enabled: isFin, queryFn: () => api.get<{ decisions: LogRow[] }>('/v1/decisions/log') })
  const refresh = () => { qc.invalidateQueries({ queryKey: ['decision-crossings'] }); qc.invalidateQueries({ queryKey: ['decision-log'] }) }

  if (!isFin) return (
    <div className="fadeup"><Eyebrow>Decisions</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">Forward-risk decisions are for financial books (bank / asset manager / insurer / REIT).</Card>
    </div>
  )

  const crossings = cq.data?.crossings ?? []
  const approved = crossings.filter(c => c.decision?.status === 'approved').length
  const pending = crossings.filter(c => c.decision?.status === 'proposed').length
  const exposed = crossings.reduce((s, c) => s + (c.value_eur ?? 0), 0)

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>{profile?.org?.name} · act</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Forward-risk decisions</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">Exposures that cross into <b>High+</b> risk by the chosen pathway — the projection’s “act by” list. Propose a decision on each; a second pair of eyes approves it (4-eyes), and an actionable one spins a card on the board.</p>
      </div>

      {/* controls */}
      <Card className="px-5 py-4">
        <div className="grid md:grid-cols-2 gap-x-8 gap-y-3">
          <Seg label="Warming pathway" options={SCEN} value={scenario} onChange={setScenario} />
          <Seg label="Cross by" options={HZ.map(h => [h, h] as [string, string])} value={horizon} onChange={setHorizon} />
        </div>
      </Card>

      {/* summary */}
      <div className="grid sm:grid-cols-3 gap-3">
        <Stat label="Exposures crossing" value={cq.isLoading ? '—' : String(crossings.length)} sub={`${scLabel(scenario)} · by ${horizon}`} />
        <Stat label="Value newly at risk" value={cq.isLoading ? '—' : eur(exposed)} sub="crosses the High line" tone="var(--color-bad)" />
        <Stat label="Decided" value={cq.isLoading ? '—' : `${approved} / ${crossings.length}`} sub={pending > 0 ? `${pending} pending 4-eyes` : 'approved (4-eyes)'} tone={approved === crossings.length && crossings.length > 0 ? 'var(--color-good)' : pending > 0 ? 'var(--color-warn)' : undefined} />
      </div>

      {/* crossings list */}
      <Card className="p-0 overflow-hidden">
        <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
          <ShieldAlert size={15} className="text-[var(--color-bad)]" />
          <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Exposures crossing into High+ · worst hazard vs the score-50 line</span>
        </div>
        {cq.isLoading ? <div className="px-5 py-8 text-[13px] text-[var(--color-faint)]">projecting the book…</div>
          : crossings.length === 0 ? <div className="px-5 py-8 text-[13px] text-[var(--color-faint)]">No exposures newly cross into High+ under this pathway by {horizon}. Nothing to act on.</div>
          : <div className="divide-y divide-[var(--color-line)]">
              {crossings.map(c => <CrossingRow key={c.entity_id} c={c} scenario={scenario} horizon={horizon} canAct={canAct} onDone={refresh} />)}
            </div>}
      </Card>

      {/* audit log */}
      {(lq.data?.decisions.length ?? 0) > 0 && (
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
            <History size={15} className="text-[var(--color-sky)]" />
            <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Decision log</span>
          </div>
          <div className="divide-y divide-[var(--color-line)]">
            {lq.data!.decisions.map((d, i) => {
              const m = actionMeta(d.action)
              return (
                <div key={i} className="px-5 py-2.5 flex items-center gap-3 text-[12.5px]">
                  <span className="mono text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0" style={{ color: m?.tone, background: `color-mix(in oklab, ${m?.tone} 15%, transparent)` }}>{m?.label ?? d.action}</span>
                  <span className="mono text-[9px] uppercase tracking-wide shrink-0" style={{ color: d.status === 'approved' ? 'var(--color-good)' : d.status === 'proposed' ? 'var(--color-warn)' : 'var(--color-faint)' }}>{d.status}</span>
                  <span className="text-[var(--color-ink)] truncate flex-1">{d.entity_name ?? '—'}{d.rationale ? <span className="text-[var(--color-faint)]"> · {d.rationale}</span> : ''}</span>
                  <span className="mono text-[10px] text-[var(--color-faint)] shrink-0">{scLabel(d.scenario)} · {d.horizon} · {d.by?.split('@')[0]} · {new Date(d.at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })}</span>
                </div>
              )
            })}
          </div>
        </Card>
      )}
    </div>
  )
}

function CrossingRow({ c, scenario, horizon, canAct, onDone }: { c: Crossing; scenario: string; horizon: string; canAct: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [action, setAction] = useState(c.decision?.action ?? '')
  const [rationale, setRationale] = useState(c.decision?.rationale ?? '')
  const [busy, setBusy] = useState(false)
  const dm = actionMeta(c.decision?.action)
  const proposed = c.decision?.status === 'proposed'
  const save = async () => {
    if (!action) return
    setBusy(true)
    try {
      await api.post('/v1/decisions', { entity_id: c.entity_id, entity_name: c.entity_name, scenario, horizon, action, rationale: rationale.trim() || undefined })
      setOpen(false); onDone()
    } catch (e) { alert(e instanceof ApiError ? e.message : 'Could not propose the decision.') }
    finally { setBusy(false) }
  }
  return (
    <div className="px-5 py-3">
      <div className="flex items-center gap-4">
        <div className="min-w-0 flex-1">
          <div className="text-[13.5px] text-[var(--color-ink)] truncate">{c.entity_name}</div>
          <div className="mono text-[10.5px] text-[var(--color-faint)]">{[c.region, c.country].filter(Boolean).join(', ') || '—'} · driver <span className="capitalize text-[var(--color-mute)]">{hazardLabel(c.driver)}</span></div>
        </div>
        {/* score migration */}
        <div className="hidden sm:flex items-center gap-1.5 mono text-[11.5px] shrink-0">
          <span className="text-[var(--color-mute)]">{c.current_score ?? '—'}</span>
          <ArrowRight size={12} className="text-[var(--color-faint)]" />
          <span className="text-[var(--color-bad)] font-medium">{c.future_score ?? '—'}</span>
          <span className="text-[var(--color-faint)]">(+{c.delta})</span>
        </div>
        <div className="mono text-[12.5px] tabular-nums text-[var(--color-ink)] w-20 text-right shrink-0">{eur(c.value_eur)}</div>
        <div className="w-32 flex justify-end shrink-0">
          {c.decision
            ? <button onClick={() => canAct && setOpen(o => !o)} title={proposed ? 'Proposed — awaiting a second approval' : `Approved · ${c.decision.by?.split('@')[0]}`}
                className="mono text-[9px] uppercase tracking-wide px-2 py-1 rounded inline-flex items-center gap-1"
                style={proposed ? { color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 15%, transparent)' } : { color: dm?.tone, background: `color-mix(in oklab, ${dm?.tone} 15%, transparent)` }}>
                {proposed ? <><Clock size={10} /> {dm?.label} · 4-eyes</> : <><Check size={11} /> {dm?.label ?? c.decision.action}</>}
              </button>
            : canAct
              ? <Button variant="ghost" onClick={() => setOpen(o => !o)}>Decide</Button>
              : <span className="mono text-[10px] text-[var(--color-faint)]">awaiting a decision</span>}
        </div>
      </div>

      {open && canAct && (
        <div className="mt-3 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-3 space-y-2.5">
          <div className="flex flex-wrap gap-1.5">
            {ACTIONS.map(a => (
              <button key={a.key} onClick={() => setAction(a.key)} className={`px-2.5 py-1.5 rounded-lg text-[12px] border transition ${action === a.key ? 'border-transparent text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}
                style={action === a.key ? { background: `color-mix(in oklab, ${a.tone} 16%, transparent)` } : undefined}>
                <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: a.tone }} />{a.label}</span>
              </button>
            ))}
          </div>
          <textarea value={rationale} onChange={e => setRationale(e.target.value)} rows={2} placeholder="Rationale (recorded in the audit log)…"
            className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)] resize-none" />
          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={save} disabled={busy || !action}><Check size={13} /> Propose decision</Button>
            <button onClick={() => setOpen(false)} className="text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Cancel</button>
            <span className="mono text-[9.5px] text-[var(--color-faint)] ml-auto">{c.decision ? `last: ${dm?.label} · ${c.decision.status}` : 'needs a second approval (4-eyes)'}</span>
          </div>
        </div>
      )}
    </div>
  )
}

function Seg({ label, options, value, onChange }: { label: string; options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div>
      <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-2">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map(([k, l]) => (
          <button key={k} onClick={() => onChange(k)} className={`px-2.5 py-1.5 rounded-lg text-[12px] border transition ${value === k ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{l}</button>
        ))}
      </div>
    </div>
  )
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub: string; tone?: string }) {
  return (
    <Card className="px-4 py-3.5">
      <div className="mono text-[10px] uppercase tracking-[0.14em] text-[var(--color-faint)]">{label}</div>
      <div className="display text-[26px] leading-none mt-2 tabular-nums" style={tone ? { color: tone } : undefined}>{value}</div>
      <div className="mono text-[9.5px] text-[var(--color-faint)] mt-1.5">{sub}</div>
    </Card>
  )
}
