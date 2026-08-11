import { type ReactNode, useState } from 'react'
import { NavLink, useNavigate, useLocation } from 'react-router-dom'
import { Home, Building2, Sprout, Map as MapIcon, BellRing, ShieldCheck, FileText, FlaskConical, Database, LogOut, Settings, Globe, ArrowLeft, Leaf, Landmark, LifeBuoy, BookOpen, KanbanSquare, AlertOctagon, CalendarDays, Gauge, GitBranch, Table2, RadioTower, Layers, Sun, Moon, LineChart, Crosshair, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { useResizableWidth } from '../lib/resizable'
import { BrandMark } from './ui'

// sector = organizations.type. The agri workspace (manufacturer) and the four financial verticals see
// different operating surfaces behind the shared globe. `sectors` gates an item to specific org types
// (undefined = every sector). This keeps a bank out of the Sourcing/EUDR pages, and agri out of Portfolio.
const AGRI = ['manufacturer']
const FIN = ['bank', 'insurer', 'asset_manager', 'reit']
const SECTOR_TAG: Record<string, string> = { manufacturer: 'AGRI', bank: 'BANK', insurer: 'INSURER', asset_manager: 'ASSET MGMT', reit: 'REIT' }

type Item = { to: string; label: string; icon: typeof Home; end?: boolean; perm?: string; anyPerm?: string[]; sectors?: string[] }
// The sidebar reads as the operational loop the platform runs: Sense → Assess → Decide → Disclose →
// Operate, then Set up. `flow` groups are the numbered stages; each carries one identifying stage hue
// (`color`, a CSS var) used on its header dot/label and on the active item's accent — so any page
// announces which stage of the loop it belongs to. Items stay sector-scoped (a bank never sees the agri
// pages), so the same six-stage spine shapes both the financial and agriculture workspaces.
type Group = { label: string | null; color?: string; flow?: boolean; items: Item[] }
const GROUPS: Group[] = [
  { label: 'Sense', color: 'var(--stage-sense)', flow: true, items: [
    { to: '/', label: 'Horizon', icon: Globe, end: true, perm: 'modules.view' },
    { to: '/home', label: 'Home', icon: Home, end: true, perm: 'modules.view', sectors: AGRI },
    { to: '/portfolio', label: 'Portfolio', icon: Landmark, perm: 'modules.view', sectors: FIN },
    { to: '/data', label: 'Data', icon: Database, perm: 'modules.view', sectors: FIN },
    { to: '/operations', label: 'Our sites', icon: Building2, perm: 'modules.view', sectors: AGRI },
    { to: '/sourcing', label: 'Suppliers & crops', icon: Sprout, perm: 'modules.view', sectors: AGRI },
    { to: '/riskmap', label: 'Risk map', icon: MapIcon, perm: 'modules.view', sectors: AGRI },
    { to: '/early-warning', label: 'Early warning', icon: BellRing, perm: 'modules.view', sectors: AGRI },
  ] },
  { label: 'Assess', color: 'var(--stage-assess)', flow: true, items: [
    { to: '/kri', label: 'KRI dashboard', icon: Gauge, perm: 'modules.view' },
    { to: '/analytics', label: 'Analytics', icon: LineChart, perm: 'modules.view', sectors: ['bank', 'asset_manager', 'reit'] },
    { to: '/models', label: 'How we score', icon: FlaskConical, perm: 'modules.view', sectors: AGRI },
  ] },
  { label: 'Decide', color: 'var(--stage-decide)', flow: true, items: [
    { to: '/decisions', label: 'Decisions', icon: Crosshair, perm: 'modules.view', sectors: FIN },
  ] },
  { label: 'Disclose', color: 'var(--stage-disclose)', flow: true, items: [
    { to: '/funds', label: 'Funds', icon: Layers, perm: 'modules.view', sectors: ['asset_manager'] },
    { to: '/compliance', label: 'Reports & filings', icon: ShieldCheck, perm: 'modules.view', sectors: FIN },
    { to: '/filings', label: 'Filings', icon: ShieldCheck, perm: 'modules.view', sectors: AGRI },
    { to: '/disclosure', label: 'Reports & EUDR', icon: FileText, perm: 'modules.view', sectors: AGRI },
    { to: '/csrd', label: 'Climate report (CSRD)', icon: FileText, perm: 'modules.view', sectors: AGRI },
    { to: '/esrs', label: 'Nature report (ESRS)', icon: Leaf, perm: 'modules.view', sectors: AGRI },
    { to: '/oversight', label: 'Supervisory view', icon: ShieldCheck, perm: 'modules.view' },
  ] },
  { label: 'Operate', color: 'var(--stage-operate)', flow: true, items: [
    { to: '/tasks', label: 'Tasks', icon: KanbanSquare, perm: 'modules.view' },
    { to: '/exceptions', label: 'Control Tower', icon: AlertOctagon, perm: 'modules.view' },
    { to: '/calendar', label: 'Calendar', icon: CalendarDays, perm: 'modules.view' },
    { to: '/transmission', label: 'Transmission', icon: RadioTower, perm: 'modules.view' },
    { to: '/reg-changes', label: 'Regulatory changes', icon: GitBranch, perm: 'modules.view' },
  ] },
  { label: 'Set up', color: 'var(--stage-setup)', items: [
    { to: '/data-dictionary', label: 'Data dictionary', icon: Table2, perm: 'modules.view' },
    { to: '/foundation', label: 'Where our data comes from', icon: Database, perm: 'modules.view', sectors: AGRI },
    // one door for all governance — Approvals / Audit / Users / Roles / Approval-matrix live as tabs inside
    { to: '/admin', label: 'Settings & team', icon: Settings,
      anyPerm: ['admin.users.manage', 'approvals.view', 'admin.audit.view', 'admin.roles.manage', 'admin.approval_policy.manage'] },
    { to: '/docs', label: 'Help & guides', icon: BookOpen, perm: 'modules.view' },
    { to: '/support', label: 'Support', icon: LifeBuoy, perm: 'portal.use' },
  ] },
  { label: 'Platform', color: 'var(--stage-setup)', items: [
    { to: '/platform', label: 'Tenants', icon: Globe, perm: 'platform.admin' },
  ] },
]

// route → its stage hue, so a page can accent its own header/sections with the same colour as its nav
// stage (the <main> sets --stage; the shared Eyebrow + section rules read it). Detail routes that aren't
// in the nav resolve by their base segment; anything unmapped falls back to the neutral blue.
const STAGE_BY_PATH: Record<string, string> = {}
for (const g of GROUPS) for (const it of g.items) if (g.color) STAGE_BY_PATH[it.to] = g.color
// detail routes opened from a stage surface inherit that stage's hue
const STAGE_BY_BASE: Record<string, string> = {
  '/asset': 'var(--stage-sense)', '/commodity': 'var(--stage-sense)', '/detail': 'var(--stage-sense)',
  '/issuer': 'var(--stage-disclose)', '/fund': 'var(--stage-disclose)',
}
function stageColorFor(pathname: string): string {
  if (STAGE_BY_PATH[pathname]) return STAGE_BY_PATH[pathname]
  const base = '/' + (pathname.split('/')[1] || '')
  return STAGE_BY_PATH[base] ?? STAGE_BY_BASE[base] ?? 'var(--color-blue)'
}

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
  // the current page's operational-flow stage hue — exposed as --stage so the shared Eyebrow and any
  // page section can accent itself to match its nav stage (see stageColorFor / the Eyebrow in ui.tsx)
  const stage = stageColorFor(pathname)
  // light is the default; the toggle flips data-theme on <html> and persists it (init runs in index.html)
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  const applyTheme = (next: 'light' | 'dark') => {
    document.documentElement.dataset.theme = next
    localStorage.setItem('tellumen.theme', next)
    setDark(next === 'dark')
  }
  // the nav is drag-to-resize (right edge) and collapses to an icon rail — both persisted, so the user's
  // chosen layout sticks across sessions. Double-click the resize handle to reset to the default width.
  const { width: navW, setWidth: setNavW, startResize } = useResizableWidth('tellumen.navw', 240, 194, 420)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('tellumen.navcollapsed') === '1')
  const toggleCollapse = () => setCollapsed(c => { localStorage.setItem('tellumen.navcollapsed', c ? '0' : '1'); return !c })
  const RAIL = 68
  const asideW = collapsed ? RAIL : navW
  return (
    <div className="min-h-screen flex">
      {/* vertical grouped sidebar — drag the right edge to resize, or collapse to an icon rail (both persisted) */}
      <aside style={{ width: asideW }} className="shrink-0 sticky top-0 h-screen flex flex-col border-r border-[var(--color-line)] bg-[var(--color-bg-2)] relative">
        <div className={clsx('h-14 flex items-center border-b border-[var(--color-line)]', collapsed ? 'justify-center px-0' : 'px-5 gap-2')}>
          <BrandMark size={24} />
          {!collapsed && <>
            <span className="display font-semibold text-[15px]">Tel<span className="text-[var(--color-sky)]">lumen</span></span>
            <span className="mono text-[9px] text-[var(--color-faint)] tracking-widest ml-1">{SECTOR_TAG[sector] ?? ''}</span>
            <button onClick={toggleCollapse} title="Collapse sidebar" className="ml-auto text-[var(--color-faint)] hover:text-[var(--color-ink)] transition"><PanelLeftClose size={16} /></button>
          </>}
        </div>

        <nav className={clsx('flex-1 overflow-y-auto overflow-x-hidden py-4 space-y-5', collapsed ? 'px-2' : 'px-3')}>
          {(() => {
            let stageNo = 0  // number only the operational-flow stages, contiguously, after sector filtering
            return GROUPS.map((g, gi) => {
              const items = g.items.filter(it =>
                (!it.perm || profile?.permissions?.includes(it.perm)) &&
                (!it.anyPerm || it.anyPerm.some(p => profile?.permissions?.includes(p))) &&
                (!it.sectors || it.sectors.includes(sector)))
              if (items.length === 0) return null
              const hue = g.color ?? 'var(--color-sky)'
              const n = g.flow ? ++stageNo : null
              return (
              <div key={gi}>
                {g.label && (collapsed
                  ? <div className="flex justify-center mb-1.5" title={g.label}><span className="w-1.5 h-1.5 rounded-full" style={{ background: hue }} /></div>
                  : <div className="px-2 mb-1.5 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: hue }} />
                      <span className="mono text-[9px] uppercase tracking-[0.18em]" style={{ color: hue }}>
                        {n != null && <span className="tabular-nums">{n} · </span>}{g.label}
                      </span>
                    </div>
                )}
                <div className="space-y-0.5">
                  {items.map(it => (
                    <NavLink key={it.to} to={it.to} end={it.end} title={collapsed ? it.label : undefined} className={({ isActive }) => clsx(
                      'relative flex items-center rounded-lg text-[14.5px] transition',
                      collapsed ? 'justify-center py-2.5' : 'gap-2.5 px-2.5 py-2.5',
                      isActive ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium'
                               : 'text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-panel)]')}>
                      {({ isActive }) => (<>
                        {isActive && <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full" style={{ background: hue }} />}
                        <it.icon size={17} className="shrink-0" style={isActive ? { color: hue } : undefined} />
                        {!collapsed && <span className="truncate">{it.label}</span>}
                      </>)}
                    </NavLink>
                  ))}
                </div>
              </div>
              )
            })
          })()}
        </nav>

        <div className={clsx('border-t border-[var(--color-line)] py-3 space-y-2.5', collapsed ? 'px-2' : 'px-4')}>
          {collapsed ? (
            <div className="flex flex-col items-center gap-2">
              <button onClick={toggleCollapse} title="Expand sidebar" className="text-[var(--color-faint)] hover:text-[var(--color-ink)] transition"><PanelLeftOpen size={17} /></button>
              <button onClick={() => applyTheme(dark ? 'light' : 'dark')} title={dark ? 'Switch to light' : 'Switch to dark'} className="text-[var(--color-faint)] hover:text-[var(--color-ink)] transition">{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
              <button onClick={logout} title="Log out" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] transition"><LogOut size={16} /></button>
            </div>
          ) : (<>
            {/* theme toggle — a clearly-labelled segmented control */}
            <div className="flex items-center gap-1 p-1 rounded-lg border border-[var(--color-line-2)]">
              <button onClick={() => applyTheme('light')} title="Light theme"
                className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11.5px] transition ${!dark ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>
                <Sun size={13} /> Light
              </button>
              <button onClick={() => applyTheme('dark')} title="Dark theme"
                className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11.5px] transition ${dark ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>
                <Moon size={13} /> Dark
              </button>
            </div>
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1 leading-tight">
                <div className="text-[12px] text-[var(--color-ink)] truncate">{profile?.org?.name}</div>
                <div className="text-[10px] text-[var(--color-faint)] mono truncate">{profile?.user?.email}</div>
              </div>
              <button onClick={logout} title="Log out" className="text-[var(--color-faint)] hover:text-[var(--color-bad)] transition shrink-0"><LogOut size={16} /></button>
            </div>
          </>)}
        </div>

        {/* drag-to-resize handle on the right edge (hidden when collapsed); double-click resets to default */}
        {!collapsed && (
          <div onMouseDown={startResize} onTouchStart={startResize} onDoubleClick={() => setNavW(240)}
            title="Drag to resize · double-click to reset"
            className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-[color-mix(in_oklab,var(--color-sky)_45%,transparent)] active:bg-[var(--color-sky)] transition z-20" />
        )}
      </aside>

      {/* content — --stage carries the current page's flow-stage hue to the shared Eyebrow + page sections */}
      <div className="flex-1 min-w-0" style={{ '--stage': stage } as React.CSSProperties}>
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
