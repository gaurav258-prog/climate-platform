import { useState } from 'react'
import { Landmark, Loader2 } from 'lucide-react'
import { useToast } from './ToastProvider'

const euro = n => n == null ? '—' : '€' + Math.round(n).toLocaleString()
const euroM = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

/** Shared "system-recommended, human-overridable, audited" valuation block --
 * used by every vertical with a valuation/discount figure (banking, real
 * estate, asset management). One component instead of three near-identical
 * copies: entityId + the two API calls are the only per-vertical inputs;
 * `extra` is a slot for a vertical-specific block (banking's LTV, real
 * estate's NOI) rendered between the headline and the override control. */
export default function ValuationOverrideSection({
  entityId, valuation, audit, canOverride, onChanged,
  overrideFn, clearFn, icon: Icon = Landmark, label = 'Valuation', discountLabel = 'Recommended valuation discount',
  extra,
}) {
  const [editing, setEditing] = useState(false)
  const [pct, setPct] = useState(valuation.effective_discount_pct)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const toast = useToast()

  async function save() {
    setBusy(true)
    try {
      await overrideFn(entityId, Number(pct), reason || null); setEditing(false); onChanged()
      toast.success(`${label} override saved — audited.`)
    } catch (e) { toast.error(e.message || 'Could not save override.') }
    finally { setBusy(false) }
  }
  async function clear() {
    setBusy(true)
    try {
      await clearFn(entityId); onChanged()
      toast.success('Override cleared — reverted to the recommended discount.')
    } catch (e) { toast.error(e.message || 'Could not clear override.') }
    finally { setBusy(false) }
  }

  return (
    <section className="rounded-2xl border border-gray-200 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400">
        <Icon size={13} /> {label}
      </div>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] text-gray-500">{discountLabel}</div>
          <div className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">{valuation.recommended_discount_pct}%</div>
        </div>
        <div className="text-right">
          <div className="text-[13px] text-gray-500">Discounted value</div>
          <div className="text-lg font-semibold text-[#1d1d1f]">{euroM(valuation.discounted_value_eur)}</div>
        </div>
      </div>

      {extra}

      {valuation.is_overridden && !editing && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          Overridden to <b>{valuation.override.discount_pct}%</b> on {String(valuation.override.overridden_at).slice(0, 10)}
          {valuation.override.reason && <> — “{valuation.override.reason}”</>}
        </div>
      )}

      {canOverride && !editing && (
        <button onClick={() => { setPct(valuation.effective_discount_pct); setEditing(true) }}
          className="mt-3 text-[12px] font-medium text-[#0071e3] hover:underline">
          {valuation.is_overridden ? 'Change override' : 'Override discount'}
        </button>
      )}

      {editing && (
        <div className="mt-3 space-y-2 rounded-xl bg-gray-50 p-3">
          <label className="block text-[11px] text-gray-500">Override discount (%)</label>
          <input type="number" min={0} max={100} step={0.5} value={pct} onChange={e => setPct(e.target.value)}
            className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
          <label className="block text-[11px] text-gray-500">Reason (optional)</label>
          <input type="text" value={reason} onChange={e => setReason(e.target.value)}
            placeholder="e.g. committee adjustment"
            className="w-full rounded-lg border border-gray-200 px-2 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
          <div className="flex gap-2 pt-1">
            <button onClick={save} disabled={busy}
              className="rounded-full bg-[#0071e3] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50">
              {busy ? <Loader2 size={13} className="animate-spin" /> : 'Save override'}
            </button>
            {valuation.is_overridden && (
              <button onClick={clear} disabled={busy} className="rounded-full border border-gray-200 px-3 py-1.5 text-[12px] text-gray-600">
                Revert to recommended
              </button>
            )}
            <button onClick={() => setEditing(false)} className="rounded-full px-3 py-1.5 text-[12px] text-gray-400">Cancel</button>
          </div>
        </div>
      )}

      {audit?.length > 0 && (
        <details className="mt-3 text-[11px] text-gray-400">
          <summary className="cursor-pointer hover:text-gray-600">Override history ({audit.length})</summary>
          <div className="mt-1.5 space-y-1">
            {audit.map((e, i) => (
              <div key={i}>
                {String(e.created_at).slice(0, 19).replace('T', ' ')} · {e.action} ·
                {' '}{e.detail?.from_pct ?? '—'}% → {e.detail?.to_pct ?? '—'}%
              </div>
            ))}
          </div>
        </details>
      )}
    </section>
  )
}

export { euro, euroM }
