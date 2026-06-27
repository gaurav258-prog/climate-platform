import { useState, useEffect, useMemo } from 'react'
import { Layers, CheckCircle2, XCircle } from 'lucide-react'
import { fetchModels } from '../api/client'

const HAZARD_META = {
  flood: { label: 'Flood', color: '#3b82f6' },
  wildfire: { label: 'Wildfire', color: '#ef4444' },
  seismic: { label: 'Seismic', color: '#a855f7' },
  heat_acute: { label: 'Heat', color: '#f59e0b' },
  drought: { label: 'Drought', color: '#eab308' },
}

// AUC → honest skill label
const skill = auc =>
  auc == null ? { txt: 'physics-based', col: '#a855f7' }
    : auc >= 0.75 ? { txt: 'strong', col: '#10b981' }
    : auc >= 0.6 ? { txt: 'real, moderate', col: '#84cc16' }
    : auc >= 0.55 ? { txt: 'real, modest', col: '#f59e0b' }
    : { txt: 'no skill', col: '#ef4444' }

export default function ModelsPage() {
  const [models, setModels] = useState(null)
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => setModels([])) }, [])

  const byHazard = useMemo(() => {
    const m = {}
    for (const row of models || []) (m[row.hazard_type] ||= []).push(row)
    return m
  }, [models])

  return (
    <div className="h-full overflow-y-auto bg-slate-950 text-slate-100">
      <div className="mx-auto max-w-5xl px-8 py-8">
        <header className="mb-6">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-slate-500">
            <Layers size={14} /> Processing · Tier 2
          </div>
          <h1 className="mt-1 text-2xl font-semibold">Models</h1>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-slate-400">
            One data foundation → a model specialized per <em>physical mechanism</em> → one output contract.
            We split a hazard into sub-models only when leave-one-event-out proves it helps. Every number below
            is <strong className="text-slate-200">honest out-of-sample skill</strong> (forecasting a held-out
            event), never an in-sample fit.
          </p>
        </header>

        {!models && <p className="text-slate-500">loading…</p>}

        <div className="space-y-4">
          {Object.entries(byHazard).map(([hz, rows]) => {
            const active = rows.find(r => r.is_active) || rows[0]
            const retired = rows.filter(r => r !== active)
            return <ModelCard key={hz} hazard={hz} active={active} retired={retired} />
          })}
        </div>

        <footer className="mt-8 rounded-xl border border-slate-800 bg-slate-900/40 p-4 text-xs leading-relaxed text-slate-400">
          <strong className="text-slate-200">Why some hazards score lower.</strong> Flood physics is predictable
          from weather; fire occurrence depends on fuel + ignition (we added FIRMS burn labels and ERA5 fuel —
          0.44→0.57); seismic ground motion is physics (intensity attenuation + Omori-Utsu aftershocks), not a
          fitted classifier, so it has no AUC. The retired rows show models we rejected because in-sample skill
          (e.g. AUC 0.997) collapsed out-of-sample.
        </footer>
      </div>
    </div>
  )
}

function ModelCard({ hazard, active, retired }) {
  const meta = HAZARD_META[hazard] || { label: hazard, color: '#64748b' }
  const s = skill(active.auc)
  const aucPct = active.auc != null ? Math.max(0, Math.min(100, (active.auc - 0.5) / 0.5 * 100)) : 100
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="h-9 w-1.5 rounded-full" style={{ background: meta.color }} />
          <div>
            <h2 className="text-lg font-semibold">{meta.label}</h2>
            <div className="font-mono text-[11px] text-slate-500">{active.model_version} · {active.algorithm}</div>
          </div>
        </div>
        <span className="flex items-center gap-1 rounded-full bg-emerald-950 px-2.5 py-1 text-[11px] font-medium text-emerald-300">
          <CheckCircle2 size={12} /> active
        </span>
      </div>

      {/* metrics */}
      <div className="mt-4 grid grid-cols-[1fr_auto] items-center gap-4">
        <div>
          <div className="mb-1 flex items-center justify-between text-[11px]">
            <span className="text-slate-400">{active.auc != null ? 'LOEO ROC-AUC' : 'Method'}</span>
            <span className="font-semibold" style={{ color: s.col }}>{s.txt}</span>
          </div>
          {active.auc != null ? (
            <div className="relative h-2 rounded-full bg-slate-800">
              <div className="absolute inset-y-0 left-1/2 w-px bg-slate-600" title="0.5 = no skill" />
              <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${aucPct}%`, background: s.col }} />
            </div>
          ) : (
            <div className="text-xs text-slate-400">Intensity Prediction Equation + Omori-Utsu aftershocks (physics)</div>
          )}
        </div>
        <div className="flex gap-4 text-center">
          <Metric label="AUC" value={active.auc != null ? active.auc.toFixed(3) : '—'} />
          <Metric label="Avg-Prec" value={active.avg_precision != null ? active.avg_precision.toFixed(3) : '—'} />
          <Metric label="cells" value={active.training_cell_count?.toLocaleString() || '—'} />
        </div>
      </div>

      {active.validation_note && (
        <p className="mt-3 border-l-2 border-slate-700 pl-3 text-[11px] leading-relaxed text-slate-400">
          {active.validation_note}
        </p>
      )}

      {retired.length > 0 && (
        <details className="mt-3 text-[11px]">
          <summary className="cursor-pointer text-slate-500 hover:text-slate-300">
            {retired.length} superseded version{retired.length > 1 ? 's' : ''}
          </summary>
          <ul className="mt-2 space-y-1">
            {retired.map(r => (
              <li key={r.model_version} className="flex items-center gap-2 text-slate-500">
                <XCircle size={11} className="shrink-0 text-slate-600" />
                <span className="font-mono">{r.model_version}</span>
                <span>AUC {r.auc != null ? r.auc.toFixed(3) : '—'}</span>
                {r.auc >= 0.95 && <span className="text-red-400/70">overfit — failed out-of-sample</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

const Metric = ({ label, value }) => (
  <div>
    <div className="text-base font-semibold tabular-nums">{value}</div>
    <div className="text-[9px] uppercase tracking-wide text-slate-500">{label}</div>
  </div>
)
