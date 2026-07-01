import { LayoutGrid, BookOpen, LifeBuoy, ShieldCheck, LogOut } from 'lucide-react'

// Top bar: brand + top-level area nav + the logged-in identity. Replaces the old
// demo "Customer" select — who you are now comes from the login session, and the
// areas you see are gated by your permissions.
const AREAS = [
  { id: 'modules', label: 'Modules',       icon: LayoutGrid },
  { id: 'docs',    label: 'Documentation', icon: BookOpen },
  { id: 'portal',  label: 'Service portal', icon: LifeBuoy, perm: 'portal.use' },
  { id: 'admin',   label: 'Admin',         icon: ShieldCheck, adminAny: true },
]

// The Admin area houses user/role/audit management AND the approvals queue, so a
// pure approver (approvals.* but no admin.*) still needs to reach it. AdminPage
// filters the sub-tabs by permission, so each role sees only what it may use.
const ADMIN_PERMS = ['admin.users.manage', 'admin.roles.manage', 'admin.audit.view',
                     'approvals.view', 'approvals.decide']

export default function LineageBar({ auth, area, onArea, onLogout }) {
  const perms = new Set(auth?.permissions || [])
  const canSee = (a) =>
    a.adminAny ? ADMIN_PERMS.some(p => perms.has(p))
    : a.perm ? perms.has(a.perm)
    : true
  const areas = AREAS.filter(canSee)

  const org = auth?.org?.name || '—'
  const role = (auth?.roles || [])[0] || 'user'

  return (
    <header className="flex items-center justify-between gap-4 border-b border-gray-200 bg-white px-5 py-2">
      <div className="flex items-center gap-5">
        <div className="text-[15px] font-semibold tracking-tight text-[#1d1d1f]">
          Climate <span className="text-[#0071e3]">Intelligence</span>
        </div>
        <nav className="hidden items-center gap-1 md:flex">
          {areas.map(a => {
            const on = area === a.id
            const Icon = a.icon
            return (
              <button key={a.id} onClick={() => onArea(a.id)}
                className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[13px] font-medium transition ${
                  on ? 'bg-[#1d1d1f] text-white' : 'text-gray-500 hover:bg-gray-100 hover:text-[#1d1d1f]'}`}>
                <Icon size={14} strokeWidth={1.9} /> {a.label}
              </button>
            )
          })}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden text-right sm:block">
          <div className="text-[12px] font-medium text-[#1d1d1f] leading-tight">{org}</div>
          <div className="text-[11px] text-gray-400 leading-tight">
            {auth?.user?.email} · <span className="capitalize">{role}</span>
          </div>
        </div>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#0071e3]/10 text-[12px] font-semibold text-[#0071e3]">
          {(auth?.user?.full_name || auth?.user?.email || '?').slice(0, 1).toUpperCase()}
        </span>
        <button onClick={onLogout} title="Log out"
          className="flex items-center gap-1 rounded-full border border-gray-200 px-3 py-1.5 text-[12px] font-medium text-gray-600 transition hover:border-gray-300 hover:text-[#1d1d1f]">
          <LogOut size={14} /> <span className="hidden sm:inline">Log out</span>
        </button>
      </div>
    </header>
  )
}
