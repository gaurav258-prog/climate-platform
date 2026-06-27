import {
  Database, Layers, Radio, Building2, Landmark, Umbrella, Sprout,
  Shield, Zap, FileText, AlertCircle, LayoutDashboard,
} from 'lucide-react'

// The four data-flow tiers — the spine of the platform.
const TIERS = [
  { id: 'platform', n: 1, icon: Database, label: 'Foundation', sub: 'Data · canonical source' },
  { id: 'models', n: 2, icon: Layers, label: 'Models', sub: 'Processing · honest skill' },
  { id: 'live', n: 3, icon: Radio, label: 'Live & Events', sub: 'Map · forecasts' },
]

const INDUSTRIES = [
  { id: 'banking', icon: Landmark, label: 'Banking' },
  { id: 'insurance', icon: Umbrella, label: 'Insurance' },
  { id: 'agriculture', icon: Sprout, label: 'Agriculture' },
]

export default function Sidebar({
  activeView, onViewChange,
  activeIndustry, onSelectIndustry = () => {},
  urgentCount = 0, triggeredCount = 0,
}) {
  return (
    <nav className="w-56 shrink-0 flex flex-col overflow-y-auto bg-slate-900 border-r border-slate-800 text-slate-100">
      <div className="px-4 pt-4 pb-3 border-b border-slate-800">
        <div className="text-sm font-semibold tracking-tight">Climate Intelligence</div>
        <div className="text-[10px] uppercase tracking-widest text-slate-500">consistency by design</div>
      </div>

      {/* Data-flow tiers */}
      <Section label="Data flow">
        {TIERS.map((t, i) => (
          <TierItem key={t.id} tier={t} active={activeView === t.id} last={i === TIERS.length - 1 && false}
            onClick={() => onViewChange(t.id)} />
        ))}
        {/* Tier 4: Industries with children */}
        <TierItem tier={{ n: 4, icon: Building2, label: 'Industries', sub: 'Outputs · per sector' }}
          active={activeView === 'industry'} onClick={() => onSelectIndustry('banking')} />
        <div className="ml-7 mt-0.5 space-y-0.5 border-l border-slate-800 pl-2">
          {INDUSTRIES.map(ind => (
            <button key={ind.id} onClick={() => onSelectIndustry(ind.id)}
              className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[11px] transition ${
                activeView === 'industry' && activeIndustry === ind.id
                  ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
              <ind.icon size={13} strokeWidth={1.6} /> {ind.label}
            </button>
          ))}
        </div>
      </Section>

      {/* Secondary modules */}
      <Section label="More">
        <FlatItem active={activeView === 'dashboard'} onClick={() => onViewChange('dashboard')}
          icon={LayoutDashboard} label="Climate Brief" />
        <FlatItem active={activeView === 'operations'} onClick={() => onViewChange('operations')}
          icon={Shield} label="Operations" badge={urgentCount || null} />
        <FlatItem active={activeView === 'parametric'} onClick={() => onViewChange('parametric')}
          icon={Zap} label="Parametric" badge={triggeredCount || null} />
        <FlatItem active={activeView === 'compliance'} onClick={() => onViewChange('compliance')}
          icon={FileText} label="Packages" />
        <FlatItem active={activeView === 'regulatory'} onClick={() => onViewChange('regulatory')}
          icon={AlertCircle} label="Regulatory" />
      </Section>

      <div className="mt-auto px-4 py-3 border-t border-slate-800">
        <p className="text-[9px] uppercase tracking-widest text-slate-500">Live feed</p>
        <p className="flex items-center gap-1.5 text-xs text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> USGS seismic · streaming
        </p>
      </div>
    </nav>
  )
}

function Section({ label, children }) {
  return (
    <div className="px-2 pt-4 pb-1">
      <p className="px-2 mb-1.5 text-[9px] uppercase tracking-[0.14em] text-slate-500">{label}</p>
      {children}
    </div>
  )
}

function TierItem({ tier, active, onClick }) {
  const Icon = tier.icon
  return (
    <button onClick={onClick}
      className={`group mb-0.5 flex w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left transition ${
        active ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-800/60'}`}>
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[11px] font-bold ${
        active ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-800 text-slate-500 group-hover:text-slate-300'}`}>
        {tier.n}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5 text-sm font-medium"><Icon size={14} strokeWidth={1.7} /> {tier.label}</span>
        <span className="block truncate text-[10px] text-slate-500">{tier.sub}</span>
      </span>
    </button>
  )
}

function FlatItem({ active, onClick, icon: Icon, label, badge }) {
  return (
    <button onClick={onClick}
      className={`mb-0.5 flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm transition ${
        active ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'}`}>
      <span className="flex items-center gap-2.5"><Icon size={16} strokeWidth={1.6} /> {label}</span>
      {badge != null && <span className="rounded-full bg-red-500/20 px-1.5 py-0.5 text-[9px] font-bold text-red-300">{badge}</span>}
    </button>
  )
}
