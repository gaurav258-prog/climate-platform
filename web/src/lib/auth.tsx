import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setToken, getToken } from './api'

export interface Profile {
  user: { id?: string; email?: string; name?: string; role?: string }
  org: { org_id: string; name: string; type: string; country?: string }
  permissions: string[]
  entitlements: string[]
}

export interface Viewing { tenant: string; as: string }

const OP_TOKEN = 'tellumen.optoken'   // the operator's own token, stashed while viewing a tenant
const VIEWING = 'tellumen.viewing'    // {tenant, as} banner info while impersonating

interface AuthState {
  profile: Profile | null
  loading: boolean
  viewing: Viewing | null
  login: (email: string, password: string, otp?: string) => Promise<void>
  logout: () => void
  viewAsTenant: (orgId: string) => Promise<void>
  exitViewing: () => void
}

const Ctx = createContext<AuthState>(null as unknown as AuthState)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState<boolean>(!!getToken())
  const [viewing, setViewing] = useState<Viewing | null>(() => {
    try { const v = localStorage.getItem(VIEWING); return v ? JSON.parse(v) : null } catch { return null }
  })

  useEffect(() => {
    // SSO return leg: the OIDC callback redirects here with the session token in the URL fragment
    // (fragments are never sent to a server or written to logs). Consume it, then clean the URL.
    const m = window.location.hash.match(/sso_token=([^&]+)/)
    if (m) {
      setToken(decodeURIComponent(m[1]))
      window.history.replaceState(null, '', window.location.pathname)
      setLoading(true)
    }
    if (!getToken()) { setLoading(false); return }
    api.get<Profile>('/v1/auth/me')
      .then(setProfile)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string, otp?: string) {
    const data = await api.post<{ access_token: string } & Profile>('/v1/auth/login', { email, password, otp })
    setToken(data.access_token)
    // full reload → the app rehydrates as the NEW user with an empty query cache, so a different org's
    // data (globe/entities/tasks) can never bleed through from the previous session
    window.location.href = '/'
  }

  function logout() {
    setToken(null); localStorage.removeItem(OP_TOKEN); localStorage.removeItem(VIEWING)
    setProfile(null); setViewing(null)
    window.location.href = '/'   // full reload → clears any cached tenant data on the way out
  }

  // platform operator opens a customer tenant's full workspace (audited server-side)
  async function viewAsTenant(orgId: string) {
    const r = await api.post<{ token: string; tenant_name: string; as_user_email: string }>('/v1/ops/impersonate', { org_id: orgId })
    localStorage.setItem(OP_TOKEN, getToken() ?? '')
    localStorage.setItem(VIEWING, JSON.stringify({ tenant: r.tenant_name, as: r.as_user_email }))
    setToken(r.token)
    window.location.href = '/'   // full reload → app rehydrates as the tenant
  }

  function exitViewing() {
    const op = localStorage.getItem(OP_TOKEN)
    if (op) setToken(op)
    localStorage.removeItem(OP_TOKEN); localStorage.removeItem(VIEWING)
    window.location.href = '/platform'
  }

  return <Ctx.Provider value={{ profile, loading, viewing, login, logout, viewAsTenant, exitViewing }}>{children}</Ctx.Provider>
}
