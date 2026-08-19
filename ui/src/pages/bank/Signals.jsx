import { useState, useEffect, useMemo } from 'react'
import { Radio, Activity, MapPin, ShieldCheck, ChevronRight } from 'lucide-react'
import ContextBar from '../../components/ContextBar'
import SeismicEventDrawer from '../../components/SeismicEventDrawer'
import ModelCheckDrawer from '../../components/ModelCheckDrawer'
import { fetchSeismicEvents, fetchVerification, fetchPortfolio } from '../../api/client'

const VERIF_REGION = 'Venezuela M7.5'

const NEAR_KM = 300

function haversine(la1, lo1, la2, lo2) {
  const R = 6371, t = Math.PI / 180
  const dp = (la2 - la1) * t, dl = (lo2 - lo1) * t
  const a = Math.sin(dp / 2) ** 2 + Math.cos(la1 * t) * Math.cos(la2 * t) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}

export default function Signals() {
  const [events, setEvents] = useState([])
  const [assets, setAssets] = useState([])
  const [verifPoints, setVerifPoints] = useState([])
  const [selEvent, setSelEvent] = useState(null)   // { e, km, asset } | null
  const [showVerif, setShowVerif] = useState(false)

  useEffect(() => {
    fetchSeismicEvents(14, 4.5).then(d => setEvents(d.events || [])).catch(() => {})
    fetchPortfolio().then(d => setAssets((d.assets || []).filter(a => a.lat != null))).catch(() => {})
    fetchVerification(VERIF_REGION).then(d => setVerifPoints(d.points || [])).catch(() => {})
  }, [])

  const verif = verifPoints[verifPoints.length - 1] || null

  // Events near the loan book (nearest asset within NEAR_KM)
  const nearby = useMemo(() => {
    if (!assets.length) return []
    return events.map(e => {
      let best = Infinity, who = null
      for (const a of assets) {
        const d = haversine(e.lat, e.lon, a.lat, a.lon)
        if (d < best) { best = d; who = a }
      }
      return { e, km: best, asset: who }
    }).filter(x => x.km <= NEAR_KM).sort((a, b) => a.km - b.km)
  }, [events, assets])

  return (
    <div className="flex h-full flex-col bg-[#f5f5f7]">
      <ContextBar scenario="baseline" horizon="current" onScenario={() => {}} onHorizon={() => {}}
        vintage="2024-10-29" label="Banking · Signals" />
      <div className="flex-1 overflow-y-auto px-8 py-8">
        <header className="mb-6">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.12em] text-gray-400">
            <Radio size={13} /> Signals
          </div>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-[#1d1d1f]">What's moving</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-gray-500">
            Live hazard events screened against your book, and our forecasts checked against reality —
            so "always current" is something you can see, not just a claim.
          </p>
        </header>

        <div className="grid grid-cols-3 gap-5">
          {/* Events near the portfolio */}
          <section className="col-span-2 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
            <h2 className="flex items-center gap-2 text-[14px] font-semibold text-[#1d1d1f]">
              <MapPin size={15} className="text-[#c2410c]" /> Events near your portfolio
              <span className="font-normal text-gray-400">— within {NEAR_KM} km, last 14 days</span>
            </h2>
            {nearby.length ? (
              <ul className="mt-3 divide-y divide-gray-100">
                {nearby.map(({ e, km, asset }) => (
                  <li key={e.event_id}>
                    <button onClick={() => setSelEvent({ e, km, asset })}
                      className="flex w-full items-center justify-between py-2.5 text-left hover:bg-gray-50">
                      <div>
                        <div className="text-[13px] font-medium text-[#1d1d1f]">M{e.magnitude.toFixed(1)} · {e.region_name}</div>
                        <div className="text-[11px] text-gray-400">{Math.round(km)} km from {asset.asset_name} · {e.origin_time?.slice(0, 10)}</div>
                      </div>
                      <span className="flex items-center gap-1.5">
                        <span className="rounded-md bg-orange-50 px-2 py-0.5 text-[11px] font-semibold text-[#c2410c]">near book</span>
                        <ChevronRight size={13} className="text-gray-300" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="mt-4 flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-3 text-[13px] text-emerald-700">
                <ShieldCheck size={16} /> No hazard events within {NEAR_KM} km of your assets in the last 14 days.
              </div>
            )}
          </section>

          {/* Model verification (honesty) */}
          <button onClick={() => verif && setShowVerif(true)}
            className="rounded-2xl border border-gray-200/70 bg-white p-5 text-left shadow-sm hover:border-gray-300">
            <h2 className="flex items-center justify-between text-[14px] font-semibold text-[#1d1d1f]">
              <span className="flex items-center gap-2"><Activity size={15} className="text-[#0071e3]" /> Model check</span>
              {verif && <ChevronRight size={14} className="text-gray-300" />}
            </h2>
            <p className="mt-0.5 text-[11px] text-gray-500">Forecast vs reality, daily</p>
            {verif ? (
              <div className="mt-3">
                <div className="text-[12px] text-gray-500">{VERIF_REGION} aftershocks</div>
                <div className="mt-1 flex items-end gap-2">
                  <span className="text-2xl font-semibold tabular-nums" style={{ color: verif.within_2sigma ? '#34c759' : '#ff3b30' }}>
                    {verif.z_score > 0 ? '+' : ''}{verif.z_score.toFixed(1)}σ
                  </span>
                  <span className="mb-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold"
                    style={{ background: verif.within_2sigma ? '#e3f9e9' : '#ffe5e3', color: verif.within_2sigma ? '#34c759' : '#ff3b30' }}>
                    {verif.within_2sigma ? 'within band' : 'out of band'}
                  </span>
                </div>
                <p className="mt-2 text-[11px] leading-snug text-gray-500">
                  Predicted {verif.predicted_count?.toFixed(0)} ± {verif.sigma?.toFixed(0)} M≥4.5 aftershocks,
                  observed {verif.observed_count}. We surface where the model and reality disagree rather than hide it.
                </p>
                <p className="mt-2 text-[11px] font-medium text-[#0071e3]">See the full {verifPoints.length}-day series →</p>
              </div>
            ) : <p className="mt-3 text-xs text-gray-400">no verification data</p>}
          </button>
        </div>

        {/* Full live feed */}
        <section className="mt-5 rounded-2xl border border-gray-200/70 bg-white p-5 shadow-sm">
          <h2 className="flex items-center gap-2 text-[14px] font-semibold text-[#1d1d1f]">
            <Radio size={15} className="text-emerald-600" /> Global hazard feed
            <span className="font-normal text-gray-400">— USGS · M≥4.5 · last 14 days</span>
          </h2>
          <ul className="mt-3 grid grid-cols-2 gap-x-8 gap-y-1">
            {events.slice(0, 16).map(e => (
              <li key={e.event_id}>
                <button onClick={() => setSelEvent({ e, km: null, asset: null })}
                  className="flex w-full items-center gap-2 border-b border-gray-50 py-1.5 text-left text-[12px] hover:bg-gray-50">
                  <span className="w-9 shrink-0 rounded-md px-1 py-0.5 text-center text-[11px] font-semibold"
                    style={{ background: e.magnitude >= 6 ? '#ffe5e3' : e.magnitude >= 5 ? '#fff0e0' : '#f0f0f2',
                             color: e.magnitude >= 6 ? '#ff3b30' : e.magnitude >= 5 ? '#ff9500' : '#6e6e73' }}>
                    {e.magnitude.toFixed(1)}
                  </span>
                  <span className="flex-1 truncate text-gray-700">{e.region_name}</span>
                  <span className="shrink-0 text-gray-400">{e.origin_time?.slice(5, 10)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {selEvent && (
        <SeismicEventDrawer event={selEvent.e} nearestAsset={selEvent.asset} distanceKm={selEvent.km}
          onClose={() => setSelEvent(null)} />
      )}
      {showVerif && (
        <ModelCheckDrawer region={VERIF_REGION} points={verifPoints} onClose={() => setShowVerif(false)} />
      )}
    </div>
  )
}
