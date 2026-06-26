
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

export default function TimelineTrackingPage() {
  const timelines = [
    { framework: 'TCFD', effective: '2023-06-26', daysToFramework: 0, customerDeadline: '2023-07-03', daysRemaining: -729, status: 'Overdue' },
    { framework: 'EU Taxonomy', effective: '2024-01-01', daysToFramework: -543, customerDeadline: '2024-01-08', daysRemaining: -895, status: 'Overdue' },
    { framework: 'SEC Climate Rules', effective: '2024-12-18', daysToFramework: -190, customerDeadline: '2024-12-25', daysRemaining: -183, status: 'Overdue' },
    { framework: 'CSRD (EU)', effective: '2025-01-01', daysToFramework: -177, customerDeadline: '2025-01-08', daysRemaining: -170, status: 'Overdue' },
    { framework: 'UK FCA Climate Rules', effective: '2025-06-01', daysToFramework: 67, customerDeadline: '2025-06-08', daysRemaining: 74, status: 'In Progress' },
    { framework: 'SBTi Validation', effective: '2026-12-31', daysToFramework: 554, customerDeadline: '2027-01-07', daysRemaining: 561, status: 'Pending' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Timeline & Deadline Tracking</h1>
            <p className="text-gray-600">Framework effective date → Customer deadline (regulatory deadline + 7 days + implementation)</p>
          </div>
          <div><SimpleIcon type="cal" /></div>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Framework</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Effective Date</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Customer Deadline</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Days Remaining</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {timelines.map((item, idx) => (
                <tr key={idx} className="hover:bg-gray-50">
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{item.framework}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{item.effective}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{item.customerDeadline}</td>
                  <td className="px-6 py-4 text-sm font-semibold">
                    <span className={item.daysRemaining < 0 ? 'text-red-600' : item.daysRemaining < 90 ? 'text-orange-600' : 'text-green-600'}>
                      {item.daysRemaining > 0 ? '+' : ''}{item.daysRemaining} days
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span className={`inline-block px-3 py-1 rounded-full text-xs font-semibold ${
                      item.status === 'Overdue' ? 'bg-red-100 text-red-800' :
                      item.status === 'In Progress' ? 'bg-yellow-100 text-yellow-800' :
                      'bg-green-100 text-green-800'
                    }`}>
                      {item.status}
                    </span>
                  </td>
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
