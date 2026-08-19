import { useState, useEffect, useCallback } from 'react'
import { LifeBuoy, Plus, Loader2, CheckCircle2 } from 'lucide-react'
import { fetchServiceRequests, createServiceRequest } from '../api/client'

const CATEGORIES = [
  ['data', 'Data request'], ['report', 'Report run'], ['onboarding', 'Onboarding'],
  ['bug', 'Bug'], ['question', 'Question'], ['other', 'Other'],
]
const STATUS_STYLE = {
  open: 'text-blue-700 bg-blue-50', in_progress: 'text-amber-700 bg-amber-50', resolved: 'text-emerald-700 bg-emerald-50',
}
const PRIO_STYLE = {
  low: 'text-gray-500 bg-gray-100', normal: 'text-gray-600 bg-gray-100',
  high: 'text-amber-700 bg-amber-50', urgent: 'text-red-700 bg-red-50',
}

export default function ServicePortalPage() {
  const [requests, setRequests] = useState(null)
  const [form, setForm] = useState({ category: 'data', subject: '', body: '', priority: 'normal' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const load = useCallback(() => {
    fetchServiceRequests().then(setRequests).catch(() => setRequests([]))
  }, [])
  useEffect(() => { load() }, [load])

  async function submit(e) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      await createServiceRequest(form)
      setForm({ category: 'data', subject: '', body: '', priority: 'normal' })
      load()
    } catch (e) { setErr(e.message || 'Could not submit request.') }
    finally { setBusy(false) }
  }

  return (
    <div className="h-full overflow-y-auto bg-[#f5f5f7]">
      <div className="mx-auto max-w-5xl px-8 py-10">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[#0071e3]/10 text-[#0071e3]"><LifeBuoy size={20} /></span>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Service portal</h1>
            <p className="text-[14px] text-gray-500">Raise requests and track them — support, data, onboarding.</p>
          </div>
        </div>

        {/* service status */}
        <div className="mt-6 flex items-center gap-2 rounded-2xl border border-gray-200/70 bg-white px-5 py-3 text-[13px] shadow-sm">
          <CheckCircle2 size={16} className="text-emerald-500" />
          <span className="font-medium text-[#1d1d1f]">All systems operational</span>
          <span className="text-gray-400">· data pipeline, scoring engine and API are healthy</span>
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-[1fr_1.3fr]">
          {/* new request */}
          <form onSubmit={submit} className="rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="flex items-center gap-2 text-[15px] font-semibold"><Plus size={16} /> New request</h2>
            <label className="mt-4 block text-[12px] font-medium text-gray-500">Category</label>
            <select value={form.category} onChange={e => setForm({ ...form, category: e.target.value })}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]">
              {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <label className="mt-3 block text-[12px] font-medium text-gray-500">Subject</label>
            <input value={form.subject} onChange={e => setForm({ ...form, subject: e.target.value })}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]"
              placeholder="Short summary" />
            <label className="mt-3 block text-[12px] font-medium text-gray-500">Details</label>
            <textarea value={form.body} onChange={e => setForm({ ...form, body: e.target.value })} rows={3}
              className="mt-1 w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]"
              placeholder="What do you need?" />
            <label className="mt-3 block text-[12px] font-medium text-gray-500">Priority</label>
            <select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}
              className="mt-1 w-full rounded-lg border border-gray-200 px-3 py-2 text-[14px] outline-none focus:border-[#0071e3]">
              {['low', 'normal', 'high', 'urgent'].map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            {err && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{err}</p>}
            <button type="submit" disabled={busy || form.subject.length < 3}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-full bg-[#0071e3] px-5 py-2.5 text-[14px] font-medium text-white transition hover:brightness-110 disabled:opacity-50">
              {busy ? <><Loader2 size={16} className="animate-spin" /> Submitting…</> : 'Submit request'}
            </button>
          </form>

          {/* my requests */}
          <div>
            <h2 className="text-[15px] font-semibold">Your organization’s requests</h2>
            {requests === null && <p className="mt-3 text-[14px] text-gray-500">Loading…</p>}
            {requests && requests.length === 0 && (
              <div className="mt-3 rounded-2xl border border-dashed border-gray-200 bg-white p-8 text-center text-[14px] text-gray-400">No requests yet.</div>
            )}
            <div className="mt-3 space-y-3">
              {(requests || []).map(r => (
                <div key={r.id} className="rounded-2xl border border-gray-200/70 bg-white p-4 shadow-sm">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-[14px] font-semibold text-[#1d1d1f]">{r.subject}</h3>
                      <p className="mt-0.5 text-[12px] text-gray-400">
                        {r.category} · {r.requester_email || '—'} · {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
                      </p>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${PRIO_STYLE[r.priority] || ''}`}>{r.priority}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${STATUS_STYLE[r.status] || ''}`}>{r.status.replace('_', ' ')}</span>
                    </div>
                  </div>
                  {r.body && <p className="mt-2 text-[13px] leading-relaxed text-gray-600">{r.body}</p>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
