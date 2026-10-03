import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { DatabaseZap, RefreshCw } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, PageHeader, SectionHead } from '../components/ui'
import { pressable } from '../lib/pressable'

// Reference data releases (E148) — a FAOSTAT crop-production file is fetched on the feed schedule and STAGED with its
// difference against the store. One platform operator reviews it and proposes landing it; a second operator approves
// (the one approvals path; the proposer can never approve). Only then are the rows written; replaced values are kept.

interface ByCommodity { added: number; revised: number; recomputed: number; years_new: number[] }
interface Revision { commodity: string; country: string; year: number; production_before: number; production_now: number; change_pct: number }
interface Fit { commodity: string; origin: string; hazard_driver: string; baseline_from: number | null; baseline_to: number | null; changed_years: number[] }
interface Summary { reader_changed_since_last_landed?: boolean; last_landed_reader?: string | null; rows_in_file: number; added: number; revised: number; recomputed: number; unchanged: number; held_not_in_file: number; by_commodity: Record<string, ByCommodity>; largest_revisions: Revision[]; calibrations_may_be_affected: Fit[] }
interface Release {
  release_id: string; source: string; file_sha256: string; reader: string; file_bytes: number; origin_url: string; last_modified: string | null
  fetched_at: string; summary: Summary; status: 'staged' | 'proposed' | 'landed' | 'rejected'; approval_request_id: string | null
  decided_at: string | null; decision_reason: string | null; landed_at: string | null
  proposed_by_id: string | null; proposed_by: string | null; review: string | null; proposed_at: string | null; decided_by: string | null
}
interface Feed { source: string; label: string; name: string; cadence_days: number; last_refresh: string | null; last_status: string | null; status: string; awaiting_review: { release_id: string; status: string } | null; attribution: string; note: string }
interface Row { commodity: string; country: string; season_year: number; change: string; production_tonnes: number | null; area_harvested_ha: number | null; yield_tonnes_ha: number | null; yoy_change_pct: number | null; held_before: Record<string, number | null> | null }

const STATUS: Record<string, string> = { staged: 'var(--color-warn)', proposed: 'var(--color-sky)', landed: 'var(--color-good)', rejected: 'var(--color-faint)' }
const num = (v: number | null | undefined, d = 1) => v == null ? '—' : v.toLocaleString('en-GB', { maximumFractionDigits: d })
const day = (s: string | null) => s ? s.slice(0, 10) : '—'

export default function ReferenceReleases() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['reference-releases'], queryFn: () => api.get<{ feeds: Feed[]; releases: Release[] }>('/v1/ops/reference-releases') })
  const me = useQuery({ queryKey: ['me'], queryFn: () => api.get<{ user?: { id?: string; user_id?: string } }>('/v1/auth/me') })
  const myId = me.data?.user?.id ?? me.data?.user?.user_id ?? null
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const check = async (f: Feed) => {
    setBusy(f.source)
    try {
      const r = await api.post<{ status: string; awaiting_review: unknown }>(`/v1/ops/reference-releases/check?source=${f.source}`, {})
      toast.success(r.status === 'failed' ? 'The check failed — see the feed status.' : r.awaiting_review ? 'A release is awaiting review.' : `Nothing new from ${f.name}.`)
    } catch (e) { toast.error(apiMessage(e, `Could not check ${f.name}.`)) }
    finally { setBusy(null); qc.invalidateQueries({ queryKey: ['reference-releases'] }) }
  }
  const d = q.data
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Platform · reference data" title="Reference data releases"
        lead="A publisher's new file is staged with its difference against what the platform holds, and lands only when approved as the Approvers policy below states — two people, or the platform's proposal and one person. Nothing reaches customers' figures before that." />
      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the releases.')}</Card>
        : <>
          {d.feeds.map(f => (
            <Card key={f.source} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="max-w-[80ch]">
                  <SectionHead icon={DatabaseZap} className="mb-1">{f.name}</SectionHead>
                  <div className="text-[12.5px] text-[var(--color-mute)]">{f.note}</div>
                  <div className="mono text-[11px] text-[var(--color-faint)] mt-2">
                    checked every {f.cadence_days} days · last check {day(f.last_refresh)} ({f.last_status ?? 'never'}) · {f.awaiting_review ? `release ${f.awaiting_review.status} — awaiting review` : 'nothing awaiting review'} · {f.attribution}
                  </div>
                </div>
                <Button variant="ghost" onClick={() => check(f)} disabled={busy !== null || !!f.awaiting_review}><RefreshCw size={13} /> Check now</Button>
              </div>
            </Card>
          ))}

          <ApproverPolicy />

          <Card className="p-0 overflow-hidden">
            <SectionHead className="px-5 py-3 border-b border-[var(--color-line)]">Releases</SectionHead>
            {d.releases.length === 0 ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">No release fetched yet.</div>
              : <div className="divide-y divide-[var(--color-line)]">
                  {d.releases.map(r => (
                    <div key={r.release_id}>
                      <div {...pressable(() => setOpen(open === r.release_id ? null : r.release_id))}
                        className="px-5 py-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[12.5px] hover:bg-[var(--color-bg-2)] cursor-pointer">
                        <span className="mono text-[10px] uppercase tracking-wide border rounded px-1.5 py-0.5" style={{ color: STATUS[r.status], borderColor: STATUS[r.status] }}>{r.status}</span>
                        <span className="text-[var(--color-ink)]">{r.source} · received {day(r.fetched_at)}</span>
                        <span className="text-[var(--color-mute)] tabular-nums">+{num(r.summary.added, 0)} added · {num(r.summary.revised, 0)} revised · {num(r.summary.recomputed, 0)} recomputed</span>
                        <span className="mono text-[10.5px] text-[var(--color-faint)]">{(r.file_bytes / 1e6).toFixed(1)} MB · sha-256 {r.file_sha256.slice(0, 12)}… · read as {r.reader}</span>
                      </div>
                      {open === r.release_id && <ReleaseReview r={r} myId={myId} onDone={() => qc.invalidateQueries({ queryKey: ['reference-releases'] })} />}
                    </div>
                  ))}
                </div>}
          </Card>
        </>}
    </div>
  )
}

function ReleaseReview({ r, myId, onDone }: { r: Release; myId: string | null; onDone: () => void }) {
  const kinds = (['revised', 'added', 'recomputed'] as const).filter(k => r.summary[k] > 0)
  const [kind, setKind] = useState<string | null>(null)
  const shown = kind ?? kinds[0] ?? 'added'
  const rows = useQuery({ queryKey: ['reference-release', r.release_id, shown], queryFn: () => api.get<{ rows: Row[] }>(`/v1/ops/reference-releases/${r.release_id}?change=${shown}`) })
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const s = r.summary
  const mine = !!myId && r.proposed_by_id === myId
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try { await fn(); toast.success(ok); setReason(''); onDone() }
    catch (e) { toast.error(apiMessage(e, 'Could not complete the step.')) }
    finally { setBusy(false) }
  }
  const decide = (decision: 'approved' | 'returned') => act(
    () => api.post(`/v1/approvals/${r.approval_request_id}/decide`, { decision, reason: reason.trim() || undefined }),
    decision === 'approved' ? 'Approved — the release has landed.' : 'Returned — nothing landed; the release is closed.')
  const lbl = 'mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5'
  return (
    <div className="px-5 pb-5 pt-2 bg-[var(--color-bg-2)] space-y-5 text-[12.5px]">
      <div className="grid sm:grid-cols-3 lg:grid-cols-6 gap-3 tabular-nums">
        {([['rows in file', s.rows_in_file], ['added', s.added], ['revised by publisher', s.revised], ['recomputed (ours)', s.recomputed], ['unchanged', s.unchanged], ['held, not in file', s.held_not_in_file]] as const).map(([k, v]) => (
          <div key={k}><div className={lbl}>{k}</div><div className="mono text-[15px] text-[var(--color-ink)]">{num(v, 0)}</div></div>
        ))}
      </div>
      {s.reader_changed_since_last_landed && <div className="text-[12px] text-[var(--color-warn)]">The reading rules changed since the last landed release ({s.last_landed_reader} → {r.reader}): rows added or recomputed here can come from our reading (more countries, a new crop mapping), not from the publisher.</div>}
      <div className="text-[11.5px] text-[var(--color-faint)] max-w-[90ch]">Revised: the publisher changed its production or area for a year already held. Recomputed: only our derived yield or year-on-year changed (one stated rounding rule). Held but not in the file: kept, never deleted.</div>

      <div className="grid lg:grid-cols-2 gap-5">
        <div className="overflow-x-auto">
          <div className={lbl}>By commodity</div>
          <table className="w-full tabular-nums"><thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left"><th className="font-normal py-1">Commodity</th><th className="font-normal text-right">Added</th><th className="font-normal text-right">Revised</th><th className="font-normal text-right">Recomputed</th><th className="font-normal text-right">New years</th></tr></thead>
            <tbody>{Object.entries(s.by_commodity).map(([c, b]) => (
              <tr key={c} className="border-t border-[var(--color-line)]"><td className="py-1 text-[var(--color-ink)]">{c}</td><td className="text-right mono">{b.added}</td><td className="text-right mono">{b.revised}</td><td className="text-right mono">{b.recomputed}</td><td className="text-right mono">{b.years_new.join(', ') || '—'}</td></tr>
            ))}</tbody></table>
        </div>
        <div className="space-y-4">
          <div>
            <div className={lbl}>Largest revisions by the publisher</div>
            {s.largest_revisions.length === 0 ? <div className="text-[var(--color-faint)]">None — no year already held was revised.</div>
              : s.largest_revisions.map((v, i) => <div key={i} className="mono text-[11.5px] text-[var(--color-mute)]">{v.commodity} {v.country} {v.year}: {num(v.production_before)} → {num(v.production_now)} t ({v.change_pct > 0 ? '+' : ''}{v.change_pct}%)</div>)}
          </div>
          <div>
            <div className={lbl}>Calibrations that may be affected</div>
            {s.calibrations_may_be_affected.length === 0 ? <div className="text-[var(--color-faint)]">None — no revised or added year falls in a calibration's window.</div>
              : <>{s.calibrations_may_be_affected.map((f, i) => <div key={i} className="mono text-[11.5px] text-[var(--color-mute)]">{f.commodity} · {f.origin} · {f.hazard_driver} ({f.baseline_from}–{f.baseline_to}): years {f.changed_years.join(', ')}</div>)}
                  <div className="text-[11px] text-[var(--color-faint)] mt-1">A calibration records its years, not its source series — listed for a refit check, never changed here.</div></>}
          </div>
        </div>
      </div>

      {kinds.length > 0 && <div className="flex gap-1.5">
        {kinds.map(k => (
          <button key={k} onClick={() => setKind(k)}
            className={`px-3 py-1 rounded-lg text-[12px] border transition ${shown === k ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            {k} · {num(r.summary[k], 0)}</button>))}
      </div>}
      <div className="overflow-x-auto max-h-80 overflow-y-auto border border-[var(--color-line)] rounded-lg">
        <table className="w-full tabular-nums text-[11.5px]"><thead className="sticky top-0 bg-[var(--color-bg-2)]"><tr className="text-[var(--color-faint)] mono text-[10px] uppercase text-left">
          <th className="font-normal px-2 py-1">Change</th><th className="font-normal px-2">Commodity</th><th className="font-normal px-2">Origin</th><th className="font-normal px-2">Year</th>
          <th className="font-normal px-2 text-right">Production t</th><th className="font-normal px-2 text-right">Area ha</th><th className="font-normal px-2 text-right">Yield t/ha</th><th className="font-normal px-2 text-right">YoY %</th></tr></thead>
          <tbody>{(rows.data?.rows ?? []).map((x, i) => (
            <tr key={i} className="border-t border-[var(--color-line)]">
              <td className="px-2 py-0.5 mono">{x.change}</td><td className="px-2">{x.commodity}</td><td className="px-2 mono">{x.country}</td><td className="px-2 mono">{x.season_year}</td>
              <Cell now={x.production_tonnes} before={x.held_before?.production_tonnes} d={1} />
              <Cell now={x.area_harvested_ha} before={x.held_before?.area_harvested_ha} d={1} />
              <Cell now={x.yield_tonnes_ha} before={x.held_before?.yield_tonnes_ha} d={4} />
              <Cell now={x.yoy_change_pct} before={x.held_before?.yoy_change_pct} d={2} />
            </tr>))}</tbody></table>
        {rows.data && rows.data.rows.length >= 500 && <div className="px-2 py-1 text-[11px] text-[var(--color-faint)]">first 500 of {num(r.summary[shown as 'added'], 0)} {shown} rows shown</div>}
      </div>

      <div className="mono text-[10.5px] text-[var(--color-faint)] break-all">{r.origin_url} · last modified {r.last_modified ?? '—'} · sha-256 {r.file_sha256}</div>

      {r.status === 'staged' && (
        <div className="space-y-2">
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} placeholder="What you reviewed (kept with the release) — or why it is rejected"
            className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 outline-none focus:border-[var(--color-sky)]" />
          <div className="flex gap-2">
            <Button variant="primary" disabled={busy || reason.trim().length < 10} onClick={() => act(() => api.post(`/v1/ops/reference-releases/${r.release_id}/propose`, { reason: reason.trim() }), 'Proposed — a second operator decides.')}>Propose landing</Button>
            <Button variant="ghost" disabled={busy || reason.trim().length < 10} onClick={() => act(() => api.post(`/v1/ops/reference-releases/${r.release_id}/reject`, { reason: reason.trim() }), 'Rejected — nothing landed.')}>Reject</Button>
          </div>
        </div>
      )}
      {r.status === 'proposed' && (
        <div className="space-y-2">
          <div className="text-[var(--color-mute)]">Proposed by <b className="text-[var(--color-ink)]">{r.proposed_by}</b> on {day(r.proposed_at)}: “{r.review}”</div>
          {mine ? <div className="text-[var(--color-faint)]">You proposed this release — a second operator decides it.</div> : <>
            <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} placeholder="Your decision note (kept with the release)"
              className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 outline-none focus:border-[var(--color-sky)]" />
            <div className="flex gap-2">
              <Button variant="primary" disabled={busy} onClick={() => decide('approved')}>Approve — land the release</Button>
              <Button variant="ghost" disabled={busy} onClick={() => decide('returned')}>Return — do not land</Button>
            </div></>}
        </div>
      )}
      {(r.status === 'landed' || r.status === 'rejected') && (
        <div className="text-[var(--color-mute)]">{r.status === 'landed' ? `Landed ${day(r.landed_at)}` : `Closed ${day(r.decided_at)}`}{r.decided_by ? ` by ${r.decided_by}` : ''}{r.proposed_by ? ` · proposed by ${r.proposed_by}` : ''}{r.decision_reason ? ` · “${r.decision_reason}”` : ''}</div>
      )}
    </div>
  )
}

// a value as the file states it; where it differs from the value held, the held value beside it (struck through)
function Cell({ now, before, d }: { now: number | null; before: number | null | undefined; d: number }) {
  const changed = before !== undefined && (before == null) !== (now == null) || (before != null && now != null && Math.abs(before - now) > 1e-9)
  return (
    <td className="px-2 text-right mono whitespace-nowrap">
      {changed && <span className="line-through text-[var(--color-faint)] mr-1.5">{num(before ?? null, d)}</span>}
      <span style={{ color: changed ? 'var(--color-warn)' : undefined }}>{num(now, d)}</span>
    </td>
  )
}

// How many people approve a platform change (E150): 2 = one proposes, another approves; 1 = the platform's system account
// proposes (it can never sign in) and one person approves — stated when the organisation has a single approver.
interface Policy { action_key: string; label: string; human_approvers: number; updated_at?: string | null; updated_by?: string | null }
function ApproverPolicy() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['platform-policy'], queryFn: () => api.get<{ policies: Policy[] }>('/v1/ops/reference-releases/policy') })
  const [edit, setEdit] = useState<string | null>(null)
  const [n, setN] = useState(2)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const save = async (key: string) => {
    setBusy(true)
    try {
      await api.put('/v1/ops/reference-releases/policy', { action_key: key, human_approvers: n, reason: reason.trim() })
      toast.success('Approval policy saved.'); setEdit(null); setReason('')
      qc.invalidateQueries({ queryKey: ['platform-policy'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the policy.')) }
    finally { setBusy(false) }
  }
  return (
    <Card className="p-5">
      <SectionHead hint="who must approve before a change reaches customers" className="mb-3">Approvers</SectionHead>
      <div className="space-y-2 text-[12.5px]">
        {(q.data?.policies ?? []).map(p => (
          <div key={p.action_key} className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-[var(--color-ink)] min-w-[18rem]">{p.label}</span>
            <span className="text-[var(--color-mute)]">{p.human_approvers === 1 ? 'one person approves — the platform proposes' : 'two people — one proposes, another approves'}</span>
            {p.updated_by && <span className="mono text-[10.5px] text-[var(--color-faint)]">set by {p.updated_by} · {String(p.updated_at).slice(0, 10)}</span>}
            {edit !== p.action_key
              ? <Button variant="ghost" onClick={() => { setEdit(p.action_key); setN(p.human_approvers) }}>Change</Button>
              : <div className="flex flex-wrap items-center gap-2 w-full">
                  <select value={n} onChange={e => setN(Number(e.target.value))} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5">
                    <option value={2}>Two people</option><option value={1}>One person (single approver)</option></select>
                  <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Why (kept in the audit record)"
                    className="flex-1 min-w-[16rem] bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 outline-none focus:border-[var(--color-sky)]" />
                  <Button variant="primary" disabled={busy || reason.trim().length < 10} onClick={() => save(p.action_key)}>Save</Button>
                  <Button variant="ghost" onClick={() => setEdit(null)}>Cancel</Button>
                </div>}
          </div>
        ))}
      </div>
    </Card>
  )
}

