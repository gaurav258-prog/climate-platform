import { Play, Pause } from 'lucide-react'
import { useState, useEffect, useRef } from 'react'

const PHASE_LABELS = {
  flood:    ['Pre-event', 'Pre-event', 'Pre-event', 'Rising', 'Rising', 'Rising', 'Rising', 'Peak', 'Peak', 'Receding', 'Receding'],
  wildfire: ['Pre-event', 'Pre-event', 'Ignition',  'Rising', 'Rising', 'Rising', 'Peak',   'Peak', 'Peak', 'Receding', 'Receding'],
  heat:     ['Pre-event', 'Pre-event', 'Rising',    'Rising', 'Rising', 'Peak',   'Peak',   'Peak', 'Peak', 'Receding', 'Receding'],
}

const PHASE_COLORS = {
  'Pre-event': 'text-slate-500',
  'Ignition':  'text-amber-500',
  'Rising':    'text-orange-400',
  'Peak':      'text-red-400',
  'Receding':  'text-slate-400',
}

export default function TimeSlider({ dates, dayIndex, onChange, hazard }) {
  const [playing, setPlaying] = useState(false)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(() => {
        onChange(prev => {
          if (prev >= dates.length - 1) { setPlaying(false); return prev }
          return prev + 1
        })
      }, 900)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [playing, dates.length, onChange])

  const phase = PHASE_LABELS[hazard]?.[dayIndex] ?? 'Pre-event'
  const date = dates[dayIndex]
  const peakIdx = PHASE_LABELS[hazard]?.lastIndexOf('Peak') ?? 8
  const isAtPeak = dayIndex === PHASE_LABELS[hazard]?.indexOf('Peak')

  return (
    <div className="absolute bottom-0 left-0 right-0 z-10 px-6 pb-5 pointer-events-none">
      <div className="pointer-events-auto max-w-xl mx-auto">
        <div className="bg-slate-950/90 backdrop-blur border border-slate-800 rounded px-5 py-3">

          {/* Top row */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setPlaying(p => !p)}
                className="text-slate-400 hover:text-white transition-colors"
              >
                {playing
                  ? <Pause  size={13} strokeWidth={1.5} />
                  : <Play   size={13} strokeWidth={1.5} />
                }
              </button>
              <span className="text-[13px] font-medium text-white tabular-nums">{date}</span>
            </div>

            <div className="flex items-center gap-2">
              <span className={`text-[10px] uppercase tracking-widest font-medium ${PHASE_COLORS[phase]}`}>
                {phase}
              </span>
              <span className="text-[10px] text-slate-600 tabular-nums">
                Day {dayIndex + 1} / {dates.length}
              </span>
            </div>
          </div>

          {/* Slider + tick marks */}
          <div className="relative">
            {/* Peak marker */}
            <div
              className="absolute top-0 -translate-x-1/2 flex flex-col items-center pointer-events-none"
              style={{ left: `${(peakIdx / (dates.length - 1)) * 100}%` }}
            >
              <span className="text-[9px] text-red-500 uppercase tracking-wider mb-0.5">peak</span>
            </div>

            <input
              type="range"
              min={0}
              max={dates.length - 1}
              value={dayIndex}
              onChange={e => onChange(Number(e.target.value))}
              className="w-full mt-3 accent-slate-400 cursor-pointer"
              style={{ height: '2px' }}
            />

            {/* Tick marks */}
            <div className="flex justify-between mt-1.5">
              {dates.map((d, i) => (
                <button
                  key={d}
                  onClick={() => onChange(i)}
                  className={`text-[9px] tabular-nums transition-colors ${
                    i === dayIndex ? 'text-slate-300' : 'text-slate-700 hover:text-slate-500'
                  }`}
                >
                  {d.slice(8)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
