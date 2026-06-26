
const SimpleIcon = ({ type }) => {
  const s = 'w-10 h-10 stroke-current stroke-1.5'
  if (type === 'bars') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="12" width="3" height="9" /><rect x="10" y="6" width="3" height="15" /><rect x="17" y="3" width="3" height="18" /></svg>
  if (type === 'check') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="9" /><path d="M7 12 L11 16 L17 8" /></svg>
  if (type === 'trend') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M3 21 L8 13 L13 16 L21 5" /></svg>
  if (type === 'cal') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="17" rx="1" /><line x1="3" y1="9" x2="21" y2="9" /></svg>
  if (type === 'stack') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="4" /><rect x="3" y="9" width="18" height="4" /><rect x="3" y="15" width="18" height="4" /></svg>
  if (type === 'compare') return <svg className={s} viewBox="0 0 24 24" fill="none"><rect x="3" y="6" width="7" height="12" /><rect x="14" y="3" width="7" height="15" /></svg>
  if (type === 'alert') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 18 H3 Z" /></svg>
  if (type === 'file') return <svg className={s} viewBox="0 0 24 24" fill="none"><path d="M4 4 L4 20 Q4 21 5 21 L19 21 Q20 21 20 20 L20 9 L14 3 L5 3 Q4 3 4 4" /></svg>
  if (type === 'branch') return <svg className={s} viewBox="0 0 24 24" fill="none"><circle cx="6" cy="4" r="2" /><circle cx="6" cy="20" r="2" /><circle cx="18" cy="12" r="2" /><path d="M6 6 L6 18 M6 12 L18 12" /></svg>
  return null
}

/**
 * Risk Materiality Calculation
 * Calculate financial impact materiality percentage vs threshold
 */
export default function RiskMaterialityPage() {
  const assets = [
    { name: 'Oil & Gas Assets', exposure: 2400, financialImpact: 450, materiality: 18.75, threshold: 5, disclosed: false },
    { name: 'Thermal Coal Mines', exposure: 1800, financialImpact: 380, materiality: 21.11, threshold: 5, disclosed: false },
    { name: 'Renewable Energy', exposure: 3200, financialImpact: 120, materiality: 3.75, threshold: 5, disclosed: true },
    { name: 'Real Estate Portfolio', exposure: 5600, financialImpact: 280, materiality: 5.0, threshold: 5, disclosed: true },
    { name: 'Agricultural Land', exposure: 2100, financialImpact: 145, materiality: 6.90, threshold: 5, disclosed: false },
    { name: 'Transportation Assets', exposure: 4200, financialImpact: 210, materiality: 5.0, threshold: 5, disclosed: true },
  ]

  const totalAssets = assets.reduce((sum, a) => sum + a.exposure, 0)
  const totalExposure = assets.reduce((sum, a) => sum + a.financialImpact, 0)
  const overallMateriality = ((totalExposure / totalAssets) * 100).toFixed(2)
  const materialized = assets.filter(a => a.materiality >= a.threshold).length
  const requiresDisclosure = assets.filter(a => a.materiality >= a.threshold && !a.disclosed).length

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      {/* Header */}
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <h1 className="text-4xl font-light text-gray-900 mb-2">Risk Materiality Calculation</h1>
              <p className="text-gray-600">Calculate financial impact materiality percentage and compare to disclosure threshold</p>
            </div>
            <div><SimpleIcon type="trend" /></div>
          </div>
        </div>
      </section>

      {/* Summary Metrics */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <p className="text-sm text-gray-600 mb-2">Total Asset Exposure</p>
            <p className="text-3xl font-semibold text-gray-900">€{totalAssets.toLocaleString()}M</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <p className="text-sm text-gray-600 mb-2">Climate Financial Impact</p>
            <p className="text-3xl font-semibold text-orange-600">€{totalExposure.toLocaleString()}M</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <p className="text-sm text-gray-600 mb-2">Overall Materiality %</p>
            <p className="text-3xl font-semibold text-purple-600">{overallMateriality}%</p>
          </div>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <p className="text-sm text-gray-600 mb-2">Requires Disclosure</p>
            <p className="text-3xl font-semibold text-red-600">{requiresDisclosure}/{materialized}</p>
          </div>
        </div>
      </section>

      {/* Asset Materiality Table */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">Asset-Level Materiality Analysis</h2>
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Asset Class</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Exposure (€M)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Financial Impact (€M)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Materiality %</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Threshold</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {assets.map((asset, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{asset.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">€{asset.exposure}M</td>
                  <td className="px-6 py-4 text-sm text-gray-700">€{asset.financialImpact}M</td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`font-semibold ${
                      asset.materiality >= asset.threshold ? 'text-red-600' : 'text-green-600'
                    }`}>
                      {asset.materiality}%
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">{asset.threshold}%</td>
                  <td className="px-6 py-4 text-sm">
                    {asset.materiality >= asset.threshold ? (
                      <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                        asset.disclosed ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                      }`}>
                        {asset.disclosed ? '✓ Disclosed' : '⚠ Requires Disclosure'}
                      </span>
                    ) : (
                      <span className="inline-block px-3 py-1 rounded-full text-xs font-semibold bg-gray-100 text-gray-800">
                        Non-Material
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Disclosure Requirements */}
      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-purple-50 border border-purple-300 rounded-lg p-8">
          <h3 className="text-lg font-semibold text-purple-900 mb-4">Disclosure Requirements</h3>
          <ul className="space-y-2 text-purple-800 text-sm">
            <li>✓ Materiality Threshold: 5.0%</li>
            <li>✓ Assets Above Threshold: {materialized}</li>
            <li>✓ Disclosed: {assets.filter(a => a.disclosed).length}</li>
            <li>✓ Pending Disclosure: {requiresDisclosure}</li>
            <li>✓ Total Material Exposure: €{assets.filter(a => a.materiality >= a.threshold).reduce((sum, a) => sum + a.exposure, 0)}M</li>
            <li>✓ Action: Disclose Oil & Gas, Coal, and Agricultural exposure in next TCFD report</li>
          </ul>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
