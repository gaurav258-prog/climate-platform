import { Activity } from 'lucide-react'

export default function RegulatoryRiskDashboardPage() {
  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Regulatory Risk Dashboard</h1>
            <p className="text-gray-600">Interactive visualization of climate and regulatory risks across portfolio</p>
          </div>
          <Activity className="text-indigo-600" size={40} />
        </div>
      </section>

      <section className="py-12 px-6 max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-6">Risk Exposure Summary</h2>
            <div className="space-y-6">
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Physical Risk</p>
                  <p className="text-sm font-semibold text-red-600">High</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-red-600" style={{width: '72%'}} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Transition Risk</p>
                  <p className="text-sm font-semibold text-orange-600">High</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-orange-600" style={{width: '68%'}} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Regulatory Risk</p>
                  <p className="text-sm font-semibold text-yellow-600">Medium</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-yellow-600" style={{width: '54%'}} />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-2">
                  <p className="text-sm text-gray-600">Reputational Risk</p>
                  <p className="text-sm font-semibold text-green-600">Low</p>
                </div>
                <div className="w-full h-3 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-green-600" style={{width: '32%'}} />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-6">Compliance Status</h2>
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-green-50 rounded-lg border border-green-200">
                <div>
                  <p className="font-semibold text-green-900">TCFD</p>
                  <p className="text-sm text-green-700">95% Complete</p>
                </div>
                <span className="text-2xl">✓</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-yellow-50 rounded-lg border border-yellow-200">
                <div>
                  <p className="font-semibold text-yellow-900">EU Taxonomy</p>
                  <p className="text-sm text-yellow-700">58% Complete</p>
                </div>
                <span className="text-2xl">⚠</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-orange-50 rounded-lg border border-orange-200">
                <div>
                  <p className="font-semibold text-orange-900">SEC Disclosure</p>
                  <p className="text-sm text-orange-700">65% Complete</p>
                </div>
                <span className="text-2xl">⚠</span>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 bg-white rounded-lg border border-gray-200 p-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-6">Portfolio Risk Heatmap</h2>
          <div className="space-y-4">
            {[
              { sector: 'Oil & Gas', flood: 8, heat: 7, wildfire: 9, seismic: 4 },
              { sector: 'Real Estate', flood: 6, heat: 8, wildfire: 5, seismic: 6 },
              { sector: 'Agriculture', flood: 9, heat: 9, wildfire: 6, seismic: 3 },
              { sector: 'Manufacturing', flood: 4, heat: 5, wildfire: 3, seismic: 7 },
            ].map((row, idx) => (
              <div key={idx} className="flex items-center gap-4">
                <p className="font-semibold text-gray-900 w-32">{row.sector}</p>
                <div className="flex gap-2 flex-1">
                  {[
                    { label: 'Flood', value: row.flood, color: 'bg-blue-600' },
                    { label: 'Heat', value: row.heat, color: 'bg-orange-600' },
                    { label: 'Wildfire', value: row.wildfire, color: 'bg-red-600' },
                    { label: 'Seismic', value: row.seismic, color: 'bg-purple-600' },
                  ].map((hazard) => (
                    <div key={hazard.label} className="flex-1">
                      <div className={`${hazard.color} h-6 rounded flex items-center justify-center text-white text-xs font-semibold`}>
                        {hazard.value}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
