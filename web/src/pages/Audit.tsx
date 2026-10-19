import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Card, PageHeader } from '../components/ui'
import { HEADING, InfoButton } from '../components/Details'
import { actionLabel } from '../lib/actionLabels'
import { prettify } from '../lib/hazards'

interface Row {
  id: string; action: string; target_type: string | null; target_id: string | null
  detail: Record<string, unknown> | null; actor_email: string | null; actor_name: string | null; created_at: string | null
}

// What a change was made to, in customer words (the audit log records the table it touched); anything else by its words.
const TARGET: Record<string, string> = {
  regulatory_filing: 'Filing', filing: 'Filing', report_snapshot: 'Frozen report', board_pack: 'Board pack',
  approval: 'Approval', approval_policy: 'Approval rule', organization: 'Organisation', organisation: 'Organisation',
  user: 'User', role: 'Role', ingest_batch: 'Data import', ingest_token: 'Upload key', client_intake: 'Client onboarding',
  fund: 'Fund', fund_share_class: 'Share class', eet_publication: 'European ESG Template', esign_request: 'Signature request',
  sftp_key: 'File-transfer key', config: 'Settings', tenant_sso_config: 'Single sign-on', subscription: 'Subscription',
  supervision_request: 'Supervisory request', period: 'Reporting period', third_party: 'Third party',
  reporting_entity: 'Reporting entity', data_feed: 'Data feed', customer_contract: 'Contract', template_answers: 'Answers',
  issuer: 'Company', model: 'Model', control: 'Control', mandate: 'Mandate',
}
const targetLabel = (t: string | null) => !t ? '—' : TARGET[t] ?? prettify(t)
const ACTION_TONE = (a: string) => a.includes('delete') ? 'text-[var(--color-bad)]' : a.includes('decide') || a.includes('approval') ? 'text-[var(--color-warn)]' : 'text-[var(--color-blue)]'
const value = (v: unknown) => v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)

// what was recorded with the change, one click away: the changed fields (before → after) or the recorded values
function details(r: Row) {
  const d = r.detail ?? {}
  const c = d.changes as Record<string, unknown> | undefined
  const fields = c && Object.keys(c).length ? c : Object.fromEntries(Object.entries(d).filter(([k]) => k !== 'target_id'))
  return {
    title: actionLabel(r.action),
    sections: [
      ...Object.entries(fields).map(([k, v]) => ({ heading: prettify(k), body: value(v) })),
      ...(r.target_id ? [{ heading: 'Reference', body: `${targetLabel(r.target_type)} ${r.target_id}` }] : []),
    ],
  }
}

export default function Audit({ embedded = false }: { embedded?: boolean }) {
  const [actor, setActor] = useState('')
  const q = useQuery({ queryKey: ['audit', actor], queryFn: () => api.get<Row[]>(`/v1/admin/audit?limit=100${actor ? `&actor=${encodeURIComponent(actor)}` : ''}`) })
  const rows = q.data ?? []

  return (
    <div className={embedded ? 'space-y-6' : 'fadeup space-y-6'}>
      {!embedded && (
        <PageHeader eyebrow="Governance · accountability" title="Audit trail" lead="Who changed what, and when."
          about={[{ heading: HEADING.shows, body: 'Every change made in your organisation: who made it, when, and — where it needed a second approval — who approved it.' },
            { heading: HEADING.read, body: 'Entries are written as changes happen and cannot be edited or removed. Open ⓘ on a row for what was recorded with it.' }]} />
      )}

      <input value={actor} onChange={e => setActor(e.target.value)} placeholder="Filter by e-mail…" aria-label="Filter by e-mail"
        className="w-full max-w-sm bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />

      {q.isLoading ? <Center>Loading…</Center> : rows.length === 0 ? <Card className="p-10 text-center text-[var(--color-faint)] text-sm">No entries yet.</Card> : (
        <Card className="p-0 overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-[var(--color-faint)] text-[10.5px] uppercase tracking-wide text-left border-b border-[var(--color-line)]">
                <th className="font-normal py-2.5 px-4">When</th><th className="font-normal px-4">Who</th>
                <th className="font-normal px-4">Action</th><th className="font-normal px-4">On</th><th className="font-normal px-4"><span className="sr-only">Details</span></th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => {
                const det = details(r)
                return (
                  <tr key={r.id} className="border-b border-[var(--color-line)] last:border-0">
                    <td className="py-2.5 px-4 tabular-nums text-[11.5px] text-[var(--color-mute)] whitespace-nowrap">{r.created_at ? new Date(r.created_at).toLocaleString() : '—'}</td>
                    <td className="px-4 text-[var(--color-ink)] whitespace-nowrap">{r.actor_name ?? r.actor_email ?? '—'}</td>
                    <td className={`px-4 whitespace-nowrap ${ACTION_TONE(r.action)}`}>{actionLabel(r.action)}</td>
                    <td className="px-4 text-[var(--color-mute)] whitespace-nowrap">{targetLabel(r.target_type)}</td>
                    <td className="px-4"><div className="flex justify-end">{det.sections.length > 0 && <InfoButton compact details={det} />}</div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[40vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
