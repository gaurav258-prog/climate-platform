import { useEffect, useState } from 'react'
import { X, MapPin, ChevronDown, Landmark, Loader2 } from 'lucide-react'
import RiskAtom, { BUCKET } from './RiskAtom'
import { fetchAsset, fetchModels, overrideValuation, clearValuationOverride } from '../api/client'

const euro = n => n == null ? '—' : '€' + Math.round(n).toLocaleString()
const euroM = n => n == null ? '—' : '€' + (n / 1e6).toFixed(1) + 'm'

// The drill-through. Opened from the table OR the map — same component, so an
// asset reads identically wherever you click it. Every hazard score carries the
// model version + scored date that produced it (defensible disclosure).
export default function AssetDrawer({ assetId, onClose, scenario = 'baseline', horizon = 'current', auth }) {
  const [data, setData] = useState(null)
  const [models, setModels] = useState([])
  const [openHz, setOpenHz] = useState(null)

  function reload() { fetchAsset(assetId).then(setData).catch(() => setData({ error: true })) }
  useEffect(() => {
    if (!assetId) return
    setData(null); setOpenHz(null)
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assetId])
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => {}) }, [])

  if (!assetId) return null
  const a = data?.asset
  const risks = (data?.risks || []).filter(r => r.scenario === scenario && r.time_horizon === horizon)
  const headline = risks.slice().sort((x, y) => y.score - x.score)[0]
  const canOverride = new Set(auth?.permissions || []).has('pricing.approve')

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-50 flex h-full w-[420px] flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 flex items-start justify-between border-b border-gray-200 bg-white/90 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            {a ? (
              <>
                <h2 className="truncate text-[17px] font-semibold text-[#1d1d1f]">{a.asset_name}</h2>
                <p className="mt-0.5 text-[12px] text-gray-500">{a.sector} · {a.country} · {a.region}</p>
              </>
            ) : <h2 className="text-[15px] text-gray-400">loading…</h2>}
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><X size={18} /></button>
        </header>

        {a && (
          <div className="space-y-5 px-5 py-5">
            {/* headline risk */}
            <section className="rounded-2xl bg-[#f5f5f7] p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[11px] uppercase tracking-wide text-gray-400">Physical risk</div>
                  <div className="text-[13px] text-gray-600">{headline ? `driven by ${headline.hazard_type}` : 'no scored hazard'}</div>
                </div>
                {headline
                  ? <RiskAtom score={headline.score} bucket={headline.risk_bucket} size="lg" showLabel />
                  : <RiskAtom score={null} bucket={null} size="lg" />}
              </div>
              {/* per-hazard rows — the same RiskAtom as the table & map */}
              <div className="mt-4 space-y-2">
                {risks.length ? risks.map(r => {
                  const m = models.find(x => x.model_version === r.model_version)
                  const open = openHz === r.hazard_type
                  return (
                    <div key={r.hazard_type} className="overflow-hidden rounded-lg bg-white">
                      <button onClick={() => setOpenHz(open ? null : r.hazard_type)}
                        className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50">
                        <div>
                          <div className="flex items-center gap-1 text-[13px] font-medium capitalize text-[#1d1d1f]">
                            {r.hazard_type.replace('_', ' ')}
                            <ChevronDown size={13} className={`text-gray-400 transition ${open ? 'rotate-180' : ''}`} />
                          </div>
                          <div className="font-mono text-[10px] text-gray-400">{r.model_version} · {String(r.scored_at).slice(0, 10)}</div>
                        </div>
                        <RiskAtom score={r.score} bucket={r.risk_bucket} size="md" />
                      </button>
                      {open && (
                        <div className="border-t border-gray-100 px-3 py-2.5 text-[11px]">
                          {m ? (
                            <>
                              <div className="text-gray-500">Out-of-sample skill:{' '}
                                <span className="font-semibold text-[#1d1d1f]">{m.auc != null ? `LOEO AUC ${m.auc.toFixed(3)}` : 'physics-based'}</span>
                                {m.avg_precision != null ? ` · AP ${m.avg_precision.toFixed(3)}` : ''}
                                {m.training_cell_count ? ` · ${m.training_cell_count.toLocaleString()} cells` : ''}
                              </div>
                              {m.validation_note && <p className="mt-1.5 leading-snug text-gray-500">{m.validation_note}</p>}
                            </>
                          ) : <p className="text-gray-400">model metadata unavailable</p>}
                        </div>
                      )}
                    </div>
                  )
                }) : <p className="text-[12px] text-gray-400">This asset's cell has not been scored — surfaced honestly, never a silent zero.</p>}
              </div>
            </section>

            {/* lending decision: system-recommended, human-overridable, audited */}
            {data.valuation && (
              <ValuationSection asset={a} valuation={data.valuation} audit={data.valuation_audit}
                canOverride={canOverride} onChanged={reload} />
            )}

            {/* exposure & disclosure facts */}
            <Facts title="Exposure" rows={[
              ['Loan / asset value', euro(a.value_eur)],
              ['Annual revenue', euro(a.revenue_eur)],
              ['Value at this risk', headline && (headline.risk_bucket === 'H' || headline.risk_bucket === 'VH') ? euroM(a.value_eur) : '—'],
            ]} />
            <TaxonomySection asset={a} />
            <Facts title="Disclosure (TCFD / EU Taxonomy)" rows={[
              ['NACE · GICS', `${a.nace_code || '—'} · ${a.gics_code || '—'}`],
              ['Construction year', a.construction_year || '—'],
              ['GHG scope 1 / 2 / 3 (tCO₂e)', `${fmt(a.ghg_scope1)} / ${fmt(a.ghg_scope2)} / ${fmt(a.ghg_scope3)}`],
            ]} />

            {/* provenance footer */}
            <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-[11px] text-gray-500">
              <MapPin size={13} className="text-gray-400" />
              <span className="font-mono">{a.h3_cell}</span>
              <span className="text-gray-300">·</span>
              <span>projected from canonical_scores</span>
            </div>
          </div>
        )}
      </aside>
    </>
  )
}

const fmt = n => n == null ? '—' : Math.round(n).toLocaleString()

function ValuationSection({ asset, valuation, audit, canOverride, onChanged }) {
  const [editing, setEditing] = useState(false)
  const [pct, setPct] = useState(valuation.effective_discount_pct)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  async function save() {
    setBusy(true)
    try { await overrideValuation(asset.asset_id, Number(pct), reason || null); setEditing(false); onChanged() }
    finally { setBusy(false) }
  }
  async function clear() {
    setBusy(true)
    try { await clearValuationOverride(asset.asset_id); onChanged() }
    finally { setBusy(false) }
  }

  return (
    <section className="rounded-2xl border border-gray-200 p-4">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] uppercase tracking-wide text-gray-400">
        <Landmark size={13} /> Lending decision
      </div>
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[13px] text-gray-500">Recommended valuation discount</div>
          <div className="text-2xl font-semibold tracking-tight text-[#1d1d1f]">{valuation.recommended_discount_pct}%</div>
        </div>
        <div className="text-right">
          <div className="text-[13px] text-gray-500">Discounted value</div>
          <div className="text-lg font-semibold text-[#1d1d1f]">{euroM(valuation.discounted_value_eur)}</div>
        </div>
      </div>

      {valuation.original_ltv_pct != null && (
        <div className="mt-3 flex items-center justify-between rounded-xl bg-gray-50 px-3 py-2">
          <div>
            <div className="text-[11px] text-gray-500">Loan-to-value</div>
            <div className="text-[13px] font-medium text-[#1d1d1f]">{euro(valuation.outstanding_loan_balance_eur)} outstanding</div>
          </div>
          <div className="text-right">
            <span className="text-[13px] text-gray-500">{valuation.original_ltv_pct}%</span>
            <span className="mx-1.5 text-gray-300">→</span>
            <span className={`text-[13px] font-semibold ${valuation.climate_adjusted_ltv_pct >= 100 ? 'text-red-600' : 'text-[#1d1d1f]'}`}>
              {valuation.climate_adjusted_ltv_pct}% climate-adjusted
            </span>
          </div>
        </div>
      )}

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
            placeholder="e.g. credit committee adjustment"
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

const TAXONOMY_BADGE = {
  eligible: 'bg-amber-50 text-amber-700',
  not_eligible: 'bg-gray-100 text-gray-500',
  not_assessed: 'bg-gray-100 text-gray-400',
}
const TAXONOMY_LABEL = { eligible: 'Eligible', not_eligible: 'Not eligible', not_assessed: 'Not assessed' }

/** EU Taxonomy status shown WITH its reasoning -- never a bare enum. "Eligible" cites the exact
 * Annex I section; "not eligible"/"not assessed" say why, and never silently claim "aligned"
 * without the technical-screening + safeguards data that would require (see
 * ml/regulatory/eu_taxonomy_classifier.py's docstring). */
function TaxonomySection({ asset: a }) {
  const status = a.taxonomy_status || 'not_assessed'
  const reasoning = a.dnsh_assessment || {}
  return (
    <section>
      <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">EU Taxonomy alignment</h3>
      <div className="rounded-2xl border border-gray-200 p-3">
        <div className="flex items-center justify-between">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TAXONOMY_BADGE[status] || TAXONOMY_BADGE.not_assessed}`}>
            {TAXONOMY_LABEL[status] || status}
          </span>
        </div>
        {reasoning.activity_ref && (
          <p className="mt-2 text-[11px] leading-snug text-gray-500">{reasoning.activity_ref}</p>
        )}
        {status !== 'not_assessed' && (
          <p className="mt-2 text-[11px] leading-snug text-gray-400">
            Never "aligned" without verifying substantial contribution and minimum safeguards —
            data this platform doesn't yet collect (see Trust &amp; assurance › Methodology).
          </p>
        )}
        {reasoning.dnsh_climate_adaptation_flag && (
          <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[11px] leading-snug text-amber-800">
            {reasoning.dnsh_climate_adaptation_flag}
          </p>
        )}
      </div>
    </section>
  )
}

function Facts({ title, rows }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">{title}</h3>
      <div className="divide-y divide-gray-100 rounded-2xl border border-gray-200">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between px-3 py-2 text-[13px]">
            <span className="text-gray-500">{k}</span>
            <span className="font-medium text-[#1d1d1f]">{v}</span>
          </div>
        ))}
      </div>
    </section>
  )
}
