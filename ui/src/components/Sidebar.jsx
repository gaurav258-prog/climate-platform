import { Map, Shield, Zap, FileText, LayoutDashboard, Waves, Flame, Thermometer, TrendingUp, Zap as Seismic } from 'lucide-react'

const HAZARD_ICONS = {
  flood:    <Waves       size={18} strokeWidth={1.5} />,
  wildfire: <Flame       size={18} strokeWidth={1.5} />,
  heat:     <Thermometer size={18} strokeWidth={1.5} />,
  seismic:  <Seismic     size={18} strokeWidth={1.5} />,
}

const HAZARD_COLORS = { flood: '#3b82f6', wildfire: '#f97316', heat: '#eab308', seismic: '#8b0000' }

export default function Sidebar({
  activeView, onViewChange,
  activeHazard, onHazardChange,
  urgentCount = 0, triggeredCount = 0,
}) {
  function nav(id) { return () => onViewChange(id) }

  return (
    <nav className="w-48 shrink-0 bg-white border-r border-gray-200 flex flex-col overflow-y-auto">

      {/* Overview */}
      <Section label="Overview">
        <NavItem id="dashboard" active={activeView === 'dashboard'} onClick={nav('dashboard')}
          icon={<LayoutDashboard size={18} strokeWidth={1.5} />} label="Climate Brief" />
      </Section>

      {/* Monitoring */}
      <Section label="Monitoring">
        <NavItem id="map" active={activeView === 'map'} onClick={nav('map')}
          icon={<Map size={18} strokeWidth={1.5} />} label="Risk Map" />

        {/* Hazard sub-items — always visible, indent slightly */}
        {['flood', 'wildfire', 'heat', 'seismic'].map(h => (
          <button
            key={h}
            onClick={() => { onHazardChange(h); onViewChange('map') }}
            className={`flex items-center gap-2 pl-7 pr-3 py-2 text-[11px] rounded-lg mx-1 transition-all font-light ${
              activeView === 'map' && activeHazard === h
                ? 'bg-gray-100 text-gray-900'
                : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
            }`}
          >
            <span style={{ color: activeView === 'map' && activeHazard === h ? HAZARD_COLORS[h] : 'currentColor' }}>
              {HAZARD_ICONS[h]}
            </span>
            <span className="capitalize">{h}</span>
          </button>
        ))}
      </Section>

      {/* Response */}
      <Section label="Response">
        <NavItem id="operations" active={activeView === 'operations'} onClick={nav('operations')}
          icon={<Shield size={18} strokeWidth={1.5} />} label="Operations"
          badge={urgentCount > 0 ? urgentCount : null} badgeColor="red" />
        <NavItem id="parametric" active={activeView === 'parametric'} onClick={nav('parametric')}
          icon={<Zap size={18} strokeWidth={1.5} />} label="Parametric"
          badge={triggeredCount > 0 ? triggeredCount : null} badgeColor="red" />
      </Section>

      {/* Compliance */}
      <Section label="Compliance">
        <NavItem id="compliance" active={activeView === 'compliance'} onClick={nav('compliance')}
          icon={<FileText size={18} strokeWidth={1.5} />} label="Packages" />
      </Section>

      {/* Analytics (placeholder) */}
      <Section label="Analytics">
        <NavItem id="trends" active={false} onClick={() => {}} disabled
          icon={<TrendingUp size={18} strokeWidth={1.5} />} label="Trends" />
      </Section>

      {/* Footer */}
      <div className="mt-auto px-3 py-3 border-t border-gray-200">
        <p className="text-xs text-gray-500 uppercase tracking-wider mb-1 font-light">Last ingestion</p>
        <p className="text-sm text-green-600 font-light">6 min ago</p>
      </div>
    </nav>
  )
}

function Section({ label, children }) {
  return (
    <div className="px-2 pt-4 pb-1">
      <p className="text-[9px] text-gray-500 uppercase tracking-[0.12em] px-2 mb-1 font-light">{label}</p>
      {children}
    </div>
  )
}

function NavItem({ id, active, onClick, icon, label, badge, badgeColor = 'gray', disabled }) {
  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      className={`w-full flex items-center justify-between px-3 py-3 rounded-lg text-sm font-light transition-all mb-0.5 ${
        disabled
          ? 'text-gray-400 cursor-default'
          : active
          ? 'bg-gray-100 text-gray-900'
          : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
      }`}
    >
      <span className="flex items-center gap-3">
        {icon && <span style={{ display: 'flex', alignItems: 'center' }}>{icon}</span>}
        {label}
      </span>
      {badge != null && (
        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full min-w-[18px] text-center ${
          badgeColor === 'red' ? 'bg-red-100 text-red-600' : 'bg-gray-100 text-gray-600'
        }`}>
          {badge}
        </span>
      )}
    </button>
  )
}
