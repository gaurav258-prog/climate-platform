import { GitCompare } from 'lucide-react'

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
          <GitCompare className="text-pink-600" size={40} />
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
