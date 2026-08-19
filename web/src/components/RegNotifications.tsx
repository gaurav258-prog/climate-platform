import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { BellRing, Clock, AlertTriangle, CheckCircle2, Flag } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card } from './ui'

// Regulatory-notification clock — the "notify the regulator within N hours" workflow. A human flags a breach as
// notifiable; the card runs the statutory countdown, flags overdue, and captures the evidence of what was sent.
// Every timestamp is real; nothing is auto-fired (notifiability is a compliance judgement).

interface NEvent { event_id: string; title: string; authority: string | null; severity: string | null; status: string; overdue: boolean; hours_remaining: number | null; due_at: string; notified_ref: string | null }
interface NResp { events: NEvent[]; summary: { n_open: number; n_overdue: number; next_due_hours: number | null } }
interface Episode { kri_key: string; label: string; severity: string; open: boolean; onset_at: string }
interface LagResp { episodes: Episode[] }

const rem = (h: number | null) => h == null ? '—' : h < 0 ? `${Math.abs(h).toFixed(0)}h overdue` : h < 48 ? `${h.toFixed(0)}h left` : `${Math.round(h / 24)}d left`

export default function RegNotifications({ framework }: { framework: string }) {
  const qc = useQueryClient()
  const { profile } = useAuth()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const nq = useQuery({ queryKey: ['reg-notifications'], queryFn: () => api.get<NResp>('/v1/notifications') })
  const lq = useQuery({ queryKey: ['kri-detection-lag', framework], queryFn: () => api.get<LagResp>(`/v1/reg-tasks/kri/detection-lag?framework=${framework}`), enabled: !!framework })
  const [recId, setRecId] = useState<string | null>(null)
  const [ref, setRef] = useState('')

  const events = nq.data?.events ?? []
  // open breaches not yet flagged for notification
  const flaggable = (lq.data?.episodes ?? []).filter(e => e.open && !events.some(n => n.title.includes(e.label)))

  const refresh = () => { qc.invalidateQueries({ queryKey: ['reg-notifications'] }) }
  const flag = async (e: Episode) => {
    try {
      await api.post('/v1/notifications', {
        title: `${e.label} — breach exceeds appetite`, source_type: 'kri_breach',
        source_ref: `${framework}:${e.kri_key}`, category: 'material_breach', severity: e.severity,
        arose_at_iso: e.onset_at, window_hours: 72,
      })
      refresh(); toast.success('Notification clock started.')
    } catch { toast.error('Could not raise the notification.') }
  }
  const record = async (id: string) => {
    try { await api.post(`/v1/notifications/${id}/record`, { notified_ref: ref || undefined }); setRecId(null); setRef(''); refresh(); toast.success('Notification recorded.') }
    catch { toast.error('Could not record it.') }
  }

  if (events.length === 0 && flaggable.length === 0) return null
  const s = nq.data?.summary

  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <BellRing size={15} className="text-[var(--color-blue)]" />
        <h3 className="font-semibold text-[14px] text-[var(--color-ink)]">Regulatory notifications</h3>
        <span className="text-[12px] text-[var(--color-mute)] hidden sm:inline">· notify-within-window clock</span>
        {!!s?.n_overdue && <span className="mono text-[10px] px-2 py-0.5 rounded-full ml-auto" style={{ color: 'var(--color-bad)', background: 'color-mix(in oklab, var(--color-bad) 14%, transparent)' }}>{s.n_overdue} overdue</span>}
      </div>

      {events.length > 0 && (
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)] mb-3">
          {events.map(e => (
            <div key={e.event_id} className="py-2.5">
              <div className="flex items-center gap-2.5 text-[12.5px]">
                <span className="flex-1 min-w-0 truncate text-[var(--color-ink)]">{e.title}</span>
                {e.authority && <span className="mono text-[10px] text-[var(--color-faint)] shrink-0">{e.authority}</span>}
                {e.status === 'notified'
                  ? <span className="mono text-[10.5px] inline-flex items-center gap-1 shrink-0" style={{ color: 'var(--color-good)' }}><CheckCircle2 size={12} /> notified{e.notified_ref ? ` · ${e.notified_ref}` : ''}</span>
                  : <span className="mono text-[10.5px] inline-flex items-center gap-1 shrink-0" style={{ color: e.overdue ? 'var(--color-bad)' : 'var(--color-warn)' }}>{e.overdue ? <AlertTriangle size={12} /> : <Clock size={12} />} {rem(e.hours_remaining)}</span>}
              </div>
              {e.status === 'open' && canAct && (
                <div className="mt-1.5 flex items-center gap-2">
                  {recId === e.event_id ? (
                    <>
                      <input value={ref} onChange={ev => setRef(ev.target.value)} placeholder="Regulator reference…" autoFocus
                        className="flex-1 min-w-0 bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded px-2 py-1 text-[12px] outline-none focus:border-[var(--color-sky)]" />
                      <button onClick={() => record(e.event_id)} className="mono text-[11px] px-2.5 py-1 rounded bg-[var(--color-sky)] text-[var(--color-on-accent)]">Save</button>
                      <button onClick={() => { setRecId(null); setRef('') }} className="mono text-[11px] text-[var(--color-faint)]">cancel</button>
                    </>
                  ) : (
                    <button onClick={() => setRecId(e.event_id)} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">Record notification sent →</button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {canAct && flaggable.length > 0 && (
        <div>
          <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1.5">Flag a breach as notifiable</div>
          <div className="flex flex-wrap gap-1.5">
            {flaggable.slice(0, 6).map(e => (
              <button key={e.kri_key} onClick={() => flag(e)}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] px-2.5 py-1 mono text-[11px] text-[var(--color-mute)] hover:border-[var(--color-warn)] hover:text-[var(--color-warn)] transition">
                <Flag size={11} /> {e.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
