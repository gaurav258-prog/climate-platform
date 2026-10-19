import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Plus } from 'lucide-react'
import { frameworkLabel } from '../lib/labels'
import { api, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Button, PageHeader, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { DetailsBody, HEADING } from '../components/Details'
import SpecRegister from '../components/SpecRegister'
import { Dialog } from '../components/Dialog'

// The change pipeline, to the UI standard (2026-10-16) — the platform's own delivery board: every new or amended rule
// tracked from spotted to shipped (identified → analysis → scheduled → in development → testing → released), and the
// template specifications each version is built to, with their four-eyes sign-off. Platform operators only; customers
// see the Regulatory outlook (/reg-changes) instead.

interface Change { change_id: string; title: string; framework: string | null; summary: string | null; citation: string | null; stage: string; owner: string; impact: string | null; effective_date: string | null; is_platform: boolean }
interface Stage { key: string; changes: Change[] }
interface Board { stages: Stage[]; summary: { total: number; released: number } }

const ORDER = ['identified', 'analysis', 'scheduled', 'in_dev', 'testing', 'released'] as const
const STAGE: Record<string, { label: string; color: string }> = {
  identified: { label: 'Identified', color: 'var(--color-slate)' }, analysis: { label: 'Analysis', color: 'var(--color-sky)' },
  scheduled: { label: 'Scheduled', color: '#2dd4bf' }, in_dev: { label: 'In development', color: 'var(--color-warn)' },
  testing: { label: 'Testing', color: '#a78bfa' }, released: { label: 'Released', color: 'var(--color-good)' },
}
const NEXT: Record<string, string> = { identified: 'analysis', analysis: 'scheduled', scheduled: 'in_dev', in_dev: 'testing', testing: 'released' }
const month = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
const day = (s: string) => new Date(`${s.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })

const ABOUT = [
  { heading: HEADING.shows, body: 'Every new or amended rule the platform adapts to, on its way from spotted to shipped, and the template specifications each regulation’s versions are built to.' },
  { heading: HEADING.read, body: 'A change moves left to right through six stages. Changes the platform manages for everyone are read-only here; a change your organisation registered can be moved on by anyone allowed to publish reports.' },
  { heading: HEADING.limits, body: 'An internal board, not shown to customers. Customers see what a change means for them on the Regulatory outlook.' },
]

export default function RegPipeline() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['reg-changes'], queryFn: () => api.get<Board>('/v1/reg-changes/board') })
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ title: '', framework: '', effective_date: '' })
  const [sel, setSel] = useState<Change | null>(null)
  const d = q.data
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-changes'] })
  const all = d?.stages.flatMap(s => s.changes) ?? []

  const add = async () => {
    if (!form.title.trim()) return
    try { await api.post('/v1/reg-changes', { title: form.title.trim(), framework: form.framework || null, effective_date: form.effective_date || null }); setForm({ title: '', framework: '', effective_date: '' }); setAdding(false); refresh() }
    catch (e) { toast.error(apiMessage(e, 'Could not register the change.')) }
  }
  const advance = async (c: Change) => {
    try { await api.post(`/v1/reg-changes/${c.change_id}/advance`, { stage: NEXT[c.stage] }); refresh(); return true }
    catch (e) { toast.error(apiMessage(e, 'Could not move the change.')); return false }
  }
  const field = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]'

  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Platform · internal delivery" title="Regulatory change pipeline" lead="Every rule change, from spotted to shipped." about={ABOUT}
        actions={canAct && <Button variant="ghost" onClick={() => setAdding(a => !a)}><Plus size={14} /> Register change</Button>} />

      {adding && (
        <Card className="p-3 flex flex-wrap items-center gap-2">
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="What changes" aria-label="Title" className={`${field} flex-1 min-w-[14rem]`} />
          <input value={form.framework} onChange={e => setForm({ ...form, framework: e.target.value })} placeholder="Regulation" aria-label="Regulation" className={`${field} w-36`} />
          <input type="date" value={form.effective_date} onChange={e => setForm({ ...form, effective_date: e.target.value })} aria-label="Takes effect" className={field} />
          <Button variant="primary" onClick={add} disabled={!form.title.trim()}>Add</Button>
        </Card>
      )}

      {q.isLoading ? <Card className="p-8 text-center text-[13px] text-[var(--color-faint)]">Loading…</Card>
        : !d ? <Card className="p-8 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the pipeline.')}</Card>
        : <>
          <StatGrid cols={4} items={[
            { label: 'Changes tracked', value: d.summary.total },
            { label: 'Still moving', value: d.summary.total - d.summary.released, accent: d.summary.total - d.summary.released ? 'var(--color-sky)' : undefined },
            { label: 'Released', value: d.summary.released },
            { label: 'Your organisation’s', value: all.filter(c => !c.is_platform).length },
          ]} />

          {d.summary.total > 0 && (
            <Card className="p-4">
              <div className="flex w-full overflow-hidden rounded-full h-3 bg-[var(--color-panel-2)]" role="img"
                aria-label={ORDER.map(s => `${STAGE[s].label} ${d.stages.find(x => x.key === s)?.changes.length ?? 0}`).join(', ')}>
                {ORDER.map(s => { const n = d.stages.find(x => x.key === s)?.changes.length ?? 0
                  return n ? <div key={s} title={`${STAGE[s].label}: ${n}`} style={{ width: `${(n / d.summary.total) * 100}%`, background: STAGE[s].color }} /> : null })}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
                {ORDER.map(s => <span key={s} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: STAGE[s].color }} />{STAGE[s].label} {d.stages.find(x => x.key === s)?.changes.length ?? 0}</span>)}
              </div>
            </Card>
          )}

          <div className="overflow-x-auto pb-2">
            <div className="grid grid-cols-6 gap-3 min-w-[1080px]">
              {ORDER.map((s, si) => {
                const items = d.stages.find(x => x.key === s)?.changes ?? []
                return (
                  <div key={s} className="rounded-xl bg-[var(--color-panel)] border border-[var(--color-line)] p-2">
                    <div className="flex items-center gap-1.5 px-1.5 py-1.5">
                      <span className="w-5 h-5 rounded-full flex items-center justify-center text-[10.5px] font-medium" style={{ background: `color-mix(in oklab, ${STAGE[s].color} 18%, transparent)`, color: STAGE[s].color }}>{si + 1}</span>
                      <span className="text-[12px] font-medium text-[var(--color-ink)]">{STAGE[s].label}</span>
                      <span className="ml-auto text-[11px] text-[var(--color-faint)] tabular-nums">{items.length}</span>
                    </div>
                    <div className="space-y-2">
                      {items.map(c => (
                        <div key={c.change_id} className="rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] p-2.5">
                          <button type="button" onClick={() => setSel(c)} className="text-[12.5px] text-[var(--color-ink)] hover:text-[var(--color-sky)] transition leading-snug text-left">{c.title}</button>
                          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                            {c.framework && <span className="text-[10.5px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-sky)]">{frameworkLabel(c.framework)}</span>}
                            <span className="text-[10.5px] text-[var(--color-faint)]">{c.is_platform ? 'Platform' : 'Yours'}</span>
                            {c.effective_date && <span className="text-[10.5px] text-[var(--color-faint)]">{month(c.effective_date)}</span>}
                          </div>
                          {canAct && !c.is_platform && NEXT[c.stage] && (
                            <button type="button" onClick={() => advance(c)} className="mt-1.5 inline-flex items-center gap-0.5 text-[11px] text-[var(--color-sky)] hover:underline">{STAGE[NEXT[c.stage]].label}<ChevronRight size={11} /></button>
                          )}
                        </div>
                      ))}
                      {items.length === 0 && <div className="text-[11px] text-[var(--color-faint)] px-1.5 py-2 text-center">—</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </>}

      <SpecRegister canSign={(profile?.permissions ?? []).includes('platform.admin')} userId={profile?.user.id} />

      {sel && (
        <Dialog title={sel.title} onClose={() => setSel(null)}>
          <div className="space-y-4">
            <div className="flex flex-wrap gap-2">
              <StatusChip label={STAGE[sel.stage]?.label ?? 'Unknown stage'} tone={sel.stage === 'released' ? 'good' : 'neutral'} />
              {sel.framework && <StatusChip label={frameworkLabel(sel.framework)} tone="neutral" />}
              <StatusChip label={sel.is_platform ? 'Managed by the platform' : 'Your organisation’s'} tone="neutral" />
              {sel.effective_date && <StatusChip label={`Takes effect ${day(sel.effective_date)}`} tone="neutral" />}
            </div>
            <DetailsBody sections={[{ heading: 'Summary', body: sel.summary }, { heading: 'Impact', body: sel.impact }, { heading: 'Source', body: sel.citation }]
              .filter((x): x is { heading: string; body: string } => !!x.body)} />
            {canAct && !sel.is_platform && NEXT[sel.stage] && (
              <Button variant="primary" onClick={async () => { if (await advance(sel)) setSel({ ...sel, stage: NEXT[sel.stage] }) }}>Move to {STAGE[NEXT[sel.stage]].label.toLowerCase()}</Button>
            )}
            {sel.is_platform && <p className="text-[12px] text-[var(--color-faint)] m-0">Managed by the platform for every organisation: read-only here.</p>}
          </div>
        </Dialog>
      )}
    </div>
  )
}
