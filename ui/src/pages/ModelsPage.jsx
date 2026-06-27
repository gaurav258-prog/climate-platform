import { useState, useEffect, useMemo } from 'react'
import { Layers, CheckCircle2, XCircle } from 'lucide-react'
import { fetchModels } from '../api/client'

const HAZARD_META = {
  flood: { label: 'Flood', color: '#0071e3' },
  wildfire: { label: 'Wildfire', color: '#ff3b30' },
  seismic: { label: 'Seismic', color: '#af52de' },
  heat_acute: { label: 'Heat', color: '#ff9500' },
  drought: { label: 'Drought', color: '#ffcc00' },
}

// AUC → honest skill label
const skill = auc =>
  auc == null ? { txt: 'physics-based', col: '#af52de' }
    : auc >= 0.75 ? { txt: 'strong', col: '#34c759' }
    : auc >= 0.6 ? { txt: 'real, moderate', col: '#34c759' }
    : auc >= 0.55 ? { txt: 'real, modest', col: '#ff9500' }
    : { txt: 'no skill', col: '#ff3b30' }

export default function ModelsPage() {
  const [models, setModels] = useState(null)
  useEffect(() => { fetchModels().then(d => setModels(d.models || [])).catch(() => setModels([])) }, [])

  const byHazard = useMemo(() => {
    const m = {}
    for (const row of models || []) (m[row.hazard_type] ||= []).push(row)
    return m
  }, [models])

  return (
    <div className="h-full overflow-y-auto bg-[#f5f5f7] text-[#1d1d1f]">
      <div className="mx-auto max-w-5xl px-8 py-12">
        <header className="mb-8">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Layers size={13} /> Processing · Tier 2
          </div>
          <h1 className="mt-2 text-4xl font-semibold tracking-tight">Models</h1>
          <p className="mt-3 max-w-3xl text-[17px] leading-relaxed text-gray-500">
            One data foundation → a model specialized per <em>physical mechanism</em> → one output contract.
            We split a hazard into sub-models only when leave-one-event-out proves it helps. Every number below
            is <span className="text-[#1d1d1f]">honest out-of-sample skill</span> — forecasting a held-out
            event, never an in-sample fit.
          </p>
        </header>

        {!models && <p className="text-gray-400">loading…</p>}

        <div className="space-y-5">
          {Object.entries(byHazard).map(([hz, rows]) => {
            const active = rows.find(r => r.is_active) || rows[0]
            const retired = rows.filter(r => r !== active)
            return <ModelCard key={hz} hazard={hz} active={active} retired={retired} />
          })}
        </div>

        <footer className="mt-8 rounded-2xl border border-gray-200/70 bg-white p-6 text-sm leading-relaxed text-gray-500 shadow-sm">
          <span className="text-[#1d1d1f] font-medium">Why some hazards score lower.</span> Flood physics is
          predictable from weather; fire occurrence depends on fuel + ignition (we added FIRMS burn labels and
          ERA5 fuel — 0.44→0.57); seismic ground motion is physics (intensity attenuation + Omori-Utsu
          aftershocks), not a fitted classifier, so it has no AUC. The retired rows show models we rejected
          because in-sample skill (e.g. AUC 0.997) collapsed out-of-sample.
        </footer>
      </div>
    </div>
  )
}

function ModelCard({ hazard, active, retired }) {
  const meta = HAZARD_META[hazard] || { label: hazard, color: '#86868b' }
  const s = skill(active.auc)
  const aucPct = active.auc != null ? Math.max(0, Math.min(100, (active.auc - 0.5) / 0.5 * 100)) : 100
  return (
    <section className="rounded-2xl border border-gray-200/70 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <span className="h-10 w-1.5 rounded-full" style={{ background: meta.color }} />
          <div>
            <h2 className="text-xl font-semibold tracking-tight">{meta.label}</h2>
            <div className="font-mono text-[11px] text-gray-400">{active.model_version} · {active.algorithm}</div>
          </div>
        </div>
        <span className="flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-1 text-[11px] font-medium text-green-600">
          <CheckCircle2 size={12} /> active
        </span>
      </div>

      <div className="mt-5 grid grid-cols-[1fr_auto] items-center gap-6">
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px]">
            <span className="text-gray-400">{active.auc != null ? 'LOEO ROC-AUC' : 'Method'}</span>
            <span className="font-semibold" style={{ color: s.col }}>{s.txt}</span>
          </div>
          {active.auc != null ? (
            <div className="relative h-2 rounded-full bg-gray-100">
              <div className="absolute inset-y-0 left-1/2 w-px bg-gray-300" title="0.5 = no skill" />
              <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${aucPct}%`, background: s.col }} />
            </div>
          ) : (
            <div className="text-[13px] text-gray-500">Intensity Prediction Equation + Omori-Utsu aftershocks (physics)</div>
          )}
        </div>
        <div className="flex gap-5 text-center">
          <Metric label="AUC" value={active.auc != null ? active.auc.toFixed(3) : '—'} />
          <Metric label="Avg-Prec" value={active.avg_precision != null ? active.avg_precision.toFixed(3) : '—'} />
          <Metric label="cells" value={active.training_cell_count?.toLocaleString() || '—'} />
        </div>
      </div>

      {active.validation_note && (
        <p className="mt-4 border-l-2 border-gray-200 pl-3 text-[12px] leading-relaxed text-gray-500">
          {active.validation_note}
        </p>
      )}

      {retired.length > 0 && (
        <details className="mt-3 text-[11px]">
          <summary className="cursor-pointer text-gray-400 hover:text-gray-600">
            {retired.length} superseded version{retired.length > 1 ? 's' : ''}
          </summary>
          <ul className="mt-2 space-y-1">
            {retired.map(r => (
              <li key={r.model_version} className="flex items-center gap-2 text-gray-400">
                <XCircle size={11} className="shrink-0 text-gray-300" />
                <span className="font-mono">{r.model_version}</span>
                <span>AUC {r.auc != null ? r.auc.toFixed(3) : '—'}</span>
                {r.auc >= 0.95 && <span className="text-[#ff3b30]/70">overfit — failed out-of-sample</span>}
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
    <div className="text-lg font-semibold tabular-nums">{value}</div>
    <div className="text-[9px] uppercase tracking-wide text-gray-400">{label}</div>
  </div>
)
