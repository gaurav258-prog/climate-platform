import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setToken, getToken } from './api'

export interface Profile {
  user: { id?: string; email?: string; name?: string; role?: string }
  org: { org_id: string; name: string; type: string; country?: string }
  permissions: string[]
  entitlements: string[]
}

interface AuthState {
  profile: Profile | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const Ctx = createContext<AuthState>(null as unknown as AuthState)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState<boolean>(!!getToken())

  useEffect(() => {
    if (!getToken()) return
    api.get<Profile>('/v1/auth/me')
      .then(setProfile)
      .catch(() => setToken(null))
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    const data = await api.post<{ access_token: string } & Profile>('/v1/auth/login', { email, password })
    setToken(data.access_token)
    const me = await api.get<Profile>('/v1/auth/me')
    setProfile(me)
  }

  function logout() {
    setToken(null)
    setProfile(null)
  }

  return <Ctx.Provider value={{ profile, loading, login, logout }}>{children}</Ctx.Provider>
}
