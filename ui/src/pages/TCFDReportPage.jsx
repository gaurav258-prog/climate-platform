
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

export default function TCFDReportPage() {
  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">TCFD Disclosure Report</h1>
            <p className="text-gray-600">Task Force on Climate-related Financial Disclosures - Full Report</p>
          </div>
          <div><SimpleIcon type="file" /></div>
        </div>
      </section>

      <section className="py-12 px-6 max-w-4xl mx-auto">
        <div className="space-y-8">
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Governance</h2>
            <p className="text-gray-700 mb-4">The Board of Directors oversees climate-related issues through the Risk Committee. Our Climate Governance Framework establishes clear accountability for climate risk management across all business units.</p>
            <p className="text-gray-600 text-sm">Completion: 95% | Last Updated: Jun 26, 2026</p>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Strategy</h2>
            <p className="text-gray-700 mb-4">We integrate climate scenarios into our business strategy. Our analysis covers 1.5°C, 2°C, and 4°C pathways, assessing portfolio impacts on revenue, NPV, and stranded assets through 2050.</p>
            <p className="text-gray-600 text-sm">Completion: 87% | Last Updated: Jun 24, 2026</p>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Risk Management</h2>
            <p className="text-gray-700 mb-4">Our risk management process integrates climate risks into enterprise-wide frameworks. We conduct annual climate scenario analysis and stress tests to assess portfolio resilience.</p>
            <p className="text-gray-600 text-sm">Completion: 78% | Last Updated: Jun 20, 2026</p>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Metrics & Targets</h2>
            <p className="text-gray-700 mb-4">Scope 1: 5,200 kt CO2e | Scope 2: 3,100 kt CO2e | Scope 3: 12,400 kt CO2e | Target: 50% reduction by 2030</p>
            <p className="text-gray-600 text-sm">Completion: 92% | Last Updated: Jun 18, 2026</p>
          </div>

          <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-all">
            Download Full Report (PDF)
          </button>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
