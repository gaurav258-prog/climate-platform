import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Plus, ExternalLink, X } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Eyebrow, Card, Button } from '../components/ui'

// Regulatory-change register — the "change the bank" pipeline: a rule change tracked from spotted to shipped
// (identified → analysis → scheduled → in dev → testing → released).

interface Change { change_id: string; title: string; framework: string | null; summary: string | null; citation: string | null; stage: string; owner: string; impact: string | null; effective_date: string | null; is_platform: boolean }
interface Stage { key: string; changes: Change[] }
interface Board { stages: Stage[]; summary: { total: number; released: number } }

const LABEL: Record<string, string> = { identified: 'Identified', analysis: 'Analysis', scheduled: 'Scheduled', in_dev: 'In development', testing: 'Testing', released: 'Released' }
const ORDER = ['identified', 'analysis', 'scheduled', 'in_dev', 'testing', 'released']
const NEXT: Record<string, string> = { identified: 'analysis', analysis: 'scheduled', scheduled: 'in_dev', in_dev: 'testing', testing: 'released' }

export default function RegChanges() {
  const { profile } = useAuth()
  const qc = useQueryClient()
  const canAct = (profile?.permissions ?? []).includes('reports.publish')
  const q = useQuery({ queryKey: ['reg-changes'], queryFn: () => api.get<Board>('/v1/reg-changes/board') })
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ title: '', framework: '', effective_date: '' })
  const [sel, setSel] = useState<Change | null>(null)
  const d = q.data
  const refresh = () => qc.invalidateQueries({ queryKey: ['reg-changes'] })

  const add = async () => {
    if (!form.title.trim()) return
    try { await api.post('/v1/reg-changes', { title: form.title.trim(), framework: form.framework || null, effective_date: form.effective_date || null }); setForm({ title: '', framework: '', effective_date: '' }); setAdding(false); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not register the change.') }
  }
  const advance = async (c: Change) => {
    try { await api.post(`/v1/reg-changes/${c.change_id}/advance`, { stage: NEXT[c.stage] }); refresh() }
    catch (e) { alert(e instanceof ApiError ? e.message : 'Could not advance.') }
  }

  return (
    <div className="fadeup space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <Eyebrow>Change the bank</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2 mb-1">Regulatory changes</h1>
          <p className="text-[var(--color-mute)] text-sm max-w-2xl">Every new or amended rule tracked from spotted to shipped — monitored, analysed, scheduled, built, tested and released — so nothing catches the filing off guard.</p>
        </div>
        {canAct && <Button variant="ghost" onClick={() => setAdding(a => !a)}><Plus size={14} /> Register change</Button>}
      </div>

      {adding && (
        <Card className="p-3 flex flex-wrap items-center gap-2">
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Change title (e.g. SFDR RTS 2026 — revised PAI methodology)" className="flex-1 min-w-[240px] bg-transparent outline-none text-[14px]" />
          <input value={form.framework} onChange={e => setForm({ ...form, framework: e.target.value })} placeholder="Framework" className="w-28 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none" />
          <input type="date" value={form.effective_date} onChange={e => setForm({ ...form, effective_date: e.target.value })} className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12px] outline-none" />
          <Button variant="primary" onClick={add} disabled={!form.title.trim()}>Add</Button>
        </Card>
      )}

      {d && <div className="mono text-[11px] text-[var(--color-faint)]">{d.summary.total} change{d.summary.total === 1 ? '' : 's'} tracked · {d.summary.released} released</div>}

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

      {sel && (
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
