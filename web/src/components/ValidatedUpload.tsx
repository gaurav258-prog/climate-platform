import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Upload, Download, FileSpreadsheet, CheckCircle2, AlertTriangle, ShieldCheck, Clock } from 'lucide-react'
import { upload as uploadFile, download } from '../lib/api'
import { ControlsPanel, LandingNote, type Controls } from './IntakeControls'
import MoneyDeclaration from './MoneyDeclaration'
import MappingEditor, { MappingNote, useTemplateMappings, type MappingReport } from './MappingEditor'

// The one customer-data upload control, used by every sector's book (loan tape, SoV, properties, holdings, plots).
// It fronts the intake pipeline (services/intake/pipeline.py):
//   drop a file → we inspect it and run every check (nothing saved) → you import
//   every check passed → imported now · a check failed → you give a reason and it goes to a SECOND person
//   scanner unavailable → held · refused on security grounds → nothing kept

interface Finding { code: string; severity: 'block' | 'warn'; message: string }
interface Security { status: 'passed' | 'warned' | 'blocked'; findings: Finding[]; malware_scan?: string; malware?: string }
export interface ValRep {
  filename: string; n_total: number; n_valid: number; n_error: number
  errors: { row: number; problems: string[] }[]; controls?: Controls; security?: Security; mapping?: MappingReport | null
}
interface MissingCols { missing_columns?: string[]; source_columns?: string[]; suggested_mapping?: Record<string, string> }
interface Endpoints { validate: string; upload: string; template: string; templateFile: string }
type Outcome = { state: string; message?: string; batch_id?: string; approval_request_id?: string; n_uploaded?: number; controls?: Controls; notes?: Record<string, unknown> } & Record<string, unknown>

export default function ValidatedUpload({ intro, dropLabel, endpoints, onDone, renderDone, accept = '.csv,.xlsx', template, declareMoney }: {
  intro: React.ReactNode; dropLabel: string; endpoints: Endpoints; onDone: () => void
  renderDone: (res: Outcome) => React.ReactNode; accept?: string
  template?: string   // intake template key — enables column mapping for files in the customer's own layout
  declareMoney?: boolean   // a non-template upload that carries amounts: ask for their currency + book date too
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [rep, setRep] = useState<ValRep | null>(null)
  const [phase, setPhase] = useState<'idle' | 'checking' | 'checked' | 'importing' | 'done' | 'error'>('idle')
  const [msg, setMsg] = useState<string | null>(null)
  const [result, setResult] = useState<Outcome | null>(null)
  const [declRows, setDeclRows] = useState('')
  const [declTotal, setDeclTotal] = useState('')
  const [reason, setReason] = useState('')
  const [rechecking, setRechecking] = useState(false)
  const { saved, reload } = useTemplateMappings(template)
  const [profileId, setProfileId] = useState('')
  const [mapping, setMapping] = useState(false)   // the mapping editor is open for this file
  // every batch declares the currency of its amounts and the date its figures describe — never assumed
  const [ccy, setCcy] = useState('')
  const [bookDate, setBookDate] = useState('')
  const declares = !!template || !!declareMoney
  const needsDecl = declares && (!ccy || !bookDate)
  const money = (): Record<string, string | undefined> => declares ? { currency: ccy || undefined, book_date: bookDate || undefined } : {}

  const errOf = (e: unknown) => (e as { body?: { error?: { error?: string; message?: string; controls?: Controls; security?: Security } & MissingCols } })?.body?.error
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
    setResult(null); setMsg(null); setRep(null); setMapping(false); setPhase('checking')
    try {
      setRep(await uploadFile<ValRep>(endpoints.validate, f, 'file', { ...money(), mapping_profile_id: pid || undefined })); setPhase('checked')
    } catch (e: unknown) {
      const er = errOf(e)
      if (template && er?.source_columns?.length) { setMapping(true); setPhase('error'); setMsg(missingMsg(er)); return }
      setMsg(missingMsg(er) ?? er?.message ?? `We couldn’t read that file — please upload a ${dropLabel} as ${accept.replaceAll(',', ' or ')}.`)
      setPhase('error')
    }
  }
  const pick = (f: File) => {
    setFile(f); setReason(''); setDeclRows(''); setDeclTotal('')
    if (needsDecl) { setRep(null); setPhase('idle'); setMsg('Choose the currency and the book date above — then the file is checked.'); return }
    check(f, profileId)
  }
  // declaring (or changing) the currency / book date re-checks the chosen file at the new rates
  useEffect(() => { if (file && declares && ccy && bookDate && phase !== 'done' && phase !== 'importing') check(file, profileId) }, [ccy, bookDate]) // eslint-disable-line react-hooks/exhaustive-deps
  const recheck = async () => {
    if (!file) return
    setRechecking(true); setMsg(null)
    try { setRep(await uploadFile<ValRep>(endpoints.validate, file, 'file', declared())) }
    catch (e: unknown) { setMsg(errOf(e)?.message ?? 'Those declared figures could not be read — check the numbers.') }
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
      if (er?.controls) { setRep(r => r ? { ...r, controls: er.controls } : r); setMsg(er.message ?? 'This batch needs attention.'); setPhase('checked') }
      else { setMsg(er?.message ?? 'Something went wrong saving — please try again.'); setPhase('error') }
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

  return (
    <div>
      <p className="text-[13px] text-[var(--color-mute)] mb-3">{intro}</p>
      <input ref={inputRef} type="file" accept={accept} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) pick(f) }} />

      {template && saved.length > 0 && phase !== 'done' && (
        <label className="flex items-center gap-2 mb-2 text-[11.5px] text-[var(--color-mute)]">Your file’s layout
          <select value={profileId} onChange={e => { setProfileId(e.target.value); if (file) check(file, e.target.value) }}
            className="rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1 text-[12px] text-[var(--color-ink)]">
            <option value="">our template’s column names</option>
            {saved.map(s => <option key={s.profile_id} value={s.profile_id}>{s.name} (v{s.version})</option>)}
          </select></label>
      )}
      {declares && phase !== 'done' && (
        <div className="mb-2"><MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate}
          note="A currency or book_date column in the file overrides these per row. Values convert at the book date’s rate; yearly figures (income, spend) at the average of the 12 months to it." /></div>
      )}
      {phase === 'idle' && msg && <div className="mb-2 text-[12px]" style={{ color: 'var(--color-warn)' }}>{msg}</div>}
      {phase !== 'done' && !mapping && (
        <div onClick={() => inputRef.current?.click()}
          onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const f = e.dataTransfer.files?.[0]; if (f) pick(f) }}
          className="rounded-xl border border-dashed border-[var(--color-line-2)] bg-[var(--color-bg-2)] px-4 py-6 text-center cursor-pointer hover:border-[var(--color-sky)] transition">
          <Upload size={18} className="mx-auto text-[var(--color-faint)] mb-2" />
          <div className="text-[13px] text-[var(--color-ink)]">Drop your {dropLabel} here <span className="text-[var(--color-faint)]">— {accept.replaceAll('.', '').toUpperCase().replace(',', ' or ')} —</span> or <span className="text-[var(--color-sky)]">browse</span></div>
          <button onClick={e => { e.stopPropagation(); download(endpoints.template, endpoints.templateFile) }}
            className="mt-2 inline-flex items-center gap-1.5 mono text-[10.5px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><Download size={12} /> download the template</button>
        </div>
      )}

      {phase === 'checking' && <div className="mono text-[11px] text-[var(--color-faint)] mt-3">inspecting the file and checking every row…</div>}
      {phase === 'error' && msg && <div className="mt-3 text-[12.5px] flex items-center gap-2 flex-wrap" style={{ color: 'var(--color-warn)' }}><AlertTriangle size={14} /> {msg} <button onClick={reset} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline ml-1">try another file</button></div>}
      {template && mapping && file && (
        <MappingEditor key={profileId + file.name} template={template} file={file} base={base}
          onCancel={() => { setMapping(false); if (!rep) reset() }}
          onSaved={async pid => { setProfileId(pid); await reload(); check(file, pid) }} />
      )}

      {(phase === 'checked' || phase === 'importing') && rep && !mapping && (
        <div className="mt-3 rounded-xl border border-[var(--color-line)] overflow-hidden">
          <div className="flex items-center gap-2.5 flex-wrap px-4 py-2.5 bg-[var(--color-bg-2)] border-b border-[var(--color-line)]">
            <FileSpreadsheet size={14} className="text-[var(--color-faint)]" />
            <span className="mono text-[11.5px] text-[var(--color-ink)] truncate max-w-[240px]">{rep.filename}</span>
            <span className="mono text-[10px] text-[var(--color-faint)]">{rep.n_total} rows</span>
            <span className="mono text-[9.5px] px-2 py-0.5 rounded-full" style={{ color: 'var(--color-good)', background: 'color-mix(in oklab,var(--color-good) 14%,transparent)' }}>{rep.n_valid} ready</span>
            {rep.n_error > 0 && <span className="mono text-[9.5px] px-2 py-0.5 rounded-full" style={{ color: 'var(--color-warn)', background: 'color-mix(in oklab,var(--color-warn) 14%,transparent)' }}>{rep.n_error} need fixing</span>}
          </div>

          {rep.mapping && <MappingNote report={rep.mapping} />}
          {sec && (
            <div className="flex items-start gap-2 px-4 py-2 border-b border-[var(--color-line-2)] text-[12px]">
              <ShieldCheck size={14} className="mt-0.5 shrink-0" style={{ color: sec.status === 'passed' ? 'var(--color-good)' : 'var(--color-warn)' }} />
              <div><b className="text-[var(--color-ink)]">File security</b> <span className="text-[var(--color-mute)]">— real file type confirmed, no macros or hidden content{sec.status === 'passed' ? '' : ' (see below)'}. Malware scan: {sec.malware_scan ?? 'on import'}.</span>
                {sec.findings.map(f => <div key={f.code} style={{ color: 'var(--color-warn)' }}>{f.message}</div>)}</div>
            </div>
          )}

          {rep.errors.slice(0, 6).map(e => (
            <div key={e.row} className="flex gap-3 px-4 py-2 border-b border-[var(--color-line-2)] text-[12px]">
              <span className="mono text-[10px] text-[var(--color-faint)] w-14 shrink-0">row {e.row}</span>
              <span style={{ color: 'var(--color-bad, #e0574a)' }}>{e.problems.join(' · ')}</span>
            </div>
          ))}
          {rep.n_error > 6 && <div className="px-4 py-2 border-b border-[var(--color-line-2)] mono text-[10.5px] text-[var(--color-faint)]">…and {rep.n_error - 6} more</div>}

          {rep.controls && <ControlsPanel controls={rep.controls} onMapValues={template ? () => setMapping(true) : undefined} valueLabel={rep.controls.transformation.excluded.value_field} declRows={declRows} declTotal={declTotal}
            setDeclRows={setDeclRows} setDeclTotal={setDeclTotal} onRecheck={recheck} checking={rechecking} />}
          {msg && <div className="px-4 py-2 text-[12px] border-t border-[var(--color-line-2)]" style={{ color: 'var(--color-warn)' }}>{msg}</div>}

          {needsApproval && (
            <div className="px-4 py-3 border-t border-[var(--color-line-2)]">
              <label className="text-[11.5px] text-[var(--color-ink)]">A check failed, so this batch needs a second person’s approval before anything is imported. Why should it be imported?
                <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2} placeholder="e.g. The rejected rows are closed loans; the rest are the current book."
                  className="block mt-1 w-full rounded-md border border-[var(--color-line)] bg-[var(--color-bg)] px-2 py-1.5 text-[12px] text-[var(--color-ink)]" /></label>
            </div>
          )}
          <div className="flex items-center gap-2.5 flex-wrap px-4 py-3 border-t border-[var(--color-line-2)]">
            <button disabled={rep.n_valid === 0 || phase === 'importing' || gate === 'blocked' || (needsApproval && reason.trim().length < 10)} onClick={doImport}
              className="mono text-[11.5px] px-3.5 py-2 rounded-lg bg-[var(--color-sky)] text-white hover:brightness-110 transition disabled:opacity-45">
              {phase === 'importing' ? 'sending…' : needsApproval ? 'Send for approval' : `Import ${rep.n_valid} ready ${rep.n_valid === 1 ? 'row' : 'rows'}`}</button>
            {template && file && <button onClick={() => setMapping(true)} className="mono text-[11px] px-3 py-2 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)]">{profileId ? 'Edit column mapping' : 'Map my columns'}</button>}
            {rep.n_error > 0 && <button onClick={downloadFixList} className="mono text-[11px] px-3 py-2 rounded-lg border border-[var(--color-line)] text-[var(--color-mute)] hover:text-[var(--color-ink)]"><Download size={12} className="inline mr-1" />Download rows to fix</button>}
            <button onClick={reset} className="mono text-[10.5px] text-[var(--color-faint)] hover:text-[var(--color-ink)] ml-auto">choose a different file</button>
            <span className="mono text-[9.5px] text-[var(--color-faint)] w-full">Nothing is saved until you {needsApproval ? 'send it and a second person approves' : 'import'}.</span>
          </div>
        </div>
      )}

      {phase === 'done' && result && (() => { const ok = !result.state || result.state === 'imported'; return (
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-[var(--color-line)] px-4 py-3"
          style={{ background: `color-mix(in oklab,var(${ok ? '--color-good' : '--color-warn'}) 8%,transparent)` }}>
          {ok ? <CheckCircle2 size={16} className="mt-0.5" style={{ color: 'var(--color-good)' }} /> : <Clock size={16} className="mt-0.5" style={{ color: 'var(--color-warn)' }} />}
          <span className="text-[13px] text-[var(--color-ink)]">
            {ok ? renderDone(result)
              : result.state === 'awaiting_approval' ? <>Sent for approval — nothing is imported until a second person approves it. <Link to="/approvals" className="text-[var(--color-sky)] hover:underline">Open approvals</Link></>
              : result.message}
            {result.controls && <LandingNote controls={result.controls} notes={result.notes} />}
            {result.batch_id && !result.controls?.landing && <div className="mono text-[10px] text-[var(--color-faint)] mt-1">batch {String(result.batch_id).slice(0, 8)}</div>}
          </span>
          <button onClick={reset} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline ml-auto">upload another file</button>
        </div>
      ) })()}
    </div>
  )
}

function missingMsg(detail: unknown): string | null {
  const m = (detail as { missing_columns?: string[] })?.missing_columns
  const mapped = (detail as MissingCols)?.source_columns?.length
  if (Array.isArray(m) && m.length) return `Your file is missing required column${m.length === 1 ? '' : 's'}: ${m.join(', ')}. ${mapped ? 'If your file names them differently, map your columns below.' : 'Start from the template.'}`
  if (typeof detail === 'string') return detail
  return null
}
