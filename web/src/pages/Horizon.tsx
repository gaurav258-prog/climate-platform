import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Play, Pause, Camera, ArrowRight, Grid3x3, X, Maximize2, Minimize2 } from 'lucide-react'
import { api } from '../lib/api'
import HexMap from '../components/HexMap'
import { useAuth } from '../lib/auth'
import { COAST } from '../lib/coastline'

interface GAsset {
  id: string; name: string; kind: string; lat: number; lon: number; region: string
  value_eur: number; hazard: string; traj: Record<string, number>; adaptations?: string[]; eudr_undetermined?: boolean; facets?: { k: string; v: string }[]
}
interface Check { key: string; label: string; ok: boolean; hint: string | null }
interface Kpis { book_value_eur: number; n_assets: number; n_elevated: number; readiness: { passed: number; total: number; checks: Check[] }; volume_at_risk_eur_today: number | null }
interface MyScope { roles: string[]; raised_pending: number }
interface GlobeResp { scenario: string; sector?: string; noun?: string; horizons: string[]; n_assets: number; volume_at_risk_eur_today: number | null; kpis?: Kpis; my_scope?: MyScope; assets: GAsset[] }
interface Task { key: string; title: string; detail: string; severity: string; cta_label: string; cta_href: string; bucket: string; due: string | null }
interface Ent { entity_id: string; name: string; kind: string; n_assets: number }
const SEV_COL: Record<string, string> = { action: 'var(--color-sky)', warning: 'var(--color-warn)', info: 'var(--color-blue)', good: 'var(--color-good)' }

const HY = [2025, 2030, 2050, 2100]           // horizon years ↔ current / 2030 / 2050 / 2100
const HK = ['current', '2030', '2050', '2100']
const D2R = Math.PI / 180
const SUN = (() => { const v = [-0.5, 0.42, 0.76]; const m = Math.hypot(v[0], v[1], v[2]); return v.map(x => x / m) })()
const pretty = (h: string) => h.replace(/_/g, ' ')

// real projected score (0..100) at an arbitrary year, linearly interpolating the golden-source horizons
function scoreAt(a: GAsset, y: number): number {
  const t = a.traj
  if (y <= HY[0]) return t.current
  for (let i = 1; i < 4; i++) if (y <= HY[i]) { const f = (y - HY[i - 1]) / (HY[i] - HY[i - 1]); return t[HK[i - 1]] + (t[HK[i]] - t[HK[i - 1]]) * f }
  return t['2100']
}
function col(l: number): [number, number, number] { return l < 28 ? [207, 232, 255] : l < 50 ? [232, 178, 76] : l < 75 ? [233, 116, 74] : [210, 59, 59] }
function stateName(l: number) { return l < 28 ? 'safe' : l < 50 ? 'elevated' : l < 75 ? 'high' : 'severe' }

function KpiCard({ label, value, tint, onClick }: { label: string; value: string; tint?: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-left rounded-lg border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-3 py-2.5 hover:border-[var(--color-sky)] transition">
      <div className="display text-[19px] leading-none" style={{ color: tint || '#F4EFE6' }}>{value}</div>
      <div className="mono text-[9px] tracking-[0.1em] uppercase text-[var(--color-faint)] mt-1.5">{label}</div>
    </button>
  )
}

export default function Horizon() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const qc = useQueryClient()
  const [resolving, setResolving] = useState(false)
  // drill-down overlay: a KPI ('book'|'elevated'|'readiness'|'scope') or a task
  const [panel, setPanel] = useState<{ kind: string; task?: Task } | null>(null)
  // entity the analyst is working on (an analyst can cover several) — the active reporting entity
  const [entOpen, setEntOpen] = useState(false)
  const [entityId, setEntityId] = useState<string | null>(null)  // null = All entities (whole org)
  // granular H3 grid modal for the selected site
  const [hexOpen, setHexOpen] = useState(false)
  // mobile (<800px): the two rails can't sit side-by-side over the globe, so a segmented control shows
  // one at a time. Ignored at ≥800px, where both rails render as usual.
  const [mobileTab, setMobileTab] = useState<'overview' | 'tasks'>('overview')
  // site detail panel width — user can drag the left edge (any size) or maximize to full window
  const [selW, setSelW] = useState(440)
  const [selMax, setSelMax] = useState(false)
  const startSelResize = (e: React.PointerEvent) => {
    e.preventDefault(); setSelMax(false)
    const move = (ev: PointerEvent) => setSelW(Math.max(320, Math.min(window.innerWidth, window.innerWidth - ev.clientX)))
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }
  const toggleSelMax = () => setSelMax(m => !m)
  const cvRef = useRef<HTMLCanvasElement>(null)
  const yearElRef = useRef<HTMLDivElement>(null)
  const statElRef = useRef<HTMLDivElement>(null)
  const [sel, setSel] = useState<GAsset | null>(null)
  const [beltName, setBeltName] = useState<string | null>(null)
  // start PAUSED at "today" — the year only advances when the user presses play or drags the scrubber
  const [playing, setPlaying] = useState(false)
  // viewYear mirrors the animating year into React so the SELECTED site's live values (score, badge) update
  // as time plays; `target` is the year the scrubber sets — play runs only up to it, then stops.
  const [viewYear, setViewYear] = useState(2025)
  const [targetYear, setTargetYear] = useState(2100)  // the year play animates TO (set by the scrubber)
  const S = useRef({ year: 2025, target: 2100, lon0: -8 * D2R, lat0: 20 * D2R, tLon: -8 * D2R, tLat: 20 * D2R, drag: false, moved: false, px: 0, py: 0, play: false, yearInt: 2025, focus: null as GAsset | null, belt: null as string | null, snap: false })

  const q = useQuery({ queryKey: ['globe', entityId], queryFn: () => api.get<GlobeResp>('/v1/me/globe' + (entityId ? `?entity_id=${entityId}` : '')) })
  const assets = q.data?.assets ?? []
  const kpis = q.data?.kpis
  const myScope = q.data?.my_scope
  // real reporting entities the analyst can scope to (legal entity / fund / client / …)
  const eq = useQuery({ queryKey: ['entities'], queryFn: () => api.get<{ entities: Ent[] }>('/v1/me/entities') })
  const entityList = eq.data?.entities ?? []
  const activeEntity = entityId ? (entityList.find(e => e.entity_id === entityId)?.name ?? '—') : `All of ${profile?.org?.name ?? 'the org'}`
  // sector-aware noun (bank→financed assets, insurer→insured locations, agri→sites & origins, …)
  const noun = q.data?.noun ?? 'assets'
  // "enter operations" lands on the operating surface for this sector: financial books open the Portfolio,
  // the agri workspace opens its cockpit. (The four financial sectors report sector = their org type.)
  const opsHref = ['bank', 'insurer', 'asset_manager', 'reit'].includes(q.data?.sector ?? '') ? '/portfolio' : '/home'
  const nounRef = useRef('assets')
  useEffect(() => { nounRef.current = q.data?.noun ?? 'assets' }, [q.data])
  // "what needs you" — the same real, role-filtered signals as the cockpit, surfaced on the landing
  const tq = useQuery({ queryKey: ['my-tasks', entityId], queryFn: () => api.get<{ tasks: Task[] }>('/v1/me/tasks' + (entityId ? `?entity_id=${entityId}` : '')) })
  const tasks = tq.data?.tasks ?? []

  // region groups (belts) — group real assets by their region/country
  const beltsRef = useRef<Record<string, GAsset[]>>({})
  useEffect(() => {
    const b: Record<string, GAsset[]> = {}
    for (const a of assets) (b[a.region || '—'] = b[a.region || '—'] || []).push(a)
    beltsRef.current = b
  }, [assets])
  const beltMean = (r: string) => { const g = beltsRef.current[r] || []; const la = g.reduce((s, a) => s + a.lat, 0) / g.length; const lo = g.reduce((s, a) => s + a.lon, 0) / g.length; return [la, lo] }

  // open the globe already looking at YOUR assets (their centroid)
  const centeredRef = useRef(false)
  useEffect(() => {
    if (centeredRef.current || assets.length === 0) return
    centeredRef.current = true
    const mLat = assets.reduce((s, a) => s + a.lat, 0) / assets.length
    const mLon = assets.reduce((s, a) => s + a.lon, 0) / assets.length
    S.current.lon0 = S.current.tLon = mLon * D2R
    S.current.lat0 = S.current.tLat = Math.max(-1.1, Math.min(1.1, mLat * D2R))
  }, [assets])

  const openBelt = (r: string) => { const [la, lo] = beltMean(r); S.current.belt = r; S.current.tLon = lo * D2R; S.current.tLat = Math.max(-1.1, Math.min(1.1, la * D2R)); S.current.play = false; setPlaying(false); setBeltName(r) }
  const closeBelt = () => { S.current.belt = null; setBeltName(null) }

  useEffect(() => { S.current.play = playing }, [playing])

  useEffect(() => {
    const cv = cvRef.current!; const ctx = cv.getContext('2d')!
    let raf = 0, W = 0, H = 0, DPR = 1, gx = 0, gy = 0, Rg = 0, tprev = 0
    const resize = () => {
      DPR = Math.min(2, devicePixelRatio || 1); W = cv.clientWidth; H = cv.clientHeight
      cv.width = W * DPR; cv.height = H * DPR; ctx.setTransform(DPR, 0, 0, DPR, 0, 0)
      gx = W * 0.5; gy = H * 0.53
      // size the globe to the VIEWPORT, not the (nav-narrowed) content area, so the left nav never shrinks
      // it — it stays the exact size it was full-screen. Uniform radius → always a true circle, never squeezed.
      Rg = Math.min(window.innerWidth * 0.34, window.innerHeight * 0.40)
    }
    resize(); addEventListener('resize', resize)

    const project = (la: number, lo: number) => {
      const lat = la * D2R, lon = lo * D2R, dl = lon - S.current.lon0, cl = Math.cos(lat), l0 = S.current.lat0
      const Z = Math.sin(l0) * Math.sin(lat) + Math.cos(l0) * cl * Math.cos(dl)
      const X = cl * Math.sin(dl), Y = Math.cos(l0) * Math.sin(lat) - Math.sin(l0) * cl * Math.cos(dl)
      return { x: gx + Rg * X, y: gy - Rg * Y, vis: Z > 0, depth: Z, illum: X * SUN[0] + Y * SUN[1] + Z * SUN[2] }
    }
    // dotted land mask for the night-lights (coarse ellipses; the coastlines are the real geometry)
    const LAND: number[][] = [[-100, 45, 30, 20], [-118, 52, 16, 12], [-75, 50, 20, 15], [-88, 15, 12, 8], [-63, -6, 16, 15], [-64, -34, 11, 17], [-42, 72, 15, 9], [12, 50, 20, 11], [22, 63, 14, 8], [15, 25, 30, 15], [24, -14, 18, 18], [45, 27, 14, 12], [80, 58, 46, 16], [78, 22, 12, 11], [105, 12, 15, 13], [110, 36, 20, 14], [118, -2, 20, 7], [134, -25, 17, 11], [-2, 54, 5, 5], [10, 36, 10, 4]]
    const landPts: number[][] = []
    for (let la = -78; la <= 80; la += 3.4) for (let lo = -178; lo <= 180; lo += 3.6) for (const L of LAND) { const dx = (lo - L[0]) / L[2], dy = (la - L[1]) / L[3]; if (dx * dx + dy * dy < 1) { landPts.push([la, lo]); break } }
    const stars = Array.from({ length: 170 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 1.3, t: Math.random() * 6.28 }))

    let regionRects: { r: string; x0: number; x1: number; y0: number; y1: number }[] = []
    const hit = (mx: number, my: number): GAsset | null => { const pool = S.current.belt ? (beltsRef.current[S.current.belt] || []) : assets; let best = 20, h: GAsset | null = null; for (const a of pool) { const p = project(a.lat, a.lon); if (!p.vis) continue; const d = Math.hypot(p.x - mx, p.y - my); if (d < best) { best = d; h = a } } return h }
    const hitRegion = (mx: number, my: number): string | null => { for (const rr of regionRects) if (mx >= rr.x0 && mx <= rr.x1 && my >= rr.y0 && my <= rr.y1) return rr.r; return null }

    const onDown = (e: PointerEvent) => { if (S.current.focus) return; S.current.drag = true; S.current.moved = false; S.current.px = e.clientX; S.current.py = e.clientY; cv.setPointerCapture(e.pointerId) }
    const onMove = (e: PointerEvent) => {
      if (S.current.drag) { const dx = e.clientX - S.current.px, dy = e.clientY - S.current.py; if (Math.abs(dx) + Math.abs(dy) > 3) S.current.moved = true; S.current.lon0 -= dx * 0.005; S.current.lat0 = Math.max(-1.2, Math.min(1.2, S.current.lat0 + dy * 0.005)); S.current.tLon = S.current.lon0; S.current.tLat = S.current.lat0; S.current.px = e.clientX; S.current.py = e.clientY; return }
      cv.style.cursor = (hit(e.clientX, e.clientY) || hitRegion(e.clientX, e.clientY)) ? 'pointer' : 'grab'
    }
    const onUp = (e: PointerEvent) => { if (!S.current.drag) return; S.current.drag = false; if (S.current.moved) return; const a = hit(e.clientX, e.clientY); if (a) { S.current.focus = a; S.current.play = false; setPlaying(false); setSel(a); return } if (!S.current.belt) { const r = hitRegion(e.clientX, e.clientY); if (r) openBelt(r) } }
    cv.addEventListener('pointerdown', onDown); cv.addEventListener('pointermove', onMove); cv.addEventListener('pointerup', onUp)

    const drawCaption = () => {
      const b = H - 18, MONO = 'ui-monospace,Menlo,monospace', SERIF = 'Georgia,serif'
      const g = ctx.createLinearGradient(0, H - 100, 0, H); g.addColorStop(0, 'rgba(4,6,11,0)'); g.addColorStop(1, 'rgba(4,6,11,0.92)'); ctx.fillStyle = g; ctx.fillRect(0, H - 100, W, 100)
      ctx.textAlign = 'left'; ctx.fillStyle = '#5C6879'; ctx.font = '600 11px ' + MONO; ctx.fillText('TELLUMEN · HORIZON · ' + (profile?.org?.name || ''), 30, b - 44)
      ctx.fillStyle = '#F4EFE6'; ctx.font = '600 30px ' + SERIF; ctx.fillText(String(Math.round(S.current.year)), 30, b - 12)
      let el = 0; for (const a of assets) if (scoreAt(a, S.current.year) >= 50) el++
      ctx.fillStyle = '#8C99AC'; ctx.font = '12px ' + MONO; ctx.fillText(el + ' of ' + assets.length + ' ' + nounRef.current + ' at elevated risk · disorderly 2°C path', 30, b + 4)
      ctx.textAlign = 'right'; ctx.fillStyle = '#8FC0F0'; ctx.font = 'italic 17px ' + SERIF; ctx.fillText("See what's coming.", W - 30, b - 14)
    }

    const draw = (ts: number) => {
      const t = ts * 0.001
      if (!S.current.drag) { S.current.lon0 += (S.current.tLon - S.current.lon0) * 0.09; S.current.lat0 += (S.current.tLat - S.current.lat0) * 0.09 }
      if (S.current.play) { const dt = Math.min(0.05, (ts - tprev) / 1000); S.current.year += dt * 9; if (S.current.year >= S.current.target) { S.current.year = S.current.target; S.current.play = false; setPlaying(false) } }
      // mirror the integer year into React so a selected site's live values re-render as time plays
      const yi = Math.round(S.current.year); if (yi !== S.current.yearInt) { S.current.yearInt = yi; setViewYear(yi) }
      tprev = ts
      const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#05070d'); g.addColorStop(1, '#0a1120'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
      for (const s of stars) { const tw = .5 + .5 * Math.sin(t * 1.5 + s.t); ctx.globalAlpha = .12 + tw * .45; ctx.fillStyle = '#cfe0ff'; ctx.fillRect(s.x * W, s.y * H, s.r, s.r) } ctx.globalAlpha = 1

      // sphere
      const og = ctx.createRadialGradient(gx - Rg * 0.35, gy - Rg * 0.4, Rg * 0.1, gx, gy, Rg); og.addColorStop(0, '#12233a'); og.addColorStop(.55, '#0b1524'); og.addColorStop(1, '#070d17'); ctx.fillStyle = og; ctx.beginPath(); ctx.arc(gx, gy, Rg, 0, 7); ctx.fill()
      ctx.save(); ctx.beginPath(); ctx.arc(gx, gy, Rg, 0, 7); ctx.clip()
      const spx = gx + Rg * SUN[0], spy = gy - Rg * SUN[1], apx = gx - Rg * SUN[0], apy = gy + Rg * SUN[1]
      let dg = ctx.createRadialGradient(spx, spy, 0, spx, spy, Rg * 1.55); dg.addColorStop(0, 'rgba(150,180,215,0.16)'); dg.addColorStop(.5, 'rgba(120,150,190,0.05)'); dg.addColorStop(1, 'rgba(0,0,0,0)'); ctx.fillStyle = dg; ctx.fillRect(gx - Rg, gy - Rg, Rg * 2, Rg * 2)
      let ng = ctx.createRadialGradient(apx, apy, 0, apx, apy, Rg * 1.5); ng.addColorStop(0, 'rgba(2,4,9,0.6)'); ng.addColorStop(.6, 'rgba(2,4,9,0.18)'); ng.addColorStop(1, 'rgba(0,0,0,0)'); ctx.fillStyle = ng; ctx.fillRect(gx - Rg, gy - Rg, Rg * 2, Rg * 2)
      ctx.restore()
      // night city-lights / day faint land
      for (const p of landPts) { const pr = project(p[0], p[1]); if (!pr.vis) continue; if (pr.illum > 0.02) { ctx.globalAlpha = 0.05 + pr.depth * 0.13; ctx.fillStyle = '#43648a'; ctx.beginPath(); ctx.arc(pr.x, pr.y, 0.9, 0, 7); ctx.fill() } else { const tw = .55 + .45 * Math.sin(t * 2 + pr.x * 0.05); ctx.globalAlpha = (0.11 + pr.depth * 0.32) * tw; ctx.fillStyle = '#F5D69A'; ctx.beginPath(); ctx.arc(pr.x, pr.y, 0.85, 0, 7); ctx.fill() } } ctx.globalAlpha = 1
      // coastlines
      ctx.strokeStyle = 'rgba(150,182,214,0.34)'; ctx.lineWidth = 0.75; ctx.lineJoin = 'round'
      for (const ring of COAST) { ctx.beginPath(); let pv = false; for (let i = 0; i < ring.length; i++) { const p = project(ring[i][1], ring[i][0]); if (p.vis) { if (pv) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y); pv = true } else pv = false } ctx.stroke() }
      // atmosphere
      const rim = ctx.createRadialGradient(gx, gy, Rg * 0.96, gx, gy, Rg * 1.09); rim.addColorStop(0, 'rgba(127,178,230,0)'); rim.addColorStop(.55, 'rgba(127,178,230,0.4)'); rim.addColorStop(1, 'rgba(127,178,230,0)'); ctx.beginPath(); ctx.arc(gx, gy, Rg * 1.05, 0, 7); ctx.lineWidth = Rg * 0.09; ctx.strokeStyle = rim; ctx.stroke()

      // region labels (belts) — click to frame a region
      regionRects = []
      if (!S.current.focus) {
        ctx.font = '600 11px ui-monospace,Menlo,monospace'; ctx.textAlign = 'center'
        for (const rn of Object.keys(beltsRef.current)) {
          const g = beltsRef.current[rn]; const mla = g.reduce((s, a) => s + a.lat, 0) / g.length, mlo = g.reduce((s, a) => s + a.lon, 0) / g.length
          const p = project(mla, mlo); if (!p.vis || p.depth < 0.3) continue
          const dimr = S.current.belt && S.current.belt !== rn ? 0.25 : 0.62
          ctx.fillStyle = `rgba(180,196,214,${dimr})`; ctx.fillText(rn.toUpperCase(), p.x, p.y - 16)
          const w = ctx.measureText(rn.toUpperCase()).width; regionRects.push({ r: rn, x0: p.x - w / 2 - 8, x1: p.x + w / 2 + 8, y0: p.y - 26, y1: p.y - 6 })
        }
      }
      // assets — real coordinates, real interpolated risk
      let elevated = 0
      for (const a of assets) {
        const p = project(a.lat, a.lon); const l = scoreAt(a, S.current.year); if (l >= 50) elevated++
        if (!p.vis) continue
        const [r, gg, b] = col(l), flared = l >= 50, sel2 = S.current.focus === a
        let dim = S.current.focus && !sel2 ? 0.16 : 1
        if (!S.current.focus && S.current.belt && a.region !== S.current.belt) dim = 0.2
        const tw = .6 + .4 * Math.sin(t * (flared ? 4 : 1.4) + a.lon)
        const dep = 0.55 + 0.45 * p.depth
        const sz = (2 * (flared ? 1.6 : 1) * (sel2 ? 1.5 : 1)) * dep * (1 + l / 100 * 0.8)
        const al = dep * (0.7 + tw * 0.3) * dim
        const gl = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, sz * 7); gl.addColorStop(0, `rgba(${r},${gg},${b},${al * (flared ? 0.9 : 0.5)})`); gl.addColorStop(1, `rgba(${r},${gg},${b},0)`)
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(p.x, p.y, sz * 7, 0, 7); ctx.fill()
        ctx.fillStyle = `rgba(${Math.min(255, r + 60)},${Math.min(255, gg + 50)},${Math.min(255, b + 50)},${al})`; ctx.beginPath(); ctx.arc(p.x, p.y, sz, 0, 7); ctx.fill()
        if (sel2) { ctx.strokeStyle = `rgba(${r},${gg},${b},${.5 + .3 * tw})`; ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(p.x, p.y, sz + 9 + 2 * tw, 0, 7); ctx.stroke() }
      }
      if (yearElRef.current) yearElRef.current.textContent = String(Math.round(S.current.year))
      if (statElRef.current) statElRef.current.textContent = `${elevated} of ${assets.length} ${nounRef.current} at elevated risk`
      if (S.current.snap) { S.current.snap = false; drawCaption(); try { const a = document.createElement('a'); a.download = 'tellumen-horizon-' + Math.round(S.current.year) + '.png'; a.href = cv.toDataURL('image/png'); a.click() } catch { /* */ } }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', resize); cv.removeEventListener('pointerdown', onDown); cv.removeEventListener('pointermove', onMove); cv.removeEventListener('pointerup', onUp) }
  }, [assets, profile])

  const closeSel = () => { S.current.focus = null; if (S.current.belt) { const [la, lo] = beltMean(S.current.belt); S.current.tLon = lo * D2R; S.current.tLat = Math.max(-1.1, Math.min(1.1, la * D2R)) } setSel(null) }
  const cur = sel ? scoreAt(sel, viewYear) : 0
  // globe-native closure: run the real satellite EUDR determination, then the flag + task clear
  const resolveEudr = async () => {
    setResolving(true)
    try {
      await api.post('/v1/supply/eudr/determine', {})
      await qc.invalidateQueries({ queryKey: ['globe'] })
      await qc.invalidateQueries({ queryKey: ['my-tasks'] })
      closeSel()
    } finally { setResolving(false) }
  }
  // belt aggregate for the banner
  const beltAssets = beltName ? (beltsRef.current[beltName] || []) : []
  const beltElevated = beltAssets.filter(a => scoreAt(a, S.current.year) >= 50).length

  // left-rail / right-rail helpers
  const fmtEur = (v: number) => v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${Math.round(v / 1e3)}k`
  const BUCKETS: [string, string, string][] = [['overdue', 'Overdue', '#D23B3B'], ['this_week', 'This week', '#E8B24C'], ['upcoming', 'Upcoming', '#8FC0F0'], ['open', 'Open · no fixed date', '#5c6879']]
  const openKpi = (k: string) => { S.current.play = false; setPlaying(false); setPanel({ kind: k }) }
  const openTask = (t: Task) => { S.current.play = false; setPlaying(false); setPanel({ kind: 'task', task: t }) }
  // Choose the year to animate TO, then run from today up to it, so you watch the progression arrive.
  const playTo = (y: number) => { S.current.target = y; setTargetYear(y); S.current.year = 2025; S.current.yearInt = 2025; setViewYear(2025); S.current.play = true; setPlaying(true) }
  const togglePlay = () => {
    if (playing) { S.current.play = false; setPlaying(false); return }
    if (S.current.year >= S.current.target) { S.current.year = 2025; S.current.yearInt = 2025; setViewYear(2025) }  // at the end → replay from today
    S.current.play = true; setPlaying(true)
  }
  const displayTasks = tasks
  const topByValue = [...assets].sort((a, b) => b.value_eur - a.value_eur).slice(0, 6)
  const elevated2050 = assets.filter(a => (a.traj['2050'] ?? a.traj.current) >= 50).sort((a, b) => (b.traj['2050'] ?? 0) - (a.traj['2050'] ?? 0))

  return (
    <div className="absolute inset-0 bg-[#04060b] overflow-hidden select-none">
      <canvas ref={cvRef} className="absolute inset-0 w-full h-full cursor-grab" />
      {/* top chrome — brand lives in the nav now; this just labels the front door */}
      <div className="absolute top-7 left-8 pointer-events-none transition-opacity" style={{ opacity: beltName || sel ? 0.1 : 1 }}>
        <span className="mono text-[10px] tracking-[0.26em] text-[var(--color-faint)] uppercase">Horizon · {profile?.org?.name}</span>
      </div>
      {/* region (belt) banner */}
      {beltName && !sel && (
        <div className="absolute top-5 left-8 flex items-center gap-4 z-10">
          <button onClick={closeBelt} className="mono text-[10px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3.5 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">← all regions</button>
          <div>
            <div className="display text-[26px] text-[#F4EFE6] leading-none">{beltName}</div>
            <div className="mono text-[11px] text-[var(--color-mute)] mt-1">{beltAssets.length} {noun} · <b className="text-[#E9744A]">{beltElevated} at elevated risk</b> · disorderly 2°C</div>
          </div>
        </div>
      )}
      <div className="absolute top-6 right-8 text-right pointer-events-none hidden min-[1120px]:block">
        <div className="display italic text-[clamp(15px,1.8vw,20px)] text-[#F4EFE6]">See what's coming.</div>
        <div className="mono text-[9.5px] tracking-[0.2em] text-[var(--color-faint)] uppercase mt-1.5">{profile?.org?.name} · {assets.length} {noun} · real coordinates</div>
      </div>

      {/* mobile-only segmented control — pick which rail to show over the globe (hidden ≥800px) */}
      {!sel && !beltName && !panel && (
        <div className="hidden max-[800px]:flex absolute top-[52px] left-3 right-3 z-20 gap-1 p-1 rounded-full border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur">
          {([['overview', 'Overview'], ['tasks', `Needs you${displayTasks.length ? ` · ${displayTasks.length}` : ''}`]] as const).map(([k, lbl]) => (
            <button key={k} onClick={() => setMobileTab(k)}
              className={`flex-1 rounded-full py-1.5 mono text-[11px] tracking-wide transition ${mobileTab === k ? 'bg-[#17233a] text-[#F4EFE6]' : 'text-[var(--color-mute)]'}`}>{lbl}</button>
          ))}
        </div>
      )}

      {/* LEFT rail — the year, then MY SCOPE + org KPIs (all clickable → drill-down) */}
      {!sel && !beltName && !panel && (
      <div className={`absolute left-8 top-[11%] w-[min(272px,32vw)] max-h-[calc(100vh-130px)] overflow-y-auto flex flex-col gap-2.5 pr-1 max-[800px]:left-3 max-[800px]:right-3 max-[800px]:top-[100px] max-[800px]:bottom-[128px] max-[800px]:w-auto max-[800px]:max-h-none max-[800px]:gap-2.5 ${mobileTab === 'overview' ? '' : 'max-[800px]:hidden'}`}>
        {/* entity selector — the reporting entity the analyst is working on (they can cover several) */}
        <div className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur">
          <button onClick={() => setEntOpen(o => !o)} className="w-full text-left px-3.5 py-2.5 rounded-xl hover:bg-[#0e1728]">
            <div className="flex items-center justify-between gap-2">
              <span className="mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Working on</span>
              <span className="mono text-[10px] text-[var(--color-mute)] shrink-0">{entityList.length ? `${entityList.length} entities ` : ''}{entOpen ? '▴' : '▾'}</span>
            </div>
            <div className="text-[13.5px] text-[#F4EFE6] truncate mt-0.5">{activeEntity}</div>
          </button>
          {entOpen && (
            <div className="border-t border-[var(--color-line)] px-2 py-2 flex flex-col gap-0.5">
              {[{ entity_id: null as string | null, name: `All of ${profile?.org?.name ?? 'the org'}`, kind: 'all', n_assets: assets.length }, ...entityList].map(e => {
                const on = e.entity_id === entityId
                return (
                  <button key={e.entity_id ?? 'all'} onClick={() => { setEntityId(e.entity_id); setEntOpen(false) }}
                    className={`text-left rounded-lg px-2.5 py-2 flex items-center gap-2.5 ${on ? 'bg-[#0e1728]' : 'hover:bg-[#0e1728]'}`}>
                    <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: on ? 'var(--color-sky)' : 'transparent', border: on ? 'none' : '1px solid #3a4a60' }} />
                    <span className="flex-1 min-w-0">
                      <span className={`block text-[14px] truncate ${on ? 'text-[var(--color-sky)]' : 'text-[var(--color-ink)]'}`}>{e.name}</span>
                      <span className="mono text-[10px] text-[var(--color-faint)]">{e.kind === 'all' ? 'whole org' : e.kind.replace('_', ' ')}{e.entity_id ? ` · ${e.n_assets} assets` : ''}</span>
                    </span>
                  </button>
                )
              })}
              <div className="mono text-[10.5px] text-[var(--color-faint)] px-2.5 pt-1.5">picking one scopes the globe & KPIs</div>
            </div>
          )}
        </div>
        <div>
          <div className="mono text-[10px] tracking-[0.28em] text-[var(--color-faint)] uppercase mb-0.5 pointer-events-none">Standing as of</div>
          <div ref={yearElRef} className="display font-semibold text-[clamp(34px,4.4vw,60px)] leading-[.82] text-[#F4EFE6] pointer-events-none" style={{ letterSpacing: '-1px' }}>2025</div>
          <div ref={statElRef} className="mono text-[12px] text-[var(--color-mute)] mt-2 pointer-events-none">— of {assets.length} {noun} at elevated risk</div>
        </div>
        {myScope && (
          <button onClick={() => openKpi('scope')} className="text-left rounded-lg border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-3.5 py-2.5 hover:border-[var(--color-sky)] transition">
            <div className="mono text-[10px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Your scope</div>
            <div className="text-[13.5px] text-[var(--color-ink)] mt-0.5 capitalize">{myScope.roles.join(' · ') || 'viewer'}</div>
            <div className="mono text-[11.5px] text-[var(--color-mute)] mt-0.5">{tasks.length} open action{tasks.length !== 1 ? 's' : ''}{myScope.raised_pending ? ` · ${myScope.raised_pending} you raised` : ''}</div>
          </button>
        )}
        {kpis && (
          <div className="grid grid-cols-2 gap-2">
            <KpiCard label="book value" value={fmtEur(kpis.book_value_eur)} onClick={() => openKpi('book')} />
            <KpiCard label="elevated by 2050" value={`${kpis.n_elevated}/${kpis.n_assets}`} tint="#E9744A" onClick={() => openKpi('elevated')} />
            <KpiCard label="filing readiness" value={`${kpis.readiness.passed}/${kpis.readiness.total}`} tint={kpis.readiness.passed === kpis.readiness.total ? '#5FB98C' : '#E8B24C'} onClick={() => openKpi('readiness')} />
            {kpis.volume_at_risk_eur_today != null
              ? <KpiCard label="€ at risk today" value={fmtEur(kpis.volume_at_risk_eur_today)} tint="#E8B24C" onClick={() => openKpi('elevated')} />
              : <KpiCard label={noun} value={String(kpis.n_assets)} onClick={() => openKpi('book')} />}
          </div>
        )}
        {!kpis && (
          <div className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3 text-[12px] text-[var(--color-mute)] max-w-[300px]">
            {q.isLoading ? 'Loading your book…' : q.isError
              ? 'Could not load your book — your session may have expired. Reload, or sign out and back in.'
              : 'No located assets yet — add your first ones to see them here.'}
          </div>
        )}
      </div>
      )}

      {/* RIGHT rail — WHAT NEEDS YOU, grouped by urgency (severity is the colour within each bucket) */}
      {!sel && !beltName && !panel && (
      <div className={`absolute right-8 top-[12%] w-[min(320px,42vw)] max-h-[calc(100vh-280px)] overflow-y-auto pr-0.5 max-[800px]:left-3 max-[800px]:right-3 max-[800px]:top-[100px] max-[800px]:bottom-[128px] max-[800px]:w-auto max-[800px]:max-h-none ${mobileTab === 'tasks' ? '' : 'max-[800px]:hidden'}`}>
        <div className="mono text-[11px] tracking-[0.2em] uppercase text-[var(--color-faint)] mb-3 max-[800px]:hidden">What needs you</div>
        {displayTasks.length === 0 && (
          <div className="rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3 text-[12px] text-[var(--color-mute)]">
            {tq.isLoading ? 'Loading…' : tq.isError ? 'Could not load your tasks — reload or sign in again.' : 'All clear — nothing needs you right now.'}
          </div>
        )}
        <div className="flex flex-col gap-4">
          {BUCKETS.map(([bk, label, bcol]) => { const ts = displayTasks.filter(t => t.bucket === bk); if (!ts.length) return null; return (
            <div key={bk}>
              <div className="flex items-center gap-2 mb-2">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: bcol }} />
                <span className="mono text-[11px] tracking-[0.16em] uppercase" style={{ color: bcol }}>{label}</span>
                <span className="mono text-[11px] text-[var(--color-faint)]">{ts.length}</span>
              </div>
              <div className="flex flex-col gap-2">
                {ts.map(t => (
                  <button key={t.key} onClick={() => openTask(t)}
                    className="group text-left rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-4 py-3 hover:border-[color:var(--tint)] transition"
                    style={{ ['--tint' as string]: SEV_COL[t.severity] || 'var(--color-sky)' }}>
                    <div className="flex items-center gap-2.5">
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: SEV_COL[t.severity] || 'var(--color-sky)', boxShadow: `0 0 8px ${SEV_COL[t.severity] || 'var(--color-sky)'}` }} />
                      <span className="flex-1 min-w-0 text-[14px] text-[var(--color-ink)] leading-snug">{t.title}</span>
                    </div>
                    {t.due && <div className="mono text-[11.5px] text-[var(--color-faint)] mt-1 ml-[18px]">{t.due}</div>}
                  </button>
                ))}
              </div>
            </div>
          )})}
        </div>
      </div>
      )}

      {/* drill-down overlay — hybrid: facts + quick action here; deep work opens the workspace page */}
      {panel && (
        <div className="absolute top-0 right-0 bottom-0 w-[min(400px,46vw)] z-20 p-8 overflow-y-auto max-[800px]:w-full max-[800px]:p-5 max-[800px]:!bg-[#070b13]"
          style={{ background: 'linear-gradient(270deg,#070b13 60%,#070b13cc 90%,transparent)' }}>
          <button onClick={() => setPanel(null)} className="mono text-[11.5px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3.5 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">← back</button>
          {panel.kind === 'scope' && myScope && (
            <div className="mt-6">
              <div className="mono text-[11.5px] tracking-[0.22em] uppercase text-[var(--color-faint)]">Your scope</div>
              <div className="display text-[30px] text-[#F4EFE6] mt-1.5 capitalize">{myScope.roles.join(' · ') || 'viewer'}</div>
              <div className="text-[14px] text-[var(--color-mute)] mt-3 leading-relaxed">Assets are org-wide — everyone sees the whole book. Your scope is what you can <b className="text-[#F4EFE6]">act on</b>: {tasks.length} open action{tasks.length !== 1 ? 's' : ''} routed to your role{myScope.raised_pending ? `, and ${myScope.raised_pending} approval${myScope.raised_pending !== 1 ? 's' : ''} you raised waiting on a second pair of eyes` : ''}.</div>
              <div className="mono text-[11px] tracking-[0.18em] uppercase text-[var(--color-faint)] mt-6 mb-2">Your open actions</div>
              <div className="flex flex-col gap-2">{tasks.map(t => (
                <button key={t.key} onClick={() => openTask(t)} className="text-left rounded-lg border border-[var(--color-line)] px-3 py-2.5 hover:border-[var(--color-sky)] text-[14px] text-[var(--color-ink)]">{t.title}</button>))}</div>
            </div>
          )}
          {panel.kind === 'readiness' && kpis && (
            <div className="mt-6">
              <div className="mono text-[11.5px] tracking-[0.22em] uppercase text-[var(--color-faint)]">Filing readiness</div>
              <div className="display text-[30px] text-[#F4EFE6] mt-1.5">{kpis.readiness.passed} of {kpis.readiness.total} controls green</div>
              <div className="text-[14px] text-[var(--color-mute)] mt-2 leading-relaxed">The pre-filing checklist — each is a real control, not a score.</div>
              <div className="flex flex-col gap-3 mt-5">{kpis.readiness.checks.map(c => (
                <div key={c.key} className="flex gap-3 items-start">
                  <span className="mt-0.5 shrink-0 text-[15px]" style={{ color: c.ok ? '#5FB98C' : '#E8B24C' }}>{c.ok ? '✓' : '○'}</span>
                  <div><div className="text-[14px] text-[var(--color-ink)] leading-snug">{c.label}</div>{c.hint && <div className="mono text-[11.5px] text-[var(--color-faint)] mt-0.5">{c.hint}</div>}</div>
                </div>))}</div>
              <button onClick={() => nav('/admin')} className="mt-6 w-full inline-flex items-center justify-center gap-2 mono text-[11px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">Open readiness in Admin <ArrowRight size={14} /></button>
            </div>
          )}
          {(panel.kind === 'book' || panel.kind === 'elevated') && kpis && (
            <div className="mt-6">
              <div className="mono text-[11.5px] tracking-[0.22em] uppercase text-[var(--color-faint)]">{panel.kind === 'book' ? 'Book value' : 'Elevated by 2050'}</div>
              <div className="display text-[30px] text-[#F4EFE6] mt-1.5">{panel.kind === 'book' ? fmtEur(kpis.book_value_eur) : `${kpis.n_elevated} of ${kpis.n_assets} ${noun}`}</div>
              <div className="text-[14px] text-[var(--color-mute)] mt-2 leading-relaxed">{panel.kind === 'book' ? `Total value across your ${assets.length} located ${noun}. Top exposures:` : 'Highest projected physical-risk under the disorderly-2°C path at 2050:'}</div>
              <div className="flex flex-col gap-1.5 mt-4">
                {(panel.kind === 'book' ? topByValue : elevated2050).slice(0, 8).map(a => { const l = a.traj['2050'] ?? a.traj.current; const [r, g, b] = col(l); return (
                  <button key={a.id} onClick={() => { setPanel(null); S.current.focus = a; setSel(a) }} className="flex items-center justify-between gap-3 text-left rounded-lg border border-[var(--color-line)] px-3 py-2 hover:border-[var(--color-sky)]">
                    <span className="min-w-0"><span className="block text-[14px] text-[var(--color-ink)] truncate">{a.name}</span><span className="mono text-[11px] text-[var(--color-faint)]">{a.region}</span></span>
                    <span className="mono text-[13px] shrink-0" style={{ color: `rgb(${r},${g},${b})` }}>{panel.kind === 'book' ? fmtEur(a.value_eur) : `${Math.round(l)}/100`}</span>
                  </button>) })}
              </div>
            </div>
          )}
          {panel.kind === 'task' && panel.task && (
            <div className="mt-6">
              <div className="mono text-[11.5px] tracking-[0.22em] uppercase" style={{ color: SEV_COL[panel.task.severity] || 'var(--color-sky)' }}>{panel.task.bucket.replace('_', ' ')}{panel.task.due ? ` · ${panel.task.due}` : ''}</div>
              <div className="display text-[26px] leading-tight text-[#F4EFE6] mt-2">{panel.task.title}</div>
              <div className="text-[14.5px] text-[var(--color-mute)] mt-3 leading-relaxed">{panel.task.detail}</div>
              <button onClick={() => nav(panel.task!.cta_href)} className="mt-6 w-full inline-flex items-center justify-center gap-2 mono text-[13px] text-[#0b1206] bg-[var(--color-sky)] border border-[var(--color-sky)] rounded-full px-5 py-3.5 hover:opacity-90">{panel.task.cta_label} <ArrowRight size={14} /></button>
              <div className="mono text-[11px] text-[var(--color-faint)] mt-3 text-center">opens the workspace to complete it</div>
            </div>
          )}
        </div>
      )}

      {/* selected asset */}
      {sel && (
        <div className="absolute top-0 right-0 bottom-0 z-10 p-8 overflow-y-auto max-[800px]:!w-full max-[800px]:p-5 max-[800px]:!bg-[#070b13]"
          style={{ width: selMax ? '100vw' : selW, maxWidth: '100vw', background: selMax ? '#070b13' : 'linear-gradient(270deg,#070b13 80%,#070b13ee 93%,transparent)' }}>
          {/* drag the left edge to resize */}
          <div onPointerDown={startSelResize} title="drag to resize"
            className="absolute left-0 top-0 bottom-0 w-2 cursor-ew-resize group flex items-center justify-center">
            <div className="w-0.5 h-10 rounded bg-[var(--color-line-2)] group-hover:bg-[var(--color-sky)]" />
          </div>
          <div className="flex items-center justify-between gap-3">
            <button onClick={closeSel} className="mono text-[11.5px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3.5 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">← back</button>
            <button onClick={toggleSelMax} title="expand / restore"
              className="grid place-items-center w-8 h-8 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
              {selMax ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </div>
          <div className="mono text-[11.5px] tracking-[0.22em] uppercase text-[var(--color-faint)] mt-6">{sel.region} · {sel.kind}</div>
          <div className="display text-[34px] leading-tight text-[#F4EFE6] mt-1.5">{sel.name}</div>
          <div className="mono text-[12px] text-[var(--color-faint)] mt-2">◉ {Math.abs(sel.lat).toFixed(1)}°{sel.lat >= 0 ? 'N' : 'S'}, {Math.abs(sel.lon).toFixed(1)}°{sel.lon >= 0 ? 'E' : 'W'}</div>
          {(() => { const [r, g, b] = col(cur); return (
            <div className="inline-flex items-center gap-2 mt-3 mono text-[11px] tracking-wide uppercase px-3 py-1.5 rounded-full"
              style={{ background: `color-mix(in oklab, rgb(${r},${g},${b}) 16%, transparent)`, color: `rgb(${Math.min(255, r + 40)},${Math.min(255, g + 40)},${Math.min(255, b + 40)})` }}>
              <span className="w-2 h-2 rounded-full" style={{ background: `rgb(${r},${g},${b})` }} />{stateName(cur)} · {viewYear}
            </div>) })()}
          <div className="text-[14px] text-[var(--color-mute)] mt-4 leading-[1.9]">
            worst hazard&nbsp;&nbsp;<b className="text-[#F4EFE6]">{pretty(sel.hazard)}</b><br />
            risk score now&nbsp;&nbsp;<b className="text-[#F4EFE6]">{Math.round(cur)}/100</b>
          </div>
          {/* sector-specific key parameters for THIS site — real columns from the sector's own table */}
          {sel.facets && sel.facets.length > 0 && (
            <>
              <div className="mono text-[11px] tracking-[0.18em] uppercase text-[var(--color-faint)] mt-6 mb-2.5">Site parameters</div>
              <div className="grid grid-cols-2 gap-2">
                {sel.facets.map((f, i) => (
                  <div key={i} className="rounded-lg border border-[var(--color-line)] px-3 py-2.5">
                    <div className="text-[17px] text-[#F4EFE6] leading-tight">{f.v}</div>
                    <div className="mono text-[10.5px] tracking-[0.05em] uppercase text-[var(--color-faint)] mt-1">{f.k}</div>
                  </div>
                ))}
              </div>
            </>
          )}
          <div className="mono text-[11px] tracking-[0.18em] uppercase text-[var(--color-faint)] mt-6 mb-2.5">Risk trajectory · golden source</div>
          <div className="flex items-end gap-1.5 h-[70px]">
            {[2025, 2035, 2045, 2055, 2065, 2075, 2085, 2100].map(yy => { const l = scoreAt(sel, yy); const [r, g, b] = col(l); return (
              <div key={yy} className="flex-1 flex flex-col items-center gap-1.5">
                <div className="w-full rounded-t" style={{ height: (8 + l * 0.6) + 'px', background: `rgb(${r},${g},${b})` }} />
                <div className="mono text-[8.5px] text-[#4b5768]">{String(yy).slice(2)}</div>
              </div>) })}
          </div>
          <div className="text-[12.5px] text-[var(--color-faint)] mt-4 leading-relaxed">
            Real physical-risk score under the disorderly-2°C path, interpolated across the golden source's
            current / 2030 / 2050 / 2100 horizons. Carried in your CSRD · ESRS E1 disclosure.
          </div>
          {/* what to do — real adaptation measures for this hazard */}
          {sel.adaptations && sel.adaptations.length > 0 && (
            <div className="mt-5 pt-4 border-t border-[var(--color-line)]">
              <div className="mono text-[11px] tracking-[0.18em] uppercase text-[var(--color-faint)] mb-2.5">What you can do · adaptation</div>
              <ul className="flex flex-col gap-2.5">
                {sel.adaptations.map((a, i) => (
                  <li key={i} className="flex gap-2.5 text-[14px] text-[var(--color-mute)] leading-snug">
                    <span className="text-[var(--color-good)] shrink-0 mt-0.5">→</span>{a}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* globe-native closure — an open compliance action resolved right here */}
          {sel.eudr_undetermined && (
            <div className="mt-5 pt-4 border-t border-[var(--color-line)]">
              <div className="mono text-[11px] tracking-[0.18em] uppercase text-[var(--color-warn)] mb-2">Needs action · EUDR</div>
              <div className="text-[13.5px] text-[var(--color-mute)] leading-relaxed mb-3">This plot is EUDR-covered but has no deforestation-free determination yet — required before you can file.</div>
              <button onClick={resolveEudr} disabled={resolving}
                className="w-full inline-flex items-center justify-center gap-2 mono text-[13px] text-[#0b1206] bg-[var(--color-good)] border border-[var(--color-good)] rounded-full px-5 py-3 hover:opacity-90 disabled:opacity-60">
                {resolving ? 'running satellite determination…' : 'Run EUDR determination'} {!resolving && <ArrowRight size={14} />}
              </button>
            </div>
          )}
          {/* granular drill — the H3 res-8 grid + basemap under this exact location */}
          <button onClick={() => setHexOpen(true)}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 mono text-[13px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
            <Grid3x3 size={14} /> View granular grid (H3 · ~0.7 km)</button>
          {/* deeper drill — the full per-site record (agri has a dedicated detail page); others open the workspace */}
          <button onClick={() => nav((sel.kind === 'plot' || sel.kind === 'site') ? `/detail/${sel.kind}/${sel.id}` : '/home')}
            className="mt-4 w-full inline-flex items-center justify-center gap-2 mono text-[13px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
            {(sel.kind === 'plot' || sel.kind === 'site') ? 'Open full site record' : 'Open in workspace'} <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* controls */}
      <button onClick={() => (S.current.snap = true)} className="absolute right-8 bottom-[136px] inline-flex items-center gap-2 mono text-[10.5px] text-[var(--color-mute)] bg-[#0b121e] border border-[#223046] rounded-full px-4 py-2.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] max-[800px]:hidden"><Camera size={13} /> save snapshot</button>
      <button onClick={() => nav(opsHref)} className="absolute right-8 bottom-[84px] inline-flex items-center gap-2 mono text-[11px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] max-[800px]:right-3 max-[800px]:bottom-[78px] max-[800px]:py-2.5">enter operations <ArrowRight size={14} /></button>

      <div className="absolute left-0 right-0 bottom-0 px-8 pb-6 pt-5" style={{ background: 'linear-gradient(0deg,#04060bE6 30%,transparent)' }}>
        <div className="flex items-center gap-4 max-w-[1200px] mx-auto">
          <button onClick={togglePlay} title={playing ? 'Pause' : `Play to ${targetYear}`}
            className="w-11 h-11 shrink-0 rounded-full border border-[#2a3a50] bg-[#0e1626] grid place-items-center text-[#F4EFE6] hover:border-[var(--color-sky)]">
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          {/* the thumb tracks the year (moves during play); dragging is pure manual scrub — it does NOT
              change the play target, so you can inspect any year without losing your target */}
          <input type="range" min={2025} max={2100} step={1} value={Math.round(viewYear)}
            onChange={e => { const y = +e.target.value; S.current.year = y; S.current.yearInt = y; S.current.play = false; setPlaying(false); setViewYear(y) }}
            className="flex-1 min-w-0 accent-[var(--color-sky)] cursor-pointer" />
          {/* choose the year to play TO — click runs the globe from today up to it */}
          <div className="flex items-center gap-1 shrink-0">
            <span className="mono text-[10px] text-[var(--color-faint)] mr-0.5 max-[560px]:hidden">play to</span>
            {[2030, 2050, 2100].map(y => (
              <button key={y} onClick={() => playTo(y)}
                className={`mono text-[11px] px-2 py-1 rounded-md border transition ${targetYear === y ? 'border-[var(--color-sky)] text-[var(--color-sky)] bg-[#0e1626]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>{y}</button>
            ))}
          </div>
          <div className="mono text-[12px] text-[var(--color-ink)] shrink-0 tabular-nums w-11 text-right">{Math.round(viewYear)}</div>
        </div>
      </div>

      {/* granular H3 grid modal — the drill-down beneath the overview globe */}
      {hexOpen && sel && (
        <div className="fixed inset-0 z-30 grid place-items-center bg-[#04060bcc] backdrop-blur-sm p-6" onClick={() => setHexOpen(false)}>
          <div className="relative w-[min(760px,92vw)] h-[min(560px,82vh)] rounded-2xl overflow-hidden border border-[var(--color-line-2)] bg-[#070b13]" onClick={e => e.stopPropagation()}>
            <div className="absolute top-0 left-0 right-0 z-10 flex items-center justify-between px-5 py-3 bg-[#070b13cc] backdrop-blur border-b border-[var(--color-line)]">
              <div>
                <div className="mono text-[10px] tracking-[0.2em] uppercase text-[var(--color-faint)]">Granular grid · {sel.region} · {sel.kind}</div>
                <div className="display text-[18px] text-[#F4EFE6] leading-tight">{sel.name}</div>
              </div>
              <button onClick={() => setHexOpen(false)} className="grid place-items-center w-8 h-8 rounded-full border border-[var(--color-line-2)] text-[var(--color-mute)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><X size={15} /></button>
            </div>
            <div className="absolute inset-0 pt-[58px]">
              <HexMap lat={sel.lat} lon={sel.lon} assets={assets} selectedId={sel.id}
                scenario={q.data?.scenario}
                horizon={viewYear <= 2027 ? 'current' : viewYear <= 2040 ? '2030' : viewYear <= 2075 ? '2050' : '2100'} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
