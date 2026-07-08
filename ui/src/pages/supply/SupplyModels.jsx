import { useState, useEffect, useCallback } from 'react'
import { ShieldCheck, CheckCircle2, AlertTriangle, FlaskConical, Pencil, X } from 'lucide-react'
import { fetchSupplyValidation, fetchSupplyModels, overrideCommodityCogs, clearCommodityCogsOverride } from '../../api/client'

const HAZ_LABEL = { heat_acute: 'Heat', drought: 'Drought', frost: 'Frost' }
const eur = n => n == null ? '—' : '€' + (n / 1e6).toFixed(2) + 'm'

export default function SupplyModels({ auth }) {
  const [val, setVal] = useState(null)
  const [mod, setMod] = useState(null)
  const [editing, setEditing] = useState(null)   // commodity_id being edited
  const [form, setForm] = useState({ value: '', reason: '' })
  const [busy, setBusy] = useState(false)
  const canOverride = new Set(auth?.permissions || []).has('pricing.approve')

  const load = useCallback(() => {
    fetchSupplyValidation().then(setVal).catch(() => setVal(null))
    fetchSupplyModels().then(setMod).catch(() => setMod(null))
  }, [])
  useEffect(() => { load() }, [load])

  function startEdit(c) {
    setEditing(c.commodity_id)
    setForm({ value: c.override ? c.override.override_p50_eur : '', reason: '' })
  }
  async function save(c) {
    setBusy(true)
    try {
      await overrideCommodityCogs(c.commodity_id, Number(form.value), form.reason || null)
      setEditing(null); load()
    } catch (e) { alert(e.message || 'Could not save override.') }
    finally { setBusy(false) }
  }
  async function clearOverride(c) {
    setBusy(true)
    try { await clearCommodityCogsOverride(c.commodity_id); load() }
    finally { setBusy(false) }
  }

  return (
    <div className="h-full overflow-y-auto bg-[#f5f5f7]">
      <div className="mx-auto max-w-4xl px-8 py-8">
        <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
          <ShieldCheck size={13} /> Models & validation
        </div>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">Why the numbers hold up</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
          Every commodity's € is a projection of the golden source through an impact function.
          Here's each hazard model, which commodities are event-backtested, and the backtests themselves —
          including where the data says something other than the obvious.
        </p>

        {/* the backtests — the credibility centerpiece */}
        <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold text-[#1d1d1f]">
            <FlaskConical size={15} className="text-[#0071e3]" /> Event backtests
            <span className="font-normal text-gray-400">— reproduce real events, honestly</span>
          </h2>
          {!val ? <p className="mt-3 text-gray-400">loading…</p> : (
            <div className="mt-3 space-y-3">
              {val.events.map(e => (
                <div key={e.event} className="rounded-xl border border-gray-100 bg-[#fafafa] p-4">
                  <div className="flex items-center justify-between">
                    <div className="text-[14px] font-semibold text-[#1d1d1f]">{e.event}
                      <span className="ml-2 rounded-full bg-[#0071e3]/10 px-2 py-0.5 text-[10px] font-medium text-[#0071e3] capitalize">{HAZ_LABEL[e.hazard] || e.hazard}</span>
                    </div>
                    <div className="text-right text-[11px] text-gray-500">
                      supply <b className="text-[#1d1d1f]">{e.observed_prod_shock_pct}%</b> ·
                      model <b className="text-[#c2410c]">+{e.model_price_move_pct}%</b>
                      {e.observed_price_move_pct != null && <> vs obs <b className="text-[#1d1d1f]">+{e.observed_price_move_pct}%</b></>}
                    </div>
                  </div>
                  <p className="mt-2 text-[12px] leading-relaxed text-gray-600">{e.skill_note}</p>
                  <p className="mt-1 text-[10px] text-gray-400">{e.source}</p>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* hazard models */}
        <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
          <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Hazard models <span className="font-normal text-gray-400">— climatology, transparent</span></h2>
          {!mod ? <p className="mt-3 text-gray-400">loading…</p> : (
            <div className="mt-3 divide-y divide-gray-100">
              {mod.hazard_models.map(h => (
                <div key={h.hazard_type} className="py-2.5">
                  <div className="flex items-center gap-2 text-[13px] font-medium text-[#1d1d1f]">
                    <CheckCircle2 size={14} className="text-emerald-500" /> {HAZ_LABEL[h.hazard_type] || h.hazard_type}
                    <span className="text-[11px] font-normal text-gray-400">{h.model_version}</span>
                  </div>
                  <div className="mt-0.5 pl-6 text-[11px] text-gray-500">{h.algorithm}</div>
                  {h.validation_note && <div className="mt-1 pl-6 text-[11px] italic text-gray-400">{h.validation_note}</div>}
                </div>
              ))}
              {/* frost — built but blocked */}
              <div className="py-2.5">
                <div className="flex items-center gap-2 text-[13px] font-medium text-gray-500">
                  <AlertTriangle size={14} className="text-amber-500" /> Frost
                  <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">pending data</span>
                </div>
                <div className="mt-0.5 pl-6 text-[11px] text-gray-400">{mod.frost_note}</div>
              </div>
            </div>
          )}
        </section>

        {/* per-commodity calibration */}
        {mod && (
          <section className="mt-6 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="text-[13px] font-semibold text-[#1d1d1f]">Commodity calibration
              <span className="font-normal text-gray-400"> — validated vs indicative, never blended</span></h2>
            <div className="mt-3 divide-y divide-gray-100">
              {mod.commodities.map(c => (
                <div key={c.commodity_id} className="py-2.5">
                  <div className="flex items-center justify-between text-[13px]">
                    <span className="flex items-center gap-2 text-[#1d1d1f]">
                      {c.commodity}
                      {c.calibration === 'backtested'
                        ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">backtested</span>
                        : <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-500">indicative</span>}
                      {c.override && <span className="rounded-full bg-[#0071e3]/10 px-2 py-0.5 text-[10px] font-medium text-[#0071e3]">overridden</span>}
                    </span>
                    {canOverride && editing !== c.commodity_id && (
                      <button onClick={() => startEdit(c)} className="flex items-center gap-1 text-[11px] font-medium text-[#0071e3] hover:underline">
                        <Pencil size={11} /> {c.override ? 'Edit override' : 'Override'}
                      </button>
                    )}
                  </div>
                  {c.override && editing !== c.commodity_id && (
                    <p className="mt-1 text-[11px] text-gray-500">
                      Model says {eur(c.override.model_p50_eur)} · overridden to <b className="text-[#1d1d1f]">{eur(c.override.override_p50_eur)}</b>
                      {c.override.reason && <> — "{c.override.reason}"</>}
                    </p>
                  )}
                  {editing === c.commodity_id && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-[#fafafa] p-3">
                      <input type="number" step="0.01" placeholder="Override P50 (EUR)" value={form.value}
                        onChange={e => setForm(f => ({ ...f, value: e.target.value }))}
                        className="w-40 rounded-lg border border-gray-200 px-2.5 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
                      <input type="text" placeholder="Reason (required for audit)" value={form.reason}
                        onChange={e => setForm(f => ({ ...f, reason: e.target.value }))}
                        className="min-w-[220px] flex-1 rounded-lg border border-gray-200 px-2.5 py-1.5 text-[13px] outline-none focus:border-[#0071e3]" />
                      <button onClick={() => save(c)} disabled={busy || !form.value}
                        className="rounded-full bg-[#0071e3] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50">Save</button>
                      {c.override && (
                        <button onClick={() => clearOverride(c)} disabled={busy}
                          className="flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1.5 text-[12px] text-gray-600 hover:border-red-300 hover:text-red-600">
                          <X size={12} /> Clear
                        </button>
                      )}
                      <button onClick={() => setEditing(null)} className="text-[12px] text-gray-400 hover:underline">Cancel</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-4 text-[11px] leading-relaxed text-gray-400">
              Impact function {mod.impact_version}. "Backtested" = the commodity's chain reproduces a real
              event; "indicative" = v0 defaults, shown for exposure but not yet event-validated. A procurement
              analyst with on-the-ground supplier knowledge can override a commodity's modelled COGS-at-risk
              with a mandatory reason — audited, same as banking/insurance/real-estate/asset-management's
              valuation overrides.
            </p>
          </section>
        )}
      </div>
    </div>
  )
}
