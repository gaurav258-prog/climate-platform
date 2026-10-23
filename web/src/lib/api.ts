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

/** The human message of a refused request, whatever the endpoint's error shape ({error:{message}}, {detail}, {message}). */
export function apiMessage(e: unknown, fallback: string): string {
  if (!(e instanceof ApiError)) return fallback
  const b = e.body as { error?: { message?: string } | string; detail?: { message?: string } | string; message?: string } | string | null
  if (typeof b === 'string') return b || fallback
  const pick = (v: unknown) => (typeof v === 'string' ? v : (v as { message?: string } | undefined)?.message)
  return pick(b?.error) ?? pick(b?.detail) ?? b?.message ?? fallback
}

/** The structured detail behind a refused request's message (core/errors.py: {error: {error, message, detail}}), if any. */
export function apiDetail(e: unknown): { what?: string; why?: string; next?: string } | null {
  if (!(e instanceof ApiError)) return null
  const b = e.body as { error?: { detail?: unknown } } | null
  const d = b && typeof b === 'object' ? b.error?.detail : null
  return d && typeof d === 'object' ? d as { what?: string; why?: string; next?: string } : null
}

// The server's own reason, whichever shape it arrives in ({error: {message}}, {message}, {detail: {message} | string})
// — a person sees why, never just a status code.
function reasonOf(body: unknown): string | null {
  if (typeof body === 'string') return body || null
  if (!body || typeof body !== 'object') return null
  const b = body as Record<string, unknown>
  for (const k of ['error', 'detail']) {
    const v = b[k]
    if (typeof v === 'string' && v) return v
    if (v && typeof v === 'object' && typeof (v as Record<string, unknown>).message === 'string') return (v as Record<string, string>).message
  }
  return typeof b.message === 'string' ? b.message : null
}

export class ApiError extends Error {
  status: number
  body: unknown
  constructor(status: number, body: unknown) {
    super(reasonOf(body) ?? `HTTP ${status}`)
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
export function upload<T>(path: string, file: File, field = 'file', extra?: Record<string, string | undefined>): Promise<T> {
  const fd = new FormData(); fd.append(field, file)
  for (const [k, v] of Object.entries(extra ?? {})) if (v !== undefined && v !== '') fd.append(k, v)   // optional form fields (declared controls, sign-off)
  return api.post<T>(path, fd)
}

// Authenticated file download: fetches with the bearer, streams to a Blob, triggers a browser save.
// A plain <a href> can't carry the JWT, so tenant-scoped .xlsx endpoints need this.
// The name the server gives a file (Content-Disposition: RFC 5987 filename*, else filename).
export function serverFilename(header: string | null): string | null {
  if (!header) return null
  const star = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (star) return decodeURIComponent(star[1])
  const plain = /filename="([^"]+)"/i.exec(header)
  return plain ? plain[1] : null
}

// `filename` omitted: the file keeps the server's name (a regulator's package whose name is part of the format).
export async function download(path: string, filename?: string): Promise<void> {
  const token = getToken()
  const res = await fetch(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) {                                  // the refusal read as request() reads it, never as raw text (E340)
    const text = await res.text()
    const data = text ? safeJson(text) : null
    throw new ApiError(res.status, (data as { detail?: unknown })?.detail ?? data ?? text)
  }
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = filename ?? serverFilename(res.headers.get('Content-Disposition')) ?? 'download'; a.click()
  URL.revokeObjectURL(a.href)
}
