
import SimpleIcon from '../components/SimpleIcon'
}

export default function EUTaxonomyReportPage() {
  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">EU Taxonomy Alignment Report</h1>
            <p className="text-gray-600">Economic Activities Classification - Sustainable Finance Disclosure</p>
          </div>
          <div><SimpleIcon type="file" /></div>
        </div>
      </section>

      <section className="py-12 px-6 max-w-4xl mx-auto">
        <div className="space-y-8">
          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Taxonomy Alignment</h2>
            <p className="text-gray-700 mb-4">Revenue from Taxonomy-aligned activities: €14.2B (42% of total)</p>
            <div className="space-y-3">
              <div><p className="text-sm text-gray-600">Climate Change Mitigation (CCM)</p><div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-green-600" style={{width: '38%'}} /></div></div>
              <div><p className="text-sm text-gray-600">Climate Change Adaptation (CCA)</p><div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-blue-600" style={{width: '12%'}} /></div></div>
              <div><p className="text-sm text-gray-600">Water & Circular Economy</p><div className="w-full h-2 bg-gray-200 rounded-full overflow-hidden"><div className="h-full bg-cyan-600" style={{width: '8%'}} /></div></div>
            </div>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">DNSH Compliance</h2>
            <p className="text-gray-700 mb-4">Do No Significant Harm assessment across all activities</p>
            <p className="text-gray-600 text-sm">Climate Change Adaptation: 95% | Water: 88% | Circular Economy: 92% | Pollution: 85%</p>
          </div>

          <div className="bg-white rounded-lg border border-gray-200 p-8">
            <h2 className="text-2xl font-semibold text-gray-900 mb-4">Capital Allocation</h2>
            <p className="text-gray-700 mb-4">CapEx commitment to Taxonomy-aligned activities: €2.1B (18% of total)</p>
            <p className="text-gray-600 text-sm">Enabling activities: €340M | Transitional activities: €820M</p>
          </div>

          <button className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg transition-all">
            Download Full Report (PDF)
          </button>
        </div>
      </section>

      <div className="h-12" />
    </div>
  )
}
