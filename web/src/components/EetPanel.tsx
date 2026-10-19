import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSpreadsheet, Download, Send, Table2, ChevronRight } from 'lucide-react'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button, SectionHead } from './ui'
import { apiMessage } from './ShareClasses'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Ring, SidePanel, TONE } from './sfdr/visuals'
import { EET_USE, fmtDate } from './sfdr/words'

// European ESG Template (EET) — the file a fund manager sends distributors and insurers: one row per share class, every
// field of the template in order. The platform fills what it computes from the book (identity, SFDR category, value,
// every adverse-impact figure with its coverage); the manager answers the rest. Prepare → a second person approves in
// Approvals → the version is published and downloads. A change in the book shows as "changed since published".

interface Gap { field: string; section: string; definition: string; codification: string; answerable: boolean; isins: string[] }
interface Check { issuer_id: string; issuer: string; field: string; label: string; reported: number; estimate: number; msg: Message; fund_name: string }
interface Driver { field: string; definition: string | null; kind: string; codification: string; choices: string[]; scope: 'organisation' | 'fund'; settles: string[] }
interface Draft {
  uses: string[]; note_msgs: Message[]; data_checks: Check[]; funds: Record<string, { statement: string; reference_year: number | null; fund_name: string }>
  rows: { fund_id: string; isin: string; n_filled: number }[]
  completeness: { n_rows: number; n_required: number; n_filled: number; filled_pct: number | null; n_blocking: number; blocking: Gap[]; n_to_review: number; to_review: string[]; review_drivers: Driver[]; n_data_checks: number; ready: boolean }
}
interface Field { name: string; kind: string; choices: string[]; multi: boolean; scope: 'organisation' | 'fund'; codification: string; definition?: string }
interface Version { publication_id: string; version: number; status: string; uses: string[]; reference_date: string; prepared_by: string | null; prepared_at: string; decided_by: string | null; n_share_classes: number; decision_reason: string | null }
interface Changes { published: { version: number } | null; up_to_date?: boolean; added_share_classes?: string[]; removed_share_classes?: string[]; n_changed_fields?: number }
type Refused = { field: string; msg: Message }

const box = 'bg-[var(--color-panel)] border border-[var(--color-line-2)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]'
const fieldName = (name: string) => name.split('_').slice(1).join(' ')        // the field's printed name, without its number
const versionName = (n: number) => `Version ${n}`
const STATUS: Record<string, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  published: { label: 'Published', tone: 'good' }, pending: { label: 'Awaiting approval', tone: 'warn' }, rejected: { label: 'Rejected', tone: 'bad' },
}

export default function EetPanel() {
  const qc = useQueryClient()
  const [uses, setUses] = useState<string[]>(['entity'])
  const u = uses.join(',')
  const draft = useQuery({ queryKey: ['eet-draft', u], queryFn: () => api.get<Draft>(`/v1/eet/draft?uses=${u}`), enabled: uses.length > 0 })
  const fields = useQuery({ queryKey: ['eet-fields', u], queryFn: () => api.get<{ fields: Field[] }>(`/v1/eet/fields?uses=${u}&only=required`), enabled: uses.length > 0 })
  const versions = useQuery({ queryKey: ['eet-versions'], queryFn: () => api.get<{ versions: Version[] }>('/v1/eet/versions') })
  const changes = useQuery({ queryKey: ['eet-changes'], queryFn: () => api.get<Changes>('/v1/eet/changes') })
  const [panel, setPanel] = useState<'answers' | 'checks' | null>(null)
  const [busy, setBusy] = useState(false)
  const d = draft.data
  const refresh = () => ['eet-draft', 'eet-versions', 'eet-changes'].forEach(k => qc.invalidateQueries({ queryKey: [k] }))

  const prepare = async () => {
    setBusy(true)
    try {
      const v = await api.post<Version>('/v1/eet/versions', { uses })
      toast.success(`${versionName(v.version)} prepared — a second person approves it in Approvals.`); refresh()
    } catch (e) { toast.error(apiMessage(e, 'Could not prepare the template.')) } finally { setBusy(false) }
  }
  const c = d?.completeness
  const ch = changes.data
  const toAnswer = (c?.n_blocking ?? 0) + (c?.review_drivers.length ?? 0)
  const about = {
    title: 'European ESG Template', sections: [
      { heading: HEADING.shows, body: 'The file you send distributors and insurers: one row per share class, every field of the template. We fill what we compute from your holdings; you answer the rest. A second person approves each version before it is published.' },
      { heading: HEADING.sources, body: d ? <ul className="list-disc pl-4 space-y-0.5">{Object.values(d.funds).map(f => <li key={f.fund_name}>{f.fund_name}: adverse-impact figures from the {f.statement === 'filed' ? `${f.reference_year} record` : 'live figures'}</li>)}</ul> : 'Your funds\' adverse-impact figures.' },
      { heading: 'Standard', body: 'FinDatEx European ESG Template, version 1.1.3.' },
    ],
  }

  return (
    <Card className="p-0 overflow-hidden">
      <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <SectionHead icon={Table2}>European ESG Template</SectionHead>
          <InfoButton compact details={about} />
        </div>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="What the file is for">
          {EET_USE.map(x => (
            <label key={x.k} className={`text-[11.5px] px-2 py-1 rounded-md border cursor-pointer ${uses.includes(x.k) ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-faint)]'}`}>
              <input type="checkbox" className="sr-only" checked={uses.includes(x.k)} onChange={e => setUses(e.target.checked ? [...uses, x.k] : uses.filter(y => y !== x.k))} />{x.label}
            </label>))}
        </div>
      </div>

      {ch?.published && ch.up_to_date === false && (
        <div className="px-5 py-2 flex items-center gap-2" style={{ background: 'color-mix(in oklab, var(--color-warn) 8%, transparent)' }}>
          <StatusChip tone="warn" label={`Changed since ${versionName(ch.published.version)}`} />
          <InfoButton compact details={{ title: 'What changed', sections: [{ heading: HEADING.shows, body: (
            <ul className="list-disc pl-4 space-y-0.5">
              <li>{ch.n_changed_fields ?? 0} figure(s) changed</li>
              {!!ch.added_share_classes?.length && <li>{ch.added_share_classes.length} new share class(es)</li>}
              {!!ch.removed_share_classes?.length && <li>{ch.removed_share_classes.length} share class(es) closed</li>}
            </ul>) }, { heading: 'What you can do', body: 'Prepare the next version.' }] }} />
        </div>)}

      <div className="p-5 space-y-4">
        {!d ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div>
          : d.rows.length === 0 ? <div className="text-[12.5px] text-[var(--color-mute)]">No active share classes yet — add them on each fund's page.</div>
          : <>
            <div className="flex flex-wrap items-center gap-6">
              <Ring value={c?.filled_pct ?? 0} tone={c?.ready ? TONE.good : TONE.warn} />
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-[12px] text-[var(--color-mute)]">
                <span><b className="block text-[18px] font-semibold tabular-nums text-[var(--color-ink)]">{d.rows.length}</b>share classes</span>
                <span><b className="block text-[18px] font-semibold tabular-nums" style={{ color: c?.n_blocking ? 'var(--color-warn)' : 'var(--color-good)' }}>{c?.n_blocking ?? 0}</b>to answer</span>
                <span><b className="block text-[18px] font-semibold tabular-nums text-[var(--color-ink)]">{c?.n_to_review ?? 0}</b>if they apply</span>
                <span><b className="block text-[18px] font-semibold tabular-nums" style={{ color: d.data_checks.length ? 'var(--color-warn)' : 'var(--color-ink)' }}>{d.data_checks.length}</b>figures to check</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {toAnswer > 0 && <Button variant="ghost" onClick={() => setPanel('answers')}>Answer fields <ChevronRight size={13} /></Button>}
              {d.data_checks.length > 0 && <Button variant="ghost" onClick={() => setPanel('checks')}>Check figures <ChevronRight size={13} /></Button>}
              <Button variant="primary" onClick={prepare} disabled={busy || !c?.ready}><Send size={13} /> Prepare version for approval</Button>
              {d.note_msgs.length > 0 && <InfoButton label="How the figures are filled" details={{ title: 'How the figures are filled', sections: d.note_msgs.map(m => ({ heading: m.label, body: [m.detail?.what, m.detail?.why].filter(Boolean).join(' ') })) }} />}
            </div>
          </>}

        {(versions.data?.versions.length ?? 0) > 0 && (
          <div className="border-t border-[var(--color-line)] pt-3">
            <div className="text-[12.5px] font-medium text-[var(--color-ink)] mb-1.5">Versions</div>
            <ol className="relative border-l border-[var(--color-line-2)] ml-1.5 space-y-2.5">{versions.data!.versions.map(v => {
              const s = STATUS[v.status] ?? { label: 'Recorded', tone: 'neutral' as const }
              return (
                <li key={v.publication_id} className="pl-4 relative flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                  <span className="absolute -left-[5px] top-1.5 w-2 h-2 rounded-full" style={{ background: s.tone === 'good' ? 'var(--color-good)' : s.tone === 'warn' ? 'var(--color-warn)' : 'var(--color-faint)' }} />
                  <span className="text-[var(--color-ink)]">{versionName(v.version)}</span>
                  <StatusChip tone={s.tone} label={s.label} />
                  <span className="text-[var(--color-faint)]">{fmtDate(v.reference_date)} · {v.n_share_classes} share class{v.n_share_classes === 1 ? '' : 'es'}</span>
                  <InfoButton compact details={{ title: versionName(v.version), sections: [
                    { heading: 'Prepared', body: `${v.prepared_by ?? '—'}, ${fmtDate(v.prepared_at)}` },
                    ...(v.decided_by ? [{ heading: v.status === 'published' ? 'Approved' : 'Decided', body: v.decided_by }] : []),
                    ...(v.decision_reason ? [{ heading: 'Reason given', body: v.decision_reason }] : []),
                    { heading: 'Uses', body: v.uses.map(x => EET_USE.find(e => e.k === x)?.label ?? x).join(', ') },
                  ] }} />
                  {v.status !== 'rejected' && (['xlsx', 'csv'] as const).map(f => (
                    <button key={f} onClick={() => download(`/v1/eet/versions/${v.publication_id}/export?format=${f}`, `EET_v${v.version}.${f}`).catch(() => toast.error('Could not download.'))}
                      className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">
                      {f === 'xlsx' ? <FileSpreadsheet size={12} /> : <Download size={12} />}{f === 'xlsx' ? 'Excel' : 'CSV'}{v.status === 'pending' ? ' (draft)' : ''}</button>))}
                </li>)
            })}</ol>
          </div>)}
      </div>

      {panel === 'answers' && d && <AnswerPanel d={d} fields={fields.data?.fields ?? []} onClose={() => setPanel(null)} onSaved={refresh} />}
      {panel === 'checks' && d && <ChecksPanel checks={d.data_checks} onClose={() => setPanel(null)} onSaved={refresh} />}
    </Card>
  )
}

// the fields still to answer, each with its definition as the template prints it: questions that settle conditional
// fields first, then the mandatory fields, then the conditional ones to answer if they apply
function AnswerPanel({ d, fields, onClose, onSaved }: { d: Draft; fields: Field[]; onClose: () => void; onSaved: () => void }) {
  const [vals, setVals] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [refused, setRefused] = useState<Refused[]>([])
  const fmeta = Object.fromEntries(fields.map(f => [f.name, f]))
  const fundOf = Object.fromEntries(d.rows.map(r => [r.isin, r.fund_id]))
  const allFunds = [...new Set(d.rows.map(r => r.fund_id))]
  const c = d.completeness
  type Input = { field: string; definition: string; m: Field; fid: string | null; key: string; kind: 'first' | 'required' | 'review'; settles: number }
  const inputs: Input[] = [
    ...c.review_drivers.flatMap(dr => (dr.scope === 'organisation' ? [null] : allFunds).map(fid => ({
      field: dr.field, definition: dr.definition ?? '', m: { name: dr.field, kind: dr.kind, choices: dr.choices, multi: false, scope: dr.scope, codification: dr.codification },
      fid, key: `${dr.field}|${fid ?? ''}`, kind: 'first' as const, settles: dr.settles.length }))),
    ...c.blocking.flatMap(g => {
      const m = fmeta[g.field]
      if (!g.answerable || !m) return []
      return (m.scope === 'organisation' ? [null] : [...new Set(g.isins.map(i => fundOf[i]))]).map(fid => ({
        field: g.field, definition: g.definition, m, fid, key: `${g.field}|${fid ?? ''}`, kind: 'required' as const, settles: 0 }))
    }),
    ...c.to_review.flatMap(name => {
      const m = fmeta[name]
      if (!m) return []
      return (m.scope === 'organisation' ? [null] : allFunds).map(fid => ({
        field: name, definition: m.definition ?? '', m, fid, key: `${name}|${fid ?? ''}`, kind: 'review' as const, settles: 0 }))
    }),
  ]
  const save = async () => {
    setBusy(true)
    try {
      const byTarget: Record<string, Record<string, string>> = {}
      for (const i of inputs) if (vals[i.key]?.trim()) (byTarget[i.fid ?? ''] ??= {})[i.field] = vals[i.key]
      let out: Refused[] = []
      for (const [fid, values] of Object.entries(byTarget)) {
        const r = await api.put<{ refused: Refused[] }>('/v1/eet/answers', { fund_id: fid || undefined, values })
        out = out.concat(r.refused)
      }
      setRefused(out)
      if (out.length) toast.error(`${out.length} answer(s) not saved.`)
      else { toast.success('Answers saved.'); setVals({}) }
      onSaved()
    } catch (e) { toast.error(apiMessage(e, 'Could not save the answers.')) } finally { setBusy(false) }
  }
  const TAG = { first: 'Answer first', required: 'Required', review: 'If it applies' } as const
  return (
    <SidePanel title="Fields to answer" wide onClose={onClose}
      about={{ title: 'Fields to answer', sections: [{ heading: HEADING.read, body: 'Questions marked "Answer first" decide whether the conditional fields apply. Required fields must have a value before a version can be prepared. A figure from your holdings always wins over an answer.' }] }}>
      <div className="space-y-3">
        {refused.length > 0 && (
          <div className="rounded-lg border p-3 space-y-1" style={{ borderColor: 'color-mix(in oklab, var(--color-bad) 45%, transparent)' }}>
            {refused.map(r => <div key={r.field} className="text-[12px] text-[var(--color-mute)] flex items-center gap-1.5">{fieldName(r.field)}: <MessageLine m={r.msg} className="text-[var(--color-bad)]" /></div>)}
          </div>)}
        <div className="rounded-xl border border-[var(--color-line-2)] divide-y divide-[var(--color-line)]">
          {inputs.map(i => (
            <div key={i.key} className="px-3 py-2.5 flex flex-wrap items-center gap-3">
              <div className="flex-1 min-w-[240px]">
                <div className="flex flex-wrap items-center gap-1.5 text-[12.5px] text-[var(--color-ink)]">
                  <StatusChip tone={i.kind === 'required' ? 'warn' : 'neutral'} label={i.kind === 'first' && i.settles ? `${TAG.first} · settles ${i.settles}` : TAG[i.kind]} />
                  {fieldName(i.field)}{i.fid && Object.keys(d.funds).length > 1 && <span className="text-[var(--color-faint)]"> · {d.funds[i.fid]?.fund_name}</span>}
                  {i.definition && <InfoButton compact details={{ title: fieldName(i.field), sections: [{ heading: 'Definition', body: i.definition }, { heading: 'Format', body: i.m.codification }] }} />}
                </div>
              </div>
              {i.m.kind === 'choice' && !i.m.multi
                ? <select value={vals[i.key] ?? ''} onChange={e => setVals({ ...vals, [i.key]: e.target.value })} className={box} aria-label={fieldName(i.field)}>
                    <option value="">—</option>{i.m.choices.map(o => <option key={o}>{o}</option>)}</select>
                : <input value={vals[i.key] ?? ''} onChange={e => setVals({ ...vals, [i.key]: e.target.value })} aria-label={fieldName(i.field)}
                    className={`${box} ${i.m.kind === 'text' ? 'w-64' : 'w-36'}`} />}
            </div>))}
        </div>
        <Button onClick={save} disabled={busy || !Object.values(vals).some(v => v.trim())}>Save answers</Button>
      </div>
    </SidePanel>
  )
}

// company figures that look like a unit slip: correct them in the data, or confirm each as right with the reason
function ChecksPanel({ checks, onClose, onSaved }: { checks: Check[]; onClose: () => void; onSaved: () => void }) {
  const [why, setWhy] = useState<Record<string, string>>({})
  const confirm = async (k: Check) => {
    const key = `${k.issuer_id}|${k.field}`
    try {
      await api.post('/v1/eet/data-checks/confirm', { issuer_id: k.issuer_id, field: k.field, value: k.reported, reason: why[key] ?? '' })
      toast.success(`${k.issuer}: ${k.label} confirmed.`); setWhy({ ...why, [key]: '' }); onSaved()
    } catch (e) { toast.error(apiMessage(e, 'Could not confirm the figure.')) }
  }
  return (
    <SidePanel title="Figures to check" onClose={onClose}
      about={{ title: 'Figures to check', sections: [{ heading: HEADING.read, body: 'A company figure far from its sector or country average often comes from a unit slip. Correct it in your holdings upload or data feed — or confirm it is right, with the reason. A version is prepared only when none is open.' }] }}>
      <div className="space-y-3">
        {checks.map(k => { const key = `${k.issuer_id}|${k.field}`; return (
          <div key={key} className="rounded-lg border border-[var(--color-line)] p-3 space-y-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12.5px]">
              <span className="text-[var(--color-ink)]">{k.issuer} · {k.label}</span>
              <span className="tabular-nums text-[var(--color-mute)]">{k.reported.toLocaleString('en-GB')}</span>
            </div>
            <MessageLine m={k.msg} className="text-[12px] text-[var(--color-warn)]" />
            <div className="flex flex-wrap gap-2">
              <input value={why[key] ?? ''} onChange={e => setWhy({ ...why, [key]: e.target.value })} placeholder="Why it is right (source, page)" aria-label="Why it is right" className={`${box} flex-1 min-w-[200px]`} />
              <Button onClick={() => confirm(k)} disabled={!(why[key] ?? '').trim()}>Confirm as right</Button>
            </div>
          </div>) })}
      </div>
    </SidePanel>
  )
}
