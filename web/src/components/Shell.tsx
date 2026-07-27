import { type ReactNode } from 'react'
import { NavLink } from 'react-router-dom'
import { LogOut } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../lib/auth'
import { BrandMark } from './ui'

const TABS = [
  { to: '/disclosure', label: 'Disclosure & EUDR' },
  { to: '/cogs', label: 'COGS-at-risk' },
  { to: '/sourcing', label: 'Sourcing book' },
  { to: '/riskmap', label: 'Risk map' },
  { to: '/early-warning', label: 'Early warning' },
  { to: '/models', label: 'Models & validation' },
  { to: '/foundation', label: 'Data foundation' },
]

export default function Shell({ children }: { children: ReactNode }) {
  const { profile, logout } = useAuth()
  return (
    <div className="min-h-screen flex flex-col">
      {/* top bar */}
      <header className="sticky top-0 z-20 backdrop-blur bg-[color-mix(in_oklab,var(--color-bg)_82%,transparent)] border-b border-[var(--color-line)]">
        <div className="mx-auto max-w-[1200px] px-6 h-14 flex items-center gap-3">
          <BrandMark size={26} />
          <span className="display font-semibold text-[15px]">Tel<span className="text-[var(--color-sky)]">lumen</span></span>
          <span className="mono text-[10px] text-[var(--color-faint)] tracking-widest ml-1 hidden sm:inline">AGRICULTURE</span>
          <div className="ml-auto flex items-center gap-4">
            <div className="text-right leading-tight hidden sm:block">
              <div className="text-[12px] text-[var(--color-ink)]">{profile?.org?.name}</div>
              <div className="text-[10px] text-[var(--color-faint)] mono">{profile?.user?.email}</div>
            </div>
            <button onClick={logout} title="Log out"
              className="text-[var(--color-faint)] hover:text-[var(--color-bad)] transition"><LogOut size={18} /></button>
          </div>
        </div>
        {/* sharp tab strip */}
        <nav className="mx-auto max-w-[1200px] px-4 flex gap-1 overflow-x-auto">
          {TABS.map(t => (
            <NavLink key={t.to} to={t.to} className={({ isActive }) => clsx(
              'relative whitespace-nowrap px-3 py-2.5 text-[13px] transition',
              isActive ? 'text-[var(--color-ink)]' : 'text-[var(--color-mute)] hover:text-[var(--color-ink)]')}>
              {({ isActive }) => (<>
                {t.label}
                {isActive && <span className="absolute left-2 right-2 -bottom-px h-0.5 rounded-full bg-[var(--color-sky)]" />}
              </>)}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="flex-1 mx-auto max-w-[1200px] w-full px-6 py-7">{children}</main>
    </div>
  )
}
