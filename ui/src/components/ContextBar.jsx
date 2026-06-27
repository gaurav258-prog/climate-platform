// Persistent context strip — always tells you which world you're looking at:
// scenario, time horizon, how current the data is, and that the engine is live.
// Sits at the top of the workspace so no screen is ever ambiguous.

const SCENARIOS = [
  ['baseline', 'Baseline'],
  ['orderly_1_5c', 'Orderly 1.5°C'],
  ['disorderly_2c', 'Disorderly 2°C'],
  ['hot_house_3_5c', 'Hot-house 3.5°C'],
]
const HORIZONS = [['current', 'Current'], ['2030', '2030'], ['2050', '2050'], ['2100', '2100']]

function Select({ value, onChange, options, label }) {
  return (
    <label className="flex items-center gap-1.5 text-[12px] text-gray-500">
      <span className="text-gray-400">{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)}
        className="rounded-lg border border-gray-200 bg-white px-2 py-1 text-[12px] font-medium text-[#1d1d1f] outline-none hover:border-gray-300 focus:border-[#0071e3]">
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

export default function ContextBar({ scenario, horizon, onScenario, onHorizon, vintage, label }) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 bg-white/80 px-5 py-2 backdrop-blur">
      <div className="flex items-center gap-2 text-[13px]">
        <span className="font-semibold text-[#1d1d1f]">{label || 'Banking'}</span>
      </div>
      <div className="flex items-center gap-4">
        <Select label="Scenario" value={scenario} onChange={onScenario} options={SCENARIOS} />
        <Select label="Horizon" value={horizon} onChange={onHorizon} options={HORIZONS} />
        <span className="hidden items-center gap-1.5 text-[11px] text-gray-400 sm:flex">
          data current{vintage ? ` · ${vintage}` : ''}
        </span>
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-600">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> live
        </span>
      </div>
    </div>
  )
}
