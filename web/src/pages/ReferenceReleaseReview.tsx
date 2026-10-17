import { type ReactNode, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Button } from '../components/ui'
import { HBar } from '../components/Charts'
import { Dialog, CloseButton } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine, DetailsBody, messageDetails, type Message } from '../components/Details'

// One release, opened from Reference data releases (UI standard, 2026-10-16): what the publisher's file changes — as a
// bar, by crop, and its largest revisions — the rows the reading set aside, the calibrations to re-check, the rows
// themselves, and the decision. The file's own record (address, fingerprint, reading rules) is one click away.

type Detail = Message['detail']
export interface ByCommodity { added: number; revised: number; recomputed: number; years_new: number[] }
export interface Revision { commodity: string; place: string; year: number; production_before: number; production_now: number; change_pct: number }
export interface Fit { commodity: string; place: string; driver: { label: string; detail: Detail }; baseline_from: number | null; baseline_to: number | null; changed_years: number[] }
export interface Aside { code: string | null; label: string; detail: Detail; rows: number }
export interface Summary { rows_in_file: number; added: number; revised: number; recomputed: number; unchanged: number; held_not_in_file: number; set_aside: Aside[]; by_commodity: Record<string, ByCommodity>; largest_revisions: Revision[]; calibrations_may_be_affected: Fit[] }
export interface Release {
  release_id: string; source_key: string | null; source_name: string; file_sha256: string; reader: string; file_bytes: number
  origin_url: string; last_modified: string | null; fetched_at: string; summary: Summary; status: 'staged' | 'proposed' | 'landed' | 'rejected'
  approval_request_id: string | null; decided_at: string | null; decision_reason: string | null; landed_at: string | null
  proposed_by_id: string | null; proposed_by_name: string | null; review: string | null; proposed_at: string | null; decided_by: string | null
  reading_changed: Message | null
}
interface Row { commodity: string; place: string; season_year: number; change: Kind; production_tonnes: number | null; area_harvested_ha: number | null; yield_tonnes_ha: number | null; yoy_change_pct: number | null; held_before: Record<string, number | null> | null }
type Kind = 'added' | 'revised' | 'recomputed'

export const STATUS: Record<Release['status'], { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  staged: { label: 'To review', tone: 'warn' }, proposed: { label: 'Awaiting approval', tone: 'warn' },
  landed: { label: 'Applied', tone: 'good' }, rejected: { label: 'Not applied', tone: 'neutral' },
}
export const KIND: Record<Kind, { label: string; color: string }> = {
  added: { label: 'Added', color: 'var(--color-sky)' }, revised: { label: 'Revised', color: 'var(--color-warn)' },
  recomputed: { label: 'Recomputed', color: 'var(--color-slate)' },
}
const KINDS: Kind[] = ['added', 'revised', 'recomputed']
export const num = (v: number | null | undefined, d = 0) => v == null ? '—' : v.toLocaleString('en-GB', { maximumFractionDigits: d })
export const day = (s: string | null | undefined) => s ? new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
// consecutive years as one range: 1866–1950, 1962–2026 — a source landing its whole history lists ranges, not 160 years
const yearRanges = (ys: number[]) => ys.filter((y, i) => i === 0 || y !== ys[i - 1] + 1).map(y => {
  let end = y
  while (ys.includes(end + 1)) end++
  return end === y ? String(y) : `${y}–${end}`
}).join(', ')

const READ = [
  { heading: HEADING.read, body: <ul className="list-disc pl-5 space-y-1">
    <li><b>Added</b> — a year the platform does not hold yet.</li>
    <li><b>Revised</b> — the publisher changed its production or area for a year already held.</li>
    <li><b>Recomputed</b> — only the yield or year-on-year change the platform derives changed, under one stated rounding rule.</li>
    <li><b>Kept, not in the file</b> — rows the platform holds that the file no longer lists. They are kept, never deleted.</li>
  </ul> },
]

// The three steps of a release: received, proposed by a reviewer, applied by an approver (or closed without applying).
export function Stepper({ r, compact }: { r: Release; compact?: boolean }) {
  const closed = r.status === 'rejected'
  const steps: { label: string; done: boolean; tone: string; when?: string | null; who?: string | null; note?: string | null; skipped?: boolean }[] = [
    { label: 'Received', done: true, tone: 'var(--color-good)', when: r.fetched_at },
    { label: 'Proposed', done: !!r.proposed_at, tone: 'var(--color-good)', when: r.proposed_at, who: r.proposed_by_name, note: r.review, skipped: closed && !r.proposed_at },
    closed ? { label: 'Not applied', done: true, tone: 'var(--color-bad)', when: r.decided_at, who: r.decided_by, note: r.decision_reason }
      : { label: 'Applied', done: r.status === 'landed', tone: 'var(--color-good)', when: r.landed_at, who: r.decided_by, note: r.decision_reason },
  ]
  return (
    <ol className={`flex items-start ${compact ? 'gap-0' : 'gap-1'}`} aria-label="Release steps">
      {steps.map((s, i) => {
        const c = s.done ? s.tone : 'var(--color-line-2)'
        return (
          <li key={s.label} className={`flex items-start ${compact ? '' : 'flex-1 min-w-0'}`} title={compact ? `${s.label}${s.when ? ` · ${day(s.when)}` : ''}` : undefined}>
            <div className={`flex flex-col ${compact ? '' : 'min-w-0'}`}>
              <div className="flex items-center">
                <span className={`rounded-full shrink-0 ${compact ? 'w-2.5 h-2.5' : 'w-3.5 h-3.5'}`}
                  style={{ background: s.done ? c : 'transparent', border: `2px ${s.skipped ? 'dashed' : 'solid'} ${c}` }} />
                {!compact && <span className="ml-2 text-[12.5px] font-medium" style={{ color: s.done ? 'var(--color-ink)' : 'var(--color-faint)' }}>{s.label}</span>}
                {!compact && s.note && <InfoButton compact className="ml-1" details={{ title: `${s.label} — note`, sections: [{ heading: s.who ?? 'Note', body: s.note }] }} />}
              </div>
              {!compact && <div className="ml-5.5 pl-0.5 text-[11.5px] text-[var(--color-mute)] leading-snug">{s.skipped ? '—' : s.when ? day(s.when) : 'Not yet'}{s.who ? <span className="block truncate text-[var(--color-faint)]">{s.who}</span> : null}</div>}
            </div>
            {i < steps.length - 1 && <span className={`h-0.5 mt-[5px] ${compact ? 'w-3' : 'flex-1 mx-2 mt-[7px]'}`} style={{ background: steps[i + 1].done || steps[i + 1].skipped ? 'var(--color-good)' : 'var(--color-line-2)' }} />}
          </li>
        )
      })}
    </ol>
  )
}

// One 100% bar of the rows the file changes: added, revised, recomputed.
export function ChangeBar({ s, height = 8 }: { s: Summary; height?: number }) {
  const parts = KINDS.map(k => ({ k, n: s[k] })).filter(p => p.n > 0)
  const total = parts.reduce((a, p) => a + p.n, 0)
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-[var(--color-panel-2)]" style={{ height }} role="img"
      aria-label={parts.map(p => `${KIND[p.k].label} ${num(p.n)}`).join(', ') || 'No changes'}>
      {parts.map(p => <div key={p.k} title={`${KIND[p.k].label}: ${num(p.n)}`} style={{ width: `${(p.n / total) * 100}%`, background: KIND[p.k].color, minWidth: 2 }} />)}
    </div>
  )
}

export function Legend({ kinds }: { kinds: Kind[] }) {
  return <div className="flex flex-wrap gap-x-3 gap-y-1">{kinds.map(k => <span key={k} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: KIND[k].color }} />{KIND[k].label}</span>)}</div>
}

// Rows per crop, stacked by kind of change, on one scale.
function ByCrop({ by }: { by: Record<string, ByCommodity> }) {
  const crops = Object.entries(by).map(([c, b]) => ({ c, b, n: b.added + b.revised + b.recomputed })).filter(x => x.n > 0).sort((a, b) => b.n - a.n)
  const max = Math.max(1, ...crops.map(x => x.n))
  return (
    <div className="space-y-1.5">
      {crops.map(({ c, b, n }) => (
        <div key={c} className="flex items-center gap-2 text-[11.5px]">
          <span className="w-24 shrink-0 truncate text-right text-[var(--color-mute)]">{c}</span>
          <div className="flex-1 flex h-3.5 rounded overflow-hidden bg-[var(--color-panel-2)]">
            <div className="flex h-full" style={{ width: `${Math.max(1.5, (n / max) * 100)}%` }}>
              {KINDS.filter(k => b[k] > 0).map(k => <div key={k} title={`${KIND[k].label}: ${num(b[k])}`} style={{ width: `${(b[k] / n) * 100}%`, background: KIND[k].color, minWidth: 2 }} />)}
            </div>
          </div>
          <span className="w-16 text-right tabular-nums text-[var(--color-ink)]">{num(n)}</span>
          <span className="w-20 truncate text-[10.5px] text-[var(--color-faint)]" title={b.years_new.length ? `New years: ${yearRanges(b.years_new)}` : undefined}>
            {b.years_new.length ? `+${b.years_new.length} new yr` : ''}</span>
        </div>
      ))}
    </div>
  )
}

// The publisher's largest revisions, as a change in production around zero.
function Revisions({ list }: { list: Revision[] }) {
  const max = Math.max(1, ...list.map(v => Math.abs(v.change_pct)))
  return (
    <div className="space-y-1.5">
      {list.map((v, i) => {
        const up = v.change_pct >= 0
        return (
          <div key={i} className="flex items-center gap-2 text-[11.5px]" title={`${v.commodity} · ${v.place} · ${v.year}: ${num(v.production_before, 1)} t → ${num(v.production_now, 1)} t`}>
            <span className="w-72 shrink-0 truncate text-right text-[var(--color-mute)]">{v.commodity} · {v.place} · {v.year}</span>
            <div className="flex-1 relative h-3.5">
              <div className="absolute inset-y-0 left-1/2 w-px bg-[var(--color-line-2)]" />
              <div className="absolute inset-y-0 rounded-sm" style={{ [up ? 'left' : 'right']: '50%', width: `${Math.max(1, (Math.abs(v.change_pct) / max) * 50)}%`, background: up ? 'var(--color-sky)' : 'var(--color-slate)' }} />
            </div>
            <span className="w-14 text-right tabular-nums" style={{ color: up ? 'var(--color-sky)' : 'var(--color-slate)' }}>{up ? '+' : ''}{v.change_pct.toFixed(1)}%</span>
          </div>
        )
      })}
    </div>
  )
}

function Block({ title, info, children }: { title: string; info?: { heading: string; body: ReactNode }[]; children: ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2"><h4 className="text-[13px] font-semibold text-[var(--color-ink)] m-0">{title}</h4>
        {info && <InfoButton compact details={{ title, sections: info }} />}</div>
      {children}
    </section>
  )
}

export function ReleaseReview({ r, attribution, myId, onClose, onDone }: { r: Release; attribution?: string; myId: string | null; onClose: () => void; onDone: () => void }) {
  const s = r.summary
  const kinds = (['revised', 'added', 'recomputed'] as const).filter(k => s[k] > 0)
  const [kind, setKind] = useState<Kind | null>(null)
  const shown = kind ?? kinds[0] ?? 'added'
  const rows = useQuery({ queryKey: ['reference-release', r.release_id, shown], queryFn: () => api.get<{ rows: Row[] }>(`/v1/ops/reference-releases/${r.release_id}?change=${shown}`) })
  const [aside, setAside] = useState<Aside | null>(null)
  const [file, setFile] = useState(false)
  const changes = s.added + s.revised + s.recomputed
  return (
    <Drawer label={r.source_name} onClose={onClose} className="w-full max-w-3xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5 space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><span className="text-[17px] font-semibold text-[var(--color-ink)]">{r.source_name}</span><StatusChip label={STATUS[r.status].label} tone={STATUS[r.status].tone} /></div>
          <div className="text-[12px] text-[var(--color-mute)] mt-0.5">Received {day(r.fetched_at)} · {num(s.rows_in_file)} rows</div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="ghost" onClick={() => setFile(true)}><FileText size={14} /> File details</Button>
          <CloseButton onClick={onClose} />
        </div>
      </div>
      <Stepper r={r} />
      {r.reading_changed && <div className="text-[12.5px] text-[var(--color-warn)]"><MessageLine m={r.reading_changed} /></div>}

      <Block title="What the file changes" info={READ}>
        <ChangeBar s={s} height={14} />
        <div className="flex flex-wrap items-center justify-between gap-2 mt-2">
          <Legend kinds={['added', 'revised', 'recomputed']} />
          <span className="text-[11.5px] text-[var(--color-mute)] tabular-nums">{num(changes)} of {num(s.rows_in_file)} rows change{s.held_not_in_file ? ` · ${num(s.held_not_in_file)} kept, not in the file` : ''}</span>
        </div>
      </Block>

      {Object.keys(s.by_commodity).length > 0 && changes > 0 && <Block title="By crop"><ByCrop by={s.by_commodity} /></Block>}
      {s.largest_revisions.length > 0 && <Block title="Largest revisions" info={[{ heading: HEADING.shows, body: 'The years already held whose production the publisher changed most, as a share of the figure held before. Hover a bar for the two figures.' }]}><Revisions list={s.largest_revisions} /></Block>}
      {s.calibrations_may_be_affected.length > 0 && (
        <Block title="Calibrations to re-check" info={[{ heading: HEADING.shows, body: 'Crop calibrations whose years include a year this file adds or revises.' }, { heading: HEADING.limits, body: 'A calibration records its years, not the series it read, so it is listed here for a re-check. Nothing here changes it.' }]}>
          <div className="max-h-56 overflow-y-auto space-y-1">
            {s.calibrations_may_be_affected.map((f, i) => (
              <div key={i} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] py-1 border-b border-[var(--color-line)]">
                <span className="text-[var(--color-ink)] min-w-[12rem]">{f.commodity} · {f.place}</span>
                <StatusChip label={f.driver.label} tone="neutral" />
                <span className="text-[var(--color-mute)] tabular-nums">{f.baseline_from ?? '—'}–{f.baseline_to ?? '—'}</span>
                <span className="text-[var(--color-faint)] tabular-nums" title={yearRanges(f.changed_years)}>{f.changed_years.length} {f.changed_years.length === 1 ? 'year' : 'years'} changed</span>
              </div>
            ))}
          </div>
        </Block>
      )}
      {s.set_aside.length > 0 && (
        <Block title="Rows set aside" info={[{ heading: HEADING.shows, body: 'Rows of the file the platform does not read, counted by reason. They are listed so nothing is dropped silently; none of them is stored.' }]}>
          <HBar data={s.set_aside.map(a => ({ label: a.label, value: a.rows, color: 'var(--color-slate)' }))} format={n => num(n)} labelWidth="w-64" height={18}
            onBar={i => setAside(s.set_aside[i])} />
        </Block>
      )}

      <Block title="Rows">
        {kinds.length > 0 && <div className="flex gap-1.5 mb-2">
          {kinds.map(k => (
            <button key={k} onClick={() => setKind(k)}
              className={`px-3 py-1 rounded-full text-[12px] border transition ${shown === k ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
              {KIND[k].label} · {num(s[k])}</button>))}
        </div>}
        {kinds.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">The file changes no row.</div> : (
          <div className="overflow-x-auto max-h-80 overflow-y-auto border border-[var(--color-line)] rounded-lg">
            <table className="w-full tabular-nums text-[11.5px]"><thead className="sticky top-0 bg-[var(--color-bg-2)]"><tr className="text-[var(--color-mute)] text-left">
              <th className="font-medium px-2 py-1.5">Crop</th><th className="font-medium px-2">Place</th><th className="font-medium px-2">Year</th>
              <th className="font-medium px-2 text-right">Production (t)</th><th className="font-medium px-2 text-right">Area (ha)</th><th className="font-medium px-2 text-right">Yield (t/ha)</th><th className="font-medium px-2 text-right">Year on year</th></tr></thead>
              <tbody>{(rows.data?.rows ?? []).map((x, i) => (
                <tr key={i} className="border-t border-[var(--color-line)]">
                  <td className="px-2 py-0.5 text-[var(--color-ink)]">{x.commodity}</td><td className="px-2 whitespace-nowrap">{x.place}</td><td className="px-2">{x.season_year}</td>
                  <Cell now={x.production_tonnes} before={x.held_before?.production_tonnes} d={1} />
                  <Cell now={x.area_harvested_ha} before={x.held_before?.area_harvested_ha} d={1} />
                  <Cell now={x.yield_tonnes_ha} before={x.held_before?.yield_tonnes_ha} d={4} />
                  <Cell now={x.yoy_change_pct} before={x.held_before?.yoy_change_pct} d={2} pct />
                </tr>))}</tbody></table>
            {rows.data && rows.data.rows.length >= 500 && <div className="px-2 py-1 text-[11px] text-[var(--color-faint)]">The first 500 of {num(s[shown])}.</div>}
          </div>
        )}
      </Block>

      <Decision r={r} myId={myId} onDone={onDone} />

      {aside && <Dialog title={aside.label} onClose={() => setAside(null)} className="max-w-xl">
        <div className="text-[12.5px] text-[var(--color-mute)] mb-3">{num(aside.rows)} rows</div>
        <DetailsBody sections={messageDetails({ label: aside.label, detail: aside.detail }).sections} />
      </Dialog>}
      {file && <FileDetails r={r} attribution={attribution} onClose={() => setFile(false)} />}
    </Drawer>
  )
}

// a value as the file states it; where it differs from the value held, the held value beside it (struck through)
function Cell({ now, before, d, pct }: { now: number | null; before: number | null | undefined; d: number; pct?: boolean }) {
  const changed = before !== undefined && (before == null) !== (now == null) || (before != null && now != null && Math.abs(before - now) > 1e-9)
  const f = (v: number | null) => v == null ? '—' : `${num(v, d)}${pct ? '%' : ''}`
  return (
    <td className="px-2 text-right whitespace-nowrap">
      {changed && <span className="line-through text-[var(--color-faint)] mr-1.5">{f(before ?? null)}</span>}
      <span style={{ color: changed ? 'var(--color-warn)' : undefined }}>{f(now)}</span>
    </td>
  )
}

// The file's own record: where it came from, its publisher's date, its fingerprint and the reading rules applied.
function FileDetails({ r, attribution, onClose }: { r: Release; attribution?: string; onClose: () => void }) {
  const fact = (label: string, value: ReactNode) => <div className="flex justify-between gap-4 py-1.5 border-b border-[var(--color-line)] text-[12.5px]"><span className="text-[var(--color-mute)] shrink-0">{label}</span><span className="text-right text-[var(--color-ink)] break-all">{value}</span></div>
  return (
    <Dialog title="File details" onClose={onClose} className="max-w-xl">
      {fact('Publisher', r.source_name)}
      {fact('Fetched from', <a href={r.origin_url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">{new URL(r.origin_url).hostname}</a>)}
      {fact("Publisher's date", r.last_modified ? r.last_modified : 'Not stated')}
      {fact('Received', day(r.fetched_at))}
      {fact('Size', `${(r.file_bytes / 1e6).toFixed(1)} MB`)}
      {fact('File fingerprint', <span className="mono text-[11px]">{r.file_sha256}</span>)}
      {fact('Reading rules', <span className="mono text-[11px]">{r.reader}</span>)}
      {attribution && <div className="text-[11.5px] text-[var(--color-faint)] mt-3">{attribution}</div>}
      <div className="mt-4"><DetailsBody sections={[{ heading: HEADING.read, body: 'The fingerprint identifies the exact file received; the same file is never staged twice. The reading rules identify how the platform read it — another reading of the same file is another release.' }]} /></div>
    </Dialog>
  )
}

function Decision({ r, myId, onDone }: { r: Release; myId: string | null; onDone: () => void }) {
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try { await fn(); toast.success(ok); setNote(''); onDone() }
    catch (e) { toast.error(apiMessage(e, 'Could not complete the step.')) }
    finally { setBusy(false) }
  }
  const box = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  if (r.status === 'staged') return (
    <Block title="Your review">
      <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} className={box} aria-label="Review note"
        placeholder="What you reviewed — or why the release is rejected. Kept with the release." />
      <div className="flex gap-2 mt-2">
        <Button disabled={busy || note.trim().length < 10} onClick={() => act(() => api.post(`/v1/ops/reference-releases/${r.release_id}/propose`, { reason: note.trim() }), 'Proposed. A second person decides.')}>Propose applying</Button>
        <Button variant="ghost" disabled={busy || note.trim().length < 10} onClick={() => act(() => api.post(`/v1/ops/reference-releases/${r.release_id}/reject`, { reason: note.trim() }), 'Rejected. Nothing was applied.')}>Reject</Button>
      </div>
    </Block>
  )
  if (r.status === 'proposed') return (
    <Block title="Decision">
      {!!myId && r.proposed_by_id === myId ? <div className="text-[12.5px] text-[var(--color-faint)]">You proposed this release. A second person decides.</div> : <>
        <textarea value={note} onChange={e => setNote(e.target.value)} rows={2} className={box} aria-label="Decision note" placeholder="Your decision note. Kept with the release." />
        <div className="flex gap-2 mt-2">
          <Button disabled={busy} onClick={() => act(() => api.post(`/v1/approvals/${r.approval_request_id}/decide`, { decision: 'approved', reason: note.trim() || undefined }), 'Approved. The release is applied.')}>Approve and apply</Button>
          <Button variant="ghost" disabled={busy} onClick={() => act(() => api.post(`/v1/approvals/${r.approval_request_id}/decide`, { decision: 'returned', reason: note.trim() || undefined }), 'Returned. Nothing was applied.')}>Return</Button>
        </div></>}
    </Block>
  )
  return null
}
