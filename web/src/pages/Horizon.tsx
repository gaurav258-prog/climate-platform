import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Play, Pause, Camera, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { COAST } from '../lib/coastline'

interface GAsset {
  id: string; name: string; kind: string; lat: number; lon: number; region: string
  value_eur: number; hazard: string; traj: Record<string, number>; adaptations?: string[]
}
interface GlobeResp { scenario: string; horizons: string[]; n_assets: number; volume_at_risk_eur_today: number | null; assets: GAsset[] }
interface Task { key: string; title: string; detail: string; severity: string; cta_label: string; cta_href: string }
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

export default function Horizon() {
  const nav = useNavigate()
  const { profile } = useAuth()
  const cvRef = useRef<HTMLCanvasElement>(null)
  const yearElRef = useRef<HTMLDivElement>(null)
  const statElRef = useRef<HTMLDivElement>(null)
  const [sel, setSel] = useState<GAsset | null>(null)
  const [beltName, setBeltName] = useState<string | null>(null)
  const [playing, setPlaying] = useState(true)
  const S = useRef({ year: 2025, lon0: -8 * D2R, lat0: 20 * D2R, tLon: -8 * D2R, tLat: 20 * D2R, drag: false, moved: false, px: 0, py: 0, play: true, focus: null as GAsset | null, belt: null as string | null, snap: false })

  const q = useQuery({ queryKey: ['globe'], queryFn: () => api.get<GlobeResp>('/v1/me/globe') })
  const assets = q.data?.assets ?? []
  const euroToday = q.data?.volume_at_risk_eur_today
  // "what needs you" — the same real, role-filtered signals as the cockpit, surfaced on the landing
  const tq = useQuery({ queryKey: ['my-tasks'], queryFn: () => api.get<{ tasks: Task[] }>('/v1/me/tasks') })
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
    const resize = () => { DPR = Math.min(2, devicePixelRatio || 1); W = cv.clientWidth; H = cv.clientHeight; cv.width = W * DPR; cv.height = H * DPR; ctx.setTransform(DPR, 0, 0, DPR, 0, 0); gx = W * 0.5; gy = H * 0.52; Rg = Math.min(W * 0.42, H * 0.46) }
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
      ctx.fillStyle = '#8C99AC'; ctx.font = '12px ' + MONO; ctx.fillText(el + ' of ' + assets.length + ' assets at elevated risk · disorderly 2°C path', 30, b + 4)
      ctx.textAlign = 'right'; ctx.fillStyle = '#8FC0F0'; ctx.font = 'italic 17px ' + SERIF; ctx.fillText("See what's coming.", W - 30, b - 14)
    }

    const draw = (ts: number) => {
      const t = ts * 0.001
      if (!S.current.drag) { S.current.lon0 += (S.current.tLon - S.current.lon0) * 0.09; S.current.lat0 += (S.current.tLat - S.current.lat0) * 0.09 }
      if (S.current.play) { const dt = Math.min(0.05, (ts - tprev) / 1000); S.current.year += dt * 9; if (S.current.year >= 2100) { S.current.year = 2100; S.current.play = false; setPlaying(false) } }
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
      if (statElRef.current) statElRef.current.textContent = `${elevated} of ${assets.length} assets at elevated risk`
      if (S.current.snap) { S.current.snap = false; drawCaption(); try { const a = document.createElement('a'); a.download = 'tellumen-horizon-' + Math.round(S.current.year) + '.png'; a.href = cv.toDataURL('image/png'); a.click() } catch { /* */ } }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', resize); cv.removeEventListener('pointerdown', onDown); cv.removeEventListener('pointermove', onMove); cv.removeEventListener('pointerup', onUp) }
  }, [assets, profile])

  const closeSel = () => { S.current.focus = null; if (S.current.belt) { const [la, lo] = beltMean(S.current.belt); S.current.tLon = lo * D2R; S.current.tLat = Math.max(-1.1, Math.min(1.1, la * D2R)) } setSel(null) }
  const cur = sel ? scoreAt(sel, S.current.year) : 0
  // belt aggregate for the banner
  const beltAssets = beltName ? (beltsRef.current[beltName] || []) : []
  const beltElevated = beltAssets.filter(a => scoreAt(a, S.current.year) >= 50).length

  return (
    <div className="fixed inset-0 bg-[#04060b] overflow-hidden select-none">
      <canvas ref={cvRef} className="absolute inset-0 w-full h-full cursor-grab" />
      {/* top chrome */}
      <div className="absolute top-6 left-8 flex items-center gap-3 pointer-events-none transition-opacity" style={{ opacity: beltName || sel ? 0.1 : 1 }}>
        <div className="display text-[19px]">Tel<span className="text-[var(--color-sky)] italic">lumen</span></div>
        <span className="mono text-[9px] tracking-[0.26em] text-[var(--color-faint)] uppercase">Horizon</span>
      </div>
      {/* region (belt) banner */}
      {beltName && !sel && (
        <div className="absolute top-5 left-8 flex items-center gap-4 z-10">
          <button onClick={closeBelt} className="mono text-[10px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3.5 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">← all regions</button>
          <div>
            <div className="display text-[26px] text-[#F4EFE6] leading-none">{beltName}</div>
            <div className="mono text-[11px] text-[var(--color-mute)] mt-1">{beltAssets.length} sites · <b className="text-[#E9744A]">{beltElevated} at elevated risk</b> · disorderly 2°C</div>
          </div>
        </div>
      )}
      <div className="absolute top-6 right-8 text-right pointer-events-none">
        <div className="display italic text-[clamp(15px,1.8vw,20px)] text-[#F4EFE6]">See what's coming.</div>
        <div className="mono text-[9.5px] tracking-[0.2em] text-[var(--color-faint)] uppercase mt-1.5">{profile?.org?.name} · {assets.length} sites · real coordinates</div>
      </div>

      {/* year + readout + WHAT NEEDS YOU — one top-anchored left column (the preemptive landing) */}
      {!sel && !beltName && (
      <div className="absolute left-8 top-[15%] w-[min(400px,44vw)]">
        <div className="mono text-[10px] tracking-[0.28em] text-[var(--color-faint)] uppercase mb-1 pointer-events-none">Standing as of</div>
        <div ref={yearElRef} className="display font-semibold text-[clamp(56px,9.5vw,124px)] leading-[.8] text-[#F4EFE6] pointer-events-none" style={{ letterSpacing: '-2px' }}>2025</div>
        <div ref={statElRef} className="mono text-[13px] text-[var(--color-mute)] mt-4 pointer-events-none">— of {assets.length} assets at elevated risk</div>
        {euroToday != null && <div className="mono text-[11px] text-[var(--color-faint)] mt-1.5 pointer-events-none">€{(euroToday / 1e6).toFixed(1)}m volume-at-risk today (validated crops)</div>}
        {tasks.length > 0 && (
          <div className="mt-7">
            <div className="mono text-[9.5px] tracking-[0.22em] uppercase text-[var(--color-faint)] mb-2.5 pointer-events-none">What needs you</div>
            <div className="flex flex-col gap-2">
              {tasks.slice(0, 3).map(t => (
                <button key={t.key} onClick={() => nav(t.cta_href)}
                  className="group flex items-center gap-3 text-left rounded-xl border border-[var(--color-line)] bg-[#0b121ecc] backdrop-blur px-3.5 py-2.5 hover:border-[color:var(--tint)] transition"
                  style={{ ['--tint' as string]: SEV_COL[t.severity] || 'var(--color-sky)' }}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: SEV_COL[t.severity] || 'var(--color-sky)', boxShadow: `0 0 8px ${SEV_COL[t.severity] || 'var(--color-sky)'}` }} />
                  <span className="flex-1 min-w-0 text-[12.5px] text-[var(--color-ink)] truncate">{t.title}</span>
                  <span className="mono text-[10.5px] shrink-0" style={{ color: SEV_COL[t.severity] || 'var(--color-sky)' }}>{t.cta_label} →</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      )}

      {/* selected asset */}
      {sel && (
        <div className="absolute top-0 right-0 bottom-0 w-[min(400px,44vw)] z-10 p-8 overflow-y-auto"
          style={{ background: 'linear-gradient(270deg,#070b13 60%,#070b13cc 90%,transparent)' }}>
          <button onClick={closeSel} className="mono text-[10px] text-[var(--color-mute)] border border-[var(--color-line-2)] rounded-full px-3 py-1.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">← back</button>
          <div className="mono text-[10px] tracking-[0.24em] uppercase text-[var(--color-faint)] mt-6">{sel.region} · {sel.kind}</div>
          <div className="display text-[34px] leading-tight text-[#F4EFE6] mt-1.5">{sel.name}</div>
          <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1.5">◉ {Math.abs(sel.lat).toFixed(1)}°{sel.lat >= 0 ? 'N' : 'S'}, {Math.abs(sel.lon).toFixed(1)}°{sel.lon >= 0 ? 'E' : 'W'}</div>
          {(() => { const [r, g, b] = col(cur); return (
            <div className="inline-flex items-center gap-2 mt-3 mono text-[11px] tracking-wide uppercase px-3 py-1.5 rounded-full"
              style={{ background: `color-mix(in oklab, rgb(${r},${g},${b}) 16%, transparent)`, color: `rgb(${Math.min(255, r + 40)},${Math.min(255, g + 40)},${Math.min(255, b + 40)})` }}>
              <span className="w-2 h-2 rounded-full" style={{ background: `rgb(${r},${g},${b})` }} />{stateName(cur)} · {Math.round(S.current.year)}
            </div>) })()}
          <div className="mono text-[11.5px] text-[var(--color-mute)] mt-4 leading-[1.7]">
            worst hazard&nbsp;&nbsp;<b className="text-[#F4EFE6]">{pretty(sel.hazard)}</b><br />
            risk score now&nbsp;&nbsp;<b className="text-[#F4EFE6]">{Math.round(cur)}/100</b><br />
            value&nbsp;&nbsp;<b className="text-[#F4EFE6]">€{(sel.value_eur / 1e6).toFixed(1)}m</b>
          </div>
          <div className="mono text-[9.5px] tracking-[0.2em] uppercase text-[var(--color-faint)] mt-6 mb-2.5">Risk trajectory · golden source</div>
          <div className="flex items-end gap-1.5 h-[70px]">
            {[2025, 2035, 2045, 2055, 2065, 2075, 2085, 2100].map(yy => { const l = scoreAt(sel, yy); const [r, g, b] = col(l); return (
              <div key={yy} className="flex-1 flex flex-col items-center gap-1.5">
                <div className="w-full rounded-t" style={{ height: (8 + l * 0.6) + 'px', background: `rgb(${r},${g},${b})` }} />
                <div className="mono text-[8.5px] text-[#4b5768]">{String(yy).slice(2)}</div>
              </div>) })}
          </div>
          <div className="text-[11px] text-[var(--color-faint)] mt-4 leading-relaxed">
            Real physical-risk score under the disorderly-2°C path, interpolated across the golden source's
            current / 2030 / 2050 / 2100 horizons. Carried in your CSRD · ESRS E1 disclosure.
          </div>
          {/* what to do — real adaptation measures for this hazard */}
          {sel.adaptations && sel.adaptations.length > 0 && (
            <div className="mt-5 pt-4 border-t border-[var(--color-line)]">
              <div className="mono text-[9.5px] tracking-[0.2em] uppercase text-[var(--color-faint)] mb-2.5">What you can do · adaptation</div>
              <ul className="flex flex-col gap-2">
                {sel.adaptations.map((a, i) => (
                  <li key={i} className="flex gap-2.5 text-[12.5px] text-[var(--color-mute)] leading-snug">
                    <span className="text-[var(--color-good)] shrink-0 mt-0.5">→</span>{a}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {/* the action — one click into the operating page for this asset */}
          <button onClick={() => nav(sel.kind === 'plot' ? '/sourcing' : '/operations')}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 mono text-[11px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">
            open in {sel.kind === 'plot' ? 'Sourcing' : 'Operations'} <ArrowRight size={14} />
          </button>
        </div>
      )}

      {/* controls */}
      <button onClick={() => (S.current.snap = true)} className="absolute right-8 bottom-[136px] inline-flex items-center gap-2 mono text-[10.5px] text-[var(--color-mute)] bg-[#0b121e] border border-[#223046] rounded-full px-4 py-2.5 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]"><Camera size={13} /> save snapshot</button>
      <button onClick={() => nav('/home')} className="absolute right-8 bottom-[84px] inline-flex items-center gap-2 mono text-[11px] text-[#F4EFE6] bg-[#0e1626] border border-[#2a3a50] rounded-full px-5 py-3 hover:border-[var(--color-sky)] hover:text-[var(--color-sky)]">enter operations <ArrowRight size={14} /></button>

      <div className="absolute left-0 right-0 bottom-0 px-8 pb-6 pt-5" style={{ background: 'linear-gradient(0deg,#04060bE6 30%,transparent)' }}>
        <div className="flex items-center gap-4 max-w-[1200px] mx-auto">
          <button onClick={() => { if (S.current.year >= 2100) S.current.year = 2025; const p = !playing; S.current.play = p; setPlaying(p) }}
            className="w-11 h-11 shrink-0 rounded-full border border-[#2a3a50] bg-[#0e1626] grid place-items-center text-[#F4EFE6] hover:border-[var(--color-sky)]">
            {playing ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <input type="range" min={2025} max={2100} step={1} defaultValue={2025}
            onInput={e => { S.current.year = +(e.target as HTMLInputElement).value; S.current.play = false; setPlaying(false) }}
            onPointerDown={() => { S.current.play = false; setPlaying(false) }}
            className="flex-1 accent-[var(--color-sky)] cursor-pointer" />
          <div className="mono text-[10px] text-[var(--color-faint)] shrink-0">2025 → 2100</div>
        </div>
      </div>
    </div>
  )
}
