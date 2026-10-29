import { useState } from 'react'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import { HEADING } from '../Details'
import { SidePanel } from '../sfdr/visuals'
import { ROLE } from './words'

// An undertaking's reporting role for a financial year (services/governance/csrd_roles.py), sent for a second person's
// approval: the ESRS statement and the EU Taxonomy reports read who reports from it.

const input = 'block w-full mt-1 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1.5 text-[12.5px]'
const PARENT = { parent_name: 'Parent’s name', parent_registered_office: 'Parent’s registered office', parent_report_ref: 'Link to its consolidated report' } as const

export default function ReportingRoleForm({ periodEnd, entity, name, initial, onClose, onSent }: {
  periodEnd: string; entity: string; name?: string; initial?: string; onClose: () => void; onSent: () => void
}) {
  const [r, setR] = useState<string>(initial ?? 'individual')
  const [parent, setParent] = useState({ parent_name: '', parent_registered_office: '', parent_report_ref: '' })
  const [basis, setBasis] = useState('')
  const [busy, setBusy] = useState(false)
  const send = async () => {
    setBusy(true)
    try {
      await api.post('/v1/periods/role', { period_end: periodEnd, entity_id: entity || null, role: r, basis: basis || null,
        ...(r === 'exempt_subsidiary' ? parent : {}) })
      toast.success('Role sent — a second person approves it under Approvals'); onSent()
    } catch (e) { toast.error(apiMessage(e, 'Could not state the role.')) } finally { setBusy(false) }
  }
  return (
    <SidePanel title={name ? `Reporting role · ${name}` : 'Reporting role'} onClose={onClose}
      about={{ title: 'Reporting role', sections: [{ heading: HEADING.read, body: 'The role for this financial year decides which point of the Directive applies. A second person approves it.' },
        { heading: 'Legal basis', body: 'Directive 2013/34/EU: Article 19a (individual statement), Article 29a (consolidated statement), Articles 19a(9) and 29a(8) (exempt subsidiary).' }] }}>
      <div className="space-y-3">
        <label className="block text-[12.5px] text-[var(--color-mute)]">Role
          <select aria-label="Role" value={r} onChange={e => setR(e.target.value)} className={input}>
            {Object.entries(ROLE).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        {r === 'exempt_subsidiary' && (Object.keys(PARENT) as (keyof typeof PARENT)[]).map(k => (
          <label key={k} className="block text-[12.5px] text-[var(--color-mute)]">{PARENT[k]}
            <input aria-label={PARENT[k]} value={parent[k]} onChange={e => setParent(p => ({ ...p, [k]: e.target.value }))} className={input} /></label>))}
        <label className="block text-[12.5px] text-[var(--color-mute)]">Basis (optional)
          <textarea rows={2} value={basis} onChange={e => setBasis(e.target.value)} className={input} /></label>
        <div className="flex gap-2"><Button variant="primary" onClick={send} disabled={busy}>Send for approval</Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button></div>
      </div>
    </SidePanel>
  )
}
