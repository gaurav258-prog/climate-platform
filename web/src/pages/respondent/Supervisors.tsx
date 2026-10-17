import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Landmark } from 'lucide-react'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button, Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { day, useCan } from './common'

// Who supervises us, whether we have acknowledged it, and what each supervisor may see. Regional figures reach the
// supervisor regardless; individual sites only while we grant it — our decision, audited on both sides.
interface Sup { supervision_id: string; regulator_org_id: string; regulator: string; jurisdiction: string | null
  site_access: boolean; site_access_granted_at: string | null; site_access_revoked_at: string | null; since: string | null; acknowledged_at: string | null }

export function SupervisoryAccess() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['my-supervisors'], queryFn: () => api.get<{ supervisors: Sup[]; about: Message }>('/v1/me/supervisors') })
  const canManage = useCan('admin.users.manage')
  const [busy, setBusy] = useState<string | null>(null)
  const act = async (s: Sup, path: string, body: object, done: string) => {
    setBusy(s.supervision_id)
    try { await api.post(`/v1/me/supervisors/${s.supervision_id}/${path}`, body); toast.success(done); await qc.invalidateQueries({ queryKey: ['my-supervisors'] }) }
    catch (e) { toast.error(apiMessage(e, 'Could not save the change.')) }
    finally { setBusy(null) }
  }
  const sups = q.data?.supervisors ?? []
  if (!q.isLoading && sups.length === 0) return null
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3">
        <SectionHead icon={Landmark}>Your supervisors</SectionHead>
        {q.data?.about && <InfoButton compact details={messageDetails(q.data.about)} />}
      </div>
      <div className="divide-y divide-[var(--color-line)]">
        {sups.map(s => (
          <div key={s.supervision_id} className="py-2.5 flex items-center gap-3 flex-wrap">
            <div className="min-w-0 mr-auto">
              <div className="text-[13.5px] text-[var(--color-ink)]">{s.regulator}</div>
              {s.jurisdiction && <div className="text-[11.5px] text-[var(--color-faint)]">{s.jurisdiction}</div>}
            </div>
            <StatusChip label={s.acknowledged_at ? 'Acknowledged' : 'Not acknowledged'} tone={s.acknowledged_at ? 'good' : 'warn'} />
            <StatusChip label={s.site_access ? 'Sites visible' : 'Regional figures only'} tone={s.site_access ? 'warn' : 'neutral'} />
            <InfoButton compact details={{ title: s.regulator, sections: [
              { heading: 'Supervising since', body: day(s.since) },
              { heading: 'Acknowledged', body: s.acknowledged_at ? day(s.acknowledged_at) : 'Not yet' },
              { heading: 'Site-level access', body: s.site_access ? `Granted on ${day(s.site_access_granted_at)}`
                : s.site_access_revoked_at ? `Revoked on ${day(s.site_access_revoked_at)}` : 'Never granted' },
            ] }} />
            {canManage && !s.acknowledged_at && (
              <Button variant="ghost" onClick={() => act(s, 'acknowledge', {}, 'Supervision acknowledged.')} disabled={busy === s.supervision_id}>Acknowledge</Button>)}
            {canManage && (
              <Button onClick={() => act(s, 'site-access', { granted: !s.site_access }, s.site_access ? 'Site-level access revoked.' : 'Site-level access granted.')} disabled={busy === s.supervision_id}>
                {busy === s.supervision_id ? 'Saving…' : s.site_access ? 'Revoke site access' : 'Grant site access'}
              </Button>)}
          </div>
        ))}
      </div>
    </Card>
  )
}
