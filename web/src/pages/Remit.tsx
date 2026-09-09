import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { FileLock2 } from 'lucide-react'
import { api } from '../lib/api'
import { BrandMark } from '../components/ui'
import { SECTION_LABEL, STATUS, type Remittance } from '../components/Remittance'

// The recipient's page: opened from the link in the remittance e-mail, no login. Shows what was remitted, by whom,
// for what, until when, and offers the watermarked PDF and the scoped JSON. Every open and download is logged on
// the issuing authority's and the entity's audit trails; the API refuses once expired, revoked or exhausted.
type View = Remittance & { notice: string }
export default function Remit() {
  const { token = '' } = useParams()
  const [d, setD] = useState<View | null>(null); const [err, setErr] = useState<string | null>(null)
  useEffect(() => { api.get<View>(`/v1/remit/${token}`).then(setD).catch(() => setErr('This link is not a remittance we know, or it has been removed.')) }, [token])
  const st = d ? STATUS[d.status] : null
  return (
    <div className="public-page">
      <div className="w-full max-w-[560px] fadeup">
        <div className="flex items-center gap-3 mb-6"><BrandMark size={34} /><div className="display text-xl font-semibold">Tel<span className="text-[var(--color-sky)]">lumen</span></div></div>
        <div className="card p-6">
          {err && <div className="text-center py-4"><h1 className="display text-xl font-semibold m-0">Not available</h1><p className="text-[13px] text-[var(--color-mute)] mt-2">{err}</p></div>}
          {!d && !err && <p className="text-[var(--color-faint)] text-sm">Opening…</p>}
          {d && st && (
            <div>
              <div className="text-[var(--color-sky)] mb-2"><FileLock2 size={20} /></div>
              <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-blue)] mb-1">Governed remittance · {d.reference}</div>
              <h1 className="display text-xl font-semibold m-0">Supervisory case file — {d.entity}</h1>
              <p className="text-[13px] text-[var(--color-mute)] mt-1.5">Remitted by {d.regulator} to {d.recipient_name} ({d.recipient_kind_label}) on {d.created_at.slice(0, 10)}{d.created_by ? ` by ${d.created_by}` : ''}.</p>
              <dl className="mt-4 grid grid-cols-[120px_1fr] gap-y-1.5 text-[12.5px]">
                <dt className="text-[var(--color-faint)]">Status</dt><dd className="m-0 font-medium" style={{ color: st.color }}>{st.label}</dd>
                <dt className="text-[var(--color-faint)]">Purpose</dt><dd className="m-0 text-[var(--color-ink)]">{d.purpose}</dd>
                <dt className="text-[var(--color-faint)]">Legal basis</dt><dd className="m-0 text-[var(--color-ink)]">{d.legal_basis.stated ? `${d.legal_basis.stated} · ` : ''}{d.legal_basis.url ? <a href={d.legal_basis.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">{d.legal_basis.ref}</a> : d.legal_basis.ref}</dd>
                <dt className="text-[var(--color-faint)]">Sections</dt><dd className="m-0 text-[var(--color-ink)]">{d.sections.map(s => SECTION_LABEL[s] ?? s).join(', ')}</dd>
                <dt className="text-[var(--color-faint)]">Expires</dt><dd className="m-0 text-[var(--color-ink)]">{d.expires_at.slice(0, 16).replace('T', ' ')} UTC{d.max_downloads ? ` · ${d.n_downloads} of ${d.max_downloads} downloads used` : ''}</dd>
                <dt className="text-[var(--color-faint)]">Document hash</dt><dd className="m-0 mono text-[11px] text-[var(--color-mute)] break-all">{d.pdf_sha256}</dd>
              </dl>
              {d.status === 'active' ? (
                <div className="flex gap-2 mt-5">
                  <a href={`/v1/remit/${token}/download.pdf`} className="flex-1 justify-center inline-flex items-center rounded-lg bg-[var(--color-sky)] text-[#08111f] px-4 py-2.5 text-[13px] font-medium hover:bg-[var(--color-blue)] transition">Download the case file (PDF)</a>
                  <a href={`/v1/remit/${token}/download.json`} className="justify-center inline-flex items-center rounded-lg border border-[var(--color-line-2)] px-4 py-2.5 text-[13px] text-[var(--color-ink)] hover:border-[var(--color-sky)] transition">JSON</a>
                </div>
              ) : <div className="mt-5 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] px-4 py-3 text-[12.5px] text-[var(--color-mute)]">
                {d.status === 'revoked' ? 'The issuing authority has revoked this remittance.' : d.status === 'expired' ? 'This remittance has expired.' : 'This remittance has reached its download limit.'} Contact {d.regulator} if you still need the case file.</div>}
              <p className="text-[11.5px] text-[var(--color-faint)] mt-4">{d.notice}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
