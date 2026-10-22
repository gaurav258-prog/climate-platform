import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Gauge, ShieldCheck, Workflow } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { Card, SectionHead } from '../../components/ui'
import { HEADING, InfoButton, MessageLine, type Message } from '../../components/Details'
import { StatusChip } from '../../components/StatusChip'
import { AppetiteHistory } from '../../components/GrcFollowups'
import AppetiteBar from '../kri/AppetiteBar'
import { RAG, STATUS_WORD, value as kriValue, type Kpi } from '../kri/model'
import { Share, Toggle, refused, sel } from './parts'
import { savedWords } from './words'

// Governance settings: which changes need a second person, what runs on its own once a decision is approved, and the
// appetite band on each key risk indicator. Names come from the server (names.admin.policy, .admin.field).

interface Policy { action_key: string; label: string; requires_approval: boolean; material_fields: string[]; material: { key: string; label: string }[]
  org_override: boolean; supports_threshold?: boolean; threshold_eur?: number | null }

const MATRIX = {
  title: 'Approval matrix', sections: [
    { heading: HEADING.shows, body: 'The changes that wait for a second person’s approval before they apply. Every change is recorded in the audit trail, whether or not it needs approval.' },
    { heading: HEADING.read, body: 'The approver is anyone in your team with the Approver role, and never the person who made the change. Where fields are listed, only a change to one of them needs approval; others apply directly.' },
    { heading: HEADING.limits, body: 'Switching approval off withdraws the requests still waiting: nothing is applied, and the person who asked can make the change again directly.' },
  ],
}

export function Matrix() {
  const q = useQuery({ queryKey: ['approval-policy'], queryFn: () => api.get<Policy[]>('/v1/admin/approval-policy') })
  const [busy, setBusy] = useState<string | null>(null)
  const rows = q.data ?? []
  const set = async (p: Policy, patch: { requires_approval?: boolean; threshold_eur?: number | null }) => {
    setBusy(p.action_key)
    try {
      const out = await api.patch<{ withdrawn?: Message | null }>('/v1/admin/approval-policy', {
        action_key: p.action_key, material_fields: p.material_fields,
        requires_approval: patch.requires_approval ?? p.requires_approval,
        threshold_eur: patch.threshold_eur !== undefined ? patch.threshold_eur : p.threshold_eur,
      })
      if (out?.withdrawn) toast.info(out.withdrawn.detail?.what ?? out.withdrawn.label)
      await q.refetch()
    } catch (e) { refused(e, 'The rule could not be saved.') } finally { setBusy(null) }
  }
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex flex-wrap items-center gap-4">
        <SectionHead icon={ShieldCheck} className="gap-1.5">Changes that need a second person <InfoButton compact details={MATRIX} /></SectionHead>
        <div className="ml-auto w-56"><Share n={rows.filter(r => r.requires_approval).length} of={rows.length} label="Need approval" tone="var(--color-good)" /></div>
      </div>
      {rows.map(p => (
        <div key={p.action_key} className="px-4 py-3 border-b border-[var(--color-line)] last:border-0">
          <div className="flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <div className="text-[13.5px] text-[var(--color-ink)]">{p.label}</div>
              <div className="flex flex-wrap items-center gap-1.5 mt-1">
                <StatusChip tone={p.org_override ? 'good' : 'neutral'} label={p.org_override ? 'Your rule' : 'Platform default'} />
                {p.material.map(f => <span key={f.key} className="text-[11.5px] px-2 py-0.5 rounded-full bg-[var(--color-panel-2)] text-[var(--color-mute)]">{f.label}</span>)}
              </div>
            </div>
            <span className="text-[12px] w-28 text-right" style={{ color: p.requires_approval ? 'var(--color-good)' : 'var(--color-faint)' }}>{p.requires_approval ? 'Second person' : 'Applies directly'}</span>
            <Toggle on={p.requires_approval} disabled={busy === p.action_key} label={`${p.label}: needs a second person`}
              onChange={() => set(p, { requires_approval: !p.requires_approval })} />
          </div>
          {p.supports_threshold && p.requires_approval && (
            <div className="flex flex-wrap items-center gap-2 mt-2.5 text-[12px] text-[var(--color-mute)]">
              Only when the exposure is above
              <input type="number" min={0} defaultValue={p.threshold_eur ?? 0} aria-label="Exposure above which approval is needed"
                onBlur={e => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== (p.threshold_eur ?? 0)) set(p, { threshold_eur: v }) }}
                className={clsx(sel, 'w-32 tabular-nums')} />
              EUR · {(p.threshold_eur ?? 0) === 0 ? 'every decision needs approval' : 'smaller decisions apply directly'}
            </div>
          )}
        </div>
      ))}
    </Card>
  )
}

// ── what runs on its own once a decision is approved ─────────────────────────────────────────────────────────
interface Play { action: string; label: string; spin_task?: boolean; assignee_user_id?: string | null; due_days?: number | null
  notify?: boolean; flag_disclosure?: boolean; watchlist?: boolean; webhook?: boolean; org_override?: boolean }
interface Member { user_id: string; email: string; name: string }
const STEPS: { key: keyof Play; label: string; hint: string }[] = [
  { key: 'spin_task', label: 'Task', hint: 'A tracked task on the board' },
  { key: 'notify', label: 'Tell the owner', hint: 'An e-mail to the task’s owner' },
  { key: 'flag_disclosure', label: 'Flag for filing', hint: 'The exposure is included in the next climate disclosure' },
  { key: 'watchlist', label: 'Watchlist', hint: 'On the watchlist, with a re-check scheduled' },
  { key: 'webhook', label: 'Notify your systems', hint: 'An event sent to the addresses registered under Integrations' },
]
const PLAYBOOK = {
  title: 'When a decision is approved', sections: [
    { heading: HEADING.shows, body: 'The steps that run on their own once a decision on a flagged exposure — a forward crossing or a tested loss — is approved.' },
    { heading: HEADING.read, body: 'All steps are off until you switch them on. Choose the task’s owner and the days allowed for the task or the re-check. Anything sent outside your workspace still needs a person.' },
  ],
}

export function DecisionPlaybook() {
  const q = useQuery({ queryKey: ['decision-playbook'], queryFn: () => api.get<{ members: Member[]; playbook: Play[] }>('/v1/admin/decision-playbook') })
  const [busy, setBusy] = useState<string | null>(null)
  const set = async (p: Play, patch: Partial<Play>) => {
    setBusy(p.action)
    try { await api.patch('/v1/admin/decision-playbook', { action: p.action, ...patch }); await q.refetch() }
    catch (e) { refused(e, 'The step could not be saved.') } finally { setBusy(null) }
  }
  const members = q.data?.members ?? []
  return (
    <Card className="p-0 overflow-x-auto">
      <div className="p-4 border-b border-[var(--color-line)]"><SectionHead icon={Workflow} className="gap-1.5">When a decision is approved <InfoButton compact details={PLAYBOOK} /></SectionHead></div>
      <table className="data-table w-full text-[12.5px]">
        <thead><tr><th>Decision</th>{STEPS.map(s => <th key={s.key} className="text-center whitespace-nowrap" title={s.hint}>{s.label}</th>)}<th>Owner and days</th></tr></thead>
        <tbody>
          {(q.data?.playbook ?? []).map(p => (
            <tr key={p.action}>
              <td className="whitespace-nowrap"><span className="text-[var(--color-ink)] font-medium">{p.label}</span>{p.org_override && <span className="ml-2 text-[11px] text-[var(--color-faint)]">Your rule</span>}</td>
              {STEPS.map(s => {
                const on = !!p[s.key]
                return (
                  <td key={s.key} className="text-center">
                    <button disabled={busy === p.action} onClick={() => set(p, { [s.key]: !on } as Partial<Play>)} aria-pressed={on} aria-label={`${p.label}: ${s.hint}`}
                      className={clsx('inline-grid place-items-center w-7 h-7 rounded-full border transition disabled:opacity-50', on ? 'border-transparent' : 'border-[var(--color-line-2)] hover:border-[var(--color-sky)]')}
                      style={on ? { background: 'color-mix(in oklab, var(--color-good) 22%, transparent)' } : undefined}>
                      <span className="w-2 h-2 rounded-full" style={{ background: on ? 'var(--color-good)' : 'var(--color-line-2)' }} />
                    </button>
                  </td>
                )
              })}
              <td>
                {(p.spin_task || p.watchlist) ? (
                  <div className="flex items-center gap-2">
                    {p.spin_task && (
                      <select value={p.assignee_user_id ?? ''} onChange={e => set(p, { assignee_user_id: e.target.value || null })} disabled={busy === p.action} aria-label="Owner" className={sel}>
                        <option value="">No owner</option>
                        {members.map(m => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}
                      </select>
                    )}
                    <input type="number" min={0} defaultValue={p.due_days ?? 0} aria-label={p.spin_task ? 'Days to do the task' : 'Days to the re-check'}
                      onBlur={e => { const v = Math.max(0, Number(e.target.value) || 0); if (v !== (p.due_days ?? 0)) set(p, { due_days: v }) }} className={clsx(sel, 'w-16 tabular-nums')} />
                    <span className="text-[11.5px] text-[var(--color-faint)]">days</span>
                  </div>
                ) : <span className="text-[var(--color-faint)]">—</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

// ── the appetite band on each key risk indicator ─────────────────────────────────────────────────────────────
interface AppetiteKpi { key: string; label: string; fmt: Kpi['fmt']; value: number | null; amber: number | null; red: number | null; direction: Kpi['direction']; status: Kpi['status'] }
interface Appetite { supported: boolean; about?: Message; framework?: string; label?: string; frameworks?: { framework: string; label: string }[]; kpis?: AppetiteKpi[] }
const APPETITE = {
  title: 'Risk appetite', sections: [
    { heading: HEADING.shows, body: 'The band that grades each key risk indicator: crossing the warning level turns it amber, crossing the breach level turns it red.' },
    { heading: HEADING.read, body: 'An indicator with no band is shown but not graded. Direction says which way is worse. Type a level and leave the field to save it; a change may wait for a second person, as set in the approval matrix.' },
  ],
}

export function RiskAppetite() {
  const qc = useQueryClient()
  const [fw, setFw] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['kri-appetite', fw], queryFn: () => api.get<Appetite>(`/v1/admin/kri-appetite${fw ? `?framework=${fw}` : ''}`) })
  const [busy, setBusy] = useState<string | null>(null)
  const d = q.data
  const set = async (k: AppetiteKpi, patch: Record<string, unknown>) => {
    setBusy(k.key)
    try {
      const r = await api.patch<{ status?: string }>('/v1/admin/kri-appetite', { kri_key: k.key, framework: d?.framework, ...patch })
      toast.success(savedWords(r.status, 'Band saved — the indicator is graded against it.'))
      await q.refetch(); await qc.invalidateQueries({ queryKey: ['kri-appetite-history'] })
    } catch (e) { refused(e, 'The band could not be saved.') } finally { setBusy(null) }
  }
  if (d && !d.supported) return <Card className="p-6">{d.about && <MessageLine m={d.about} className="text-[13px] text-[var(--color-mute)]" />}</Card>
  const kpis = d?.kpis ?? []
  const graded = kpis.filter(k => k.status)
  return (
    <Card className="p-0 overflow-hidden">
      <div className="p-4 border-b border-[var(--color-line)] flex flex-wrap items-center gap-3">
        <SectionHead icon={Gauge} className="gap-1.5">Risk appetite <InfoButton compact details={APPETITE} /></SectionHead>
        <div className="ml-auto flex flex-wrap gap-1.5">
          {(['red', 'amber', 'ok'] as const).map(s => {
            const n = graded.filter(k => k.status === s).length
            return n ? <StatusChip key={s} tone={s === 'ok' ? 'good' : s === 'amber' ? 'warn' : 'bad'} label={`${n} ${STATUS_WORD[s].toLowerCase()}`} /> : null
          })}
          <StatusChip tone="neutral" label={`${kpis.length - graded.length} not graded`} />
        </div>
      </div>
      {(d?.frameworks ?? []).length > 1 && (
        <div className="px-4 py-2.5 border-b border-[var(--color-line)] flex flex-wrap gap-1.5">
          {d!.frameworks!.map(f => (
            <button key={f.framework} onClick={() => setFw(f.framework)} aria-pressed={d?.framework === f.framework}
              className={clsx('px-2.5 py-1 rounded-lg text-[12px] border transition', d?.framework === f.framework ? 'bg-[var(--color-sky)] text-[var(--color-on-accent)] border-transparent' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>{f.label}</button>
          ))}
        </div>
      )}
      {!d ? <div className="px-4 py-6 text-[13px] text-[var(--color-faint)]">Loading…</div> : kpis.map(k => {
        const kpi = k as unknown as Kpi
        return (
          <div key={k.key} className="px-4 py-3 border-b border-[var(--color-line)] last:border-0 grid gap-3 md:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)_auto] items-center">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                {k.status && <span className="w-2 h-2 rounded-full shrink-0" style={{ background: RAG[k.status] }} />}
                <span className="text-[13px] text-[var(--color-ink)]">{k.label}</span>
                <span className="ml-auto text-[13px] tabular-nums" style={{ color: k.status ? RAG[k.status] : 'var(--color-mute)' }}>{k.value == null ? '—' : kriValue(kpi)}</span>
              </div>
              <div className="mt-2.5"><AppetiteBar k={kpi} /></div>
            </div>
            <div className="flex items-center gap-2">
              <Level label="Warning" value={k.amber} disabled={busy === k.key} onCommit={v => set(k, { amber: v })} />
              <Level label="Breach" value={k.red} disabled={busy === k.key} onCommit={v => set(k, { red: v })} />
            </div>
            <select value={k.direction ?? 'higher_worse'} disabled={busy === k.key} onChange={e => set(k, { direction: e.target.value })} aria-label={`${k.label}: which way is worse`} className={sel}>
              <option value="higher_worse">Higher is worse</option>
              <option value="lower_worse">Lower is worse</option>
            </select>
          </div>
        )
      })}
      <AppetiteHistory framework={d?.framework} />
    </Card>
  )
}

function Level({ label, value, disabled, onCommit }: { label: string; value: number | null; disabled: boolean; onCommit: (v: number | null) => void }) {
  return (
    <label className="flex flex-col text-[11.5px] text-[var(--color-faint)]">{label}
      <input type="number" step="any" disabled={disabled} defaultValue={value ?? ''} placeholder="—"
        onBlur={e => { const raw = e.target.value.trim(); const v = raw === '' ? null : Number(raw); if (v !== value) onCommit(Number.isNaN(v as number) ? null : v) }}
        className={clsx(sel, 'w-24 mt-0.5 tabular-nums')} />
    </label>
  )
}
