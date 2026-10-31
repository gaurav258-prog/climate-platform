import { useState } from 'react'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Button } from '../ui'
import { HEADING } from '../Details'
import { SidePanel } from '../sfdr/visuals'

// An institution's size class and listing for a reference date (services/governance/crr_filers.py), each sent for a
// second person's approval: they decide whether it discloses its ESG risks twice a year or once, and whether a
// subsidiary discloses its own. The statements and their choices come from the server.

// listing_for: the size classes whose frequency the listing decides (a G-SII's and a non-large institution's it does not)
export interface Statement { key: string; label: string; choices: Record<string, string>; listing_for?: string[] }

const input = 'block w-full mt-1 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1.5 text-[12.5px]'

export default function SizeListingForm({ periodEnd, member, name, statements, onClose, onSent }: {
  periodEnd: string; member: string; name: string; statements: Statement[]; onClose: () => void; onSent: () => void
}) {
  const [pick, setPick] = useState<Record<string, string>>(() => Object.fromEntries(statements.map(s => [s.key, Object.keys(s.choices)[0]])))
  const [busy, setBusy] = useState(false)
  const size = statements.find(s => s.listing_for)
  // with a size class to state, the listing is asked only for a size class it decides
  const asked = statements.filter(s => !size || s === size || size.listing_for!.includes(pick[size.key]))
  const send = async () => {
    setBusy(true)
    try {
      for (const s of asked)
        await api.post('/v1/provided', { framework: 'bank_p3esg', datapoint_key: s.key, value_text: pick[s.key],
                                         breakdown_member: member, reporting_period_end: periodEnd })
      toast.success('Sent — it takes effect once a second person approves it under Approvals'); onSent()
    } catch (e) { toast.error(apiDetail(e)?.what ?? apiMessage(e, 'Could not send the statement.')) } finally { setBusy(false) }
  }
  return (
    <SidePanel title={`Size class and listing · ${name}`} onClose={onClose}
      about={{ title: 'Size class and listing', sections: [
        { heading: HEADING.read, body: 'A G-SII, or a large institution that is listed, discloses its ESG risks at the half-year and the year end; every other institution at the year end. A large subsidiary discloses its own. Each statement is for this reference date, and a second person approves it.' },
        { heading: 'Listed', body: 'It has issued securities admitted to trading on a regulated market of a Member State.' },
        { heading: 'Legal basis', body: 'Regulation (EU) No 575/2013, Art. 4(1)(133), (146), (148); Arts 13(1), 433a, 433b and 433c.' }] }}>
      <div className="space-y-3">
        <div className="text-[12px] text-[var(--color-faint)]">For the reference date {periodEnd}</div>
        {asked.map(s => (
          <label key={s.key} className="block text-[12.5px] text-[var(--color-mute)]">{s.label}
            <select aria-label={s.label} value={pick[s.key]} onChange={e => setPick(p => ({ ...p, [s.key]: e.target.value }))} className={input}>
              {Object.entries(s.choices).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>))}
        <div className="flex gap-2"><Button variant="primary" onClick={send} disabled={busy}>Send for approval</Button>
          <Button variant="ghost" onClick={onClose}>Cancel</Button></div>
      </div>
    </SidePanel>
  )
}
