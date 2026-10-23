import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, FileSpreadsheet, ArrowRight } from 'lucide-react'
import { api, download, upload } from '../lib/api'
import { StatusChip } from './StatusChip'
import { HEADING, InfoButton, messageDetails } from './Details'
import MoneyDeclaration from './MoneyDeclaration'
import { Said, errMessage, plural } from './intake/parts'
import type { Message } from './Details'

// The sector's standard file (the product owner's decision of 2026-10-23): one Excel workbook holding every book the
// sector sends, a sheet each — checked sheet by sheet, and each accepted sheet scored and its losses run by itself.
// Systems send the same books by the API from the same field definitions.

interface SheetInfo { sheet: string; book: string; about: Message; fields: { name: string; required: boolean }[] }
interface SheetResult {
  sheet: string; book: string; state: string; batch_id?: string | null; gate?: 'pass' | 'needs_signoff' | 'blocked'
  gate_messages?: Message[]
  n_total?: number; n_valid?: number; n_error?: number; n_uploaded?: number; msg?: Message | null
  scoring?: string; losses?: { state: string } | null; errors?: { row: number; problems: string[] }[]
}
interface Outcome { sheets: SheetResult[] }

type Tone = 'good' | 'warn' | 'bad' | 'neutral'
// What each sheet's outcome means for the customer — a word and a colour.
function said(r: SheetResult): { label: string; tone: Tone } {
  if (r.state === 'checked') return r.gate === 'pass' ? { label: 'Ready to send', tone: 'good' }
    : r.gate === 'blocked' ? { label: 'Nothing can be imported', tone: 'bad' } : { label: 'Needs a second person', tone: 'warn' }
  return ({
    imported: { label: 'Imported', tone: 'good' }, awaiting_approval: { label: 'With a second person', tone: 'warn' },
    held: { label: 'Held for a scan', tone: 'warn' }, rejected: { label: 'Refused', tone: 'bad' },
    refused: { label: 'Refused', tone: 'bad' }, empty: { label: 'No rows', tone: 'neutral' },
  } as Record<string, { label: string; tone: Tone }>)[r.state] ?? { label: r.state, tone: 'neutral' }
}

export default function StandardFile({ sector, onDone }: { sector: string; onDone?: () => void }) {
  const qc = useQueryClient()
  const input = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [reason, setReason] = useState('')
  const [ccy, setCcy] = useState('')            // the currency of the amounts and the date they describe — never assumed
  const [bookDate, setBookDate] = useState('')
  const [busy, setBusy] = useState<'check' | 'send' | null>(null)
  const [out, setOut] = useState<{ kind: 'check' | 'send'; sheets: SheetResult[] } | null>(null)
  const [err, setErr] = useState<Message | null>(null)
  const info = useQuery({ queryKey: ['workbook-sheets'], queryFn: () => api.get<{ about: Message; sheets: SheetInfo[] }>('/v1/intake/workbook/sheets') })
  const needsSecond = out?.kind === 'check' && out.sheets.some(s => s.state === 'checked' && s.gate === 'needs_signoff')
  const MIN_REASON = 10   // the intake's own minimum (services/intake/pipeline.MIN_REASON)

  const run = async (kind: 'check' | 'send') => {
    if (!file) return
    setBusy(kind); setErr(null)
    try {
      const money = { currency: ccy || undefined, book_date: bookDate || undefined }
      const res = await upload<Outcome>(kind === 'check' ? '/v1/intake/workbook/check' : '/v1/intake/workbook', file, 'file',
        kind === 'send' ? { ...money, approval_reason: reason.trim() || undefined } : money)
      setOut({ kind, sheets: res.sheets })
      if (kind === 'send') { qc.invalidateQueries({ queryKey: ['intake-batches'] }); onDone?.() }
    } catch (e: unknown) {
      setErr(errMessage(e, 'That file could not be read — send your sector’s standard file as .xlsx'))
    } finally { setBusy(null) }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <FileSpreadsheet size={16} className="text-[var(--color-sky)]" />
        <span className="text-[13.5px] font-medium text-[var(--color-ink)]">Your standard file</span>
        {info.data?.about && <InfoButton compact details={messageDetails(info.data.about)} />}
        <button onClick={() => download(`/v1/intake/workbooks/${sector}.xlsx`, `tellumen_${sector}_standard_file.xlsx`)}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-ink)] transition">
          <Download size={13} /> Download blank file
        </button>
      </div>

      {info.data && (
        <div className="flex flex-wrap gap-1.5">
          {info.data.sheets.map(s => (
            <span key={s.book} title={s.about?.label} className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line)] px-2.5 py-0.5 text-[11.5px] text-[var(--color-mute)]">
              {s.sheet}<span className="mono text-[10px] text-[var(--color-faint)]">{s.fields.filter(f => f.required).length}*</span>
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <MoneyDeclaration currency={ccy} setCurrency={setCcy} bookDate={bookDate} setBookDate={setBookDate} />
        <InfoButton compact details={{ title: 'Currency and book date', sections: [
          { heading: HEADING.shows, body: 'The currency your amounts are in, and the date your figures describe — for every sheet. Neither is ever assumed.' },
          { heading: HEADING.read, body: 'A currency or book date column in a sheet overrides these for its rows.' }] }} />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input ref={input} type="file" accept=".xlsx" className="hidden"
          onChange={e => { setFile(e.target.files?.[0] ?? null); setOut(null); setErr(null) }} />
        <button onClick={() => input.current?.click()}
          className="rounded-lg border border-dashed border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-mute)] hover:border-[var(--color-sky)] transition max-w-[18rem] truncate">
          {file ? file.name : 'Choose your filled file'}
        </button>
        <button disabled={!file || !!busy} onClick={() => run('check')}
          className="rounded-lg border border-[var(--color-line-2)] px-3 py-1.5 text-[12px] text-[var(--color-ink)] disabled:opacity-40 hover:border-[var(--color-sky)] transition">
          {busy === 'check' ? 'Checking…' : 'Check'}
        </button>
        <button disabled={!file || !!busy || (needsSecond && reason.trim().length < MIN_REASON)} onClick={() => run('send')}
          className="rounded-lg bg-[var(--color-sky)] px-3 py-1.5 text-[12px] font-medium text-[var(--color-bg)] disabled:opacity-40 transition">
          {busy === 'send' ? 'Sending…' : 'Send'}
        </button>
      </div>

      {needsSecond && (
        <label className="block text-[12px] text-[var(--color-mute)]">
          Why send rows that fail a check? A second person approves those sheets.
          <textarea value={reason} onChange={e => setReason(e.target.value)} rows={2}
            className="mt-1 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]" />
        </label>
      )}

      {err && <Said m={err} tone="bad" className="text-[12.5px]" />}
      {out && <Results out={out} />}
    </div>
  )
}

function Results({ out }: { out: { kind: 'check' | 'send'; sheets: SheetResult[] } }) {
  return (
    <div className="rounded-lg border border-[var(--color-line)] divide-y divide-[var(--color-line)]">
      {out.sheets.map(r => {
        const s = said(r)
        const started = [r.scoring === 'queued' && 'scores', r.losses?.state === 'queued' && 'losses'].filter(Boolean)
        return (
          <div key={r.sheet} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-[12.5px]">
            <span className="text-[var(--color-ink)] min-w-[9rem]">{r.sheet}</span>
            <StatusChip tone={s.tone} label={s.label} />
            {r.n_total != null && (
              <span className="text-[var(--color-mute)] tabular-nums">
                {plural(r.n_valid ?? 0, 'row')} pass{r.n_error ? <> · <span style={{ color: 'var(--color-warn)' }}>{plural(r.n_error, 'row')} fail</span></> : ''}
              </span>
            )}
            {started.length > 0 && <span className="text-[var(--color-faint)]">{started.join(' and ')} started</span>}
            {r.msg && <Said m={r.msg} className="text-[var(--color-mute)]" />}
            {r.gate === 'needs_signoff' && !!r.gate_messages?.length && (
              <InfoButton label="Why" details={{ title: `${r.sheet} — why a second person approves`, sections: r.gate_messages.map(m => (
                { heading: m.label, body: [m.detail?.what, m.detail?.next].filter(Boolean).join(' ') })) }} />
            )}
            {!!r.errors?.length && (
              <InfoButton label="Rows to fix" details={{ title: `${r.sheet} — rows to fix`, sections: r.errors.map(e => (
                { heading: `Row ${e.row}`, body: e.problems.join('; ') })) }} />
            )}
            {r.state === 'awaiting_approval' && (
              <Link to="/approvals" className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)]">Open approvals <ArrowRight size={12} /></Link>
            )}
          </div>
        )
      })}
    </div>
  )
}
