import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { X, ShieldCheck, RotateCcw, Save, Clock, MapPin } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card, Button } from './ui'
import { hazardLabel, sevColor } from '../lib/hazards'

// The per-asset drill for the four financial books — the depth the agri /detail/* pages already had, plus
// the actions an analyst needs: override the model's valuation discount (bank / asset-mgr / REIT), or set a
// policy's parametric trigger band (insurer). Every action is audited server-side; the audit trail is shown.

export interface DrawerCfg {
  prefix: string; itemKey: string; nameKey: string; valueKey: string; typeKey: string
  valuationKey?: string; auditKey: string; overrideMode: 'valuation' | 'trigger'
}

// the detail endpoints return the raw per-hazard×horizon rows: hazard_type / risk_bucket (not hazard/bucket)
interface Haz { hazard_type: string; score: number; risk_bucket: string; time_horizon?: string; model_version?: string }
interface Val {
  discounted_value_eur?: number; is_overridden?: boolean
  recommended_discount_pct?: number; effective_discount_pct?: number
  original_ltv_pct?: number; climate_adjusted_ltv_pct?: number
  vulnerability_factor?: number
  vulnerability?: { applied: boolean; drivers: { attr: string; value: unknown; factor: number }[] }
}
interface Trigger { hazard_type?: string; attachment_score?: number; exhaustion_score?: number; status?: string }
interface AuditRow { actor_user_id?: string; action: string; detail?: Record<string, unknown>; created_at: string }
type Detail = Record<string, unknown>

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const BUCKET: Record<string, string> = { VH: 'severe', H: 'high', M: 'elevated', L: 'low' }
const errText = (e: unknown, fb: string) => {
  if (e instanceof ApiError) {
    const b = e.body as { message?: string; error?: { message?: string } } | string | undefined
    if (typeof b === 'string') return b
    return b?.message ?? b?.error?.message ?? fb
  }
  return fb
}

export default function AssetDrawer({ cfg, id, onClose, onChanged }: { cfg: DrawerCfg; id: string; onClose: () => void; onChanged: () => void }) {
  const q = useQuery({ queryKey: ['fin-detail', cfg.prefix, id], queryFn: () => api.get<Detail>(`/v1/${cfg.prefix}/${cfg.itemKey}/${id}`) })
  const d = q.data
  const item = (d?.[cfg.itemKey] as Record<string, unknown> | undefined)
  // detail returns one row per hazard × horizon — collapse to the worst score per hazard for a clean view
  const risksRaw = (d?.risks as Haz[] | undefined) ?? []
  const risks = (() => {
    const worst = new Map<string, Haz>()
    for (const r of risksRaw) { const c = worst.get(r.hazard_type); if (!c || r.score > c.score) worst.set(r.hazard_type, r) }
    return [...worst.values()].sort((a, b) => b.score - a.score)
  })()
  const val = (cfg.valuationKey ? d?.[cfg.valuationKey] : undefined) as Val | undefined
  const audit = (d?.[cfg.auditKey] as AuditRow[] | undefined) ?? []
  const reload = () => { q.refetch(); onChanged() }

  const name = item ? String(item[cfg.nameKey] ?? '—') : '—'
  const value = item ? (item[cfg.valueKey] as number | null) : null
  const atype = item?.[cfg.typeKey] ? String(item[cfg.typeKey]) : null
  const region = item?.region ? String(item.region) : null
  const country = item?.country ? String(item.country) : null
  const lat = item?.lat as number | undefined, lon = item?.lon as number | undefined

  return (
    <div className="fixed inset-0 z-50 flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/50" />
      <div className="relative w-full max-w-xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-[var(--color-line)] bg-[var(--color-bg-2)]">
          <div className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">{cfg.itemKey}</div>
          <button onClick={onClose} className="text-[var(--color-faint)] hover:text-[var(--color-ink)]"><X size={18} /></button>
        </div>

        {q.isLoading || !d ? <div className="p-8 text-[13px] text-[var(--color-faint)]">loading…</div>
          : d.error ? <div className="p-8 text-[13px] text-[var(--color-bad)]">{String(d.error)}</div>
          : (
          <div className="p-6 space-y-6">
            <div>
              <h2 className="display text-xl font-semibold">{name}</h2>
              <div className="mono text-[11px] text-[var(--color-faint)] mt-1 flex flex-wrap items-center gap-x-2">
                <span className="text-[var(--color-mute)]">{eur(value)}</span>
                {atype && <span>· {atype.replace(/_/g, ' ')}</span>}
                {(region || country) && <span>· {[region, country].filter(Boolean).join(', ')}</span>}
                {lat != null && lon != null && <span className="inline-flex items-center gap-1"><MapPin size={10} /> {Math.abs(lat).toFixed(2)}°{lat >= 0 ? 'N' : 'S'}, {Math.abs(lon).toFixed(2)}°{lon >= 0 ? 'E' : 'W'}</span>}
              </div>
            </div>

            {/* hazards */}
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Physical risk · every hazard scored</div>
              <Card className="p-4">
                {risks.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">Not scored yet.</div>
                  : <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1.5">
                      {risks.map(h => (
                        <div key={h.hazard_type} className="flex items-center justify-between gap-3 text-[12.5px] border-b border-[var(--color-line)] py-1">
                          <span className="text-[var(--color-mute)] capitalize truncate">{h.hazard_type.replace(/_/g, ' ')}</span>
                          <span className="mono tabular-nums shrink-0" style={{ color: sevColor(h.score) }}>{Math.round(h.score)}/100 · {BUCKET[h.risk_bucket] ?? h.risk_bucket}</span>
                        </div>
                      ))}
                    </div>}
              </Card>
            </div>

            {/* action: valuation override, or insurer trigger */}
            {cfg.overrideMode === 'valuation'
              ? <ValuationPanel cfg={cfg} id={id} val={val} onDone={reload} />
              : <TriggerPanel id={id} item={item} risks={risks} onDone={reload} />}

            {/* audit trail */}
            <div>
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-2">Audit trail · last actions</div>
              {audit.length === 0 ? <div className="text-[12px] text-[var(--color-faint)]">No overrides or changes on record.</div>
                : <div className="space-y-2">
                    {audit.map((a, i) => (
                      <div key={i} className="flex gap-2 text-[12px]">
                        <Clock size={12} className="mt-0.5 text-[var(--color-faint)] shrink-0" />
                        <div className="min-w-0">
                          <span className="text-[var(--color-ink)]">{a.action.replace(/[._]/g, ' ')}</span>
                          <span className="mono text-[10px] text-[var(--color-faint)] ml-2">{new Date(a.created_at).toLocaleString('en-GB')}</span>
                          {a.detail && (a.detail.from_pct != null || a.detail.to_pct != null) &&
                            <div className="mono text-[10.5px] text-[var(--color-mute)]">{String(a.detail.from_pct ?? '—')}% → {a.detail.to_pct == null ? 'recommended' : `${a.detail.to_pct}%`}{typeof a.detail.reason === 'string' ? ` · “${a.detail.reason}”` : ''}</div>}
                        </div>
                      </div>
                    ))}
                  </div>}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function ValuationPanel({ cfg, id, val, onDone }: { cfg: DrawerCfg; id: string; val?: Val; onDone: () => void }) {
  const { profile } = useAuth()
  const canPrice = (profile?.permissions ?? []).includes('pricing.approve')
  const cur = val?.effective_discount_pct ?? val?.recommended_discount_pct ?? 0
  const [pct, setPct] = useState<string>(String(cur))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const path = `/v1/${cfg.prefix}/${cfg.itemKey}/${id}/valuation-override`

  const apply = async () => {
    setBusy(true); setErr(null)
    try { await api.post(path, { discount_pct: Number(pct), reason: reason || undefined }); setReason(''); onDone() }
    catch (e) { setErr(errText(e, 'Could not apply the override.')) } finally { setBusy(false) }
  }
  const clear = async () => {
    setBusy(true); setErr(null)
    try { await api.del(path); onDone() }
    catch (e) { setErr(errText(e, 'Could not clear the override.')) } finally { setBusy(false) }
  }

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Climate-adjusted valuation</div>
        {val?.is_overridden && <span className="mono text-[10px] px-1.5 py-0.5 rounded" style={{ color: '#e8b24c', background: '#e8b24c22' }}>analyst override on file</span>}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[12.5px]">
        <Row k="Risk-adjusted value" v={eur(val?.discounted_value_eur)} />
        <Row k="Recommended discount" v={val?.recommended_discount_pct != null ? `${val.recommended_discount_pct}%` : '—'} />
        <Row k="Effective discount" v={val?.effective_discount_pct != null ? `${val.effective_discount_pct}%` : '—'} />
        {val?.original_ltv_pct != null && <Row k="LTV" v={`${val.original_ltv_pct}% → ${val.climate_adjusted_ltv_pct}%`} />}
      </div>
      {val?.vulnerability?.applied && val.vulnerability_factor != null && (
        <div className="mono text-[11px] text-[var(--color-faint)] leading-relaxed">
          vulnerability <b className="text-[var(--color-mute)]">×{val.vulnerability_factor}</b> — {val.vulnerability.drivers.map(dr => `${dr.attr.replace(/_/g, ' ')} ${String(dr.value)}`).join(' · ')}
        </div>
      )}

      {canPrice ? (
        <div className="pt-3 border-t border-[var(--color-line)] space-y-2">
          <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]">Override the discount</div>
          {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] px-2 py-1.5">
              <input type="number" min={0} max={100} step={0.5} value={pct} onChange={e => setPct(e.target.value)}
                className="w-16 bg-transparent outline-none text-[13px] text-right tabular-nums" />
              <span className="text-[var(--color-faint)] text-[12px]">%</span>
            </div>
            <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Reason (audited)"
              className="flex-1 bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
          </div>
          <div className="flex gap-2">
            <Button variant="primary" onClick={apply} disabled={busy || pct === ''}><ShieldCheck size={14} /> Apply override</Button>
            {val?.is_overridden && <Button variant="ghost" onClick={clear} disabled={busy}><RotateCcw size={14} /> Revert to recommended</Button>}
          </div>
        </div>
      ) : <div className="pt-2 border-t border-[var(--color-line)] text-[11.5px] text-[var(--color-faint)]">Overriding the valuation needs the <span className="mono">pricing.approve</span> permission.</div>}
    </Card>
  )
}

function TriggerPanel({ id, item, risks, onDone }: { id: string; item?: Record<string, unknown>; risks: Haz[]; onDone: () => void }) {
  const { profile } = useAuth()
  const canPrice = (profile?.permissions ?? []).includes('pricing.approve')
  const existing = (item?.trigger as Trigger | undefined)
  const hazardOpts = risks.map(r => r.hazard_type)
  const [hazard, setHazard] = useState<string>(existing?.hazard_type ?? hazardOpts[0] ?? '')
  const [att, setAtt] = useState<string>(existing?.attachment_score != null ? String(existing.attachment_score) : '50')
  const [exh, setExh] = useState<string>(existing?.exhaustion_score != null ? String(existing.exhaustion_score) : '80')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [ok, setOk] = useState(false)

  const save = async () => {
    setBusy(true); setErr(null); setOk(false)
    if (Number(exh) <= Number(att)) { setErr('Exhaustion must be greater than attachment.'); setBusy(false); return }
    try {
      await api.post(`/v1/insurance/policies/${id}/trigger-config`, { hazard_type: hazard, attachment_score: Number(att), exhaustion_score: Number(exh) })
      setOk(true); onDone()
    } catch (e) { setErr(errText(e, 'Could not save the trigger.')) } finally { setBusy(false) }
  }

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Parametric trigger</div>
        {existing?.hazard_type && <span className="mono text-[10px] text-[var(--color-mute)]">{hazardLabel(existing.hazard_type)} · {existing.attachment_score}–{existing.exhaustion_score}</span>}
      </div>
      {item?.pricing != null && typeof item.pricing === 'object' && (
        <div className="mono text-[11px] text-[var(--color-faint)]">pricing on file — expected loss & premium computed from the golden source.</div>
      )}
      {canPrice ? (
        <div className="space-y-2">
          {err && <div className="text-[12px] text-[var(--color-bad)]">{err}</div>}
          {ok && <div className="text-[12px] text-[var(--color-good)]">Trigger band saved.</div>}
          <div className="grid grid-cols-3 gap-2">
            <label className="text-[11px] text-[var(--color-faint)]">Hazard
              <select value={hazard} onChange={e => setHazard(e.target.value)} className="mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12.5px] outline-none focus:border-[var(--color-sky)]">
                {hazardOpts.length === 0 && <option value="">—</option>}
                {hazardOpts.map(h => <option key={h} value={h}>{hazardLabel(h)}</option>)}
              </select>
            </label>
            <label className="text-[11px] text-[var(--color-faint)]">Attachment
              <input type="number" min={0} max={100} value={att} onChange={e => setAtt(e.target.value)} className="mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12.5px] tabular-nums outline-none focus:border-[var(--color-sky)]" />
            </label>
            <label className="text-[11px] text-[var(--color-faint)]">Exhaustion
              <input type="number" min={0} max={100} value={exh} onChange={e => setExh(e.target.value)} className="mt-1 w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2 py-1.5 text-[12.5px] tabular-nums outline-none focus:border-[var(--color-sky)]" />
            </label>
          </div>
          <div className="mono text-[10px] text-[var(--color-faint)]">Payout begins when the hazard score crosses attachment, and is full at exhaustion.</div>
          <Button variant="primary" onClick={save} disabled={busy || !hazard}><Save size={14} /> Save trigger band</Button>
        </div>
      ) : <div className="text-[11.5px] text-[var(--color-faint)]">Configuring a parametric trigger needs the <span className="mono">pricing.approve</span> permission.</div>}
    </Card>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between border-b border-[var(--color-line)] pb-1"><span className="text-[var(--color-mute)]">{k}</span><span className="text-[var(--color-ink)] mono tabular-nums">{v}</span></div>
}
