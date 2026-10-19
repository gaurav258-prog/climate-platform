import { useEffect, type MutableRefObject, type RefObject } from 'react'
import { COAST } from '../../lib/coastline'
import type { Asset } from './types'

// The Horizon globe: a canvas earth with the book at its real coordinates. Figures are the server's, at the modelled
// years (stops); between two stops the dots only blend their colour as the view moves on — nothing is computed there.

export const D2R = Math.PI / 180
const SUN = (() => { const v = [-0.5, 0.42, 0.76]; const m = Math.hypot(v[0], v[1], v[2]); return v.map(x => x / m) })()

// ── live ISS orbit overlay — the real sub-satellite point (fetched) and its ground track ──────────────────
export const ISS_PERIOD_S = 92.9 * 60          // one orbit ≈ 92.9 min (drawing only)
const ISS_DEG_PER_S = 360 / ISS_PERIOD_S
const EARTH_DEG_PER_S = 360 / 86164            // sidereal spin — precesses the track westward each orbit
const ISS_INCL = 51.6                          // orbital inclination (°)
export function inclHeading(la: number): number {
  const c = Math.cos(ISS_INCL * D2R) / Math.max(0.05, Math.cos(la * D2R))
  return Math.asin(Math.max(-1, Math.min(1, c))) / D2R
}
export function bearingDeg(la1: number, lo1: number, la2: number, lo2: number): number {
  const p1 = la1 * D2R, p2 = la2 * D2R, dl = (lo2 - lo1) * D2R
  const y = Math.sin(dl) * Math.cos(p2)
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (Math.atan2(y, x) / D2R + 360) % 360
}
function gcDest(la: number, lo: number, brg: number, ang: number): [number, number] {
  const p1 = la * D2R, l1 = lo * D2R, th = brg * D2R, d = ang * D2R
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(th))
  const l2 = l1 + Math.atan2(Math.sin(th) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2))
  return [p2 / D2R, ((l2 / D2R + 540) % 360) - 180]
}

// One colour ramp for a 0–100 score, pale → amber → red: a visual scale, not a threshold. Grey = no score.
const RAMP: [number, number, number][] = [[207, 232, 255], [232, 178, 76], [210, 59, 59]]
export function ramp(s: number | null): [number, number, number] {
  if (s == null) return [110, 122, 140]
  const t = Math.max(0, Math.min(1, s / 100)) * (RAMP.length - 1), i = Math.min(RAMP.length - 2, Math.floor(t)), f = t - i
  return [0, 1, 2].map(k => Math.round(RAMP[i][k] + (RAMP[i + 1][k] - RAMP[i][k]) * f)) as [number, number, number]
}
export const rgb = (c: [number, number, number], a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`

// the colour blend between two stops (pos is fractional while the view moves on); the server's score at a stop
export function blendScore(a: Asset, pos: number): number | null {
  const i = Math.max(0, Math.min(a.score.length - 1, Math.floor(pos))), f = pos - i
  const s0 = a.score[i], s1 = a.score[Math.min(a.score.length - 1, i + 1)]
  if (s0 == null) return s1 ?? null
  if (s1 == null || f === 0) return s0
  return s0 + (s1 - s0) * f
}
export const nearest = (pos: number, n: number) => Math.max(0, Math.min(n - 1, Math.round(pos)))

export interface View {
  pos: number; target: number; lon0: number; lat0: number; tLon: number; tLat: number; drag: boolean; moved: boolean
  px: number; py: number; play: boolean; stop: number; focus: Asset | null; belt: string | null; snap: boolean
}
export interface Iss { lat: number; lon: number; hdg: number; t0: number }

export function useGlobe({ cvRef, railRef, S, assets, belts, iss, issScreen, onStop, onPlayEnd, onHover, onPick, onBelt, onIss, caption }: {
  cvRef: RefObject<HTMLCanvasElement | null>; railRef: RefObject<HTMLDivElement | null>; S: MutableRefObject<View>
  assets: Asset[]; belts: MutableRefObject<Record<string, Asset[]>>
  iss: MutableRefObject<Iss | null>; issScreen: MutableRefObject<{ x: number; y: number; vis: boolean }>
  onStop: (i: number) => void; onPlayEnd: () => void
  onHover: (t: { a: Asset; x: number; y: number } | null) => void; onPick: (a: Asset) => void; onBelt: (r: string) => void
  onIss: () => void; caption: () => { top: string; big: string; line: string; tag: string }
}) {
  useEffect(() => {
    const cv = cvRef.current!; const ctx = cv.getContext('2d')!
    let raf = 0, W = 0, H = 0, DPR = 1, gx = 0, gy = 0, Rg = 0, tprev = 0
    const resize = () => {
      DPR = Math.min(2, devicePixelRatio || 1); W = cv.clientWidth; H = cv.clientHeight
      cv.width = W * DPR; cv.height = H * DPR; ctx.setTransform(DPR, 0, 0, DPR, 0, 0)
      gy = H * 0.53
      // fit the globe into the clear band right of the rail, so it never slides under the tiles
      if (window.innerWidth > 800) {
        const cr = cv.getBoundingClientRect(), GAP = 22
        let lE = W * 0.28; const rE = W * 0.9
        const lp = railRef.current; if (lp) { const r = lp.getBoundingClientRect(); if (r.width) lE = (r.right - cr.left) + GAP }
        const bandW = Math.max(240, rE - lE)
        gx = lE + bandW / 2; Rg = Math.min(bandW / 2, H * 0.42)
      } else { gx = W * 0.5; Rg = Math.min(W * 0.42, H * 0.36) }
    }
    resize(); addEventListener('resize', resize)
    // the sidebar expanding/collapsing resizes the content area without a window 'resize' — observe the canvas and rail
    const ro = new ResizeObserver(resize); ro.observe(cv)
    if (railRef.current) ro.observe(railRef.current)

    const project = (la: number, lo: number) => {
      const lat = la * D2R, lon = lo * D2R, dl = lon - S.current.lon0, cl = Math.cos(lat), l0 = S.current.lat0
      const Z = Math.sin(l0) * Math.sin(lat) + Math.cos(l0) * cl * Math.cos(dl)
      const X = cl * Math.sin(dl), Y = Math.cos(l0) * Math.sin(lat) - Math.sin(l0) * cl * Math.cos(dl)
      return { x: gx + Rg * X, y: gy - Rg * Y, vis: Z > 0, depth: Z, illum: X * SUN[0] + Y * SUN[1] + Z * SUN[2] }
    }
    // dotted land mask for the night lights (coarse ellipses; the coastlines are the real geometry)
    const LAND: number[][] = [[-100, 45, 30, 20], [-118, 52, 16, 12], [-75, 50, 20, 15], [-88, 15, 12, 8], [-63, -6, 16, 15], [-64, -34, 11, 17], [-42, 72, 15, 9], [12, 50, 20, 11], [22, 63, 14, 8], [15, 25, 30, 15], [24, -14, 18, 18], [45, 27, 14, 12], [80, 58, 46, 16], [78, 22, 12, 11], [105, 12, 15, 13], [110, 36, 20, 14], [118, -2, 20, 7], [134, -25, 17, 11], [-2, 54, 5, 5], [10, 36, 10, 4]]
    const landPts: number[][] = []
    for (let la = -78; la <= 80; la += 3.4) for (let lo = -178; lo <= 180; lo += 3.6) for (const L of LAND) { const dx = (lo - L[0]) / L[2], dy = (la - L[1]) / L[3]; if (dx * dx + dy * dy < 1) { landPts.push([la, lo]); break } }
    const stars = Array.from({ length: 170 }, () => ({ x: Math.random(), y: Math.random(), r: Math.random() * 1.3, t: Math.random() * 6.28 }))

    let regionRects: { r: string; x0: number; x1: number; y0: number; y1: number }[] = []
    const hit = (mx: number, my: number): Asset | null => { const pool = S.current.belt ? (belts.current[S.current.belt] || []) : assets; let best = 20, h: Asset | null = null; for (const a of pool) { const p = project(a.lat, a.lon); if (!p.vis) continue; const d = Math.hypot(p.x - mx, p.y - my); if (d < best) { best = d; h = a } } return h }
    const hitRegion = (mx: number, my: number): string | null => { for (const rr of regionRects) if (mx >= rr.x0 && mx <= rr.x1 && my >= rr.y0 && my <= rr.y1) return rr.r; return null }
    const rel = (e: PointerEvent): [number, number] => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top] }
    const onDown = (e: PointerEvent) => { if (S.current.focus) return; S.current.drag = true; S.current.moved = false; const [x, y] = rel(e); S.current.px = x; S.current.py = y; cv.setPointerCapture(e.pointerId) }
    const onMove = (e: PointerEvent) => {
      const [x, y] = rel(e)
      if (S.current.drag) { onHover(null); const dx = x - S.current.px, dy = y - S.current.py; if (Math.abs(dx) + Math.abs(dy) > 3) S.current.moved = true; S.current.lon0 -= dx * 0.005; S.current.lat0 = Math.max(-1.2, Math.min(1.2, S.current.lat0 + dy * 0.005)); S.current.tLon = S.current.lon0; S.current.tLat = S.current.lat0; S.current.px = x; S.current.py = y; return }
      const is = issScreen.current, overIss = is.vis && Math.hypot(is.x - x, is.y - y) < 16
      const ha = S.current.focus ? null : hit(x, y)
      cv.style.cursor = (overIss || ha || hitRegion(x, y)) ? 'pointer' : 'grab'
      onHover(ha ? { a: ha, x, y } : null)
    }
    const onLeave = () => onHover(null)
    const onUp = (e: PointerEvent) => {
      if (!S.current.drag) return; S.current.drag = false; if (S.current.moved) return; const [x, y] = rel(e)
      const is = issScreen.current; if (is.vis && Math.hypot(is.x - x, is.y - y) < 16) { onIss(); return }
      const a = hit(x, y); if (a) { onPick(a); return }
      if (!S.current.belt) { const r = hitRegion(x, y); if (r) onBelt(r) }
    }
    cv.addEventListener('pointerdown', onDown); cv.addEventListener('pointermove', onMove); cv.addEventListener('pointerup', onUp); cv.addEventListener('pointerleave', onLeave)

    const drawCaption = () => {
      const c = caption(), b = H - 18, MONO = 'ui-monospace,Menlo,monospace', SERIF = 'Georgia,serif'
      const g = ctx.createLinearGradient(0, H - 100, 0, H); g.addColorStop(0, 'rgba(4,6,11,0)'); g.addColorStop(1, 'rgba(4,6,11,0.92)'); ctx.fillStyle = g; ctx.fillRect(0, H - 100, W, 100)
      ctx.textAlign = 'left'; ctx.fillStyle = '#5C6879'; ctx.font = '600 11px ' + MONO; ctx.fillText(c.top, 30, b - 44)
      ctx.fillStyle = '#F4EFE6'; ctx.font = '600 30px ' + SERIF; ctx.fillText(c.big, 30, b - 12)
      ctx.fillStyle = '#8C99AC'; ctx.font = '12px ' + MONO; ctx.fillText(c.line, 30, b + 4)
      ctx.textAlign = 'right'; ctx.fillStyle = '#8FC0F0'; ctx.font = 'italic 17px ' + SERIF; ctx.fillText(c.tag, W - 30, b - 14)
    }

    const draw = (ts: number) => {
      const t = ts * 0.001, n = assets[0]?.score.length ?? 1
      if (!S.current.drag) { S.current.lon0 += (S.current.tLon - S.current.lon0) * 0.09; S.current.lat0 += (S.current.tLat - S.current.lat0) * 0.09 }
      if (S.current.play) {
        const dt = Math.min(0.05, (ts - tprev) / 1000); S.current.pos += dt * 0.55
        if (S.current.pos >= S.current.target) { S.current.pos = S.current.target; S.current.play = false; onPlayEnd() }
      }
      const st = nearest(S.current.pos, n); if (st !== S.current.stop) { S.current.stop = st; onStop(st) }
      tprev = ts
      const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#05070d'); g.addColorStop(1, '#0a1120'); ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
      for (const s of stars) { const tw = .5 + .5 * Math.sin(t * 1.5 + s.t); ctx.globalAlpha = .12 + tw * .45; ctx.fillStyle = '#cfe0ff'; ctx.fillRect(s.x * W, s.y * H, s.r, s.r) } ctx.globalAlpha = 1
      // sphere, day glow, night side
      const og = ctx.createRadialGradient(gx - Rg * 0.35, gy - Rg * 0.4, Rg * 0.1, gx, gy, Rg); og.addColorStop(0, '#12233a'); og.addColorStop(.55, '#0b1524'); og.addColorStop(1, '#070d17'); ctx.fillStyle = og; ctx.beginPath(); ctx.arc(gx, gy, Rg, 0, 7); ctx.fill()
      ctx.save(); ctx.beginPath(); ctx.arc(gx, gy, Rg, 0, 7); ctx.clip()
      const spx = gx + Rg * SUN[0], spy = gy - Rg * SUN[1], apx = gx - Rg * SUN[0], apy = gy + Rg * SUN[1]
      const dg = ctx.createRadialGradient(spx, spy, 0, spx, spy, Rg * 1.55); dg.addColorStop(0, 'rgba(150,180,215,0.16)'); dg.addColorStop(.5, 'rgba(120,150,190,0.05)'); dg.addColorStop(1, 'rgba(0,0,0,0)'); ctx.fillStyle = dg; ctx.fillRect(gx - Rg, gy - Rg, Rg * 2, Rg * 2)
      const ng = ctx.createRadialGradient(apx, apy, 0, apx, apy, Rg * 1.5); ng.addColorStop(0, 'rgba(2,4,9,0.6)'); ng.addColorStop(.6, 'rgba(2,4,9,0.18)'); ng.addColorStop(1, 'rgba(0,0,0,0)'); ctx.fillStyle = ng; ctx.fillRect(gx - Rg, gy - Rg, Rg * 2, Rg * 2)
      ctx.restore()
      for (const p of landPts) { const pr = project(p[0], p[1]); if (!pr.vis) continue; if (pr.illum > 0.02) { ctx.globalAlpha = 0.05 + pr.depth * 0.13; ctx.fillStyle = '#43648a'; ctx.beginPath(); ctx.arc(pr.x, pr.y, 0.9, 0, 7); ctx.fill() } else { const tw = .55 + .45 * Math.sin(t * 2 + pr.x * 0.05); ctx.globalAlpha = (0.11 + pr.depth * 0.32) * tw; ctx.fillStyle = '#F5D69A'; ctx.beginPath(); ctx.arc(pr.x, pr.y, 0.85, 0, 7); ctx.fill() } } ctx.globalAlpha = 1
      ctx.strokeStyle = 'rgba(150,182,214,0.34)'; ctx.lineWidth = 0.75; ctx.lineJoin = 'round'
      for (const ring of COAST) { ctx.beginPath(); let pv = false; for (let i = 0; i < ring.length; i++) { const p = project(ring[i][1], ring[i][0]); if (p.vis) { if (pv) ctx.lineTo(p.x, p.y); else ctx.moveTo(p.x, p.y); pv = true } else pv = false } ctx.stroke() }
      const rim = ctx.createRadialGradient(gx, gy, Rg * 0.96, gx, gy, Rg * 1.09); rim.addColorStop(0, 'rgba(127,178,230,0)'); rim.addColorStop(.55, 'rgba(127,178,230,0.4)'); rim.addColorStop(1, 'rgba(127,178,230,0)'); ctx.beginPath(); ctx.arc(gx, gy, Rg * 1.05, 0, 7); ctx.lineWidth = Rg * 0.09; ctx.strokeStyle = rim; ctx.stroke()

      // place labels — click to frame a place; front-most win a spot, a label that would collide is skipped
      regionRects = []
      if (!S.current.focus) {
        ctx.font = '600 11px ui-monospace,Menlo,monospace'; ctx.textAlign = 'center'
        const cands = Object.keys(belts.current).map(rn => {
          const gr = belts.current[rn]; const mla = gr.reduce((s, a) => s + a.lat, 0) / gr.length, mlo = gr.reduce((s, a) => s + a.lon, 0) / gr.length
          return { rn, p: project(mla, mlo) }
        }).filter(c => c.p.vis && c.p.depth >= 0.3).sort((a, b) => b.p.depth - a.p.depth)
        for (const { rn, p } of cands) {
          const w = ctx.measureText(rn.toUpperCase()).width
          const box = { x0: p.x - w / 2 - 8, x1: p.x + w / 2 + 8, y0: p.y - 26, y1: p.y - 6 }
          if (regionRects.some(q => box.x0 < q.x1 && box.x1 > q.x0 && box.y0 < q.y1 && box.y1 > q.y0)) continue
          const dimr = S.current.belt && S.current.belt !== rn ? 0.25 : 0.62
          ctx.fillStyle = `rgba(180,196,214,${dimr})`; ctx.fillText(rn.toUpperCase(), p.x, p.y - 16)
          regionRects.push({ r: rn, ...box })
        }
      }
      // the book — real coordinates; colour from the score, a flare when the server says it is at risk at this stop
      for (const a of assets) {
        const p = project(a.lat, a.lon); if (!p.vis) continue
        const l = blendScore(a, S.current.pos), c = ramp(l), flared = !!a.at_risk[S.current.stop], sel = S.current.focus === a
        let dim = S.current.focus && !sel ? 0.16 : 1
        if (!S.current.focus && S.current.belt && a.region !== S.current.belt) dim = 0.2
        const tw = .6 + .4 * Math.sin(t * (flared ? 4 : 1.4) + a.lon)
        const dep = 0.55 + 0.45 * p.depth
        const sz = (2 * (flared ? 1.6 : 1) * (sel ? 1.5 : 1)) * dep * (1 + (l ?? 0) / 100 * 0.8)
        const al = dep * (0.7 + tw * 0.3) * dim
        const gl = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, sz * 7); gl.addColorStop(0, rgb(c, al * (flared ? 0.9 : 0.5))); gl.addColorStop(1, rgb(c, 0))
        ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(p.x, p.y, sz * 7, 0, 7); ctx.fill()
        ctx.fillStyle = rgb([Math.min(255, c[0] + 60), Math.min(255, c[1] + 50), Math.min(255, c[2] + 50)], al); ctx.beginPath(); ctx.arc(p.x, p.y, sz, 0, 7); ctx.fill()
        if (sel) { ctx.strokeStyle = rgb(c, .5 + .3 * tw); ctx.lineWidth = 1.3; ctx.beginPath(); ctx.arc(p.x, p.y, sz + 9 + 2 * tw, 0, 7); ctx.stroke() }
      }
      // the ISS: its real current point and the ground track one orbit each way (front hemisphere only)
      const st2 = iss.current
      if (st2) {
        ctx.lineWidth = 1.1; ctx.strokeStyle = 'rgba(126,182,255,0.32)'
        let pen = false; ctx.beginPath()
        for (let s = -ISS_PERIOD_S / 2; s <= ISS_PERIOD_S / 2; s += 90) {
          const [la, loRaw] = gcDest(st2.lat, st2.lon, st2.hdg, ISS_DEG_PER_S * s)
          const pp = project(la, loRaw - EARTH_DEG_PER_S * s)
          if (!pp.vis) { pen = false; continue }
          if (!pen) { ctx.moveTo(pp.x, pp.y); pen = true } else ctx.lineTo(pp.x, pp.y)
        }
        ctx.stroke()
        const dt = t - st2.t0
        const [mlat, mlon] = gcDest(st2.lat, st2.lon, st2.hdg, ISS_DEG_PER_S * dt)
        const pm = project(mlat, mlon - EARTH_DEG_PER_S * dt)
        issScreen.current = { x: pm.x, y: pm.y, vis: pm.vis }
        if (pm.vis) {
          const pulse = 0.6 + 0.4 * Math.sin(t * 2)
          const gl = ctx.createRadialGradient(pm.x, pm.y, 0, pm.x, pm.y, 14)
          gl.addColorStop(0, `rgba(150,200,255,${0.55 * pulse})`); gl.addColorStop(1, 'rgba(150,200,255,0)')
          ctx.fillStyle = gl; ctx.beginPath(); ctx.arc(pm.x, pm.y, 14, 0, 7); ctx.fill()
          ctx.strokeStyle = `rgba(150,200,255,${0.5 * pulse})`; ctx.lineWidth = 1
          ctx.beginPath(); ctx.arc(pm.x, pm.y, 8 + 2 * pulse, 0, 7); ctx.stroke()
          ctx.strokeStyle = 'rgba(210,230,255,0.95)'; ctx.lineWidth = 1.5
          ctx.beginPath(); ctx.moveTo(pm.x - 6, pm.y); ctx.lineTo(pm.x + 6, pm.y); ctx.stroke()
          ctx.fillStyle = '#EAF3FF'; ctx.beginPath(); ctx.arc(pm.x, pm.y, 2.6, 0, 7); ctx.fill()
          ctx.fillStyle = 'rgba(200,225,255,0.9)'; ctx.font = '9px ui-monospace,Menlo,monospace'; ctx.textAlign = 'left'
          ctx.fillText('ISS · live', pm.x + 12, pm.y + 3)
        }
      } else issScreen.current = { x: -1, y: -1, vis: false }

      if (S.current.snap) { S.current.snap = false; drawCaption(); try { const a = document.createElement('a'); a.download = `tellumen-horizon-${caption().big}.png`; a.href = cv.toDataURL('image/png'); a.click() } catch { /* a tainted canvas cannot be saved */ } }
      raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)
    return () => { cancelAnimationFrame(raf); removeEventListener('resize', resize); ro.disconnect(); cv.removeEventListener('pointerdown', onDown); cv.removeEventListener('pointermove', onMove); cv.removeEventListener('pointerup', onUp); cv.removeEventListener('pointerleave', onLeave) }
  }, [assets])   // eslint-disable-line react-hooks/exhaustive-deps
}
