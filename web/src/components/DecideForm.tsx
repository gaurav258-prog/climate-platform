import { useState } from 'react'
import { Check, Clock } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Button } from './ui'
import { statusLabel } from '../lib/hazards'
import { actionLabel } from '../lib/actionLabels'

// The one decision form of the decision spine, whatever signal raised the exposure (a forward crossing, a tested loss):
// the sector's verb-pack, a rationale, and the organisation's 4-eyes rule. The server's /v1/decisions/actions decides
// WHICH verbs a sector offers; this map supplies the label · tone · in-place explanation for each.
export type Meta = { label: string; tone: string; desc: string }
export const ACTION_META: Record<string, Meta> = {
  reprice: { label: 'Reprice', tone: 'var(--scn-disorderly)', desc: 'Re-price to reflect the higher climate risk — margin, spread or terms at the next renewal. Spins a board task.' },
  adjust_terms: { label: 'Adjust terms', tone: 'var(--scn-disorderly)', desc: 'Tighten covenants, LTV or collateral terms on the exposure. Spins a board task.' },
  limit_exit: { label: 'Limit / exit', tone: 'var(--color-bad)', desc: 'Cap or wind down the exposure. Spins a board task.' },
  provision: { label: 'Provision', tone: 'var(--scn-orderly)', desc: 'Review expected-loss provisioning for the exposure. Spins a board task.' },
  adjust_cover: { label: 'Adjust cover', tone: 'var(--scn-disorderly)', desc: 'Adjust deductible or limit on the policy. Spins a board task.' },
  exclude: { label: 'Exclude', tone: 'var(--color-bad)', desc: 'Add a peril exclusion at renewal. Spins a board task.' },
  non_renew: { label: 'Non-renew', tone: 'var(--color-bad)', desc: 'Decline renewal at expiry. Spins a board task.' },
  reinsure: { label: 'Reinsure', tone: 'var(--scn-orderly)', desc: 'Review reinsurance / retention on the risk. Spins a board task.' },
  reweight: { label: 'Reweight', tone: 'var(--scn-disorderly)', desc: 'Reweight the holding in the portfolio. Spins a board task.' },
  engage_issuer: { label: 'Engage issuer', tone: 'var(--scn-baseline)', desc: 'Engage the issuer on its adaptation / transition plan. Spins a board task.' },
  divest: { label: 'Divest', tone: 'var(--color-bad)', desc: 'Divest the holding. Spins a board task.' },
  hedge: { label: 'Hedge', tone: 'var(--scn-orderly)', desc: 'Hedge the exposure. Spins a board task.' },
  adaptation_capex: { label: 'Adaptation capex', tone: 'var(--scn-orderly)', desc: 'Plan resilience capex for the property. Spins a board task.' },
  reposition: { label: 'Reposition', tone: 'var(--scn-disorderly)', desc: 'Reposition the asset. Spins a board task.' },
  dispose: { label: 'Dispose', tone: 'var(--color-bad)', desc: 'Dispose of the asset. Spins a board task.' },
  insure: { label: 'Insure', tone: 'var(--scn-orderly)', desc: 'Insure the asset against the peril. Spins a board task.' },
  reallocate_origin: { label: 'Reallocate origin', tone: 'var(--scn-disorderly)', desc: 'Shift a bounded share of spend to a lower-risk origin you already source from. Spins a board task.' },
  diversify_supplier: { label: 'Diversify supplier', tone: 'var(--scn-orderly)', desc: 'Add an alternative supplier / origin to cut concentration. Spins a board task.' },
  buffer_prebuy: { label: 'Buffer / pre-buy', tone: 'var(--scn-orderly)', desc: 'Build inventory buffer or pre-buy ahead of the disruption window. Spins a board task.' },
  adaptation_invest: { label: 'Adaptation investment', tone: 'var(--scn-orderly)', desc: 'Invest with the supplier in adaptation (irrigation, storage). Spins a board task.' },
  renegotiate: { label: 'Renegotiate', tone: 'var(--scn-disorderly)', desc: 'Renegotiate contract terms to share the climate risk. Spins a board task.' },
  engage: { label: 'Engage', tone: 'var(--scn-baseline)', desc: 'Contact the counterparty to understand and reduce the risk before repricing or exiting. Spins a board task.' },
  disclose: { label: 'Disclose', tone: 'var(--scn-orderly)', desc: 'Flag this to include in the climate-risk disclosure for the period. Spins a board task.' },
  monitor: { label: 'Monitor', tone: 'var(--color-mute)', desc: 'No action yet — a watchlist with a re-review date; escalates if it worsens (when enabled in the playbook).' },
  accept: { label: 'Accept', tone: 'var(--color-faint)', desc: 'Formally accept the risk with no change, rationale on record. No board task.' },
}
export const actionMeta = (k?: string | null): Meta | undefined => k ? ACTION_META[k] : undefined

export interface Decision { action: string; rationale: string | null; status: string; by: string | null; at: string }

// Whether a decision on this exposure goes to a second approver: the organisation's rule as the server states it
// (forward_decisions.decision_policy) — off unless set; on with a threshold, from that value up.
export type Policy = { requires_approval: boolean; threshold_eur: number | null }
export const secondApprover = (p: Policy | undefined, value: number | null) =>
  !!p?.requires_approval && (p.threshold_eur == null || (value ?? 0) >= p.threshold_eur)

export function DecideForm({ body, decision, policy, value, actions, onDone, onCancel }: {
  body: Record<string, unknown>; decision: Decision | null; policy?: Policy; value: number | null
  actions: (Meta & { key: string })[]; onDone: () => void; onCancel: () => void
}) {
  const [action, setAction] = useState(decision?.action ?? '')
  const [rationale, setRationale] = useState(decision?.rationale ?? '')
  const [busy, setBusy] = useState(false)
  const dm = actionMeta(decision?.action)
  const save = async () => {
    if (!action) return
    setBusy(true)
    try {
      await api.post('/v1/decisions', { ...body, action, rationale: rationale.trim() || undefined, value_eur: value })
      onDone()
    } catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not propose the decision.') }
    finally { setBusy(false) }
  }
  return (
    <div className="mt-3 rounded-lg border border-[var(--color-line-2)] bg-[var(--color-bg-2)] p-3 space-y-2.5">
      <div className="flex flex-wrap gap-1.5">
        {actions.map(a => (
          <button key={a.key} onClick={() => setAction(a.key)} title={a.desc} className={`px-2.5 py-1.5 rounded-lg text-[12px] border transition ${action === a.key ? 'border-transparent text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}
            style={action === a.key ? { background: `color-mix(in oklab, ${a.tone} 16%, transparent)` } : undefined}>
            <span className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: a.tone }} />{a.label}</span>
          </button>
        ))}
      </div>
      {/* what the chosen action means — clarifies the decision in place */}
      <div className="text-[11.5px] text-[var(--color-mute)] min-h-[16px]">{action ? actionMeta(action)?.desc : 'Pick an action — hover any option to see what it does.'}</div>
      <textarea value={rationale} onChange={e => setRationale(e.target.value)} rows={2} placeholder="Rationale (recorded in the audit log)…"
        className="w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)] resize-none" />
      <div className="flex items-center gap-2">
        <Button variant="primary" onClick={save} disabled={busy || !action}><Check size={13} /> Propose decision</Button>
        <button onClick={onCancel} className="text-[12px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">Cancel</button>
        <span className="text-[11px] text-[var(--color-faint)] ml-auto">{decision ? `Last: ${dm?.label ?? actionLabel(decision.action)} · ${statusLabel(decision.status)}` : secondApprover(policy, value) ? 'Goes to a second approver' : 'Applies at once'}</span>
      </div>
    </div>
  )
}

// The standing decision's chip on a row: approved (the action), or proposed and awaiting the second approver.
export function DecisionChip({ decision, canAct, onClick }: { decision: Decision; canAct: boolean; onClick: () => void }) {
  const dm = actionMeta(decision.action)
  const proposed = decision.status === 'proposed'
  return (
    <button onClick={() => canAct && onClick()} title={proposed ? 'Proposed — awaiting a second approval' : `Approved · ${decision.by?.split('@')[0]}`}
      className="mono text-[9px] uppercase tracking-wide px-2 py-1 rounded inline-flex items-center gap-1"
      style={proposed ? { color: 'var(--color-warn)', background: 'color-mix(in oklab, var(--color-warn) 15%, transparent)' } : { color: dm?.tone, background: `color-mix(in oklab, ${dm?.tone} 15%, transparent)` }}>
      {proposed ? <><Clock size={10} /> {dm?.label ?? actionLabel(decision.action)} · awaiting approval</> : <><Check size={11} /> {dm?.label ?? actionLabel(decision.action)}</>}
    </button>
  )
}
