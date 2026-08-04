import { type ReactNode } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { Home, Building2, Sprout, Map as MapIcon, BellRing, ShieldCheck, FileText, FlaskConical, Database, LogOut, Settings, Globe, ArrowLeft, Leaf, Landmark, LifeBuoy, BookOpen, KanbanSquare, AlertOctagon, CalendarDays, Gauge, GitBranch, Table2, RadioTower, Layers } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { BrandMark } from './ui'

// sector = organizations.type. The agri workspace (manufacturer) and the four financial verticals see
// different operating surfaces behind the shared globe. `sectors` gates an item to specific org types
// (undefined = every sector). This keeps a bank out of the Sourcing/EUDR pages, and agri out of Portfolio.
const AGRI = ['manufacturer']
const FIN = ['bank', 'insurer', 'asset_manager', 'reit']
const SECTOR_TAG: Record<string, string> = { manufacturer: 'AGRI', bank: 'BANK', insurer: 'INSURER', asset_manager: 'ASSET MGMT', reit: 'REIT' }

type Item = { to: string; label: string; icon: typeof Home; end?: boolean; perm?: string; anyPerm?: string[]; sectors?: string[] }
const GROUPS: { label: string | null; items: Item[] }[] = [
  { label: null, items: [
    { to: '/', label: 'Horizon', icon: Globe, end: true, perm: 'modules.view' },
    { to: '/home', label: 'Home', icon: Home, end: true, perm: 'modules.view', sectors: AGRI },
    { to: '/portfolio', label: 'Portfolio', icon: Landmark, perm: 'modules.view', sectors: FIN },
    { to: '/kri', label: 'KRI dashboard', icon: Gauge, perm: 'modules.view' },
  ] },
  { label: 'Reports', items: [
    { to: '/funds', label: 'Funds', icon: Layers, perm: 'modules.view', sectors: ['asset_manager'] },
    { to: '/compliance', label: 'Reports & filings', icon: ShieldCheck, perm: 'modules.view', sectors: FIN },
  ] },
  // ── agriculture workspace ──
  { label: 'Your footprint', items: [
    { to: '/operations', label: 'Our sites', icon: Building2, perm: 'modules.view', sectors: AGRI },
    { to: '/sourcing', label: 'Suppliers & crops', icon: Sprout, perm: 'modules.view', sectors: AGRI },
  ] },
  { label: 'Risk', items: [
    { to: '/riskmap', label: 'Risk map', icon: MapIcon, perm: 'modules.view', sectors: AGRI },
    { to: '/early-warning', label: 'Early warning', icon: BellRing, perm: 'modules.view', sectors: AGRI },
  ] },
  { label: 'Reports', items: [
    { to: '/filings', label: 'Filings', icon: ShieldCheck, perm: 'modules.view', sectors: AGRI },
    { to: '/disclosure', label: 'Reports & EUDR', icon: ShieldCheck, perm: 'modules.view', sectors: AGRI },
    { to: '/csrd', label: 'Climate report (CSRD)', icon: FileText, perm: 'modules.view', sectors: AGRI },
    { to: '/esrs', label: 'Nature report (ESRS)', icon: Leaf, perm: 'modules.view', sectors: AGRI },
  ] },
  { label: 'Trust', items: [
    { to: '/models', label: 'How we score', icon: FlaskConical, perm: 'modules.view', sectors: AGRI },
    { to: '/foundation', label: 'Where our data comes from', icon: Database, perm: 'modules.view', sectors: AGRI },
  ] },
  // ── shared workflow layer — every sector, sector-scoped data ──
  { label: 'Workflow', items: [
    { to: '/tasks', label: 'Tasks', icon: KanbanSquare, perm: 'modules.view' },
    { to: '/transmission', label: 'Transmission', icon: RadioTower, perm: 'modules.view' },
    { to: '/exceptions', label: 'Control Tower', icon: AlertOctagon, perm: 'modules.view' },
    { to: '/calendar', label: 'Calendar', icon: CalendarDays, perm: 'modules.view' },
    { to: '/reg-changes', label: 'Regulatory changes', icon: GitBranch, perm: 'modules.view' },
    { to: '/data-dictionary', label: 'Data dictionary', icon: Table2, perm: 'modules.view' },
  ] },
  { label: 'Admin', items: [
    // one door for all governance — Approvals / Audit / Users / Roles / Approval-matrix live as tabs inside
    { to: '/admin', label: 'Settings & team', icon: Settings,
      anyPerm: ['admin.users.manage', 'approvals.view', 'admin.audit.view', 'admin.roles.manage', 'admin.approval_policy.manage'] },
  ] },
  { label: 'Help', items: [
    { to: '/docs', label: 'Help & guides', icon: BookOpen, perm: 'modules.view' },
    { to: '/support', label: 'Support', icon: LifeBuoy, perm: 'portal.use' },
  ] },
  { label: 'Platform', items: [
    { to: '/platform', label: 'Tenants', icon: Globe, perm: 'platform.admin' },
  ] },
]

export default function Shell({ children }: { children: ReactNode }) {
  const { profile, logout, viewing, exitViewing } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  // show Back only when there's in-app history to return to (router tracks position in history.state.idx).
  // this hides it on the first page and on detail pages opened in a fresh tab (idx 0), which keep their own link.
  const canGoBack = pathname !== '/' && (window.history.state?.idx ?? 0) > 0
  const sector = profile?.org?.type ?? ''
  // the Horizon front door is a full-bleed globe — it fills the content area beside the nav (no padded main)
  const bleed = pathname === '/'
  return (
    <div className="min-h-screen flex">
      {/* vertical grouped sidebar */}
      <aside className="w-60 shrink-0 sticky top-0 h-screen flex flex-col border-r border-[var(--color-line)] bg-[var(--color-bg-2)]">
        <div className="h-14 px-5 flex items-center gap-2 border-b border-[var(--color-line)]">
          <BrandMark size={24} />
          <span className="display font-semibold text-[15px]">Tel<span className="text-[var(--color-sky)]">lumen</span></span>
          <span className="mono text-[9px] text-[var(--color-faint)] tracking-widest ml-1">{SECTOR_TAG[sector] ?? ''}</span>
        </div>

        <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
          {GROUPS.map((g, gi) => {
            const items = g.items.filter(it =>
              (!it.perm || profile?.permissions?.includes(it.perm)) &&
              (!it.anyPerm || it.anyPerm.some(p => profile?.permissions?.includes(p))) &&
              (!it.sectors || it.sectors.includes(sector)))
            if (items.length === 0) return null
            return (
            <div key={gi}>
              {g.label && <div className="px-2 mb-1.5 mono text-[9px] uppercase tracking-[0.18em] text-[var(--color-faint)]">{g.label}</div>}
              <div className="space-y-0.5">
                {items.map(it => (
                  <NavLink key={it.to} to={it.to} end={it.end} className={({ isActive }) => clsx(
                    'relative flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[14.5px] transition',
                    isActive ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium'
                             : 'text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-panel)]')}>
                    {({ isActive }) => (<>
                      {isActive && <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-[var(--color-sky)]" />}
                      <it.icon size={17} className={isActive ? 'text-[var(--color-sky)]' : ''} />
                      {it.label}
                    </>)}
                  </NavLink>
                ))}
              </div>
            </div>
            )
          })}
        </nav>

        <div className="border-t border-[var(--color-line)] px-4 py-3 flex items-center gap-2">
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[12px] text-[var(--color-ink)] truncate">{profile?.org?.name}</div>
            <div className="text-[10px] text-[var(--color-faint)] mono truncate">{profile?.user?.email}</div>
          </div>
          <button onClick={logout} title="Log out" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] transition shrink-0"><LogOut size={16} /></button>
        </div>
      </aside>

      {/* content */}
      <div className="flex-1 min-w-0">
        {viewing && (
          <div className="sticky top-0 z-30 flex items-center justify-between gap-3 px-8 py-2 text-[12.5px] bg-[color-mix(in_oklab,var(--color-warn)_18%,var(--color-bg))] border-b border-[var(--color-warn)]">
            <span className="text-[var(--color-ink)]">Viewing <b>{viewing.tenant}</b> as a platform operator <span className="text-[var(--color-mute)]">(signed in as {viewing.as} · recorded in their audit log)</span></span>
            <button onClick={exitViewing} className="shrink-0 rounded-lg px-3 py-1 font-medium bg-[var(--color-warn)] text-[#1a1206] hover:opacity-90">Exit to platform</button>
          </div>
        )}
        {bleed ? (
          <div className="relative h-screen overflow-hidden">{children}</div>
        ) : (
          <main className="mx-auto max-w-[1200px] w-full px-8 py-7">
            {canGoBack && (
              <button onClick={() => navigate(-1)}
                className="inline-flex items-center gap-1.5 mb-4 text-[13px] text-[var(--color-mute)] hover:text-[var(--color-sky)] transition">
                <ArrowLeft size={16} /> Back
              </button>
            )}
            {children}
          </main>
        )}
      </div>
    </div>
  )
}
