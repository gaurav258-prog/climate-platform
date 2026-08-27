import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Plus, ExternalLink, X, Radar, CheckCircle2, Wrench, Rocket, KanbanSquare, Map as MapIcon, Database, Plug } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { useAuth } from '../lib/auth'
import { Card, Button, PageHeader, HeroBanner } from '../components/ui'

// Regulatory-change register — the "change the bank" pipeline: a rule change tracked from spotted to shipped
// (identified → analysis → scheduled → in dev → testing → released).

interface Change { change_id: string; title: string; framework: string | null; summary: string | null; citation: string | null; stage: string; owner: string; impact: string | null; effective_date: string | null; is_platform: boolean }
interface Stage { key: string; changes: Change[] }
interface Board { stages: Stage[]; summary: { total: number; released: number } }
interface RoadItem { id: string; name: string; status: string; whats: string; prep: string | null; citation: string; target: string }
interface Roadmap { groups: { live: RoadItem[]; building: RoadItem[]; planned: RoadItem[] }; summary: { live: number; building: number; planned: number } }

const LABEL: Record<string, string> = { identified: 'Identified', analysis: 'Analysis', scheduled: 'Scheduled', in_dev: 'In development', testing: 'Testing', released: 'Released' }
const ORDER = ['identified', 'analysis', 'scheduled', 'in_dev', 'testing', 'released']
const NEXT: Record<string, string> = { identified: 'analysis', analysis: 'scheduled', scheduled: 'in_dev', in_dev: 'testing', testing: 'released' }

export default function RegChanges() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const [tab, setTab] = useState<'pipeline' | 'roadmap'>('pipeline')
  const q = useQuery({ queryKey: ['reg-changes'], queryFn: () => api.get<Board>('/v1/reg-changes/board') })
  const rq = useQuery({ queryKey: ['reg-roadmap'], enabled: tab === 'roadmap', queryFn: () => api.get<Roadmap>('/v1/reg-changes/roadmap') })
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ title: '', framework: '', effective_date: '' })
  const [sel, setSel] = useState<Change | null>(null)
  const d = q.data
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-changes'] })

  const add = async () => {
    if (!form.title.trim()) return
    try { await api.post('/v1/reg-changes', { title: form.title.trim(), framework: form.framework || null, effective_date: form.effective_date || null }); setForm({ title: '', framework: '', effective_date: '' }); setAdding(false); refresh() }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not register the change.') }
  }
  const advance = async (c: Change) => {
    try { await api.post(`/v1/reg-changes/${c.change_id}/advance`, { stage: NEXT[c.stage] }); refresh() }
    catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not advance.') }
  }

  return (
    <div className="fadeup space-y-5">
      <PageHeader eyebrow="Regulatory maintenance" title="Regulatory changes"
        lead="Every new or amended rule tracked from spotted to shipped — and the forward roadmap of what we cover, what we're building, and what you'll need to prepare."
        actions={tab === 'pipeline' && canAct && <Button variant="ghost" onClick={() => setAdding(a => !a)}><Plus size={14} /> Register change</Button>} />

      {/* two lenses: the live change pipeline, and the forward coverage roadmap */}
      <div className="flex gap-1 p-1 rounded-xl border border-[var(--color-line)] bg-[var(--color-bg-2)] w-fit">
        {([['pipeline', 'Change pipeline', KanbanSquare], ['roadmap', 'Coverage roadmap', MapIcon]] as const).map(([k, l, Icon]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-[12.5px] transition ${tab === k ? 'bg-[var(--color-panel)] text-[var(--color-ink)] shadow-[0_0_0_1px_var(--color-line)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
            <Icon size={14} /> {l}
          </button>
        ))}
      </div>

      {tab === 'roadmap' && <RoadmapView data={rq.data} loading={rq.isLoading} />}

      {tab === 'pipeline' && (<>
      {adding && (
        <Card className="p-3 flex flex-wrap items-center gap-2">
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Change title (e.g. SFDR RTS 2026 — revised PAI methodology)" className="flex-1 min-w-[240px] bg-transparent outline-none text-[14px]" />
          <input value={form.framework} onChange={e => setForm({ ...form, framework: e.target.value })} placeholder="Framework" className="w-28 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none" />
          <input type="date" value={form.effective_date} onChange={e => setForm({ ...form, effective_date: e.target.value })} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none" />
          <Button variant="primary" onClick={add} disabled={!form.title.trim()}>Add</Button>
        </Card>
      )}

      {d && (
        <HeroBanner
          eyebrow="Change the bank"
          title={d.summary.total === 0 ? 'Nothing in the change pipeline yet.' : d.summary.total - d.summary.released > 0 ? `${d.summary.total - d.summary.released} change${d.summary.total - d.summary.released === 1 ? '' : 's'} still moving through.` : 'Every tracked change has shipped.'}
          lead="Every new or amended rule tracked from spotted to shipped — monitored, analysed, scheduled, built, tested and released — so nothing catches a filing off guard."
          stat={[
            { label: 'Changes tracked', value: d.summary.total, icon: Radar, tone: 'var(--color-sky)' },
            { label: 'Released', value: d.summary.released, icon: CheckCircle2, tone: d.summary.released > 0 ? '#4FA46E' : 'var(--color-sky)' },
          ]} />
      )}

      <div className="overflow-x-auto pb-2">
        <div className="grid grid-cols-6 gap-3 min-w-[1080px]">
          {ORDER.map((s, si) => (
            <div key={s} className="rounded-xl bg-[var(--color-panel)] border border-[var(--color-line)] p-2">
              <div className="flex items-center gap-1.5 px-1.5 py-1.5">
                <span className="w-5 h-5 rounded-full flex items-center justify-center mono text-[10px]" style={{ background: si === ORDER.length - 1 ? '#34d39922' : 'var(--color-panel-2)', color: si === ORDER.length - 1 ? '#34d399' : 'var(--color-mute)' }}>{si + 1}</span>
                <span className="mono text-[10px] uppercase tracking-wide text-[var(--color-mute)]">{LABEL[s]}</span>
              </div>
              <div className="space-y-2">
                {(d?.stages.find(x => x.key === s)?.changes ?? []).map(c => (
                  <div key={c.change_id} className="rounded-lg bg-[var(--color-bg-2)] border border-[var(--color-line)] p-2.5">
                    <button onClick={() => setSel(c)} className="text-[12px] text-[var(--color-ink)] hover:text-[var(--color-sky)] transition leading-snug text-left">{c.title}</button>
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                      {c.framework && <span className="mono text-[9px] px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-sky)]">{c.framework}</span>}
                      <span className="mono text-[9px] text-[var(--color-faint)]">{c.is_platform ? 'platform' : 'your org'}</span>
                      {c.effective_date && <span className="mono text-[9px] text-[var(--color-faint)]">eff {c.effective_date.slice(0, 7)}</span>}
                      {c.citation && <span className="inline-flex items-center gap-0.5 mono text-[9px] text-[var(--color-faint)]"><ExternalLink size={9} />{c.citation}</span>}
                    </div>
                    {canAct && !c.is_platform && NEXT[c.stage] && (
                      <button onClick={() => advance(c)} className="mt-1.5 inline-flex items-center gap-0.5 mono text-[10px] text-[var(--color-sky)] hover:underline">{LABEL[NEXT[c.stage]]}<ChevronRight size={11} /></button>
                    )}
                  </div>
                ))}
                {(d?.stages.find(x => x.key === s)?.changes ?? []).length === 0 && <div className="text-[10.5px] text-[var(--color-faint)] px-1.5 py-2 text-center">—</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
      </>)}

      {tab === 'pipeline' && sel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={() => setSel(null)}>
          <div className="absolute inset-0 bg-black/50" />
          <Card className="relative w-full max-w-lg p-0 overflow-hidden" >
            <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--color-line)]" onClick={e => e.stopPropagation()}>
              <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Regulatory change · {LABEL[sel.stage]}</span>
              <button onClick={() => setSel(null)} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={17} /></button>
            </div>
            <div className="p-5 space-y-3" onClick={e => e.stopPropagation()}>
              <h3 className="display text-lg font-semibold">{sel.title}</h3>
              <div className="flex flex-wrap gap-2 text-[11px]">
                {sel.framework && <span className="mono px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-sky)]">{sel.framework}</span>}
                <span className="mono px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)]">{sel.is_platform ? 'platform-managed' : 'your org'}</span>
                {sel.effective_date && <span className="mono px-1.5 py-0.5 rounded bg-[var(--color-panel-2)] text-[var(--color-faint)]">effective {sel.effective_date}</span>}
              </div>
              {sel.summary && <div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Summary</div><p className="text-[13px] text-[var(--color-mute)]">{sel.summary}</p></div>}
              {sel.impact && <div><div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)] mb-1">Impact</div><p className="text-[13px] text-[var(--color-mute)]">{sel.impact}</p></div>}
              {sel.citation && <div className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-sky)]"><ExternalLink size={13} /> {sel.citation}</div>}
              {canAct && !sel.is_platform && NEXT[sel.stage] && (
                <Button variant="primary" onClick={() => { advance(sel); setSel({ ...sel, stage: NEXT[sel.stage] }) }}>Advance → {LABEL[NEXT[sel.stage]]}</Button>
              )}
              {sel.is_platform && <p className="text-[11.5px] text-[var(--color-faint)]">Platform-managed change — read-only for your organisation.</p>}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

const STATUS_META: Record<string, { label: string; tone: string; icon: typeof Rocket; hint: string }> = {
  live: { label: 'Live now', tone: '#4FA46E', icon: CheckCircle2, hint: 'we file this today' },
  building: { label: 'Building', tone: '#E8B24C', icon: Wrench, hint: 'in development' },
  planned: { label: 'Planned', tone: 'var(--color-sky)', icon: Rocket, hint: 'on the roadmap' },
}

function RoadmapView({ data, loading }: { data?: Roadmap; loading: boolean }) {
  if (loading) return <Card className="p-10 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  if (!data) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the roadmap.</div>
  const s = data.summary
  return (
    <>
      <HeroBanner eyebrow="Coverage roadmap"
        title={`${s.live} live · ${s.building} building · ${s.planned} planned`}
        lead="What we cover for your sector today, what we're building next, and what's on the roadmap — with any new data or integration you'll need to prepare. Targets are our delivery intent, not a regulatory promise."
        stat={[
          { label: 'Live now', value: s.live, icon: CheckCircle2, tone: '#4FA46E' },
          { label: 'Building', value: s.building, icon: Wrench, tone: '#E8B24C' },
          { label: 'Planned', value: s.planned, icon: Rocket, tone: 'var(--color-sky)' },
        ]} />
      {(['live', 'building', 'planned'] as const).map(status => {
        const items = data.groups[status]
        if (!items.length) return null
        const m = STATUS_META[status]
        return (
          <div key={status}>
            <div className="flex items-center gap-2 mb-2.5 mt-1">
              <m.icon size={15} style={{ color: m.tone }} />
              <span className="text-[13px] font-semibold" style={{ color: m.tone }}>{m.label}</span>
              <span className="mono text-[10px] text-[var(--color-faint)]">· {m.hint}</span>
            </div>
            <div className="grid md:grid-cols-2 gap-3 mb-4">
              {items.map(it => (
                <Card key={it.id} className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-[14px] font-medium text-[var(--color-ink)] leading-snug">{it.name}</div>
                    <span className="mono text-[9px] uppercase tracking-wide px-2 py-0.5 rounded-full shrink-0" style={{ color: m.tone, background: `color-mix(in oklab, ${m.tone} 15%, transparent)` }}>{it.target}</span>
                  </div>
                  <p className="text-[12.5px] text-[var(--color-mute)] mt-1.5 leading-snug">{it.whats}</p>
                  {it.prep && (
                    <div className="mt-2.5 flex items-start gap-2 rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3 py-2">
                      {/prep|integration|credential|traces/i.test(it.prep) && /integration|credential|traces|api/i.test(it.prep)
                        ? <Plug size={13} className="text-[var(--color-warn)] shrink-0 mt-0.5" />
                        : <Database size={13} className="text-[var(--color-sky)] shrink-0 mt-0.5" />}
                      <div><div className="mono text-[9px] uppercase tracking-wide text-[var(--color-faint)]">To prepare</div><div className="text-[12px] text-[var(--color-mute)] leading-snug">{it.prep}</div></div>
                    </div>
                  )}
                  <div className="mono text-[10px] text-[var(--color-faint)] mt-2 inline-flex items-center gap-1"><ExternalLink size={10} /> {it.citation}</div>
                </Card>
              ))}
            </div>
          </div>
        )
      })}
    </>
  )
}
