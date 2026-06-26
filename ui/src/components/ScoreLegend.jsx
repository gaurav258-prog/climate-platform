const BANDS = [
  { label: 'Low',       range: '0 – 25',   color: '#10b981' },
  { label: 'Medium',    range: '25 – 50',  color: '#f59e0b' },
  { label: 'High',      range: '50 – 75',  color: '#f97316' },
  { label: 'Very High', range: '75 – 100', color: '#ef4444' },
]

export default function ScoreLegend() {
  return (
    <div className="absolute top-4 left-4 z-10">
      <div className="bg-slate-950/90 backdrop-blur border border-slate-800 rounded px-3 py-2.5">
        <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-2">
          Risk Score
        </p>
        <div className="flex flex-col gap-1.5">
          {BANDS.map(b => (
            <div key={b.label} className="flex items-center gap-2.5">
              <span
                className="w-2 h-2 rounded-full shrink-0"
                style={{ backgroundColor: b.color }}
              />
              <span className="text-[11px] text-slate-400 w-14">{b.label}</span>
              <span className="text-[10px] text-slate-700 tabular-nums">{b.range}</span>
            </div>
          ))}
        </div>
        <div className="mt-2 pt-2 border-t border-slate-800/80">
          <p className="text-[9px] text-slate-700">H3 res 8 · ≈ 0.7 km² / cell</p>
        </div>
      </div>
    </div>
  )
}
