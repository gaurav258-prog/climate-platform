import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileArchive, FileDown, Inbox, Share2 } from 'lucide-react'
import { api, apiMessage, download } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { frameworkLabel } from '../../lib/hazards'
import { Button, Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton, messageDetails, type Message } from '../../components/Details'
import { RemitDialog } from '../../components/Remittance'
import { day, field } from './common'

// The entity file's records: filings the entity transmitted to the authority, with the receipt issued, and the evidence
// packs (immutable, versioned case files) with their share-onward action. Fingerprints and notes sit behind ⓘ.

interface Tx { transmission_id: string; framework: string; period_label: string; format: string; status: string; receipt_ref: string | null; receipt_at: string | null
  payload_sha256: string | null; created_at: string; created_by: string | null; channel_label: string | null }
export function TransmissionsReceived({ orgId }: { orgId: string }) {
  const q = useQuery({ queryKey: ['entity-transmissions', orgId], queryFn: () => api.get<{ transmissions: Tx[] }>(`/v1/supervisor/entity/${orgId}/transmissions`) })
  const rows = q.data?.transmissions ?? []
  if (rows.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead icon={Inbox} hint="sent to you, receipted">Transmissions received</SectionHead>
      <div className="divide-y divide-[var(--color-line)] mt-2">{rows.map(t => (
        <div key={t.transmission_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
          <span className="text-[var(--color-ink)] mr-auto">{frameworkLabel(t.framework)} <span className="text-[var(--color-faint)]">· {t.period_label}</span></span>
          {t.receipt_ref ? <StatusChip label={`Receipt ${t.receipt_ref}`} tone="good" /> : <StatusChip value={t.status} />}
          <span className="text-[var(--color-faint)] tabular-nums">{day(t.receipt_at ?? t.created_at)}</span>
          <InfoButton compact details={{ title: frameworkLabel(t.framework), sections: [
            { heading: HEADING.shows, body: `${t.period_label}, sent by ${t.created_by ?? 'the entity'} on ${day(t.created_at)}${t.channel_label ? ` through ${t.channel_label}` : ''}, as ${t.format.toUpperCase()}.` },
            ...(t.payload_sha256 ? [{ heading: 'Content fingerprint', body: <span className="break-all tabular-nums">{t.payload_sha256}</span> }] : []),
          ] }} />
        </div>))}</div>
    </Card>
  )
}

interface Pack { pack_id: string; version: number; label: string; basis_label: string; sha256: string; pdf_bytes: number; note: string | null; generated_at: string; generated_by: string | null }
export function EvidencePacks({ orgId }: { orgId: string }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const perms = profile?.permissions ?? []
  const can = perms.includes('supervisor.evidence.export'), canRemit = perms.includes('supervisor.remit')
  const [remit, setRemit] = useState<Pack | null>(null)
  const q = useQuery({ queryKey: ['evidence-packs', orgId], enabled: can, queryFn: () => api.get<{ packs: Pack[]; about: Message }>(`/v1/supervisor/entity/${orgId}/evidence-packs`) })
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [all, setAll] = useState(false)
  if (!can) return null
  const generate = async () => {
    setBusy(true)
    try { const p = await api.post<Pack>(`/v1/supervisor/entity/${orgId}/evidence-packs`, { note: note || null }); setNote(''); toast.success(`Evidence pack generated: ${p.label}.`); await qc.invalidateQueries({ queryKey: ['evidence-packs', orgId] }) }
    catch (e) { toast.error(apiMessage(e, 'Could not generate the pack.')) } finally { setBusy(false) }
  }
  const packs = q.data?.packs ?? []
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <span className="flex items-center gap-2"><SectionHead icon={FileArchive}>Evidence packs</SectionHead>{q.data?.about && <InfoButton compact details={messageDetails(q.data.about)} />}</span>
        <span className="flex items-center gap-2">
          <input value={note} onChange={e => setNote(e.target.value)} placeholder="Note for this version" aria-label="Note for this version" className={`${field} w-56`} />
          <Button onClick={generate} disabled={busy}>{busy ? 'Generating…' : 'Generate a version'}</Button>
        </span>
      </div>
      {packs.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No pack generated yet.</div> : (
        <div className="divide-y divide-[var(--color-line)]">{(all ? packs : packs.slice(0, 4)).map(p => (
          <div key={p.pack_id} className="py-2 flex items-center gap-3 flex-wrap text-[12.5px]">
            <StatusChip label={p.label} tone="neutral" />
            <span className="text-[var(--color-ink)] mr-auto">{day(p.generated_at)} <span className="text-[var(--color-faint)]">· {p.generated_by ?? 'your authority'}</span></span>
            <InfoButton compact details={{ title: p.label, sections: [
              { heading: 'Read at', body: p.basis_label },
              ...(p.note ? [{ heading: 'Note', body: p.note }] : []),
              { heading: 'Content fingerprint', body: <span className="break-all tabular-nums">{p.sha256}</span> },
              { heading: 'Document', body: `${Math.max(1, Math.round(p.pdf_bytes / 1024))} kB PDF` },
            ] }} />
            <button type="button" onClick={() => download(`/v1/supervisor/entity/${orgId}/evidence-packs/${p.pack_id}.pdf`, `evidence-pack-v${p.version}.pdf`)}
              className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><FileDown size={13} />PDF</button>
            <button type="button" onClick={() => download(`/v1/supervisor/entity/${orgId}/evidence-packs/${p.pack_id}.json`, `evidence-pack-v${p.version}.json`)}
              className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><FileDown size={13} />Data</button>
            {canRemit && <button type="button" onClick={() => setRemit(p)} className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline"><Share2 size={13} />Share onward</button>}
          </div>))}</div>)}
      {packs.length > 4 && <button type="button" onClick={() => setAll(!all)} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">{all ? 'Show fewer' : `Show all ${packs.length} versions`}</button>}
      {remit && <RemitDialog orgId={orgId} packId={remit.pack_id} packVersion={remit.version} onClose={() => setRemit(null)} />}
    </Card>
  )
}
