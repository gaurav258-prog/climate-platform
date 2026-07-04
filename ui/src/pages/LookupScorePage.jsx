import { useState, useRef, useCallback, useEffect } from 'react'
import {
  Search, MapPin, Activity, Waves, Flame, Thermometer, ThermometerSun,
  CloudOff, Wind, Mountain, CloudFog, Loader2, AlertCircle,
} from 'lucide-react'
import BrandMark from '../components/BrandMark'
import { BUCKET } from '../components/RiskAtom'
import { lookupScore, pollLookup } from '../api/client'

const HAZ_ICON = {
  seismic: Activity, flood: Waves, wildfire: Flame, heat_acute: Thermometer,
  heat_chronic: ThermometerSun, drought: CloudOff, storm: Wind, volcanic: Mountain,
  pollution: CloudFog,
}
const HAZ_LABEL = {
  seismic: 'Seismic', flood: 'Flood', wildfire: 'Wildfire', heat_acute: 'Heat (acute)',
  heat_chronic: 'Heat (chronic)', drought: 'Drought', storm: 'Storm', volcanic: 'Volcanic',
  pollution: 'Pollution',
}
const POLL_INTERVAL_MS = 4000
const POLL_TIMEOUT_MS = 5 * 60 * 1000

function OverallCard({ overall }) {
  if (overall.score == null) {
    return (
      <div className="rounded-2xl border border-gray-200/70 bg-white p-6 text-center shadow-sm">
        <p className="text-[13px] text-gray-500">No hazard has resolved yet — results are still computing.</p>
      </div>
    )
  }
  const b = BUCKET[overall.bucket] || BUCKET.L
  return (
    <div className="rounded-2xl border border-gray-200/70 p-6 shadow-sm" style={{ background: b.bg }}>
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-[12px] font-medium uppercase tracking-wide" style={{ color: b.c }}>Overall risk score</p>
          <p className="mt-1 text-5xl font-semibold tabular-nums" style={{ color: b.c }}>{overall.score}</p>
        </div>
        <div className="text-right">
          <span className="inline-block rounded-lg bg-white px-3 py-1 text-[13px] font-semibold" style={{ color: b.c }}>
            {overall.bucket} · {b.label}
          </span>
          {overall.driver_hazard && (
            <p className="mt-2 text-[12px]" style={{ color: b.c }}>
              driven by {HAZ_LABEL[overall.driver_hazard] || overall.driver_hazard}
            </p>
          )}
        </div>
      </div>
      {overall.status === 'provisional' && (
        <p className="mt-4 flex items-center gap-1.5 text-[12px]" style={{ color: b.c }}>
          <Loader2 size={13} className="animate-spin" />
          provisional — {overall.hazards_pending} more hazard{overall.hazards_pending === 1 ? '' : 's'} still computing
        </p>
      )}
    </div>
  )
}

function HazardRow({ hazard }) {
  const Icon = HAZ_ICON[hazard.hazard_type] || Activity
  const label = HAZ_LABEL[hazard.hazard_type] || hazard.hazard_type
  const resolved = hazard.status === 'cached_hit' || hazard.status === 'scored' || hazard.status === 'done'
  const b = resolved ? (BUCKET[hazard.risk_bucket] || BUCKET.L) : null

  return (
    <div className="flex items-center justify-between rounded-xl border border-gray-200/70 bg-white px-4 py-3">
      <div className="flex items-center gap-2.5">
        <Icon size={17} className="text-gray-400" />
        <span className="text-[14px] text-[#1d1d1f]">{label}</span>
      </div>
      {resolved && (
        <span className="rounded-md px-2 py-0.5 text-[13px] font-semibold tabular-nums" style={{ background: b.bg, color: b.c }}>
          {Math.round(hazard.risk_score)} · {hazard.risk_bucket}
        </span>
      )}
      {hazard.status === 'pending' && (
        <span className="flex items-center gap-1.5 text-[12px] text-gray-400">
          <Loader2 size={13} className="animate-spin" /> computing
        </span>
      )}
      {hazard.status === 'insufficient_data' && (
        <span className="text-[12px] text-gray-400" title={hazard.reason || undefined}>not enough data</span>
      )}
      {hazard.status === 'failed' && (
        <span className="text-[12px] text-red-400">fetch failed</span>
      )}
    </div>
  )
}

export default function LookupScorePage({ onHome }) {
  const [address, setAddress] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null) // full LookupResponse
  const pollersRef = useRef(new Map()) // lookup_id -> interval id

  const clearPollers = useCallback(() => {
    for (const id of pollersRef.current.values()) clearInterval(id)
    pollersRef.current.clear()
  }, [])

  useEffect(() => () => clearPollers(), [clearPollers])

  const pollOne = useCallback((lookupId) => {
    const startedAt = Date.now()
    const tick = async () => {
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        clearInterval(pollersRef.current.get(lookupId))
        pollersRef.current.delete(lookupId)
        return
      }
      try {
        const { hazard, overall } = await pollLookup(lookupId)
        setResult(prev => {
          if (!prev) return prev
          const hazards = prev.hazards.map(h => (h.lookup_id === lookupId ? { ...h, ...hazard, hazard_type: h.hazard_type } : h))
          return { ...prev, hazards, overall }
        })
        if (hazard.status !== 'pending') {
          clearInterval(pollersRef.current.get(lookupId))
          pollersRef.current.delete(lookupId)
        }
      } catch {
        clearInterval(pollersRef.current.get(lookupId))
        pollersRef.current.delete(lookupId)
      }
    }
    const id = setInterval(tick, POLL_INTERVAL_MS)
    pollersRef.current.set(lookupId, id)
  }, [])

  const onSubmit = useCallback(async (e) => {
    e.preventDefault()
    if (!address.trim()) return
    clearPollers()
    setLoading(true); setError(null); setResult(null)
    try {
      const res = await lookupScore(address.trim())
      setResult(res)
      res.hazards.filter(h => h.status === 'pending' && h.lookup_id).forEach(h => pollOne(h.lookup_id))
    } catch (err) {
      setError(err.status === 404 ? `Could not find "${address.trim()}" — try a more specific address.` : 'Something went wrong. Try again in a moment.')
    } finally {
      setLoading(false)
    }
  }, [address, clearPollers, pollOne])

  return (
    <div className="h-screen overflow-y-auto bg-[#f5f5f7] text-[#1d1d1f]">
      <nav className="flex items-center justify-between px-8 py-4">
        <button onClick={onHome} className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
          <BrandMark size={28} /><span>Tel<span className="text-sky-600">lumen</span></span>
        </button>
        <button onClick={onHome} className="rounded-full border border-gray-200 px-4 py-2 text-[13px] font-medium text-gray-500 hover:text-[#1d1d1f]">
          Back to home
        </button>
      </nav>

      <div className="mx-auto max-w-xl px-6 pb-20 pt-6">
        <h1 className="text-3xl font-semibold tracking-tight">Any point on Earth. One number.</h1>
        <p className="mt-2 text-[14px] text-gray-500">
          Type a real address — we read live satellite, weather and seismic data and score every
          hazard we can reach today, live, in front of you.
        </p>

        <form onSubmit={onSubmit} className="mt-6 flex gap-2">
          <div className="relative flex-1">
            <MapPin size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              value={address}
              onChange={e => setAddress(e.target.value)}
              placeholder="123 Main St, Springfield..."
              className="w-full rounded-full border border-gray-200 bg-white py-2.5 pl-10 pr-4 text-[14px] outline-none focus:border-[#0071e3]"
            />
          </div>
          <button type="submit" disabled={loading || !address.trim()}
            className="flex items-center gap-2 rounded-full px-5 py-2.5 text-[14px] font-medium text-white disabled:opacity-40"
            style={{ background: '#0071e3' }}>
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            Check
          </button>
        </form>

        {error && (
          <div className="mt-6 flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-600">
            <AlertCircle size={15} /> {error}
          </div>
        )}

        {result && (
          <div className="mt-8">
            <p className="text-[13px] text-gray-500">{result.display_name || `${result.latitude}, ${result.longitude}`}</p>
            <div className="mt-3"><OverallCard overall={result.overall} /></div>
            <p className="mb-2 mt-6 text-[12px] font-medium uppercase tracking-wide text-gray-400">9 hazards checked</p>
            <div className="space-y-2">
              {result.hazards.map(h => <HazardRow key={h.hazard_type} hazard={h} />)}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
