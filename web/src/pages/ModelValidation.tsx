import { useQuery } from '@tanstack/react-query'
import { FlaskConical, CheckCircle2, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'

// Model validation — the credibility layer. Tests Tellumen's own hazard scores against the observed event
// catalogues it holds (seismic, storm): do higher-scored locations actually carry more observed near-field
// events? Reports a per-band table + a Spearman discrimination metric + an honest verdict. In-sample
// consistency (faithfulness), not out-of-sample prediction — stated plainly, and weak results shown as weak.

interface Band { band: string; n_cells: number; mean_events: number | null; pct_with_event: number | null }
interface Peril {
  available: boolean; peril: string; label: string; near_field_km: number
  n_cells_scored: number; n_events_observed: number; observed_window_years: number
  pct_cells_with_event: number; spearman: number | null; auc: number | null
  monotonic: boolean | null; passed: boolean; bands: Band[]; verdict: string; note: string
}
interface Resp { perils: Peril[] }

const BAND_COLOR: Record<string, string> = { VH: '#D23B3B', H: '#E8744A', M: '#E8B24C', L: '#7BBF8F' }
const num = (n: number) => n.toLocaleString('en-US')

function PerilCard({ p }: { p: Peril }) {
  if (!p.available) return null
  const maxMean = Math.max(...p.bands.map(b => b.mean_events ?? 0), 0.01)
  const ok = p.passed
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="display text-lg font-semibold text-[var(--color-ink)] capitalize">{p.peril}</span>
            <span className="mono text-[10px] text-[var(--color-faint)]">{p.label}</span>
          </div>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-0.5">
            {num(p.n_cells_scored)} scored cells · {num(p.n_events_observed)} observed events · {p.observed_window_years}-yr window · near field {p.near_field_km}km
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 mono text-[11px] font-semibold"
          style={{ background: ok ? '#7BBF8F22' : '#E8B24C22', color: ok ? '#4FA46E' : '#C68A1E' }}>
          {ok ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{ok ? 'Consistent' : 'Review'}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-4 mb-4">
        <div><div className="display text-[22px] font-semibold tabular-nums" style={{ color: (p.spearman ?? 0) >= 0.5 ? '#4FA46E' : (p.spearman ?? 0) >= 0.3 ? '#C68A1E' : '#D23B3B' }}>{p.spearman?.toFixed(2) ?? '—'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">Spearman ρ (score↔events)</div></div>
        <div><div className="display text-[22px] font-semibold tabular-nums text-[var(--color-ink)]">{p.auc?.toFixed(2) ?? '—'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">AUC (any event)</div></div>
        <div><div className="display text-[22px] font-semibold tabular-nums text-[var(--color-ink)]">{p.monotonic ? 'Yes' : 'No'}</div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mt-0.5">Monotonic by band</div></div>
      </div>

      {/* mean observed events by score band */}
      <div className="space-y-1.5">
        {p.bands.map(b => (
          <div key={b.band} className="flex items-center gap-2 text-[12px]">
            <span className="mono w-6 font-semibold" style={{ color: BAND_COLOR[b.band] }}>{b.band}</span>
            <div className="flex-1 h-4 rounded bg-[var(--color-panel-2)] overflow-hidden">
              <div className="h-full rounded" style={{ width: `${Math.max(1.5, 100 * (b.mean_events ?? 0) / maxMean)}%`, background: BAND_COLOR[b.band], opacity: 0.85 }} />
            </div>
            <span className="mono text-[10.5px] text-[var(--color-mute)] tabular-nums w-40 text-right">
              {b.mean_events ?? '—'} events/cell · {b.pct_with_event ?? '—'}% hit · {num(b.n_cells)} cells
            </span>
          </div>
        ))}
      </div>

      <p className="text-[12px] mt-3.5" style={{ color: ok ? 'var(--color-mute)' : '#C68A1E' }}>{p.verdict}</p>
    </Card>
  )
}

export default function ModelValidation() {
  const q = useQuery({ queryKey: ['model-validation'], queryFn: () => api.get<Resp>('/v1/realized-exposure/model-validation') })
  const d = q.data
  const note = d?.perils?.[0]?.note

  return (
    <div className="fadeup space-y-6">
      <div>
        <Eyebrow>Assess · model validation</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Score vs observed record</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          The credibility check a model-validation team or supervisor asks for: don't just publish a score — show it is consistent with what actually happened. For the perils we hold a real catalogue for, do higher-scored locations carry more observed events?
        </p>
      </div>

      {q.isLoading && <Card className="p-5 text-[13px] text-[var(--color-mute)]">Running the backtest…</Card>}

      <div className="flex items-center gap-2">
        <FlaskConical size={15} className="text-[var(--color-sky)]" />
        <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Catalogued perils · seismic, storm</span>
      </div>

      {d?.perils?.map(p => <PerilCard key={p.peril} p={p} />)}

      {note && (
        <Card className="p-4 bg-[var(--color-panel-2)]">
          <div className="mono text-[9px] uppercase tracking-[0.16em] text-[var(--color-faint)] mb-1.5">Method &amp; honesty</div>
          <p className="text-[11.5px] text-[var(--color-mute)] leading-relaxed">{note}</p>
        </Card>
      )}
    </div>
  )
}
