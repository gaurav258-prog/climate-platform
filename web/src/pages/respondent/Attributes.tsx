import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardList } from 'lucide-react'
import clsx from 'clsx'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { Button, Card, SectionHead } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { HEADING, InfoButton } from '../../components/Details'
import { field } from './common'
import { useMandates } from './data'

// What a supervisor's mandate criteria read — size, listing, public-interest status — stated by us as of a balance-sheet
// date. An attribute a requirement needs before it can be judged carries a 'Needed' chip.
interface AttrResp { attributes: Record<string, { value: unknown; source: string; as_of: string | null }>
  definitions: Record<string, { label: string; type: string; unit?: string; source?: string }>; can_edit: boolean }

const ABOUT = [
  { heading: HEADING.shows, body: 'The facts about your organisation that decide which supervisory requirements apply to it: its size, whether its securities are listed, whether it is a public-interest entity.' },
  { heading: HEADING.read, body: '‘Needed’ marks an attribute that at least one requirement cannot be judged without. Values are stated as of a balance-sheet date.' },
]

export function RegulatoryAttributes() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const isReg = profile?.org?.type === 'regulator'
  const q = useQuery({ queryKey: ['my-reg-attributes'], enabled: !isReg, queryFn: () => api.get<AttrResp>('/v1/me/supervisors/regulatory-attributes') })
  const mandates = useMandates(!isReg)
  const [form, setForm] = useState<Record<string, string>>({})
  const [asOf, setAsOf] = useState('')
  const [busy, setBusy] = useState(false)
  if (isReg || !q.data) return null
  const d = q.data
  const needed = new Set((mandates.data?.mandates ?? []).flatMap(m => m.missing))
  const editable = Object.entries(d.definitions).filter(([, def]) => !(def.source ?? '').startsWith('organizations.'))
  const stated = editable.filter(([k]) => d.attributes[k]?.value != null).length
  const fromRecord = Object.values(d.definitions).filter(def => (def.source ?? '').startsWith('organizations.')).map(def => def.label)
  const about = [...ABOUT, ...(fromRecord.length ? [{ heading: HEADING.limits, body: `From your organisation’s record, not edited here: ${fromRecord.join('; ')}.` }] : [])]
  const save = async () => {
    setBusy(true)
    try {
      const body: Record<string, unknown> = {}
      for (const [k, v] of Object.entries(form)) body[k] = v === '' ? null : d.definitions[k].type === 'bool' ? v === 'yes' : d.definitions[k].type === 'number' ? Number(v.replace(/[,\s]/g, '')) : v
      await api.put('/v1/me/supervisors/regulatory-attributes', { attributes: body, as_of: asOf || null }); setForm({}); toast.success('Regulatory attributes saved.')
      await qc.invalidateQueries({ queryKey: ['my-reg-attributes'] }); await qc.invalidateQueries({ queryKey: ['my-mandates'] })
    } catch (e) { toast.error(apiMessage(e, 'Could not save the attributes.')) } finally { setBusy(false) }
  }
  const shown = (k: string, v: unknown) => d.definitions[k].type === 'bool' ? (v ? 'yes' : 'no') : typeof v === 'number' ? v.toLocaleString('en-GB') : String(v)
  const val = (k: string) => form[k] ?? (d.attributes[k]?.value == null ? '' : shown(k, d.attributes[k].value))
  return (
    <Card className="p-5 space-y-3">
      <div className="flex items-center gap-2">
        <SectionHead icon={ClipboardList}>Regulatory attributes</SectionHead>
        <InfoButton compact details={{ title: 'Regulatory attributes', sections: about }} />
      </div>
      <div className="flex items-center gap-3 text-[12px]">
        <div className="h-2 flex-1 rounded-full bg-[var(--color-panel-2)] overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${editable.length ? (stated / editable.length) * 100 : 0}%`, background: 'var(--color-sky)' }} />
        </div>
        <span className="text-[var(--color-mute)] tabular-nums">{stated} of {editable.length} stated</span>
      </div>
      <div className="space-y-1.5 text-[13px]">
        {editable.map(([k, def]) => (
          <label key={k} className="flex items-center justify-between gap-3 border-b border-[var(--color-line)] pb-1.5">
            <span className="text-[var(--color-mute)] flex items-center gap-2 min-w-0">{def.label}{def.unit === 'eur' ? ' (€)' : ''}
              {needed.has(k) && d.attributes[k]?.value == null && <StatusChip label="Needed" tone="warn" />}</span>
            {def.type === 'bool' ? (
              <select value={val(k)} disabled={!d.can_edit} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} className={field}>
                <option value="">Not stated</option><option value="yes">Yes</option><option value="no">No</option></select>
            ) : <input value={val(k)} disabled={!d.can_edit} onChange={e => setForm(f => ({ ...f, [k]: e.target.value }))} placeholder="Not stated"
                inputMode={def.type === 'number' ? 'decimal' : undefined} className={clsx(field, 'text-right w-40')} />}
          </label>))}
      </div>
      {d.can_edit && (
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-[12px] text-[var(--color-mute)]">As of <input type="date" value={asOf} onChange={e => setAsOf(e.target.value)} className={clsx(field, 'ml-2')} /></label>
          <Button onClick={save} disabled={busy || Object.keys(form).length === 0}>{busy ? 'Saving…' : 'Save attributes'}</Button>
        </div>)}
    </Card>
  )
}
