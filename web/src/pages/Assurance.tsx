import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ShieldCheck, Download } from 'lucide-react'
import { api, apiMessage, apiDetail } from '../lib/api'
import { BrandMark, Wordmark } from '../components/BrandMark'
import { MessageLine, type Message } from '../components/Details'
import { StatusChip } from '../components/StatusChip'

// The auditor's page: opened from the share e-mail, no login. The report and its organisation, the share's state as a
// chip, its time left and downloads as bars, and the download; what the pack holds and why a share no longer serves it
// are the server's catalogue messages, one click away. Every open and download is logged on the organisation's audit trail.
interface Share {
  organisation: string; report: string | null; period_label: string; recipient_name: string; purpose: string
  expires_at: string; max_downloads: number | null; n_downloads: number; status: string; created_at: string
  created_by: string | null; state: Message | null; contents: Message
}
const day = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
const DAY_MS = 86_400_000

function Bar({ share, tone, label, right }: { share: number; tone: string; label: string; right: string }) {
  return (
    <div>
      <div className="flex items-baseline justify-between text-[12px] mb-1">
        <span className="text-[var(--color-faint)]">{label}</span><span className="text-[var(--color-ink)] tabular-nums">{right}</span>
      </div>
      <div className="h-1.5 rounded-full overflow-hidden bg-[var(--color-panel-2)]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, share * 100))}%`, background: tone }} />
      </div>
    </div>
  )
}

export default function Assurance() {
  const { token = '' } = useParams()
  const [d, setD] = useState<Share | null>(null); const [err, setErr] = useState<Message | null>(null)
  useEffect(() => {
    setD(null); setErr(null)                                   // a new link starts from nothing
    api.get<Share>(`/v1/assurance/${token}`).then(setD)
      .catch(e => setErr({ label: apiMessage(e, 'This link could not be opened'), detail: apiDetail(e) }))
  }, [token])
  const active = d?.status === 'active'
  const span = d ? new Date(d.expires_at).getTime() - new Date(d.created_at).getTime() : 0
  const left = d ? Math.max(0, Math.ceil((new Date(d.expires_at).getTime() - Date.now()) / DAY_MS)) : 0
  return (
    <div className="public-page">
      <div className="w-full max-w-[560px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={34} /><Wordmark className="block text-xl" /></div>
        <div className="card p-6">
          {err && <div className="text-center py-4"><h1 className="display text-xl font-semibold m-0">Not available</h1>
            <MessageLine m={err} className="text-[13px] text-[var(--color-mute)] mt-2 justify-center" /></div>}
          {!d && !err && <p className="text-[var(--color-faint)] text-sm">Opening…</p>}
          {d && (<div>
            <div className="flex items-center gap-2 text-[var(--color-sky)] mb-2">
              <ShieldCheck size={20} /><span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-blue)]">Assurance pack</span>
            </div>
            <h1 className="display text-xl font-semibold m-0">{d.organisation}</h1>
            <p className="text-[13.5px] text-[var(--color-mute)] mt-1 mb-0">{d.report ?? 'Its report'} · {d.period_label}</p>
            <div className="flex flex-wrap items-center gap-2 mt-3 text-[12px] text-[var(--color-faint)]">
              <StatusChip value={d.status} label={d.status === 'exhausted' ? 'Limit reached' : undefined} tone={active ? 'good' : 'bad'} /><span>Shared with {d.recipient_name} on {day(d.created_at)}{d.created_by ? ` by ${d.created_by}` : ''}</span>
            </div>
            {d.purpose && <p className="text-[13px] text-[var(--color-ink)] mt-3 mb-0 border-l-2 border-[var(--color-line-2)] pl-3">{d.purpose}</p>}
            <div className="mt-4 space-y-3">
              <Bar label={active ? `Open until ${day(d.expires_at)}` : `Expiry ${day(d.expires_at)}`} right={active ? `${left} of ${Math.round(span / DAY_MS)} days left` : '—'}
                share={active && span > 0 ? left * DAY_MS / span : 0} tone="var(--color-sky)" />
              {d.max_downloads != null && <Bar label="Downloads used" right={`${d.n_downloads} of ${d.max_downloads}`}
                share={d.max_downloads ? d.n_downloads / d.max_downloads : 0} tone={d.n_downloads >= d.max_downloads ? 'var(--color-bad)' : 'var(--color-good)'} />}
            </div>
            <MessageLine m={d.contents} className="mt-4 text-[13px] text-[var(--color-ink)]" />
            {active ? <a href={`/v1/assurance/${token}/download.zip`} className="mt-5 w-full justify-center inline-flex items-center gap-2 rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition"><Download size={15} /> Download the assurance pack (ZIP)</a>
              : d.state && <div className="mt-5 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] px-4 py-3 text-[12.5px] text-[var(--color-mute)]"><MessageLine m={d.state} /></div>}
          </div>)}
        </div>
      </div>
    </div>
  )
}
