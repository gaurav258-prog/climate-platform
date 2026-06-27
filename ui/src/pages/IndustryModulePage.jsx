import { useState, useEffect } from 'react'
import {
  Landmark, Umbrella, Sprout, Layers, TrendingUp, Building, Truck, Building2,
  ArrowRight, CheckCircle2, Database, Activity,
} from 'lucide-react'
import { INDUSTRY_BY_ID, PROCESSING_CHAIN } from '../data/industries'
import { fetchScoresSummary } from '../api/client'

const ICONS = {
  landmark: Landmark, umbrella: Umbrella, sprout: Sprout, layers: Layers,
  'trending-up': TrendingUp, building: Building, truck: Truck,
  'building-community': Building2,
}

// Placeholder insurance maths mirrored from services/intelligence/insurance_pricing.py
function samplePremium(score, sumInsured = 5_000_000) {
  const p = 0.001 * Math.pow(0.20 / 0.001, score / 100) // geometric loss curve
  const eal = sumInsured * p * 0.30                       // mean damage ratio
  return { eal, premium: eal * 1.35 }                     // expense + profit load
}

const euro = n => '€' + Math.round(n).toLocaleString()

export default function IndustryModulePage({ industryId }) {
  const ind = INDUSTRY_BY_ID[industryId]
  const [summary, setSummary] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    fetchScoresSummary().then(d => alive && setSummary(d)).catch(e => alive && setErr(String(e)))
    return () => { alive = false }
  }, [])

  if (!ind) return <div className="p-8 text-gray-600">Unknown module: {industryId}</div>
  const Icon = ICONS[ind.icon] || Landmark
  const live = summary?.hazards?.find(h => h.hazard_type === ind.liveHazard)
  const built = ind.status === 'built'

  return (
    <div className="w-full h-full overflow-y-auto bg-gray-50">
      {/* Header */}
      <section className="bg-white border-b border-gray-200 py-8 px-8">
        <div className="max-w-6xl mx-auto">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-indigo-50 flex items-center justify-center text-indigo-600">
              <Icon size={24} strokeWidth={1.5} />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-3">
                <h1 className="text-3xl font-light text-gray-900">{ind.name}</h1>
                <span className={`text-[11px] uppercase tracking-wide px-2 py-0.5 rounded-full ${built ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
                  {built ? 'Live' : 'Roadmap · same engine'}
                </span>
              </div>
              <p className="text-gray-600 mt-1">{ind.tagline}</p>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-8 py-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left: value story + functionality + workflow */}
        <div className="lg:col-span-2 space-y-8">
          {/* Value story */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Value story</h2>
            <p className="text-gray-800 leading-relaxed">{ind.valueStory}</p>
            <ul className="mt-4 space-y-2">
              {ind.valuePoints.map((v, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                  <CheckCircle2 size={16} className="text-green-600 mt-0.5 shrink-0" />
                  <span>{v}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Functionalities */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">Functionality</h2>
            <div className="grid sm:grid-cols-2 gap-3">
              {ind.functionalities.map((f, i) => (
                <div key={i} className="text-sm text-gray-800 bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">{f}</div>
              ))}
            </div>
          </div>

          {/* Workflow → processing + DB */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-1">Workflow</h2>
            <p className="text-xs text-gray-500 mb-4">Each step is wired to the processing layer and the database.</p>
            <ol className="space-y-3">
              {ind.workflow.map((w, i) => (
                <li key={i} className="flex items-start gap-3">
                  <div className="w-6 h-6 rounded-full bg-indigo-600 text-white text-xs flex items-center justify-center shrink-0 mt-0.5">{i + 1}</div>
                  <div className="flex-1">
                    <p className="text-sm text-gray-900">{w.step}</p>
                    <p className="text-xs text-gray-500 font-mono flex items-center gap-1 mt-0.5">
                      <Database size={11} /> {w.ref}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>

        {/* Right: live data panel + I/O */}
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3 flex items-center gap-2">
              <Activity size={14} /> Live from canonical_scores
            </h2>
            <LivePanel ind={ind} live={live} err={err} loading={!summary && !err} />
          </div>

          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Consumes</p>
            <p className="text-sm text-gray-800 mb-4">{ind.consumes}</p>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-2">Produces</p>
            <p className="text-sm text-gray-800">{ind.output}</p>
          </div>

          {/* the shared chain */}
          <div className="bg-white rounded-xl border border-gray-200 p-6">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-3">Shared processing chain</p>
            <div className="space-y-2">
              {PROCESSING_CHAIN.map((s, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="font-medium text-gray-900 w-14">{s.stage}</span>
                  <ArrowRight size={11} className="text-gray-300" />
                  <span className="text-gray-600 flex-1">{s.detail}</span>
                  <span className="font-mono text-[10px] text-indigo-500">{s.table}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}

function LivePanel({ ind, live, err, loading }) {
  if (loading) return <p className="text-sm text-gray-400">Loading live scores…</p>
  if (err) return <p className="text-sm text-amber-700">Platform API unreachable. Start the scores API to see live data.</p>

  // Built module whose hazard isn't scored yet (e.g. agriculture → drought)
  if (!live) {
    return (
      <div className="text-sm">
        <p className="text-gray-700 mb-2">Engine is live and wired.</p>
        <p className="text-xs text-gray-500">{ind.note || `Awaiting ${ind.liveHazard || 'hazard'} scores in canonical_scores.`}</p>
      </div>
    )
  }

  const total = live.cells
  const pct = b => total ? Math.max(2, Math.round((live.buckets[b] / total) * 100)) : 0
  const colors = { L: 'bg-green-500', M: 'bg-yellow-500', H: 'bg-orange-500', VH: 'bg-red-600' }
  const top = live.top_cells?.[0]
  const prem = top && ind.id === 'insurance' ? samplePremium(top.risk_score) : null
  const discloses = top && ind.id === 'banking' ? (top.risk_bucket === 'H' || top.risk_bucket === 'VH') : null

  return (
    <div className="text-sm space-y-4">
      <div className="grid grid-cols-2 gap-2 text-center">
        <div className="bg-gray-50 rounded-lg py-2">
          <p className="text-xl font-semibold text-gray-900">{total.toLocaleString()}</p>
          <p className="text-[11px] text-gray-500">cells scored</p>
        </div>
        <div className="bg-gray-50 rounded-lg py-2">
          <p className="text-xl font-semibold text-gray-900">{live.max_score}</p>
          <p className="text-[11px] text-gray-500">max score</p>
        </div>
      </div>

      <div>
        <p className="text-[11px] text-gray-500 mb-1">Risk distribution ({ind.liveHazard})</p>
        <div className="flex h-3 rounded-full overflow-hidden bg-gray-100">
          {['L', 'M', 'H', 'VH'].map(b => (
            live.buckets[b] > 0 ? <div key={b} className={colors[b]} style={{ width: `${pct(b)}%` }} title={`${b}: ${live.buckets[b]}`} /> : null
          ))}
        </div>
        <div className="flex justify-between text-[10px] text-gray-400 mt-1">
          <span>L {live.buckets.L}</span><span>M {live.buckets.M}</span>
          <span>H {live.buckets.H}</span><span>VH {live.buckets.VH}</span>
        </div>
      </div>

      {prem && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3">
          <p className="text-[11px] text-indigo-700 uppercase tracking-wide">Live premium · top cell (€5M)</p>
          <p className="text-lg font-semibold text-indigo-900">{euro(prem.premium)}</p>
          <p className="text-[10px] text-indigo-600">EAL {euro(prem.eal)} · score {top.risk_score}</p>
        </div>
      )}
      {discloses !== null && (
        <div className="bg-indigo-50 border border-indigo-100 rounded-lg p-3">
          <p className="text-[11px] text-indigo-700 uppercase tracking-wide">Top cell · disclosure</p>
          <p className="text-lg font-semibold text-indigo-900">{discloses ? 'Required' : 'Not material'}</p>
          <p className="text-[10px] text-indigo-600">score {top.risk_score} ({top.risk_bucket})</p>
        </div>
      )}

      {live.avg_precision != null && (
        <div className="bg-amber-50 border border-amber-100 rounded-lg p-2">
          <p className="text-[11px] font-medium text-amber-800">Model skill (honest): Avg-Precision {live.avg_precision}</p>
          {live.validation_note && <p className="text-[10px] text-amber-700 mt-0.5 leading-snug">{live.validation_note}</p>}
        </div>
      )}
      <div className="text-[10px] text-gray-400 border-t border-gray-100 pt-2 font-mono">
        {live.model_version} · vintage {live.data_vintage}
      </div>
    </div>
  )
}
