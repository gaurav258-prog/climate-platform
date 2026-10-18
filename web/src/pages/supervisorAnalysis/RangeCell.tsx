import { money } from '../../lib/money'
import { hazardLabel } from '../../lib/hazards'
import { Dialog } from '../../components/Dialog'
import { StatusChip } from '../../components/StatusChip'
import { HBar } from '../../components/Charts'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { RaiseLink, cellName, pct, type Named } from './checks'

// One cell of the quick check: its filed share on the range of that share across its country's regions, and the
// pop-up with what the range rests on. Results in the reader's words; the colour carries the result.
export type Verdict = 'plausible' | 'above_band' | 'below_band' | 'no_reference'
export const VERDICT: Record<Verdict, { label: string; color: string; tone: 'good' | 'warn' | 'neutral' }> = {
  above_band: { label: 'Above range', color: 'var(--color-warn)', tone: 'warn' },
  below_band: { label: 'Below range', color: 'var(--color-warn)', tone: 'warn' },
  plausible: { label: 'Within range', color: 'var(--color-good)', tone: 'good' },
  no_reference: { label: 'Not judged', color: 'var(--color-faint)', tone: 'neutral' },
}
export interface Band { p10: number; p25: number; p50: number; p75: number; p90: number; share_sensitive_pct: number; n_cells: number; n_regions: number; hazard_mix: Record<string, number>; built_at: string; at_risk_level: number | null }
export interface Row extends Named {
  key: string; geography: string; sector: string; exposure_eur: number | null; sensitive_physical_eur: number | null
  submitted_share_pct: number | null; band: Band | null; verdict: Verdict; verdict_label: string; reason: Message
}

export function BandBar({ r, wide }: { r: Row; wide?: boolean }) {
  if (!r.band) return <span className="text-[11.5px] text-[var(--color-faint)]">No range</span>
  const b = r.band, x = (v: number) => `${Math.max(0, Math.min(100, v))}%`
  return (
    <div className={`relative rounded bg-[var(--color-panel-2)] ${wide ? 'h-6 w-full' : 'h-4 w-40'}`} role="img"
      aria-label={`Typical range ${b.p25}% to ${b.p75}%, filed ${pct(r.submitted_share_pct)}`} title={`Typical range ${b.p25}–${b.p75}% · wider ${b.p10}–${b.p90}% · median ${b.p50}%`}>
      <div className="absolute top-0 h-full rounded bg-[var(--color-sky)]/15" style={{ left: x(b.p10), width: `${Math.max(1, b.p90 - b.p10)}%` }} />
      <div className="absolute top-0 h-full rounded bg-[var(--color-sky)]/40" style={{ left: x(b.p25), width: `${Math.max(1, b.p75 - b.p25)}%` }} />
      <div className="absolute top-0 h-full w-px bg-[var(--color-sky)]" style={{ left: x(b.p50) }} />
      {r.submitted_share_pct != null && <div className={`absolute rounded-sm ${wide ? 'top-[3px] h-[18px] w-[4px]' : 'top-[2px] h-3 w-[3px]'}`}
        style={{ left: x(r.submitted_share_pct), background: VERDICT[r.verdict].color }} />}
    </div>
  )
}

const fact = (label: string, value: React.ReactNode) => (
  <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]">
    <span className="text-[var(--color-mute)]">{label}</span><span className="text-right text-[var(--color-ink)] tabular-nums">{value}</span>
  </div>)
const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })

export function CellDialog({ r, orgId, measure, onClose }: { r: Row; orgId: string; measure: string; onClose: () => void }) {
  const b = r.band
  const mix = Object.entries(b?.hazard_mix ?? {}).sort((a, z) => z[1] - a[1])
  const out = r.verdict === 'above_band' || r.verdict === 'below_band'
  return (
    <Dialog title={cellName(r)} onClose={onClose} className="max-w-xl">
      <div className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-[12.5px]">
          <span className="inline-flex items-center gap-1.5"><StatusChip tone={VERDICT[r.verdict].tone} label={r.verdict_label} /><InfoButton compact details={messageDetails(r.reason)} /></span>
          {out && <RaiseLink orgId={orgId} cell={r} why={r.reason.label} />}
        </div>
        {b && <div className="space-y-1">
          <BandBar r={r} wide />
          <div className="flex justify-between text-[11px] text-[var(--color-faint)] tabular-nums"><span>0%</span><span>50%</span><span>100%</span></div>
        </div>}
        <div>
          {fact(measure, money(r.exposure_eur, 'EUR'))}
          {fact('Filed as sensitive', money(r.sensitive_physical_eur, 'EUR'))}
          {fact('Filed share', pct(r.submitted_share_pct))}
          {b && <>
            {fact('Typical range (middle half of regions)', `${b.p25}% – ${b.p75}%`)}
            {fact('Wider range (10th to 90th percentile)', `${b.p10}% – ${b.p90}%`)}
            {fact('Middle region (median)', `${b.p50}%`)}
            {fact('Land at or above the threshold, whole country', `${b.share_sensitive_pct}%`)}
            {fact('Regions · scored land areas', `${b.n_regions} · ${b.n_cells.toLocaleString()}`)}
            {fact('Range built on', day(b.built_at))}
          </>}
        </div>
        {mix.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0">Land at or above the threshold, by highest hazard</h4>
            <HBar data={mix.map(([h, n]) => ({ label: hazardLabel(h), value: n }))} format={n => n.toLocaleString()} labelWidth="w-52" height={18} />
          </div>)}
      </div>
    </Dialog>
  )
}
