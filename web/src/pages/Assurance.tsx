import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ShieldCheck } from 'lucide-react'
import { api } from '../lib/api'
import { BrandMark } from '../components/ui'

// The auditor's page: opened from the share e-mail, no login. Shows the filing, the purpose and the expiry, and offers
// the evidence bundle; every open and download is logged on the organisation's audit trail.
interface Share { organisation: string; framework: string; period_label: string; recipient_name: string; purpose: string; expires_at: string; max_downloads: number | null; n_downloads: number; status: string; created_at: string; created_by: string | null }
export default function Assurance() {
  const { token = '' } = useParams()
  const [d, setD] = useState<Share | null>(null); const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.get<Share>(`/v1/assurance/${token}`).then(setD).catch(() => setErr('This link is not a share we know, or it has been removed.')) }, [token])
  const gone: Record<string, string> = { revoked: 'The organisation has revoked this share.', expired: 'This share has expired.', exhausted: 'This share has reached its download limit.' }
  return (
    <div className="public-page">
      <div className="w-full max-w-[560px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={34} /><div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div></div>
        <div className="card p-6">
          {err && <div className="text-center py-4"><h1 className="display text-xl font-semibold m-0">Not available</h1><p className="text-[13px] text-[var(--color-mute)] mt-2">{err}</p></div>}
          {!d && !err && <p className="text-[var(--color-faint)] text-sm">Opening…</p>}
          {d && (<div>
            <div className="text-[var(--color-sky)] mb-2"><ShieldCheck size={20} /></div>
            <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Assurance pack · shared with {d.recipient_name}</div>
            <h1 className="display text-xl font-semibold m-0">{d.organisation} — {d.framework} {d.period_label}</h1>
            <p className="text-[13px] text-[var(--color-mute)] mt-1.5">Shared on {d.created_at.slice(0, 10)}{d.created_by ? ` by ${d.created_by}` : ''} for: {d.purpose}.</p>
            <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-1.5 text-[12.5px]">
              <dt className="text-[var(--color-faint)]">Status</dt><dd className="m-0 font-medium" style={{ color: d.status === 'active' ? 'var(--color-good)' : 'var(--color-bad)' }}>{d.status}</dd>
              <dt className="text-[var(--color-faint)]">Expires</dt><dd className="m-0">{d.expires_at.slice(0, 16).replace('T', ' ')} UTC{d.max_downloads ? ` · ${d.n_downloads} of ${d.max_downloads} downloads used` : ''}</dd>
              <dt className="text-[var(--color-faint)]">Contents</dt><dd className="m-0 text-[var(--color-mute)]">Cover, methodology, validation record, four-eyes approvals, provenance and lineage, the reporting control register with outcomes, the report as filed, and a hashed manifest.</dd>
            </dl>
            {d.status === 'active' ? <a href={`/v1/assurance/${token}/download.zip`} className="mt-5 w-full justify-center inline-flex items-center rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">Download the assurance pack (ZIP)</a>
              : <div className="mt-5 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] px-4 py-3 text-[12.5px] text-[var(--color-mute)]">{gone[d.status] ?? 'This share is not available.'} Contact {d.organisation} if you still need the pack.</div>}
            <p className="text-[11.5px] text-[var(--color-faint)] mt-4">Every open and download of this share is recorded on {d.organisation}'s audit trail. The manifest inside the pack lists the SHA-256 of every file.</p>
          </div>)}
        </div>
      </div>
    </div>
  )
}
