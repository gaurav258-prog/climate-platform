// Thin fetch wrapper against the existing FastAPI. JWT bearer from localStorage.
const TOKEN_KEY = 'tellumen.token'
const REFRESH_KEY = 'tellumen.refresh'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}
export function setRefreshToken(t: string | null) {
  if (t) localStorage.setItem(REFRESH_KEY, t)
  else localStorage.removeItem(REFRESH_KEY)
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(typeof body === 'string' ? body : `HTTP ${status}`)
    this.status = status
    this.body = body
  }
}

async function tryRefresh(): Promise<boolean> {
  const rt = getRefreshToken()
  if (!rt) return false
  try {
    const res = await fetch('/v1/auth/refresh', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: rt }),
    })
    if (!res.ok) { setToken(null); setRefreshToken(null); return false }
    const d = await res.json()
    setToken(d.access_token); setRefreshToken(d.refresh_token)
    return true
  } catch { return false }
}

async function request<T>(method: string, path: string, body?: unknown, _retried = false): Promise<T> {
  const token = getToken()
  // FormData must be sent as multipart with a browser-set boundary — never JSON-stringified, or the file is
  // destroyed. Detecting it here means api.post(path, formData) works for every uploader (bank & agri alike).
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData
  const res = await fetch(path, {
    method,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body),
  })
  // access token expired/revoked → rotate the refresh token once and retry transparently
  if (res.status === 401 && token && !_retried && !path.includes('/v1/auth/')) {
    if (await tryRefresh()) return request<T>(method, path, body, true)
  }
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) throw new ApiError(res.status, (data as { detail?: unknown })?.detail ?? data ?? text)
  return data as T
}

function safeJson(t: string) {
  try { return JSON.parse(t) } catch { return t }
}

export const api = {
  get: <T,>(p: string) => request<T>('GET', p),
  post: <T,>(p: string, b?: unknown) => request<T>('POST', p, b),
  put: <T,>(p: string, b?: unknown) => request<T>('PUT', p, b),
  patch: <T,>(p: string, b?: unknown) => request<T>('PATCH', p, b),
  del: <T,>(p: string) => request<T>('DELETE', p),
}

// Typed convenience for a single-file multipart POST. Builds the FormData and goes through the shared
// request() transport (which now handles FormData correctly), so there is ONE upload path, not a parallel one.
export function upload<T>(path: string, file: File, field = 'file'): Promise<T> {
  const fd = new FormData(); fd.append(field, file)
  return api.post<T>(path, fd)
}

// Authenticated file download: fetches with the bearer, streams to a Blob, triggers a browser save.
// A plain <a href> can't carry the JWT, so tenant-scoped .xlsx endpoints need this.
export async function download(path: string, filename: string): Promise<void> {
  const token = getToken()
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new ApiError(res.status, await res.text())
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = filename; a.click()
  URL.revokeObjectURL(a.href)
}
