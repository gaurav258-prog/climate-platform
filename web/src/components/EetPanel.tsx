import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, Download, AlertTriangle, CheckCircle2, Clock, Send } from 'lucide-react'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead } from './ui'
import { apiMessage } from './ShareClasses'

// European ESG Template (EET) — the file a fund manager sends distributors and insurers: one row per share class,
// every FinDatEx field in order. Tellumen fills what it computes from the book (identity, SFDR article, NAV, every PAI
// figure with coverage and eligible assets); the manager answers the rest here. Prepare → a second person approves in
// Approvals → the version is published and downloads. A change in the book shows as "changed since published".

const USES: { k: string; label: string }[] = [
  { k: 'entity', label: 'SFDR entity (PAI)' }, { k: 'periodic', label: 'SFDR periodic' },
  { k: 'precontractual', label: 'SFDR pre-contractual' }, { k: 'mifid', label: 'MiFID' }, { k: 'idd', label: 'IDD' },
]
interface Gap { field: string; section: string; definition: string; codification: string; answerable: boolean; isins: string[] }
interface Check { issuer_id: string; issuer: string; field: string; label: string; reported: number; estimate: number; basis: string; why: string; fund_name: string }
interface Draft {
  uses: string[]; notes: string[]; data_checks: Check[]; funds: Record<string, { statement: string; reference_year: number | null; fund_name: string }>
  rows: { fund_id: string; isin: string; n_filled: number }[]
  completeness: { n_rows: number; n_required: number; n_filled: number; filled_pct: number | null; n_blocking: number; blocking: Gap[]; n_to_review: number; to_review: string[]; review_drivers: Driver[]; n_data_checks: number; ready: boolean }
}
interface Driver { field: string; definition: string | null; kind: string; codification: string; choices: string[]; scope: 'organisation' | 'fund'; settles: string[] }
interface Field { name: string; kind: string; choices: string[]; multi: boolean; scope: 'organisation' | 'fund'; codification: string }
interface Version { publication_id: string; version: number; status: string; uses: string[]; reference_date: string; prepared_by: string | null; prepared_at: string; decided_by: string | null; n_share_classes: number; decision_reason: string | null }
interface Changes { published: { version: number } | null; up_to_date?: boolean; added_share_classes?: string[]; removed_share_classes?: string[]; n_changed_fields?: number }

const box = 'bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]'
const label = (name: string) => name.split('_').slice(1).join(' ')

export default function EetPanel() {
  const qc = useQueryClient()
  const [uses, setUses] = useState<string[]>(['entity'])
  const u = uses.join(',')
  const draft = useQuery({ queryKey: ['eet-draft', u], queryFn: () => api.get<Draft>(`/v1/eet/draft?uses=${u}`), enabled: uses.length > 0 })
  const fields = useQuery({ queryKey: ['eet-fields', u], queryFn: () => api.get<{ fields: Field[] }>(`/v1/eet/fields?uses=${u}&only=required`), enabled: uses.length > 0 })
  const versions = useQuery({ queryKey: ['eet-versions'], queryFn: () => api.get<{ versions: Version[] }>('/v1/eet/versions') })
  const changes = useQuery({ queryKey: ['eet-changes'], queryFn: () => api.get<Changes>('/v1/eet/changes') })
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [why, setWhy] = useState<Record<string, string>>({})
  const d = draft.data
  const fmeta = Object.fromEntries((fields.data?.fields ?? []).map(f => [f.name, f]))
  const fundOf = Object.fromEntries((d?.rows ?? []).map(r => [r.isin, r.fund_id]))
  const refresh = () => ['eet-draft', 'eet-versions', 'eet-changes'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))

  // one input per (field, scope target): organisation fields once, fund fields once per fund they're missing for
  // questions that settle Conditional fields come first: answering them turns "if it applies" into required / not needed
  const driverInputs = (d?.completeness.review_drivers ?? []).flatMap(dr => {
    const g: Gap = { field: dr.field, section: '', definition: dr.definition ?? '', codification: dr.codification, answerable: true, isins: [] }
    const m: Field = { name: dr.field, kind: dr.kind, choices: dr.choices, multi: false, scope: dr.scope, codification: dr.codification }
    const funds = dr.scope === 'organisation' ? [null] : [...new Set((d?.rows ?? []).map(r => r.fund_id))]
    return funds.map(fid => ({ g, m, fid, key: `${dr.field}|${fid ?? ''}`, review: false, driver: dr.settles.length }))
  })
  const inputs = driverInputs.concat((d?.completeness.blocking ?? []).flatMap(g => {
    const m = fmeta[g.field]
    if (!g.answerable || !m) return []
    const funds = m.scope === 'organisation' ? [null] : [...new Set(g.isins.map(i => fundOf[i]))]
    return funds.map(fid => ({ g, m, fid, key: `${g.field}|${fid ?? ''}`, review: false, driver: 0 }))
  })).concat((d?.completeness.to_review ?? []).flatMap(name => {
    // conditional fields whose condition depends on another answer (e.g. a Taxonomy commitment): answer if they apply
    const m = fmeta[name]
    if (!m || m.kind === undefined) return []
    const g: Gap = { field: name, section: '', definition: '', codification: m.codification, answerable: true, isins: [] }
    const funds = m.scope === 'organisation' ? [null] : [...new Set((d?.rows ?? []).map(r => r.fund_id))]
    return funds.map(fid => ({ g, m, fid, key: `${name}|${fid ?? ''}`, review: true, driver: 0 }))
  }))
  const save = async () => {
    setBusy(true)
    try {
      const byTarget: Record<string, Record<string, string>> = {}
      for (const i of inputs) if (vals[i.key]?.trim()) (byTarget[i.fid ?? ''] ??= {})[i.g.field] = vals[i.key]
      let refused: { field: string; reason: string }[] = []
      for (const [fid, values] of Object.entries(byTarget)) {
        const r = await api.put<{ refused: { field: string; reason: string }[] }>('/v1/eet/answers', { fund_id: fid || undefined, values })
        refused = refused.concat(r.refused)
      }
      if (refused.length) toast.error(`${refused.length} answer(s) not saved — ${label(refused[0].field)}: ${refused[0].reason}`)
      else toast.success('Answers saved.')
      setVals({}); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not save the answers.')) } finally { setBusy(false) }
  }
  const prepare = async () => {
    setBusy(true)
    try {
      const v = await api.post<Version>('/v1/eet/versions', { uses })
      toast.success(`EET v${v.version} prepared — a second person approves it in Approvals.`); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not prepare the EET.')) } finally { setBusy(false) }
  }
  const confirmFigure = async (k: Check) => {
    const key = `${k.issuer_id}|${k.field}`
    try {
      await api.post('/v1/eet/data-checks/confirm', { issuer_id: k.issuer_id, field: k.field, value: k.reported, reason: why[key] ?? '' })
      toast.success(`${k.issuer}: ${k.label} confirmed.`); setWhy({ ...why, [key]: '' }); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not confirm the figure.')) }
  }
  const c = d?.completeness
  const ch = changes.data

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3">
        <SectionHead hint="FinDatEx EET V1.1.3 · for distributors and insurers">European ESG Template</SectionHead>
        <div className="flex flex-wrap gap-1.5">
          {USES.map(x => (
            <label key={x.k} className={`mono text-[10.5px] px-2 py-1 rounded-md border cursor-pointer ${uses.includes(x.k) ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]'}`}>
              <input type="checkbox" className="hidden" checked={uses.includes(x.k)} onChange={e => setUses(e.target.checked ? [...uses, x.k] : uses.filter(y => y !== x.k))} />{x.label}
            </label>))}
        </div>
      </div>

      {ch?.published && ch.up_to_date === false && (
        <div className="px-5 py-2 text-[12px] flex items-center gap-1.5" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' }}>
          <AlertTriangle size={13} /> Changed since v{ch.published.version} was published — {ch.n_changed_fields ?? 0} figure(s) changed{ch.added_share_classes?.length ? `, ${ch.added_share_classes.length} new share class(es)` : ''}{ch.removed_share_classes?.length ? `, ${ch.removed_share_classes.length} closed` : ''}. Prepare the next version.
        </div>)}

      <div className="p-5 space-y-4">
        {!d ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
          : d.rows.length === 0 ? <div className="text-[12.5px] text-[var(--color-mute)]">No active share classes yet — add them on each fund's page. The EET has one row per share class.</div>
          : <>
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-[12.5px]">
              <span className="text-[var(--color-ink)]"><span className="mono tabular-nums text-[18px]">{c?.filled_pct ?? 0}%</span> of required fields filled</span>
              <span className="text-[var(--color-mute)]">{d.rows.length} share class(es) · {c?.n_blocking ? <span style={{ color: 'var(--color-warn)' }}>{c.n_blocking} still to answer</span> : <span style={{ color: 'var(--color-good)' }}>ready to prepare</span>}{c?.n_to_review ? ` · ${c.n_to_review} conditional to review` : ''}</span>
              {Object.values(d.funds).map(f => <span key={f.fund_name} className="mono text-[10.5px] text-[var(--color-faint)]">{f.fund_name}: PAI from the {f.statement === 'filed' ? `filed FY${f.reference_year} statement` : 'live draft statement'}</span>)}
            </div>
            {(d.data_checks?.length ?? 0) > 0 && (
              <div className="rounded-xl border p-3 space-y-2" style={{ borderColor: 'color-mix(in oklab, var(--color-warn) 45%, transparent)' }}>
                <div className="text-[12.5px]" style={{ color: 'var(--color-warn)' }}>
                  <AlertTriangle size={13} className="inline -mt-0.5 mr-1" />{d.data_checks.length} company figure(s) look like a unit slip. Correct the figure in your holdings upload or data feed — or confirm it is right, with the reason.
                </div>
                {d.data_checks.map(k => { const key = `${k.issuer_id}|${k.field}`; return (
                  <div key={key} className="flex flex-wrap items-center gap-2 text-[12px]">
                    <div className="flex-1 min-w-[260px]"><span className="text-[var(--color-ink)]">{k.issuer}</span> · {k.label}: <span className="mono">{k.reported}</span> <span className="text-[var(--color-faint)]">— {k.why} ({k.basis})</span></div>
                    <input value={why[key] ?? ''} onChange={e => setWhy({ ...why, [key]: e.target.value })} placeholder="why it is right (source, page)" className={`${box} w-56`} />
                    <Button onClick={() => confirmFigure(k)} disabled={!(why[key] ?? '').trim()}>Confirm as right</Button>
                  </div>) })}
              </div>)}
            {inputs.length > 0 && (
              <div className="rounded-xl border border-[var(--color-line-2)] divide-y divide-[var(--color-line)]">
                {inputs.map(({ g, m, fid, key, review, driver }) => (
                  <div key={key} className="px-3 py-2 flex flex-wrap items-center gap-3">
                    <div className="flex-1 min-w-[260px]">
                      <div className="text-[12.5px] text-[var(--color-ink)]">{review && <span className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mr-1.5">if it applies</span>}{driver > 0 && <span className="mono text-[9.5px] uppercase tracking-wide mr-1.5" style={{ color: 'var(--color-sky)' }}>answer first · settles {driver}</span>}{label(g.field)}{fid && Object.keys(d.funds).length > 1 ? <span className="text-[var(--color-faint)]"> · {d.funds[fid]?.fund_name}</span> : ''}</div>
                      <div className="text-[11px] text-[var(--color-faint)] line-clamp-2" title={g.definition}>{g.definition}</div>
                    </div>
                    {m.kind === 'choice' && !m.multi
                      ? <select value={vals[key] ?? ''} onChange={e => setVals({ ...vals, [key]: e.target.value })} className={`${box} mono`}>
                          <option value="">—</option>{m.choices.map(o => <option key={o}>{o}</option>)}</select>
                      : <input value={vals[key] ?? ''} onChange={e => setVals({ ...vals, [key]: e.target.value })} placeholder={m.codification}
                          title={m.codification} className={`${box} ${m.kind === 'text' ? 'w-64' : 'w-36 mono'}`} />}
                  </div>))}
              </div>)}
            {d.notes.length > 0 && <ul className="text-[11px] text-[var(--color-faint)] list-disc pl-4 space-y-0.5">{d.notes.map(n => <li key={n}>{n}</li>)}</ul>}
            <div className="flex flex-wrap gap-2">
              {inputs.length > 0 && <Button onClick={save} disabled={busy || !Object.values(vals).some(v => v.trim())}>Save answers</Button>}
              <Button variant="primary" onClick={prepare} disabled={busy || !c?.ready}><Send size={13} /> Prepare version for approval</Button>
            </div>
            {!c?.ready && <div className="text-[11px] text-[var(--color-faint)]">Answer the mandatory fields{c?.n_data_checks ? ' and resolve the flagged figures' : ''} above to prepare a version; a second person then approves it in Approvals before it is published.</div>}
          </>}

        {(versions.data?.versions.length ?? 0) > 0 && (
          <div className="border-t border-[var(--color-line)] pt-3">
            <div className="mono text-[9.5px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5">Versions</div>
            <div className="divide-y divide-[var(--color-line)]">{versions.data!.versions.map(v => (
              <div key={v.publication_id} className="py-2 flex flex-wrap items-center gap-3 text-[12.5px]">
                <span className="mono text-[var(--color-ink)] w-10">v{v.version}</span>
                <span className="inline-flex items-center gap-1 mono text-[10.5px] w-28" style={{ color: v.status === 'published' ? 'var(--color-good)' : v.status === 'pending' ? 'var(--color-sky)' : 'var(--color-faint)' }}>
                  {v.status === 'published' ? <CheckCircle2 size={12} /> : v.status === 'pending' ? <Clock size={12} /> : <AlertTriangle size={12} />}{v.status === 'pending' ? 'awaiting approval' : v.status}</span>
                <span className="flex-1 min-w-0 text-[var(--color-mute)] truncate">{v.n_share_classes} share class(es) · as of {v.reference_date} · prepared by {v.prepared_by ?? '—'}{v.decided_by ? ` · ${v.status === 'published' ? 'approved' : 'decided'} by ${v.decided_by}` : ''}{v.decision_reason ? ` — “${v.decision_reason}”` : ''}</span>
                {v.status !== 'rejected' && (['xlsx', 'csv'] as const).map(f => (
                  <button key={f} onClick={() => download(`/v1/eet/versions/${v.publication_id}/export?format=${f}`, `EET_v${v.version}.${f}`).catch(() => toast.error('Could not download.'))}
                    className="inline-flex items-center gap-1 mono text-[10.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">
                    {f === 'xlsx' ? <FileSpreadsheet size={12} /> : <Download size={12} />}{f.toUpperCase()}{v.status === 'pending' ? ' (draft)' : ''}</button>))}
              </div>))}
            </div>
          </div>)}
      </div>
    </Card>
  )
}
