
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

export default function RegulatoryRiskDashboardPage() {
  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Regulatory Risk Dashboard</h1>
            <p className="text-gray-600">Interactive visualization of climate and regulatory risks across portfolio</p>
          </div>
          <div><SimpleIcon type="bars" /></div>
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
