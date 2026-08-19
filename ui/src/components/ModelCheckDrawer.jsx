import { DrawerShell } from './EntityDrawerParts'

/** The full forecast-vs-reality series behind the Signals page's single "Model
 * check" headline number -- every day's predicted/observed count and z-score,
 * not just the latest. Same "never hide the disagreement" posture as the
 * summary card, just at the row level instead of a single rolled-up figure. */
export default function ModelCheckDrawer({ region, points, onClose }) {
  return (
    <DrawerShell title="Model check — full series" subtitle={region} loading={false} onClose={onClose}>
      {!points?.length ? (
        <p className="text-[13px] text-gray-400">No verification data for this region.</p>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-gray-200">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-left text-[10px] uppercase tracking-wide text-gray-400">
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 text-right font-medium">Predicted</th>
                <th className="px-3 py-2 text-right font-medium">Observed</th>
                <th className="px-3 py-2 text-right font-medium">z-score</th>
                <th className="px-3 py-2 text-center font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {points.slice().reverse().map(p => (
                <tr key={p.as_of_date} className="border-b border-gray-50 last:border-0">
                  <td className="px-3 py-2 text-gray-500">{p.as_of_date}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-[#1d1d1f]">
                    {p.predicted_count.toFixed(1)} ± {p.sigma.toFixed(1)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-[#1d1d1f]">{p.observed_count}</td>
                  <td className="px-3 py-2 text-right tabular-nums font-medium"
                    style={{ color: p.within_2sigma ? '#34c759' : '#ff3b30' }}>
                    {p.z_score > 0 ? '+' : ''}{p.z_score.toFixed(1)}σ
                  </td>
                  <td className="px-3 py-2 text-center">
                    <span className="rounded-full px-1.5 py-0.5 text-[9px] font-semibold"
                      style={{ background: p.within_2sigma ? '#e3f9e9' : '#ffe5e3', color: p.within_2sigma ? '#34c759' : '#ff3b30' }}>
                      {p.within_2sigma ? 'in band' : 'out of band'}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-[11px] leading-relaxed text-gray-400">
        Elapsed days, largest observed magnitude, and M5+ forecast/occurrence are also tracked per row
        in the underlying forecast_verification table — this view shows the fields the summary card
        rolls up.
      </p>
    </DrawerShell>
  )
}
