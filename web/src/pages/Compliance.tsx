import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, SectionHead } from '../components/ui'
import { hazardLabel } from '../lib/hazards'
import FilingCockpit from '../components/FilingCockpit'

// The financial-sector reporting workspace — the filing cockpit (requirements → eligibility & coverage →
// reporting basis → calendar → register → the final form, recon & submit in the drawer). The forward-looking
// scenario/horizon projections and the live analytical read of the book now live in Analytics/Portfolio, not
// here: a regulatory filing is a point-in-time disclosure. The insurer keeps its parametric-cover monitoring.

interface TriggerBlock { hazard_type: string; attachment_score: number; exhaustion_score: number; current_score: number | null; is_triggered: boolean; payout_pct: number; payout_eur: number }
interface TriggerRow { policy_id: string; policy_name: string; region?: string; sum_insured_eur?: number; trigger: TriggerBlock }
interface TriggersResp {
  rollup: { n_configured: number; n_triggered_now: number; total_payout_if_triggered_eur: number }
  configured: TriggerRow[]; triggered_now: TriggerRow[]
}

const TITLE: Record<string, { title: string; blurb: string }> = {
  bank:          { title: 'Reports & filings', blurb: 'The filings that need you, front and centre — everything else is a click away under Details.' },
  asset_manager: { title: 'Reports & filings', blurb: 'The filings that need you, front and centre — everything else is a click away under Details.' },
  reit:          { title: 'Reports & filings', blurb: 'The filings that need you, front and centre — everything else is a click away under Details.' },
  insurer:       { title: 'Reports & filings', blurb: 'Your climate filings and the live parametric-cover monitoring behind them.' },
}
const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
function col(l: number): [number, number, number] { return l < 28 ? [95, 185, 140] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59] }

export default function Compliance() {
  const { profile } = useAuth()
  const type = profile?.org?.type ?? ''
  const meta = TITLE[type]

  if (!meta) return (
    <div className="fadeup"><Eyebrow>Reports &amp; filings</Eyebrow>
      <Card className="p-10 mt-4 text-[13px] text-[var(--color-mute)]">This workspace has no financial reporting surface here.</Card>
    </div>
  )

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>{profile?.org?.name} · reporting</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">{meta.title}</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">{meta.blurb}</p>
      </div>

      {/* the filing workspace — requirements, eligibility & coverage, basis, calendar, register + the drawer
          (final form → recon → submit). Hidden for sectors with no frameworks wired. */}
      <FilingCockpit />

      {/* insurer: live parametric-cover monitoring stays — it's operational, not a live read of a filing */}
      {type === 'insurer' && <TriggersView />}
    </div>
  )
}

function TriggersView() {
  const q = useQuery({ queryKey: ['ins-triggers'], queryFn: () => api.get<TriggersResp>('/v1/insurance/triggers') })
  if (q.isLoading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading triggers…</Card>
  if (q.isError || !q.data) return null
  const r = q.data.rollup
  return (
    <div className="space-y-4">
      <SectionHead hint="live monitoring">Parametric cover</SectionHead>
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
      <SectionHead className="px-5 py-3 border-b border-[var(--color-line)]">{title}</SectionHead>
      <div className="divide-y divide-[var(--color-line)]">
        {rows.map(p => { const t = p.trigger; const [r, g, b] = col(t.current_score ?? 0); return (
          <div key={p.policy_id} className="px-5 py-3 flex items-center gap-4">
            <div className="min-w-0 flex-1">
              <div className="text-[14px] text-[var(--color-ink)] truncate">{p.policy_name}</div>
              <div className="mono text-[11px] text-[var(--color-faint)] truncate">{[p.region, hazardLabel(t.hazard_type)].filter(Boolean).join(' · ')} · band {Math.round(t.attachment_score)}–{Math.round(t.exhaustion_score)}</div>
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
