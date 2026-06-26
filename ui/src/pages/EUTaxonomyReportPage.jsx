
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
