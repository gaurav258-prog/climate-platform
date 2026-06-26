import { FileText } from 'lucide-react'

export default function TCFDReportPage() {
  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">TCFD Disclosure Report</h1>
            <p className="text-gray-600">Task Force on Climate-related Financial Disclosures - Full Report</p>
          </div>
          <FileText className="text-blue-600" size={40} />
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
