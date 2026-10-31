// Where each node of a figure's trace sits (the graph of /v1/filings/{id}/trace). Two layouts over the same nodes:
//   layered  the layers left to right (the law → the specification → the figure → how it was computed → the book →
//            what the calculation read), a layer in sub-columns where its nodes point to one another; within a column,
//            nodes follow the average place of the nodes that point to them, so lines cross as little as one pass allows
//   network  a force layout started from the layered one: linked nodes pull together, every pair pushes apart — run a
//            fixed number of steps, so the same trace always lands the same way (no animation, nothing random)
// Pure functions: no React, no measurement.

export interface TraceNodeRef { id: string; layer: string }
export interface TraceEdgeRef { source: string; target: string }
export interface Placed { x: number; y: number }
export interface Layout { at: Record<string, Placed>; width: number; height: number }

export const NODE_W = 184
export const NODE_H = 46
const COL_GAP = 56
const ROW_GAP = 12
const PAD = 16

// The columns of the layered layout, left to right: each layer, split into sub-columns where its nodes point to one
// another (the specification → the instruction it holds, an undertaking → its policies), each node one step right of
// the node of its own layer pointing to it. Within a column, nodes follow the average place of the nodes pointing to
// them in earlier columns; a node with none keeps its order, after them.
export interface Column { layer: string; ids: string[] }
export function columns(nodes: TraceNodeRef[], edges: TraceEdgeRef[], layers: string[]): Column[] {
  const order = new Map(nodes.map((n, i) => [n.id, i]))
  const layerOf = new Map(nodes.map(n => [n.id, n.layer]))
  const into = new Map<string, string[]>()
  for (const e of edges) into.set(e.target, [...(into.get(e.target) ?? []), e.source])
  const depth = new Map<string, number>()
  const depthOf = (id: string, seen: Set<string> = new Set()): number => {
    if (depth.has(id)) return depth.get(id)!
    if (seen.has(id)) return 0                                   // a loop inside a layer: stop
    seen.add(id)
    const same = (into.get(id) ?? []).filter(s => layerOf.get(s) === layerOf.get(id))
    const d = same.length ? 1 + Math.max(...same.map(s => depthOf(s, seen))) : 0
    depth.set(id, d)
    return d
  }
  const rank = new Map<string, number>()
  const cols: Column[] = []
  for (const layer of layers) {
    const inLayer = nodes.filter(n => n.layer === layer).map(n => n.id)
    const deepest = Math.max(-1, ...inLayer.map(id => depthOf(id)))
    for (let d = 0; d <= deepest; d++) {
      const ids = inLayer.filter(id => depthOf(id) === d)
      const score = new Map(ids.map(id => {
        const from = (into.get(id) ?? []).filter(s => rank.has(s)).map(s => rank.get(s)!)
        return [id, from.length ? from.reduce((a, b) => a + b, 0) / from.length : Number.POSITIVE_INFINITY]
      }))
      ids.sort((a, b) => (score.get(a)! === score.get(b)! ? 0 : score.get(a)! < score.get(b)! ? -1 : 1) || order.get(a)! - order.get(b)!)
      ids.forEach((id, i) => rank.set(id, i))
      cols.push({ layer, ids })
    }
  }
  return cols
}

export function layered(nodes: TraceNodeRef[], edges: TraceEdgeRef[], layers: string[]): Layout {
  const cols = columns(nodes, edges, layers).filter(c => c.ids.length)
  const tallest = Math.max(1, ...cols.map(c => c.ids.length))
  const height = PAD * 2 + tallest * NODE_H + (tallest - 1) * ROW_GAP
  const at: Record<string, Placed> = {}
  cols.forEach(({ ids }, ci) => {
    const h = ids.length * NODE_H + (ids.length - 1) * ROW_GAP
    const top = (height - h) / 2
    ids.forEach((id, ri) => { at[id] = { x: PAD + ci * (NODE_W + COL_GAP), y: top + ri * (NODE_H + ROW_GAP) } })
  })
  return { at, width: PAD * 2 + cols.length * NODE_W + (cols.length - 1) * COL_GAP, height }
}

// The frame a network layout keeps its nodes in: room for each node about 2.5 times its own box, wider than tall.
export function frame(n: number): { w: number; h: number } {
  const area = Math.max(n, 1) * (NODE_W + 24) * (NODE_H + 24) * 2.5
  const w = Math.max(900, Math.sqrt(area * 1.8))
  return { w, h: Math.max(NODE_H * 3, area / w) }
}

// Fruchterman–Reingold on node centres inside the frame, from the layered positions scaled into it, a fixed number of
// steps; boxes still overlapping are then pushed apart, and the whole moved into view.
export function network(nodes: TraceNodeRef[], edges: TraceEdgeRef[], layers: string[], steps = 300): Layout {
  const start = layered(nodes, edges, layers)
  const ids = nodes.map(n => n.id)
  const { w, h } = frame(ids.length)
  const sx = (w - NODE_W) / Math.max(start.width - NODE_W, 1), sy = (h - NODE_H) / Math.max(start.height - NODE_H, 1)
  const p = ids.map(id => ({ x: NODE_W / 2 + start.at[id].x * sx, y: NODE_H / 2 + start.at[id].y * sy }))
  const idx = new Map(ids.map((id, i) => [id, i]))
  const links = edges.map(e => [idx.get(e.source), idx.get(e.target)]).filter((l): l is [number, number] => l[0] != null && l[1] != null)
  const k = 0.9 * Math.sqrt((w * h) / Math.max(ids.length, 1))
  let t = w / 10
  for (let s = 0; s < steps; s++) {
    const d = p.map(() => ({ x: 0, y: 0 }))
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        let dx = p[i].x - p[j].x, dy = p[i].y - p[j].y
        if (dx === 0 && dy === 0) { dx = 0.01 * (i - j); dy = 0.01 }
        const dist = Math.max(Math.hypot(dx, dy), 1)
        const f = (k * k) / dist
        d[i].x += (dx / dist) * f; d[i].y += (dy / dist) * f
        d[j].x -= (dx / dist) * f; d[j].y -= (dy / dist) * f
      }
    }
    for (const [a, b] of links) {
      const dx = p[a].x - p[b].x, dy = p[a].y - p[b].y
      const dist = Math.max(Math.hypot(dx, dy), 1)
      const f = (dist * dist) / k
      d[a].x -= (dx / dist) * f; d[a].y -= (dy / dist) * f
      d[b].x += (dx / dist) * f; d[b].y += (dy / dist) * f
    }
    for (let i = 0; i < p.length; i++) {
      const len = Math.max(Math.hypot(d[i].x, d[i].y), 1e-9)
      p[i].x = Math.min(w - NODE_W / 2, Math.max(NODE_W / 2, p[i].x + (d[i].x / len) * Math.min(len, t)))
      p[i].y = Math.min(h - NODE_H / 2, Math.max(NODE_H / 2, p[i].y + (d[i].y / len) * Math.min(len, t)))
    }
    t = Math.max(t * 0.985, 0.5)
  }
  separate(p)
  const minX = Math.min(...p.map(q => q.x)) - NODE_W / 2, minY = Math.min(...p.map(q => q.y)) - NODE_H / 2
  const at: Record<string, Placed> = {}
  ids.forEach((id, i) => { at[id] = { x: PAD + p[i].x - NODE_W / 2 - minX, y: PAD + p[i].y - NODE_H / 2 - minY } })
  const width = Math.max(...Object.values(at).map(q => q.x)) + NODE_W + PAD
  const height = Math.max(...Object.values(at).map(q => q.y)) + NODE_H + PAD
  return { at, width, height }
}

// Boxes that still overlap are pushed apart along the axis they overlap least on, until none does (or 200 sweeps).
function separate(p: { x: number; y: number }[]): void {
  const w = NODE_W + 12, h = NODE_H + 12
  for (let sweep = 0; sweep < 200; sweep++) {
    let moved = false
    for (let i = 0; i < p.length; i++) {
      for (let j = i + 1; j < p.length; j++) {
        const ox = w - Math.abs(p[i].x - p[j].x), oy = h - Math.abs(p[i].y - p[j].y)
        if (ox <= 0 || oy <= 0) continue
        moved = true
        if (ox / w < oy / h) {
          const s = (p[i].x < p[j].x || (p[i].x === p[j].x && i < j) ? -1 : 1) * ox / 2
          p[i].x += s; p[j].x -= s
        } else {
          const s = (p[i].y < p[j].y || (p[i].y === p[j].y && i < j) ? -1 : 1) * oy / 2
          p[i].y += s; p[j].y -= s
        }
      }
    }
    if (!moved) return
  }
}

// A line from the right side of one node to the left side of another (or the reverse, when it runs right to left).
export function edgePath(a: Placed, b: Placed): string {
  const forward = b.x >= a.x
  const x1 = forward ? a.x + NODE_W : a.x, y1 = a.y + NODE_H / 2
  const x2 = forward ? b.x : b.x + NODE_W, y2 = b.y + NODE_H / 2
  const mx = (x1 + x2) / 2
  return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
}

// The expand parameters of the trace request: each group of nodes with how many times it was expanded.
export const expandParams = (expand: Record<string, number>) =>
  Object.entries(expand).filter(([, n]) => n > 0).map(([g, n]) => `expand=${encodeURIComponent(`${g}:${n}`)}`).join('&')
