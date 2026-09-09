import { useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, ExternalLink } from 'lucide-react'
import { api } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { frameworkLabel } from '../lib/hazards'
import { Button, Card, PageHeader, StatGrid } from '../components/ui'

// The regulatory mandate registry: which regulation, which article (curated excerpt + the official act), who it applies
// to (criteria over entity attributes), what must be delivered, through which channel and by when, and the version
// history of the act with change detection. Then the population: for every supervised entity, applies / does not
// apply / cannot determine — with what is missing and a way to ask the entity for it.
interface Cond { attribute: string; op: string; value: unknown; label: string }
interface Version { version: string; effective_from: string; summary: string; celex: string | null; acknowledged: { at: string; by: string | null; note: string | null } | null }
interface Mandate { id: string; sectors: string[]; binding: boolean; title: string; short: string; enabled: boolean
  act: { name: string; celex: string | null; url: string; form?: { name: string; celex: string | null; url: string } }
  article: { ref: string; excerpt: string; version_date: string }
  criteria: { all_of: Cond[]; tiers?: { label: string; all_of: Cond[]; frequency?: string }[] }
  deliverable: { framework: string | null; what: string; format: string; channel: string; direction: string; due: { label: string }; frequency: string }
  versions: Version[]; latest_version: string | null; latest_acknowledged: boolean
  detection: { checked_at: string | null; watched?: string[]; changes: { change_id: string; celex: string; title: string; status: string; url: string | null; detected_at: string; effective_date: string | null }[] }
  setting: { enabled: boolean; overrides: { thresholds?: Record<string, number>; due?: Record<string, unknown> }; note: string | null } | null }
interface RegResp { registry_version: string; attributes: Record<string, { label: string; type: string; unit?: string; source?: string }>; mandates: Mandate[]; n_unacknowledged: number; note: string }
interface Cell { mandate_id: string; short: string; framework: string | null; binding: boolean; status: 'applies' | 'not_applicable' | 'cannot_determine'; status_label: string
  missing: string[]; failed: string[]; tier: { label: string; frequency?: string } | null; checks: { label: string; attribute: string; result: boolean | null; tier?: string }[]; due_date: string | null; channel: string; direction: string }
interface PopResp { period_end: string; mandates: { id: string; short: string; title: string; sectors: string[] }[]
  entities: { org_id: string; name: string; type: string; country: string | null; attributes: Record<string, { value: unknown; source: string; as_of: string | null }>; mandates: Cell[]; n_applies: number; n_cannot: number; missing: string[] }[]
  attributes: Record<string, { label: string; type: string; unit?: string }>; summary: { entities: number; cannot_determine: number; attributes_missing: number } }
const SC: Record<Cell['status'], string> = { applies: 'var(--color-good)', not_applicable: 'var(--color-faint)', cannot_determine: 'var(--color-warn)' }
const fmtVal = (v: unknown, unit?: string) => v == null ? '—' : typeof v === 'boolean' ? (v ? 'yes' : 'no') : typeof v === 'number' ? (unit === 'eur' ? (v >= 1e9 ? `€${(v / 1e9).toFixed(1)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(0)}m` : `€${v.toLocaleString()}`) : v.toLocaleString()) : String(v)
const condText = (c: Cond) => c.label

export default function SupervisorMandates() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'population' ? 'population' : 'registry'
  const setTab = (t: string) => { const p = new URLSearchParams(params); p.set('tab', t); setParams(p) }
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Regulations" title="Mandates and who they apply to"
        lead="The regulations behind your supervision: the article, who it applies to, what must be delivered, through which channel and by when, and how the act has changed. Then your population against those criteria — applies, does not apply, or cannot be determined until the entity confirms an attribute." />
      <div className="flex gap-2">
        {[['registry', 'Registry'], ['population', 'Who is regulated']].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={`px-3 py-1.5 rounded-lg text-[13px] border transition ${tab === k ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{l}</button>))}
      </div>
      {tab === 'registry' ? <Registry /> : <Population />}
    </div>
  )
}

function Registry() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const can = (profile?.permissions ?? []).includes('supervisor.mandates.manage')
  const q = useQuery({ queryKey: ['sup-mandates'], queryFn: () => api.get<RegResp>('/v1/supervisor/mandates') })
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const d = q.data
  if (!d) return <div className="py-10 text-center text-[var(--color-faint)] text-sm">loading the registry…</div>
  const ack = async (m: Mandate, v: string) => { setBusy(true); try { await api.post(`/v1/supervisor/mandates/${m.id}/versions/${v}/acknowledge`, {}); await qc.invalidateQueries({ queryKey: ['sup-mandates'] }) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) } }
  const toggle = async (m: Mandate) => { setBusy(true); try { await api.put(`/v1/supervisor/mandates/${m.id}`, { enabled: !m.enabled }); await qc.invalidateQueries({ queryKey: ['sup-mandates'] }); await qc.invalidateQueries({ queryKey: ['sup-pop-mandates'] }) } catch (e) { toast.error((e as Error).message) } finally { setBusy(false) } }
  return (<>
    <StatGrid cols={3} items={[
      { label: 'Mandates in your profile', value: String(d.mandates.length), sub: `${d.mandates.filter(m => m.binding).length} binding · ${d.mandates.filter(m => !m.binding).length} guidance` },
      { label: 'Versions to acknowledge', value: String(d.n_unacknowledged), sub: 'a new version of an act your authority has not yet reviewed', accent: d.n_unacknowledged ? 'var(--color-warn)' : undefined },
      { label: 'Detected changes pending', value: String(d.mandates.reduce((a, m) => a + m.detection.changes.filter(c => c.status !== 'reviewed').length, 0)), sub: 'flagged by the EUR-Lex watch, awaiting review' },
    ]} />
    <Card className="p-5">
      <div className="text-[11.5px] text-[var(--color-mute)] mb-3">{d.note} Registry version {d.registry_version}.</div>
      <div className="divide-y divide-[var(--color-line)]">
        {d.mandates.map(m => (
          <div key={m.id} className="py-3">
            <button onClick={() => setOpen(open === m.id ? null : m.id)} className="w-full text-left flex items-center gap-3 flex-wrap">
              <ChevronRight size={13} className={`text-[var(--color-faint)] transition-transform ${open === m.id ? 'rotate-90' : ''}`} />
              <span className="text-[13.5px] text-[var(--color-ink)] font-medium">{m.title}</span>
              <span className="mono text-[10.5px] text-[var(--color-faint)]">{m.article.ref} · {m.sectors.join(', ').replace(/_/g, ' ')}</span>
              <span className={`mono text-[9.5px] uppercase px-1.5 py-0.5 rounded ${m.binding ? 'bg-[var(--color-sky)]/15 text-[var(--color-sky)]' : 'bg-[var(--color-bg-2)] text-[var(--color-faint)]'}`}>{m.binding ? 'binding' : 'guidance'}</span>
              {!m.enabled && <span className="mono text-[9.5px] uppercase px-1.5 py-0.5 rounded bg-[var(--color-bad)]/15 text-[var(--color-bad)]">disabled by your authority</span>}
              {!m.latest_acknowledged && <span className="mono text-[9.5px] uppercase px-1.5 py-0.5 rounded bg-[var(--color-warn)]/15 text-[var(--color-warn)]">version {m.latest_version} to acknowledge</span>}
              <span className="ml-auto mono text-[10.5px] text-[var(--color-faint)]">{m.deliverable.framework ? frameworkLabel(m.deliverable.framework) : m.deliverable.what.slice(0, 40)} · {m.deliverable.direction === 'push' ? 'entity submits' : 'supervisor requests'} · {m.deliverable.due.label}</span>
            </button>
            {open === m.id && (
              <div className="mt-3 ml-6 grid lg:grid-cols-2 gap-5 text-[12.5px]">
                <div className="space-y-3">
                  <div>
                    <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">The article · {m.article.ref} · text as of {m.article.version_date}</div>
                    <blockquote className="border-l-2 border-[var(--color-line-2)] pl-3 text-[var(--color-ink)] leading-relaxed">{m.article.excerpt}</blockquote>
                    <div className="mt-1.5 flex flex-wrap gap-3">
                      <a href={m.act.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">{m.act.name} <ExternalLink size={11} /></a>
                      {m.act.form && <a href={m.act.form.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Official form: {m.act.form.name} <ExternalLink size={11} /></a>}
                    </div>
                    <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">A curated digest of the article; the linked act is authoritative.</div>
                  </div>
                  <div>
                    <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Who it applies to</div>
                    <ul className="list-disc ml-4 text-[var(--color-mute)]">{m.criteria.all_of.map((c, i) => <li key={i}>{condText(c)}</li>)}</ul>
                    {m.criteria.tiers && m.criteria.tiers.length > 0 && (
                      <div className="mt-1.5 space-y-1">{m.criteria.tiers.map((t, i) => <div key={i} className="text-[var(--color-mute)]"><span className="text-[var(--color-ink)]">{t.label}</span>{t.all_of.length ? ': ' + t.all_of.map(condText).join(' and ') : ' (all others)'}{t.frequency ? ` · ${t.frequency}` : ''}</div>)}</div>)}
                  </div>
                </div>
                <div className="space-y-3">
                  <div>
                    <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">What must be delivered, how and by when</div>
                    <div className="text-[var(--color-ink)]">{m.deliverable.what}</div>
                    <div className="text-[var(--color-mute)] mt-1">Format: {m.deliverable.format}</div>
                    <div className="text-[var(--color-mute)]">Channel: {m.deliverable.channel} · <b>{m.deliverable.direction === 'push' ? 'the entity submits' : 'the supervisor requests'}</b></div>
                    <div className="text-[var(--color-mute)]">Deadline: {m.deliverable.due.label} · {m.deliverable.frequency}</div>
                  </div>
                  <div>
                    <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Versions of the act · change log</div>
                    <div className="space-y-1.5">{m.versions.map(v => (
                      <div key={v.version} className="flex items-start gap-2">
                        <span className="mono text-[10.5px] text-[var(--color-faint)] w-14 shrink-0">{v.version}</span>
                        <div className="flex-1"><span className="text-[var(--color-ink)]">from {v.effective_from}</span> · <span className="text-[var(--color-mute)]">{v.summary}</span>
                          {v.celex && <a href={`https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:${v.celex}`} target="_blank" rel="noreferrer" className="ml-1 mono text-[10px] text-[var(--color-sky)] hover:underline">CELEX {v.celex}</a>}
                          <div className="mono text-[10px] text-[var(--color-faint)]">{v.acknowledged ? `acknowledged ${v.acknowledged.at.slice(0, 10)} by ${v.acknowledged.by ?? '—'}` : 'not yet acknowledged by your authority'}</div></div>
                        {!v.acknowledged && can && <Button variant="ghost" disabled={busy} onClick={() => ack(m, v.version)}>Acknowledge</Button>}
                      </div>))}</div>
                  </div>
                  <div>
                    <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Change detection · EUR-Lex</div>
                    <div className="text-[var(--color-mute)]">{m.detection.checked_at ? `Acts ${(m.detection.watched ?? []).join(', ')} last checked ${m.detection.checked_at.slice(0, 10)}.` : m.act.celex ? 'Not yet checked by the daily EUR-Lex scan.' : 'No EU act to watch for this guidance.'}</div>
                    {m.detection.changes.map(c => <div key={c.change_id} className="mt-1 text-[var(--color-warn)]">Detected {c.detected_at.slice(0, 10)} on CELEX {c.celex}: {c.title} · {c.status}{c.url ? <a href={c.url} target="_blank" rel="noreferrer" className="ml-1 text-[var(--color-sky)] hover:underline">source</a> : null}</div>)}
                  </div>
                  {can && <div className="flex items-center gap-3"><Button variant="ghost" disabled={busy} onClick={() => toggle(m)}>{m.enabled ? 'Disable for my authority' : 'Enable for my authority'}</Button>{m.setting?.note && <span className="text-[var(--color-faint)]">{m.setting.note}</span>}</div>}
                </div>
              </div>)}
          </div>))}
      </div>
    </Card>
  </>)
}

function Population() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAsk = (profile?.permissions ?? []).includes('supervisor.requests.manage')
  const q = useQuery({ queryKey: ['sup-pop-mandates'], queryFn: () => api.get<PopResp>('/v1/supervisor/population/mandates') })
  const [open, setOpen] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const d = q.data
  const cols = useMemo(() => d?.mandates ?? [], [d])
  if (!d) return <div className="py-10 text-center text-[var(--color-faint)] text-sm">judging each entity against the criteria…</div>
  const ask = async (org_id: string, attributes: string[]) => {
    setBusy(org_id)
    try { await api.post('/v1/supervisor/population/mandates/ask', { supervised_org_id: org_id, attributes }); toast.success('Asked the entity for the missing attributes (an information request on its thread).'); await qc.invalidateQueries({ queryKey: ['supervisor-requests'] }) }
    catch (e) { toast.error((e as Error).message) } finally { setBusy(null) }
  }
  return (<>
    <StatGrid cols={3} items={[
      { label: 'Entities judged', value: String(d.summary.entities), sub: `for period ending ${d.period_end}` },
      { label: 'Cannot determine', value: String(d.summary.cannot_determine), sub: 'entities with an attribute missing', accent: d.summary.cannot_determine ? 'var(--color-warn)' : undefined },
      { label: 'Attributes to ask for', value: String(d.summary.attributes_missing), sub: 'one click raises the request' },
    ]} />
    <Card className="p-5">
      <div className="text-[11.5px] text-[var(--color-mute)] mb-3">Each cell is the criteria of one mandate evaluated on the entity's attributes. Green applies, grey does not apply, amber cannot be determined until the entity confirms what is missing. Click an entity for the checks and its attributes.</div>
      <div className="overflow-x-auto">
        <table className="data-table w-full text-[12px]">
          <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
            <th>Entity</th>{cols.map(m => <th key={m.id} className="text-center" title={m.title}>{m.short}</th>)}<th className="num">Applies</th><th>Missing</th></tr></thead>
          <tbody>{d.entities.map(e => (<>
            <tr key={e.org_id} onClick={() => setOpen(open === e.org_id ? null : e.org_id)} className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] ${open === e.org_id ? 'bg-[var(--color-bg-2)]' : ''}`}>
              <td className="text-[var(--color-ink)] whitespace-nowrap"><ChevronRight size={12} className={`inline mr-1 text-[var(--color-faint)] transition-transform ${open === e.org_id ? 'rotate-90' : ''}`} /><Link to={`/supervised/${e.org_id}`} onClick={ev => ev.stopPropagation()} className="hover:text-[var(--color-sky)] hover:underline">{e.name}</Link><span className="mono text-[10px] text-[var(--color-faint)] ml-2">{e.type.replace(/_/g, ' ')} · {e.country ?? ''}</span></td>
              {cols.map(m => { const c = e.mandates.find(x => x.mandate_id === m.id); return (
                <td key={m.id} className="text-center">{c ? <span className="mono text-[9.5px] uppercase px-1.5 py-0.5 rounded" style={{ color: SC[c.status], background: `color-mix(in oklab, ${SC[c.status]} 14%, transparent)` }} title={c.tier ? c.tier.label : c.failed.join('; ') || c.missing.join(', ')}>{c.status === 'applies' ? (c.tier?.frequency ?? 'applies') : c.status === 'cannot_determine' ? 'unknown' : 'n/a'}</span> : <span className="text-[var(--color-faint)]">·</span>}</td>) })}
              <td className="num mono text-[var(--color-mute)]">{e.n_applies}</td>
              <td className="text-[11.5px]">{e.missing.length ? <span className="text-[var(--color-warn)]">{e.missing.map(a => d.attributes[a]?.label ?? a).join(', ')}{canAsk && <> · <button disabled={busy === e.org_id} onClick={ev => { ev.stopPropagation(); ask(e.org_id, e.missing) }} className="text-[var(--color-sky)] hover:underline">ask the entity →</button></>}</span> : <span className="text-[var(--color-faint)]">—</span>}</td>
            </tr>
            {open === e.org_id && (
              <tr key={e.org_id + '-d'}><td colSpan={cols.length + 3} className="p-0"><div className="px-6 py-3 bg-[var(--color-bg-2)] grid lg:grid-cols-2 gap-4 text-[12px]">
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">The entity's attributes</div>
                  <div className="divide-y divide-[var(--color-line)]">{Object.entries(d.attributes).map(([k, def]) => { const a = e.attributes[k]; return (
                    <div key={k} className="py-1 flex justify-between gap-3"><span className="text-[var(--color-mute)]">{def.label}</span><span className={a ? 'text-[var(--color-ink)]' : 'text-[var(--color-warn)]'}>{a ? fmtVal(a.value, def.unit) : 'not stated'}{a?.source ? <span className="mono text-[10px] text-[var(--color-faint)]"> · {a.source}{a.as_of ? ` · ${a.as_of}` : ''}</span> : null}</span></div>) })}</div>
                </div>
                <div>
                  <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">The checks, mandate by mandate</div>
                  {e.mandates.map(c => (
                    <div key={c.mandate_id} className="mb-2">
                      <div className="text-[var(--color-ink)]">{c.short} · <span style={{ color: SC[c.status] }}>{c.status_label}</span>{c.tier ? ` · ${c.tier.label}` : ''}{c.due_date ? <span className="mono text-[10.5px] text-[var(--color-faint)]"> · due {c.due_date}</span> : null}</div>
                      <ul className="ml-4 list-disc text-[var(--color-mute)]">{c.checks.map((k, i) => <li key={i} style={{ color: k.result === false ? 'var(--color-faint)' : k.result == null ? 'var(--color-warn)' : undefined }}>{k.label}: {k.result == null ? 'not stated' : k.result ? 'met' : 'not met'}{k.tier ? ` (${k.tier})` : ''}</li>)}</ul>
                      <div className="mono text-[10.5px] text-[var(--color-faint)]">{c.direction === 'push' ? 'entity submits' : 'supervisor requests'} · {c.channel}</div>
                    </div>))}
                </div>
              </div></td></tr>)}
          </>))}</tbody>
        </table>
      </div>
    </Card>
  </>)
}
