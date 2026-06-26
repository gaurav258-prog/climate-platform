import { useState, useMemo } from 'react'
import { latLngToCell } from 'h3-js'
import { FileText, CheckCircle, Clock, Download, ChevronRight, AlertTriangle } from 'lucide-react'
import { MOCK_ASSETS, formatEur } from '../mockAssets'
import { generateMockScores } from '../mockData'

const RISK_DOT   = { LOW: 'bg-emerald-500', MEDIUM: 'bg-amber-400', HIGH: 'bg-orange-500', VERY_HIGH: 'bg-red-500' }
const RISK_TEXT  = { LOW: 'text-emerald-500', MEDIUM: 'text-amber-400', HIGH: 'text-orange-500', VERY_HIGH: 'text-red-500' }
const RISK_LABEL = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High', VERY_HIGH: 'Very High' }

const FRAMEWORKS = ['CSRD', 'ECB', 'EIOPA', 'MAS E-12']

const STATUS_STYLES = {
  DRAFT:    { icon: <Clock size={11} strokeWidth={1.5} />,       color: 'text-amber-400',   label: 'Draft' },
  RELEASED: { icon: <CheckCircle size={11} strokeWidth={1.5} />, color: 'text-emerald-500', label: 'Released' },
}

function useAssetScores(scores) {
  return useMemo(() => {
    const scoreMap = new Map(scores.map(s => [s.h3_cell, s]))
    return MOCK_ASSETS.map(asset => {
      const cell = latLngToCell(asset.lat, asset.lng, 8)
      const score = scoreMap.get(cell)
      return { ...asset, h3_cell: cell, score: score?.score ?? null, risk_level: score?.risk_level ?? null }
    })
  }, [scores])
}

function SummaryCard({ label, value, sub, accent }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded px-4 py-3">
      <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">{label}</p>
      <p className={`text-xl font-semibold tabular-nums ${accent ?? 'text-white'}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
    </div>
  )
}

function PackageBuilder({ assets }) {
  const [framework, setFramework] = useState('CSRD')
  const [periodStart, setPeriodStart] = useState('2024-01-01')
  const [periodEnd, setPeriodEnd]   = useState('2024-12-31')
  const [makerId, setMakerId]       = useState('')
  const [checkerId, setCheckerId]   = useState('')
  const [packages, setPackages]     = useState([])
  const [error, setError]           = useState(null)

  function createPackage() {
    if (!makerId.trim()) { setError('Maker ID required'); return }
    setError(null)
    setPackages(prev => [...prev, {
      id: `PKG-${String(prev.length + 1).padStart(3, '0')}`,
      framework,
      period: `${periodStart} – ${periodEnd}`,
      maker: makerId.trim(),
      checker: null,
      status: 'DRAFT',
      assets: assets.length,
      createdAt: new Date().toISOString().slice(0, 10),
    }])
    setMakerId('')
  }

  function approvePackage(id) {
    if (!checkerId.trim()) { setError('Checker ID required to approve'); return }
    const pkg = packages.find(p => p.id === id)
    if (pkg?.maker === checkerId.trim()) { setError('Checker must differ from maker (4-eyes rule)'); return }
    setError(null)
    setPackages(prev => prev.map(p =>
      p.id === id ? { ...p, status: 'RELEASED', checker: checkerId.trim() } : p
    ))
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Form */}
      <div className="bg-slate-900 border border-slate-800 rounded p-4">
        <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-3">New Package</p>

        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <label className="text-[10px] text-slate-600 uppercase tracking-wide block mb-1">Framework</label>
            <select
              value={framework}
              onChange={e => setFramework(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-slate-500"
            >
              {FRAMEWORKS.map(f => <option key={f}>{f}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-slate-600 uppercase tracking-wide block mb-1">Period Start</label>
            <input
              type="date" value={periodStart}
              onChange={e => setPeriodStart(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-slate-500"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-600 uppercase tracking-wide block mb-1">Period End</label>
            <input
              type="date" value={periodEnd}
              onChange={e => setPeriodEnd(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-[12px] text-slate-200 focus:outline-none focus:border-slate-500"
            />
          </div>
          <div>
            <label className="text-[10px] text-slate-600 uppercase tracking-wide block mb-1">Maker ID</label>
            <input
              type="text" value={makerId} placeholder="e.g. alice.r"
              onChange={e => setMakerId(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-[12px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-slate-500"
            />
          </div>
        </div>

        {error && (
          <div className="flex items-center gap-2 text-[11px] text-amber-400 mb-3">
            <AlertTriangle size={11} strokeWidth={1.5} />
            {error}
          </div>
        )}

        <button
          onClick={createPackage}
          className="w-full bg-slate-700 hover:bg-slate-600 text-white text-[12px] font-medium py-2 rounded transition-colors"
        >
          Create Package
        </button>
      </div>

      {/* Checker row */}
      {packages.some(p => p.status === 'DRAFT') && (
        <div className="bg-slate-900 border border-slate-800 rounded px-4 py-3">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">Checker ID (4-eyes)</p>
          <input
            type="text" value={checkerId} placeholder="e.g. bob.k"
            onChange={e => setCheckerId(e.target.value)}
            className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1.5 text-[12px] text-slate-200 placeholder-slate-600 focus:outline-none focus:border-slate-500"
          />
        </div>
      )}

      {/* Package list */}
      {packages.length > 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded overflow-hidden">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest px-4 pt-3 pb-2">Packages</p>
          <div className="divide-y divide-slate-800">
            {packages.map(pkg => {
              const st = STATUS_STYLES[pkg.status]
              return (
                <div key={pkg.id} className="px-4 py-3">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[12px] font-medium text-slate-200">{pkg.id}</span>
                      <span className="text-[10px] text-slate-600">{pkg.framework}</span>
                    </div>
                    <div className={`flex items-center gap-1 text-[10px] font-medium ${st.color}`}>
                      {st.icon}
                      {st.label}
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] text-slate-600">
                      {pkg.period} · {pkg.assets} assets · maker: {pkg.maker}
                      {pkg.checker && <> · checker: {pkg.checker}</>}
                    </div>
                    {pkg.status === 'DRAFT' ? (
                      <button
                        onClick={() => approvePackage(pkg.id)}
                        className="flex items-center gap-1 text-[10px] text-slate-400 hover:text-white transition-colors"
                      >
                        Approve <ChevronRight size={10} strokeWidth={1.5} />
                      </button>
                    ) : (
                      <button className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors">
                        <Download size={10} strokeWidth={1.5} />
                        XBRL
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

export default function CompliancePage({ scores }) {
  const assets = useAssetScores(scores)

  const summary = useMemo(() => {
    const totalExposure = MOCK_ASSETS.reduce((s, a) => s + a.exposure_eur, 0)
    const atRisk = assets
      .filter(a => a.risk_level === 'HIGH' || a.risk_level === 'VERY_HIGH')
      .reduce((s, a) => s + a.exposure_eur, 0)
    const highCount = assets.filter(a => a.risk_level === 'HIGH' || a.risk_level === 'VERY_HIGH').length
    return { totalExposure, atRisk, highCount }
  }, [assets])

  return (
    <div className="flex flex-1 overflow-hidden bg-slate-950">
      {/* Left — asset table */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-slate-800">
        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-3 p-4 border-b border-slate-800">
          <SummaryCard
            label="Portfolio Exposure"
            value={formatEur(summary.totalExposure)}
            sub={`${MOCK_ASSETS.length} assets`}
          />
          <SummaryCard
            label="At-Risk Exposure"
            value={formatEur(summary.atRisk)}
            sub="High or Very High"
            accent="text-orange-400"
          />
          <SummaryCard
            label="Assets High+"
            value={summary.highCount}
            sub="score ≥ 50"
            accent={summary.highCount > 0 ? 'text-orange-400' : 'text-white'}
          />
        </div>

        {/* Asset table */}
        <div className="flex-1 overflow-y-auto">
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 bg-slate-950 border-b border-slate-800">
              <tr>
                {['Asset', 'Type', 'Exposure', 'Risk Score', 'Level'].map(h => (
                  <th key={h} className="text-left px-4 py-2.5 text-[10px] text-slate-500 uppercase tracking-widest font-normal">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {assets.map(asset => (
                <tr key={asset.id} className="hover:bg-slate-900/50 transition-colors group">
                  <td className="px-4 py-3 text-slate-200 font-medium">{asset.name}</td>
                  <td className="px-4 py-3 text-slate-500">{asset.type}</td>
                  <td className="px-4 py-3 text-slate-300 tabular-nums">{formatEur(asset.exposure_eur)}</td>
                  <td className="px-4 py-3 tabular-nums font-semibold" style={{ color: asset.risk_level ? undefined : '#475569' }}>
                    {asset.score != null
                      ? <span className={RISK_TEXT[asset.risk_level]}>{asset.score}</span>
                      : <span className="text-slate-700">—</span>
                    }
                  </td>
                  <td className="px-4 py-3">
                    {asset.risk_level ? (
                      <div className="flex items-center gap-1.5">
                        <span className={`w-1.5 h-1.5 rounded-full ${RISK_DOT[asset.risk_level]}`} />
                        <span className={`text-[11px] ${RISK_TEXT[asset.risk_level]}`}>
                          {RISK_LABEL[asset.risk_level]}
                        </span>
                      </div>
                    ) : (
                      <span className="text-slate-700 text-[11px]">No score</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Right — package builder */}
      <div className="w-72 shrink-0 flex flex-col overflow-y-auto p-4 gap-2">
        <div className="flex items-center gap-2 mb-1">
          <FileText size={13} strokeWidth={1.5} className="text-slate-500" />
          <span className="text-[10px] text-slate-500 uppercase tracking-widest">Regulatory Packages</span>
        </div>
        <PackageBuilder assets={assets} />
      </div>
    </div>
  )
}
