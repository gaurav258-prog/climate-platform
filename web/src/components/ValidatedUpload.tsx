import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Upload, Download, FileSpreadsheet, CheckCircle2, Clock, ShieldCheck, Loader2, ListX } from 'lucide-react'
import { upload as uploadFile, download } from '../lib/api'
import { ControlsPanel, LandingNote, type Controls } from './IntakeControls'
import MoneyDeclaration from './MoneyDeclaration'
import MappingEditor, { MappingNote, useTemplateMappings, type MappingReport } from './MappingEditor'
import { pressable } from '../lib/pressable'
import { HEADING, InfoButton, messageDetails, type Message } from './Details'
import { PlainLead } from './ui'
import { Dialog } from './Dialog'
import { StatusChip } from './StatusChip'
import { Said, Segments, errMessage, plural } from './intake/parts'

// The one customer-data upload control, used by every sector's book (loan tape, SoV, properties, holdings, plots).
// It fronts the intake pipeline (services/intake/pipeline.py):
//   drop a file → we inspect it and run every check (nothing saved) → you import
//   every check passed → imported now · a check failed → you give a reason and it goes to a SECOND person
//   scanner unavailable → held · refused on security grounds → nothing kept
// What the server says comes as catalogue messages (msg: label on the screen, explanation behind ⓘ); the rows to fix
// open in a dialog.

interface Finding { code: string; severity: 'block' | 'warn'; message: string; msg?: Message }
interface Security { status: 'passed' | 'warned' | 'blocked'; findings: Finding[]; malware_scan?: string; malware?: string; malware_msg?: Message }
export interface ValRep {
  filename: string; n_total: number; n_valid: number; n_error: number
  errors: { row: number; problems: string[] }[]; controls?: Controls; security?: Security; mapping?: MappingReport | null
}
interface Endpoints { validate: string; upload: string; template: string; templateFile: string }
type Outcome = { state: string; message?: string; msg?: Message; batch_id?: string; approval_request_id?: string; n_uploaded?: number; controls?: Controls; notes?: Record<string, unknown> } & Record<string, unknown>
type Refusal = { error?: string; message?: string; detail?: Message['detail']; msg?: Message; controls?: Controls; security?: Security; source_columns?: string[] }

const SECURE: Message = { label: 'File checked and safe to read', detail: {
  what: 'The file’s real type is confirmed, and it carries no macros, embedded objects or hidden content.' } }

export default function ValidatedUpload({ intro, dropLabel, endpoints, onDone, renderDone, accept = '.csv,.xlsx', template, declareMoney }: {
  intro: React.ReactNode; dropLabel: string; endpoints: Endpoints; onDone: () => void
  renderDone: (res: Outcome) => React.ReactNode; accept?: string
  template?: string   // intake template key — enables column mapping for files in the customer's own layout
  declareMoney?: boolean   // a non-template upload that carries amounts: ask for their currency + book date too
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const seq = useRef(0)              // the latest check: an older one answering late is ignored (currency, then date)
  const [file, setFile] = useState<File | null>(null)
  const [rep, setRep] = useState<ValRep | null>(null)
  const [phase, setPhase] = useState<'idle' | 'checking' | 'checked' | 'importing' | 'done' | 'error'>('idle')
  const [msg, setMsg] = useState<Message | null>(null)
  const [result, setResult] = useState<Outcome | null>(null)
  const [declRows, setDeclRows] = useState('')
  const [declTotal, setDeclTotal] = useState('')
  const [reason, setReason] = useState('')
  const [rechecking, setRechecking] = useState(false)
  const [fixes, setFixes] = useState(false)          // the rows-to-fix dialog
  const { saved, reload } = useTemplateMappings(template)
  const [profileId, setProfileId] = useState('')
  const [mapping, setMapping] = useState(false)   // the mapping editor is open for this file
  // the currency of the amounts and the date the figures describe are never assumed: the server asks for them when the
  // file's amounts carry neither (a file without amounts, or with currency / book_date columns, needs no declaration)
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const declares = !!template || !!declareMoney
  const money = (): Record<string, string | undefined> => declares ? { currency: ccy || undefined, book_date: bookDate || undefined } : {}

  const errOf = (e: unknown) => (e as { body?: { error?: Refusal } })?.body?.error
  const declared = (): Record<string, string | undefined> => {
    const vf = rep?.controls?.transformation.excluded.value_field
    return {
      ...money(),
      mapping_profile_id: profileId || undefined,
      declared_row_count: declRows.trim() || undefined,
      declared_totals: declTotal.trim() && vf ? JSON.stringify({ [vf]: Number(declTotal.replace(/[, ]/g, '')) }) : undefined,
    }
  }

  const check = async (f: File, pid: string) => {
    const mine = ++seq.current
    setResult(null); setMsg(null); setRep(null); setMapping(false); setPhase('checking')
    try {
      const r = await uploadFile<ValRep>(endpoints.validate, f, 'file', { ...money(), mapping_profile_id: pid || undefined })
      if (mine !== seq.current) return
      setRep(r); setPhase('checked')
    } catch (e: unknown) {
      if (mine !== seq.current) return
      const er = errOf(e)
      const m = errMessage(e, `We could not read that file — upload a ${dropLabel} as ${formats(accept)}`)
      if (template && er?.source_columns?.length) { setMapping(true); setPhase('error'); setMsg(m); return }
      if (er?.error === 'currency_declaration') { setPhase('idle'); setMsg(m); return }
      setMsg(m); setPhase('error')
    }
  }
  const pick = (f: File) => {
    setFile(f); setReason(''); setDeclRows(''); setDeclTotal('')
    check(f, profileId)
  }
  // declaring (or changing) the currency / book date re-checks the chosen file at the new rates
  useEffect(() => { if (file && declares && (ccy || bookDate) && phase !== 'done' && phase !== 'importing') check(file, profileId) }, [ccy, bookDate]) // eslint-disable-line react-hooks/exhaustive-deps
  const recheck = async () => {
    if (!file) return
    const mine = ++seq.current
    setRechecking(true); setMsg(null)
    try { const r = await uploadFile<ValRep>(endpoints.validate, file, 'file', declared()); if (mine === seq.current) setRep(r) }
    catch (e: unknown) { if (mine === seq.current) setMsg(errMessage(e, 'Those figures could not be read — check the numbers')) }
    finally { setRechecking(false) }
  }
  const doImport = async () => {
    if (!file) return
    setPhase('importing'); setMsg(null)
    try {
      const res = await uploadFile<Outcome>(endpoints.upload, file, 'file', { ...declared(), approval_reason: reason.trim() || undefined })
      setResult(res); setPhase('done'); onDone()
    } catch (e: unknown) {
      const er = errOf(e)
      if (er?.controls) { setRep(r => r ? { ...r, controls: er.controls } : r); setMsg(errMessage(e, 'This batch needs attention')); setPhase('checked') }
      else { setMsg(errMessage(e, 'Something went wrong saving — please try again')); setPhase('error') }
    }
  }
  const reset = () => { setFile(null); setRep(null); setResult(null); setMsg(null); setMapping(false); setReason(''); setDeclRows(''); setDeclTotal(''); setPhase('idle'); if (inputRef.current) inputRef.current.value = '' }
  const base = saved.find(s => s.profile_id === profileId)
  const downloadFixList = () => {
    if (!rep) return
    const rows = [['row', 'what to fix'], ...rep.errors.map(e => [String(e.row), e.problems.join('; ')])]
    const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(',')).join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a'); a.href = url; a.download = 'rows-to-fix.csv'; a.click(); URL.revokeObjectURL(url)
  }

  const gate = rep?.controls?.gate.status
  const needsApproval = gate === 'needs_signoff'
  const sec = rep?.security
  const btn = 'text-[12px] px-3 py-2 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)] inline-flex items-center gap-1.5'

  return (
    <div>
      <PlainLead className="mb-3">{intro}</PlainLead>
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f) }} />

      {template && saved.length > 0 && phase !== 'done' && (
        <label className="flex items-center gap-2 mb-2 text-[12px] text-[var(--color-mute)]">Your file’s layout
          <select value={profileId} onChange={e => { setProfileId(e.target.value); if (file) check(file, e.target.value) }}
            className="rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 text-[12px] text-[var(--color-ink)]">
            <option value="">Our template’s column names</option>
            {saved.map(s => <option key={s.profile_id} value={s.profile_id}>{mappingName(s.name, s.version)}</option>)}
          </select></label>
      )}
      {declares && phase !== 'done' && (
        <div className="mb-2 flex items-end gap-2">
          <MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate} />
          <InfoButton compact className="mb-1.5" details={{ title: 'Currency and book date', sections: [
            { heading: HEADING.shows, body: 'The currency your amounts are in, and the date your figures describe. Neither is ever assumed.' },
            { heading: HEADING.read, body: 'A currency or book date column in the file overrides these for its rows. Balances convert at the book date’s rate; yearly figures (income, spend) at the average of the twelve months to it.' }] }} />
        </div>
      )}
      {phase === 'idle' && msg && <div className="mb-2 text-[12.5px]"><Said m={msg} tone="warn" /></div>}
      {phase !== 'done' && !mapping && (
        <div {...pressable(() => inputRef.current?.click())}
          onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) pick(f) }}
          className="rounded-xl border border-dashed border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-4 py-6 text-center cursor-pointer hover:border-[var(--color-sky)] transition">
          <Upload size={18} className="mx-auto text-[var(--color-faint)] mb-2" />
          <div className="text-[13px] text-[var(--color-ink)]">Drop your {dropLabel} here <span className="text-[var(--color-faint)]">({formats(accept)})</span> or <span className="text-[var(--color-sky)]">browse</span></div>
          <button onClick={e => { e.stopPropagation(); download(endpoints.template, endpoints.templateFile) }}
            className="mt-2 inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={12} /> Download the template</button>
        </div>
      )}

      {phase === 'checking' && <div className="mt-3 inline-flex items-center gap-2 text-[12.5px] text-[var(--color-faint)]"><Loader2 size={13} className="animate-spin" /> Checking every row…</div>}
      {phase === 'error' && msg && (
        <div className="mt-3 text-[12.5px] flex items-center gap-2 flex-wrap">
          <Said m={msg} tone="warn" />
          <button onClick={reset} className="text-[12px] text-[var(--color-sky)] hover:underline ml-1">Try another file</button>
        </div>)}
      {template && mapping && file && (
        <MappingEditor key={profileId + file.name} template={template} file={file} base={base}
          onCancel={() => { setMapping(false); if (!rep) reset() }}
          onSaved={async pid => { setProfileId(pid); await reload(); check(file, pid) }} />
      )}

      {(phase === 'checked' || phase === 'importing') && rep && !mapping && (
        <div className="mt-3 rounded-xl border border-[var(--color-line)] overflow-hidden">
          <div className="px-4 py-3 bg-[var(--color-bg-2)] border-b border-[var(--color-line)] space-y-2">
            <div className="flex items-center gap-2.5 flex-wrap">
              <FileSpreadsheet size={14} className="text-[var(--color-faint)]" />
              <span className="text-[12.5px] text-[var(--color-ink)] truncate max-w-[260px]">{rep.filename}</span>
              <span className="text-[12px] text-[var(--color-faint)]">{plural(rep.n_total, 'row')}</span>
              {sec && <SecurityChips sec={sec} />}
            </div>
            <Segments parts={[{ n: rep.n_valid, tone: 'good', label: 'ready' }, { n: rep.n_error, tone: 'warn', label: 'to fix' }]} total={rep.n_total} />
          </div>

          {rep.mapping && <MappingNote report={rep.mapping} />}
          {sec && sec.findings.length > 0 && (
            <div className="px-4 py-2 border-b border-[var(--color-line-2)] space-y-1 text-[12.5px]">
              {sec.findings.map(f => f.msg && <div key={f.code}><Said m={f.msg} tone="warn" /></div>)}
            </div>)}

          {rep.controls && <ControlsPanel controls={rep.controls} onMapValues={template ? () => setMapping(true) : undefined}
            valueLabel={rep.controls.transformation.excluded.value_label ?? null} declRows={declRows} declTotal={declTotal}
            setDeclRows={setDeclRows} setDeclTotal={setDeclTotal} onRecheck={recheck} checking={rechecking} />}
          {msg && <div className="px-4 py-2 text-[12.5px] border-t border-[var(--color-line-2)]"><Said m={msg} tone="warn" /></div>}

          {needsApproval && (
            <div className="px-4 py-3 border-t border-[var(--color-line-2)]">
              <label className="text-[12.5px] text-[var(--color-ink)] inline-flex items-center gap-1.5">Why should it be imported?
                <InfoButton compact details={{ title: 'A second person approves', sections: [
                  { heading: HEADING.shows, body: 'A check failed, so this batch goes to a second person before anything is imported. Your reason goes with it.' },
                  { heading: HEADING.read, body: 'Write at least ten characters — for example, which rows are left out and why the rest can be used.' }] }} />
              </label>
              <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} aria-label="Why it should be imported"
                className="block mt-1 w-full rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 text-[12.5px] text-[var(--color-ink)]" />
            </div>
          )}
          <div className="flex items-center gap-2.5 flex-wrap px-4 py-3 border-t border-[var(--color-line-2)]">
            <button disabled={rep.n_valid === 0 || phase === 'importing' || gate === 'blocked' || (needsApproval && reason.trim().length < 10)} onClick={doImport}
              className="text-[12.5px] font-medium px-3.5 py-2 rounded-lg bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:brightness-110 transition disabled:opacity-45">
              {phase === 'importing' ? 'Sending…' : needsApproval ? 'Send for approval' : `Import ${plural(rep.n_valid, 'ready row')}`}</button>
            {template && file && <button onClick={() => setMapping(true)} className={btn}>{profileId ? 'Edit column mapping' : 'Map my columns'}</button>}
            {rep.n_error > 0 && <button onClick={() => setFixes(true)} className={btn}><ListX size={13} /> {plural(rep.n_error, 'row')} to fix</button>}
            <button onClick={reset} className="text-[12px] text-[var(--color-faint)] hover:text-[var(--color-ink)] ml-auto">Choose a different file</button>
          </div>
          <div className="px-4 pb-3 -mt-1 text-[11.5px] text-[var(--color-faint)]">Nothing is saved until you {needsApproval ? 'send it and a second person approves' : 'import'}.</div>
          {fixes && <RowsToFix rep={rep} onClose={() => setFixes(false)} onDownload={downloadFixList} />}
        </div>
      )}

      {phase === 'done' && result && (() => { const ok = !result.state || result.state === 'imported'; return (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-[var(--color-line)] px-4 py-3"
          style={{ background: `color-mix(in oklab,var(${ok ? '--color-good' : '--color-warn'}) 8%,transparent)` }}>
          {ok ? <CheckCircle2 size={16} className="mt-0.5" style={{ color: 'var(--color-good)' }} /> : <Clock size={16} className="mt-0.5" style={{ color: 'var(--color-warn)' }} />}
          <div className="text-[13px] text-[var(--color-ink)] min-w-0">
            {ok ? renderDone(result)
              : result.msg ? <span className="inline-flex items-center gap-2 flex-wrap"><Said m={result.msg} />
                  {result.state === 'awaiting_approval' && <Link to="/approvals" className="text-[var(--color-sky)] hover:underline">Open approvals</Link>}</span>
              : <StatusChip value={result.state} />}
            {result.controls && <LandingNote controls={result.controls} notes={result.notes} />}
          </div>
          <button onClick={reset} className="text-[12px] text-[var(--color-sky)] hover:underline ml-auto whitespace-nowrap">Upload another file</button>
        </div>
      ) })()}
    </div>
  )
}

const formats = (accept: string) => accept.replaceAll('.', '').toUpperCase().split(',').join(' or ')
const mappingName = (name: string, version: number) => `${name} · version ${version}`

// The file's security inspection and malware scan, as two chips with their explanations one click away.
function SecurityChips({ sec }: { sec: Security }) {
  const passed = sec.status === 'passed'
  const m = sec.malware_msg
  return (
    <span className="ml-auto inline-flex items-center gap-1.5 flex-wrap">
      <span className="inline-flex items-center gap-1 text-[11.5px]" style={{ color: passed ? 'var(--color-good)' : 'var(--color-warn)' }}>
        <ShieldCheck size={13} /> {passed ? 'Safe to read' : 'Read with care'}
        <InfoButton compact details={messageDetails(passed ? SECURE : sec.findings[0]?.msg ?? SECURE)} />
      </span>
      {m && <span className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-mute)]">{m.label}<InfoButton compact details={messageDetails(m)} /></span>}
    </span>
  )
}

// Every row that cannot be imported, with what to fix — one click away from the upload.
function RowsToFix({ rep, onClose, onDownload }: { rep: ValRep; onClose: () => void; onDownload: () => void }) {
  return (
    <Dialog title={`${plural(rep.n_error, 'row')} to fix`} onClose={onClose} className="sm:max-w-2xl">
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <span className="text-[12.5px] text-[var(--color-mute)]">Each row with what stops it being imported. Fix them in your file and send it again.</span>
          <button onClick={onDownload} className="ml-auto shrink-0 inline-flex items-center gap-1.5 text-[12px] px-2.5 py-1.5 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            <Download size={12} /> Download</button>
        </div>
        <div className="max-h-[60vh] overflow-y-auto divide-y divide-[var(--color-line)] border-y border-[var(--color-line)]">
          {rep.errors.map(e => (
            <div key={e.row} className="flex gap-3 py-2 text-[12.5px]">
              <span className="w-16 shrink-0 tabular-nums text-[var(--color-faint)]">Row {e.row}</span>
              <ul className="space-y-0.5 text-[var(--color-ink)]">{e.problems.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </div>))}
        </div>
        {rep.n_error > rep.errors.length && <div className="text-[12px] text-[var(--color-faint)]">The first {plural(rep.errors.length, 'row')} are listed here and in the download.</div>}
      </div>
    </Dialog>
  )
}
