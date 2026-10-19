import { useNavigate } from 'react-router-dom'
import { ArrowRight, Crosshair, Grid3x3 } from 'lucide-react'
import { StatusChip } from '../StatusChip'
import { MessageLine } from '../Details'
import { hazardLabel } from '../../lib/labels'
import { balance, flow } from '../../lib/money'
import { ramp, rgb } from './globe'
import type { Asset, Stop } from './types'

// The asset the person picked on the globe: where it stands at the year in view, its score at every modelled year
// against the stated at-risk level, its facts, and where to act on it. Every figure is the server's.
export default function AssetCard({ a, stops, stop, level, onGrid }: {
  a: Asset; stops: Stop[]; stop: number; level: number | null; onGrid: () => void
}) {
  const nav = useNavigate()
  const s = a.score[stop], flag = a.at_risk[stop], c = ramp(s)
  const max = Math.max(100, ...a.score.map(x => x ?? 0))
  return (
    <div>
      <div className="text-[12px] text-[var(--color-faint)] mt-6">{a.kind_name}{a.region ? ` · ${a.region}` : ''}</div>
      <div className="display text-[32px] leading-tight text-[#F4EFE6] mt-1">{a.name}</div>
      <div className="flex flex-wrap items-center gap-2 mt-3">
        {flag === true && <StatusChip tone="bad" label={`At risk · ${stops[stop].label}`} />}
        {flag === false && <StatusChip tone="good" label={`Below your at-risk level · ${stops[stop].label}`} />}
        {s == null && <StatusChip tone="neutral" label={`No score · ${stops[stop].label}`} />}
      </div>

      {/* the score at the year in view: a gauge, with the hazard that leads it */}
      {s != null && (
        <div className="mt-5 rounded-xl border border-[var(--color-line)] px-4 py-3.5">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-[34px] leading-none tabular-nums" style={{ color: rgb(c) }}>{Math.round(s)}<span className="text-[15px] text-[var(--color-faint)]"> / 100</span></span>
            <span className="text-[13px] text-[var(--color-mute)] text-right">{hazardLabel(a.hazard[stop])}</span>
          </div>
          <div className="relative h-2 rounded-full bg-[#162133] mt-3 overflow-hidden">
            <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${s}%`, background: rgb(c) }} />
          </div>
          {level != null && <div className="relative h-0"><div className="absolute -top-3 w-px h-4 bg-[#F4EFE6]/70" style={{ left: `${level}%` }} /></div>}
        </div>
      )}

      {/* the score at every modelled year, against the stated level */}
      <div className="mt-5">
        <div className="text-[12px] text-[var(--color-faint)] mb-2">Score by year · highest hazard</div>
        <div className="relative flex items-end gap-2 h-[104px] pt-3">
          {level != null && <div className="absolute left-0 right-0 border-t border-dashed border-[#F4EFE6]/40" style={{ bottom: `${22 + (level / max) * 66}px` }} />}
          {stops.map((st, i) => {
            const v = a.score[i], cc = ramp(v)
            return (
              <div key={st.key} className="flex-1 flex flex-col items-center gap-1.5">
                <span className="text-[11px] tabular-nums text-[var(--color-mute)]">{v == null ? '—' : Math.round(v)}</span>
                <div className={`w-full rounded-t ${i === stop ? 'ring-1 ring-[#F4EFE6]/60' : ''}`} style={{ height: v == null ? 2 : Math.max(3, (v / max) * 66), background: rgb(cc, v == null ? 0.3 : 1) }} />
                <span className={`text-[11px] ${i === stop ? 'text-[#F4EFE6]' : 'text-[var(--color-faint)]'}`}>{st.label}</span>
              </div>
            )
          })}
        </div>
      </div>

      {a.facts.length > 0 && (
        <div className="grid grid-cols-2 gap-2 mt-5">
          {a.facts.map(f => (
            <div key={f.label} className="rounded-lg border border-[var(--color-line)] px-3 py-2.5">
              <div className="text-[15px] text-[#F4EFE6] leading-tight line-clamp-2">{f.money != null ? (f.flow ? flow(f.money) : balance(f.money)) : f.text}</div>
              <div className="text-[11.5px] text-[var(--color-faint)] mt-1">{f.label}</div>
            </div>
          ))}
        </div>
      )}

      {a.adaptations.length > 0 && (
        <div className="mt-5 pt-4 border-t border-[var(--color-line)]">
          <div className="text-[12px] text-[var(--color-faint)] mb-2.5">What you can do</div>
          <ul className="flex flex-col gap-2">
            {a.adaptations.map(x => <li key={x} className="flex gap-2.5 text-[13.5px] text-[var(--color-mute)] leading-snug"><span className="text-[var(--color-good)] shrink-0">→</span>{x}</li>)}
          </ul>
        </div>
      )}

      {a.notice && (
        <div className="mt-5 rounded-xl border border-[var(--color-warn)]/40 px-4 py-3 flex flex-wrap items-center justify-between gap-2">
          <MessageLine m={a.notice} className="text-[13.5px] text-[var(--color-ink)]" />
          <button onClick={() => nav('/eudr')} className="inline-flex items-center gap-1 text-[13px] text-[var(--color-warn)] hover:underline">Open EUDR <ArrowRight size={13} /></button>
        </div>
      )}

      {a.decide && (
        <button onClick={() => nav(`/decisions?focus=${encodeURIComponent(a.ref)}`)}
          className="mt-5 w-full inline-flex items-center justify-center gap-2 text-[13.5px] text-[#0b1206] bg-[var(--color-sky)] rounded-full px-5 py-3 hover:opacity-90">
          <Crosshair size={14} /> Decide on this exposure</button>
      )}
      {a.kind !== 'region' && (
        <button onClick={onGrid}
          className="mt-3 w-full inline-flex items-center justify-center gap-2 text-[13.5px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
          <Grid3x3 size={14} /> Surrounding grid</button>
      )}
      <button onClick={() => nav(a.record_href)}
        className="mt-3 w-full inline-flex items-center justify-center gap-2 text-[13.5px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
        {a.kind === 'region' ? 'Open the exposure map' : a.record_href.startsWith('/detail') ? 'Open the full record' : 'Open in Portfolio'} <ArrowRight size={14} />
      </button>
    </div>
  )
}
