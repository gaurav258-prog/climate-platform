import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, download } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'
import { severityHex } from '../components/SiteMap'

// Third-party physical exposure — the critical service providers, custodians, data centres and outsourcers the
// organisation depends on, located and read at the same engine score as its own sites.
interface TP { third_party_id: string; name: string; kind: string; kind_label: string; service: string | null; criticality: string; address: string | null; country: string | null; latitude: number; longitude: number; h3_cell: string
  geocode_precision: string | null; contract_ref: string | null; note: string | null; created_at: string; created_by: string | null; hazards: { hazard: string; score: number }[]; n_hazards_scored: number; max_score: number | null; worst_hazard: string | null; bucket: string | null; scored: boolean }
interface Resp { third_parties: TP[]; kinds: Record<string, string>; criticality: string[]; scenario: string; horizon: string; note: string; can_edit: boolean
  summary: { n: number; critical: number; scored: number; pending: number; high: number; critical_high: number } }
const inp = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
const CRIT: Record<string, string> = { critical: 'var(--color-bad)', important: 'var(--color-warn)', standard: 'var(--color-mute)' }

export default function ThirdParties() {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['third-parties'], queryFn: () => api.get<Resp>('/v1/third-parties'), refetchInterval: d => (d.state.data?.summary.pending ?? 0) > 0 ? 8000 : false })
  const [f, setF] = useState({ name: '', kind: 'critical_service_provider', service: '', criticality: 'critical', address: '', country: '', contract_ref: '' })
  const [busy, setBusy] = useState(false); const [open, setOpen] = useState<string | null>(null)
  const d = q.data
  const add = async () => {
    setBusy(true)
    try { await api.post('/v1/third-parties', { ...f, service: f.service || null, address: f.address || null, country: f.country || null, contract_ref: f.contract_ref || null }); toast.success(`${f.name} added — scoring its location.`); setF({ ...f, name: '', service: '', address: '', contract_ref: '' }); await qc.invalidateQueries({ queryKey: ['third-parties'] }) }
    catch (e) { toast.error((e as Error).message || 'Could not add the third party.') } finally { setBusy(false) }
  }
  const end = async (t: TP) => { if (!window.confirm(`End the relationship with ${t.name}? It stays on the audit trail.`)) return; try { await api.del(`/v1/third-parties/${t.third_party_id}`); await qc.invalidateQueries({ queryKey: ['third-parties'] }) } catch (e) { toast.error((e as Error).message) } }
  const s = d?.summary
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Assess · third parties" title="Third-party physical exposure"
        lead="The providers your operations depend on — data centres, cloud, custodians, outsourced functions — located like your own sites and read at the same engine score. A critical provider in a high-hazard cell is an operational-resilience question before it is a climate one."
        actions={<Button variant="ghost" onClick={() => download('/v1/third-parties/register.csv', 'third-party-register.csv')}>Export register (CSV)</Button>} />
      {s && <StatGrid cols={4} items={[
        { label: 'Third parties', value: String(s.n), sub: `${s.critical} critical` },
        { label: 'High or very high exposure', value: String(s.high), sub: 'max hazard score ≥ 60', accent: s.high ? 'var(--color-warn)' : 'var(--color-good)' },
        { label: 'Critical and high', value: String(s.critical_high), sub: 'needs a resilience answer', accent: s.critical_high ? 'var(--color-bad)' : 'var(--color-good)' },
        { label: 'Scored / pending', value: `${s.scored} / ${s.pending}`, sub: d?.note ? 'new locations score in the background' : '' },
      ]} />}
      {d?.can_edit && (
        <Card className="p-5">
          <div className="text-[13px] font-medium text-[var(--color-ink)] mb-2">Add a third party</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Name" className={inp} />
            <select value={f.kind} onChange={e => setF({ ...f, kind: e.target.value })} className={inp}>{Object.entries(d.kinds).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            <input value={f.service} onChange={e => setF({ ...f, service: e.target.value })} placeholder="Service provided" className={inp} />
            <select value={f.criticality} onChange={e => setF({ ...f, criticality: e.target.value })} className={inp}>{d.criticality.map(c => <option key={c} value={c}>{c}</option>)}</select>
            <input value={f.address} onChange={e => setF({ ...f, address: e.target.value })} placeholder="Address (geocoded) — or coordinates via API" className={inp + ' md:col-span-2'} />
            <input value={f.country} onChange={e => setF({ ...f, country: e.target.value.toUpperCase().slice(0, 2) })} placeholder="Country (ISO-2)" className={inp} />
            <input value={f.contract_ref} onChange={e => setF({ ...f, contract_ref: e.target.value })} placeholder="Contract reference" className={inp} />
          </div>
          <div className="flex justify-end mt-2"><Button onClick={add} disabled={busy || !f.name || !f.address}>{busy ? 'Locating…' : 'Add and score'}</Button></div>
        </Card>)}
      <Card className="p-5">
        {q.isLoading ? <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">loading…</div> : (d?.third_parties.length ?? 0) === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No third party registered yet.</div> : (
          <div className="overflow-x-auto"><table className="data-table text-[12px]">
            <thead><tr><th>Third party</th><th>Kind</th><th>Criticality</th><th>Location</th><th>Worst hazard</th><th className="num">Score</th><th>Bucket</th><th className="num">Hazards</th><th></th></tr></thead>
            <tbody>{d!.third_parties.map(t => (<>
              <tr key={t.third_party_id}>
                <td><span className="text-[var(--color-ink)]">{t.name}</span>{t.service && <div className="text-[11px] text-[var(--color-faint)]">{t.service}</div>}</td>
                <td>{t.kind_label}</td>
                <td><span className="font-medium" style={{ color: CRIT[t.criticality] }}>{t.criticality}</span></td>
                <td>{t.address ?? `${t.latitude.toFixed(3)}, ${t.longitude.toFixed(3)}`}<div className="mono text-[10px] text-[var(--color-faint)]">{t.country ?? ''} · {t.geocode_precision ?? ''} · {t.h3_cell}</div></td>
                <td>{t.worst_hazard ?? <span className="text-[var(--color-faint)]">pending</span>}</td>
                <td className="num mono" style={{ color: severityHex(t.max_score) }}>{t.max_score != null ? t.max_score.toFixed(0) : '—'}</td>
                <td>{t.bucket ?? '—'}</td>
                <td className="num mono">{t.n_hazards_scored}</td>
                <td className="whitespace-nowrap"><button onClick={() => setOpen(open === t.third_party_id ? null : t.third_party_id)} className="text-[var(--color-sky)] hover:underline">{open === t.third_party_id ? 'Hide' : 'Hazards'}</button>{d!.can_edit && <>{' · '}<button onClick={() => end(t)} className="text-[var(--color-bad)] hover:underline">End</button></>}</td>
              </tr>
              {open === t.third_party_id && <tr key={t.third_party_id + '-h'}><td colSpan={9} className="bg-[var(--color-panel-2)]"><div className="flex flex-wrap gap-1.5 py-1">{t.hazards.map(h => <span key={h.hazard} className="px-2 py-0.5 rounded-full border border-[var(--color-line)] mono text-[11px]" style={{ color: severityHex(h.score) }}>{h.hazard} {h.score.toFixed(0)}</span>)}{t.contract_ref && <span className="text-[11px] text-[var(--color-faint)] ml-auto">contract {t.contract_ref} · added {t.created_at.slice(0, 10)} by {t.created_by ?? '—'}</span>}</div></td></tr>}
            </>))}</tbody></table></div>)}
      </Card>
    </div>
  )
}
