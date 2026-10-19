import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ExternalLink } from 'lucide-react'
import { api, apiMessage } from '../../lib/api'
import { toast } from '../../lib/toast'
import { useAuth } from '../../lib/auth'
import { Button, Card, StatGrid } from '../../components/ui'
import { StatusChip } from '../../components/StatusChip'
import { CloseButton } from '../../components/Dialog'
import { Drawer } from '../../components/Drawer'
import { InfoButton, messageDetails, type Message } from '../../components/Details'
import { Failed, Loading, day } from './common'

// The mandate registry (UI standard, 2026-10-16): one card per mandate with its sectors, its kind and how it applies
// across the population as a bar; everything the act says — the article and its excerpt, the criteria, the deliverable,
// the versions and the change watch — in the mandate's side drawer, where the legal references belong.
interface Cond { attribute: string; label: string; adapted?: Message }
interface Version { version: string; effective_from: string; summary: string; celex: string | null; acknowledged: { at: string; by: string | null } | null }
export interface Mandate { id: string; sectors: string[]; sector_labels: string[]; binding: boolean; title: string; short: string; enabled: boolean
  act: { name: string; url: string; form?: { name: string; url: string } }
  article: { ref: string; excerpt: string; version_date: string }
  criteria: { all_of: Cond[]; tiers?: { label: string; all_of: Cond[]; frequency?: string }[]; scope?: { label: string } }
  deliverable: { what: string; format: string; channel: string; direction: string; due: { label: string }; frequency: string; frequency_label: string | null }
  versions: Version[]; latest_acknowledged: boolean
  detection: { checked_at: string | null; changes: { change_id: string; title: string; status: string; url: string | null; detected_at: string }[] } }
interface RegResp { mandates: Mandate[]; n_unacknowledged: number; note: Message }
export interface Applicability { mandate_id: string; status: 'applies' | 'not_applicable' | 'cannot_determine' }

const pending = (m: Mandate) => m.detection.changes.filter(c => c.status !== 'reviewed').length
const COLORS = { applies: 'var(--color-good)', cannot_determine: 'var(--color-warn)', not_applicable: 'var(--color-line-2)' } as const

function Spread({ cells }: { cells: Applicability[] }) {
  if (!cells.length) return <div className="text-[11.5px] text-[var(--color-faint)]">No entity of these sectors in your population.</div>
  const n = (s: Applicability['status']) => cells.filter(c => c.status === s).length
  const parts = (['applies', 'cannot_determine', 'not_applicable'] as const).map(s => [s, n(s)] as const)
  return (
    <div>
      <div className="flex h-2 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={`Applies to ${n('applies')}, unknown for ${n('cannot_determine')}, does not apply to ${n('not_applicable')}`}>
        {parts.map(([s, k]) => k > 0 && <span key={s} style={{ width: `${(k / cells.length) * 100}%`, background: COLORS[s] }} />)}
      </div>
      <div className="flex gap-3 mt-1 text-[11px] text-[var(--color-faint)] tabular-nums">
        <span>{n('applies')} apply</span>{n('cannot_determine') > 0 && <span className="text-[var(--color-warn)]">{n('cannot_determine')} unknown</span>}
        {n('not_applicable') > 0 && <span>{n('not_applicable')} out of scope</span>}</div>
    </div>
  )
}

export function MandateRegistry({ applicability }: { applicability: Applicability[] }) {
  const q = useQuery({ queryKey: ['sup-mandates'], queryFn: () => api.get<RegResp>('/v1/supervisor/mandates') })
  const [sel, setSel] = useState<string | null>(null)
  const d = q.data
  if (q.isLoading) return <Loading what="the registry" />
  if (!d) return <Failed what="the registry" />
  const changes = d.mandates.reduce((a, m) => a + pending(m), 0)
  const m = d.mandates.find(x => x.id === sel)
  return (<>
    <StatGrid cols={3} items={[
      { label: 'Mandates in your profile', value: String(d.mandates.length), sub: `${d.mandates.filter(x => x.binding).length} binding · ${d.mandates.filter(x => !x.binding).length} guidance` },
      { label: 'Versions to acknowledge', value: String(d.n_unacknowledged), sub: 'new versions of an act', accent: d.n_unacknowledged ? 'var(--color-warn)' : undefined },
      { label: 'Changes detected', value: String(changes), sub: 'awaiting your review', accent: changes ? 'var(--color-warn)' : undefined },
    ]} />
    <div className="flex justify-end"><InfoButton label={d.note.label} details={messageDetails(d.note)} /></div>
    <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {d.mandates.map(x => (
        <Card key={x.id} lift onClick={() => setSel(x.id)} className="p-4 cursor-pointer space-y-3">
          <div>
            <div className="text-[14.5px] font-semibold text-[var(--color-ink)] leading-tight">{x.short}</div>
            <div className="text-[12px] text-[var(--color-mute)] mt-0.5">{x.title}</div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <StatusChip label={x.binding ? 'Binding' : 'Guidance'} tone={x.binding ? 'good' : 'neutral'} />
            <StatusChip label={x.deliverable.direction === 'push' ? 'Entity submits' : 'On request'} tone="neutral" />
            {!x.enabled && <StatusChip label="Switched off" tone="bad" />}
            {!x.latest_acknowledged && <StatusChip label="Version to acknowledge" tone="warn" />}
            {pending(x) > 0 && <StatusChip label="Change detected" tone="warn" />}
          </div>
          <div className="text-[11.5px] text-[var(--color-faint)]">{x.sector_labels.join(' · ')}</div>
          <Spread cells={applicability.filter(c => c.mandate_id === x.id)} />
        </Card>))}
    </div>
    {m && <MandateDrawer m={m} onClose={() => setSel(null)} />}
  </>)
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section><h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] m-0 mb-2">{title}</h4>{children}</section>
}
const Tile = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg)] px-3 py-2.5">
    <div className="text-[11.5px] text-[var(--color-faint)] mb-0.5">{label}</div><div className="text-[12.5px] text-[var(--color-ink)] leading-relaxed">{children}</div>
  </div>)
const Crit = ({ c }: { c: Cond }) => (
  <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-line-2)] px-3 py-1 text-[12px] text-[var(--color-ink)]">
    {c.label}{c.adapted && <><StatusChip label="Adapted" tone="warn" /><InfoButton compact details={messageDetails(c.adapted)} /></>}</span>)

function MandateDrawer({ m, onClose }: { m: Mandate; onClose: () => void }) {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const can = (profile?.permissions ?? []).includes('supervisor.mandates.manage')
  const [busy, setBusy] = useState(false)
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    try { await fn(); toast.success(ok); await qc.invalidateQueries({ queryKey: ['sup-mandates'] }); await qc.invalidateQueries({ queryKey: ['sup-pop-mandates'] }) }
    catch (e) { toast.error(apiMessage(e, 'Could not save.')) } finally { setBusy(false) }
  }
  return (
    <Drawer label={m.title} onClose={onClose} className="w-full max-w-2xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-6">
      <div className="flex items-start justify-between gap-3 mb-5">
        <div className="min-w-0">
          <div className="text-[12px] text-[var(--color-mute)]">{m.sector_labels.join(' · ')}</div>
          <h2 className="display text-[21px] leading-tight text-[var(--color-ink)] m-0">{m.title}</h2>
          <div className="text-[12.5px] text-[var(--color-mute)] mt-1">{m.act.name}</div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      <div className="space-y-6">
        <Section title={`The article · ${m.article.ref}`}>
          <blockquote className="border-l-2 border-[var(--color-sky)] pl-4 m-0 text-[13.5px] text-[var(--color-ink)] leading-relaxed">{m.article.excerpt}</blockquote>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
            <a href={m.act.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">The act on EUR-Lex <ExternalLink size={11} /></a>
            {m.act.form && <a href={m.act.form.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Official form <ExternalLink size={11} /></a>}
            <span className="text-[var(--color-faint)]">Curated digest of the text as of {day(m.article.version_date)}; the act is authoritative.</span>
          </div>
        </Section>
        <Section title="Who it applies to">
          <div className="flex flex-wrap gap-2">{m.criteria.all_of.map((c, i) => <Crit key={i} c={c} />)}
            {m.criteria.scope && <Crit c={{ attribute: 'scope', label: m.criteria.scope.label }} />}</div>
          {m.criteria.tiers && m.criteria.tiers.length > 0 && <div className="grid sm:grid-cols-2 gap-2 mt-2">{m.criteria.tiers.map((t, i) => (
            <Tile key={i} label={t.label}>{t.all_of.length ? t.all_of.map(c => c.label).join(' · ') : 'All others'}</Tile>))}</div>}
        </Section>
        <Section title="What must be delivered">
          <div className="grid sm:grid-cols-2 gap-2.5">
            <Tile label="Deliverable">{m.deliverable.what}</Tile>
            <Tile label="Format">{m.deliverable.format}</Tile>
            <Tile label={m.deliverable.direction === 'push' ? 'Channel · the entity submits' : 'Channel · you request it'}>{m.deliverable.channel}</Tile>
            <Tile label={`Deadline${m.deliverable.frequency_label ? ` · ${m.deliverable.frequency_label}` : ''}`}>{m.deliverable.due.label}</Tile>
          </div>
        </Section>
        <Section title="Versions of the act">
          <ol className="relative border-l border-[var(--color-line-2)] ml-2 space-y-3 m-0 p-0 list-none">
            {m.versions.map(v => (
              <li key={v.version} className="pl-4 relative">
                <span className="absolute -left-[5px] top-1.5 w-2.5 h-2.5 rounded-full" style={{ background: v.acknowledged ? 'var(--color-good)' : 'var(--color-warn)' }} />
                <div className="flex items-start gap-3 flex-wrap">
                  <div className="flex-1 min-w-[240px] text-[12.5px]">
                    <div className="text-[11.5px] text-[var(--color-faint)]">From {day(v.effective_from)}{v.acknowledged ? ` · acknowledged ${day(v.acknowledged.at)} by ${v.acknowledged.by ?? 'your authority'}` : ''}</div>
                    <div className="text-[var(--color-ink)]">{v.summary}</div>
                    {v.celex && <a href={`https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:${v.celex}`} target="_blank" rel="noreferrer" className="text-[11.5px] text-[var(--color-sky)] hover:underline">The act on EUR-Lex ↗</a>}
                  </div>
                  {!v.acknowledged && can && <Button variant="ghost" disabled={busy}
                    onClick={() => run(() => api.post(`/v1/supervisor/mandates/${m.id}/versions/${v.version}/acknowledge`, {}), 'Version acknowledged.')}>Acknowledge</Button>}
                </div>
              </li>))}
          </ol>
        </Section>
        <Section title="Change watch">
          <div className="text-[12.5px] text-[var(--color-mute)]">{m.detection.checked_at ? `Checked on EUR-Lex ${day(m.detection.checked_at)}.` : 'Not yet checked on EUR-Lex.'}</div>
          {m.detection.changes.map(c => <div key={c.change_id} className="flex items-center gap-2 flex-wrap mt-1.5 text-[12.5px]">
            <StatusChip label={c.status === 'reviewed' ? 'Reviewed' : 'To review'} tone={c.status === 'reviewed' ? 'good' : 'warn'} />
            <span className="text-[var(--color-ink)]">{c.title}</span><span className="text-[var(--color-faint)]">{day(c.detected_at)}</span>
            {c.url && <a href={c.url} target="_blank" rel="noreferrer" className="text-[var(--color-sky)] hover:underline">Source ↗</a>}</div>)}
        </Section>
        {can && <div className="border-t border-[var(--color-line)] pt-4">
          <Button variant="ghost" disabled={busy} onClick={() => run(() => api.put(`/v1/supervisor/mandates/${m.id}`, { enabled: !m.enabled }), m.enabled ? 'Switched off for your authority.' : 'Switched on for your authority.')}>
            {m.enabled ? 'Switch off for my authority' : 'Switch on for my authority'}</Button></div>}
      </div>
    </Drawer>
  )
}
