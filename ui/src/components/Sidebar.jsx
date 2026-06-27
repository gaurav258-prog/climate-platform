import {
  Building2, Map, Briefcase, Radio, FileText,
  Database, Layers, LayoutDashboard, Shield, Zap,
} from 'lucide-react'

// The operational loop, as a workspace. Sense → Score → Project → Act sit on a
// Trust foundation. Banking is the loaded vertical; the engine is shared.
const WORKSPACE = [
  { id: 'bank-command', icon: Building2, label: 'Command Center', sub: 'Your world, right now' },
  { id: 'bank-map', icon: Map, label: 'Risk Map', sub: 'Assets on the golden source' },
  { id: 'bank-portfolio', icon: Briefcase, label: 'Portfolio', sub: 'The loan book' },
  { id: 'live', icon: Radio, label: 'Signals', sub: 'Live events · forecasts' },
  { id: 'regulatory', icon: FileText, label: 'Reports', sub: 'Disclosure & actions' },
]
const TRUST = [
  { id: 'platform', icon: Database, label: 'Foundation', sub: 'Data · canonical source' },
  { id: 'models', icon: Layers, label: 'Models', sub: 'Honest skill · provenance' },
]
const MORE = [
  { id: 'dashboard', icon: LayoutDashboard, label: 'Climate Brief' },
  { id: 'operations', icon: Shield, label: 'Operations' },
  { id: 'parametric', icon: Zap, label: 'Parametric' },
]

export default function Sidebar({ activeView, onViewChange }) {
  return (
    <nav className="w-56 shrink-0 flex flex-col overflow-y-auto bg-white border-r border-gray-200 text-[#1d1d1f]">
      <div className="px-5 pt-5 pb-3">
        <div className="text-[15px] font-semibold tracking-tight">Climate Intelligence</div>
        <div className="mt-1.5 inline-flex items-center gap-1.5 rounded-full bg-[#0071e3]/10 px-2 py-0.5 text-[10px] font-medium text-[#0071e3]">
          <Building2 size={11} /> Banking · Meridian Bank
        </div>
      </div>

      <Section label="Workspace">
        {WORKSPACE.map(t => <Item key={t.id} t={t} active={activeView === t.id} onClick={() => onViewChange(t.id)} withSub />)}
      </Section>
      <Section label="Trust & engine">
        {TRUST.map(t => <Item key={t.id} t={t} active={activeView === t.id} onClick={() => onViewChange(t.id)} withSub />)}
      </Section>
      <Section label="More">
        {MORE.map(t => <Item key={t.id} t={t} active={activeView === t.id} onClick={() => onViewChange(t.id)} />)}
      </Section>

      <div className="mt-auto px-5 py-3 border-t border-gray-200">
        <p className="text-[9px] uppercase tracking-[0.14em] text-gray-400">Live feed</p>
        <p className="mt-0.5 flex items-center gap-1.5 text-xs text-emerald-600">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" /> USGS seismic · streaming
        </p>
      </div>
    </nav>
  )
}

function Section({ label, children }) {
  return (
    <div className="px-2.5 pt-4 pb-1">
      <p className="px-2 mb-1.5 text-[9px] uppercase tracking-[0.14em] text-gray-400">{label}</p>
      {children}
    </div>
  )
}

function Item({ t, active, onClick, withSub }) {
  const Icon = t.icon
  return (
    <button onClick={onClick}
      className={`group mb-0.5 flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition ${
        active ? 'bg-gray-100' : 'hover:bg-gray-50'}`}>
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition ${
        active ? 'bg-[#0071e3] text-white' : 'bg-gray-100 text-gray-400 group-hover:text-gray-500'}`}>
        <Icon size={15} strokeWidth={1.8} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[13px] font-medium text-[#1d1d1f]">{t.label}</span>
        {withSub && <span className="block truncate text-[10px] text-gray-400">{t.sub}</span>}
      </span>
    </button>
  )
}
