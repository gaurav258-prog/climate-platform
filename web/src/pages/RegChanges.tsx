import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronRight, Plus, ExternalLink } from 'lucide-react'
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
          <input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="Change title (e.g. EBA ITS 2025 — COREP taxonomy 3.5)" className="flex-1 min-w-[240px] bg-transparent outline-none text-[14px]" />
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
                    <div className="text-[12px] text-[var(--color-ink)] leading-snug">{c.title}</div>
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
    </div>
  )
}
