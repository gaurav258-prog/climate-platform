
import SimpleIcon from '../components/SimpleIcon'

export default function PortfolioAggregationPage() {
  const sectors = [
    { name: 'Financial Services', exposure: 4200, emissions: 1200, materiality: 8.5, trend: '↓ -3%' },
    { name: 'Energy & Utilities', exposure: 3800, emissions: 2400, materiality: 12.1, trend: '↑ +5%' },
    { name: 'Real Estate', exposure: 5600, emissions: 1800, materiality: 9.3, trend: '→ Stable' },
    { name: 'Agriculture', exposure: 2100, emissions: 900, materiality: 6.2, trend: '↑ +2%' },
    { name: 'Transportation', exposure: 3200, emissions: 1600, materiality: 7.8, trend: '→ Stable' },
    { name: 'Manufacturing', exposure: 2800, emissions: 1400, materiality: 6.9, trend: '↓ -1%' },
  ]

  const geographies = [
    { region: 'Europe', exposure: 12400, emissions: 4800, materiality: 8.1 },
    { region: 'Asia-Pacific', exposure: 6200, emissions: 3200, materiality: 9.2 },
    { region: 'Americas', exposure: 5800, emissions: 2400, materiality: 7.3 },
    { region: 'Africa & Middle East', exposure: 2300, emissions: 1100, materiality: 6.8 },
  ]

  const totalExposure = sectors.reduce((sum, s) => sum + s.exposure, 0)
  const totalEmissions = sectors.reduce((sum, s) => sum + s.emissions, 0)

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Portfolio Aggregation</h1>
            <p className="text-gray-600">Sum/weight all bank assets by sector and geography for portfolio-level disclosure</p>
          </div>
          <div><SimpleIcon type="stack" /></div>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">By Sector</h2>
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Sector</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Exposure (€M)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">GHG Emissions (kt CO2e)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Materiality %</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Trend</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {sectors.map((s, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{s.name}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">€{s.exposure}M ({((s.exposure/totalExposure)*100).toFixed(1)}%)</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{s.emissions} kt ({((s.emissions/totalEmissions)*100).toFixed(1)}%)</td>
                  <td className="px-6 py-4 text-sm font-semibold text-gray-900">{s.materiality}%</td>
                  <td className="px-6 py-4 text-sm text-gray-600">{s.trend}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <h2 className="text-2xl font-light text-gray-900 mb-6">By Geography</h2>
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Region</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Exposure (€M)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">GHG Emissions (kt CO2e)</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Materiality %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {geographies.map((g, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{g.region}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">€{g.exposure}M ({((g.exposure/totalExposure)*100).toFixed(1)}%)</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{g.emissions} kt ({((g.emissions/totalEmissions)*100).toFixed(1)}%)</td>
                  <td className="px-6 py-4 text-sm font-semibold text-gray-900">{g.materiality}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
