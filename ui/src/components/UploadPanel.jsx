import { useState, useRef } from 'react'
import { Upload, FileDown, Loader2, CheckCircle2 } from 'lucide-react'

// Self-service data entry, reused across all three verticals (bank/supply/insurance) —
// same shape as RiskAtom/ContextBar/AssetDrawer's Facts: one component, three call sites.
export default function UploadPanel({ uploadFn, templateColumns, templateFilename, label, onUploaded }) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const inputRef = useRef(null)

  function downloadTemplate() {
    const csv = templateColumns.join(',') + '\n'
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url; a.download = templateFilename; a.click()
    URL.revokeObjectURL(url)
  }

  async function submit() {
    if (!file) return
    setBusy(true); setError(null); setResult(null)
    try {
      const r = await uploadFn(file)
      setResult(r)
      setFile(null)
      if (inputRef.current) inputRef.current.value = ''
      onUploaded?.()
    } catch (e) {
      setError(e.message || 'Upload failed.')
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="flex items-center gap-2 rounded-full border border-gray-200 bg-white px-4 py-2 text-[13px] font-medium text-[#1d1d1f] hover:border-gray-300">
        <Upload size={15} /> {label || 'Import CSV'}
      </button>
    )
  }

  return (
    <div className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <h3 className="text-[13px] font-semibold text-[#1d1d1f]">{label || 'Import CSV'}</h3>
        <button onClick={() => setOpen(false)} className="text-[12px] text-gray-400 hover:text-gray-600">Close</button>
      </div>
      <button onClick={downloadTemplate} className="mt-2 flex items-center gap-1.5 text-[12px] font-medium text-[#0071e3] hover:underline">
        <FileDown size={13} /> Download CSV template
      </button>
      <div className="mt-3 flex items-center gap-2">
        <input ref={inputRef} type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0] || null)}
          className="flex-1 text-[12px] text-gray-600 file:mr-3 file:rounded-full file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-[12px] file:font-medium" />
        <button onClick={submit} disabled={!file || busy}
          className="flex items-center gap-1.5 rounded-full bg-[#0071e3] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50">
          {busy ? <Loader2 size={13} className="animate-spin" /> : 'Upload'}
        </button>
      </div>
      {error && <p className="mt-2 rounded-lg bg-red-50 px-3 py-2 text-[12px] text-red-700">{error}</p>}
      {result && (
        <p className="mt-2 flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-[12px] text-emerald-800">
          <CheckCircle2 size={13} />
          {result.n_uploaded} row(s) uploaded · {result.n_cells} new location(s) ·
          {' '}{result.n_sync_scored} hazard(s) scored instantly · {result.n_gridded_dispatched} still processing
        </p>
      )}
    </div>
  )
}
