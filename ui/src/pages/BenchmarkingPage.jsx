
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

export default function BenchmarkingPage() {
  const peers = [
    { bank: 'Your Bank', score: 62, tcfd: 75, taxonomy: 58, sec: 52, ranking: 'You' },
    { bank: 'Peer A (Top)', score: 85, tcfd: 95, taxonomy: 78, sec: 82, ranking: '#1' },
    { bank: 'Peer B', score: 72, tcfd: 82, taxonomy: 68, sec: 65, ranking: '#2' },
    { bank: 'Peer C', score: 68, tcfd: 78, taxonomy: 62, sec: 64, ranking: '#3' },
    { bank: 'Peer D', score: 55, tcfd: 62, taxonomy: 48, sec: 55, ranking: '#4' },
    { bank: 'Industry Avg', score: 68, tcfd: 78, taxonomy: 63, sec: 64, ranking: 'Avg' },
  ]

  return (
    <div className="w-full h-screen overflow-y-auto bg-gray-50">
      <section className="bg-white border-b border-gray-200 py-8 px-6">
        <div className="max-w-7xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-light text-gray-900 mb-2">Comparative Benchmarking</h1>
            <p className="text-gray-600">Compare your scores vs peer group for investor and regulator positioning</p>
          </div>
          <div><SimpleIcon type="compare" /></div>
        </div>
      </section>

      <section className="py-8 px-6 max-w-7xl mx-auto">
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Bank</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Overall Score</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">TCFD</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">EU Taxonomy</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">SEC</th>
                <th className="px-6 py-3 text-left text-sm font-semibold text-gray-900">Ranking</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {peers.map((p, idx) => (
                <tr key={idx} className={p.bank === 'Your Bank' ? 'bg-blue-50' : 'hover:bg-gray-50'}>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">{p.bank}</td>
                  <td className="px-6 py-4 text-sm">
                    <span className="font-semibold text-gray-900">{p.score}</span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">{p.tcfd}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{p.taxonomy}</td>
                  <td className="px-6 py-4 text-sm text-gray-700">{p.sec}</td>
                  <td className="px-6 py-4 text-sm font-semibold text-gray-900">{p.ranking}</td>
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
