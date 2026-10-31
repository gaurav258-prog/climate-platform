// A figure's trace lays out the same way every time: its layers left to right, and a network layout that is
// deterministic and keeps every node in view without two nodes on top of each other.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { NODE_H, NODE_W, columns, edgePath, expandParams, frame, layered, network } from '../src/lib/traceLayout.ts'

const LAYERS = ['law', 'spec', 'cell', 'basis', 'book', 'source']
const nodes = [
  { id: 'act', layer: 'law' }, { id: 'spec', layer: 'spec' }, { id: 'ins', layer: 'spec' }, { id: 'cell', layer: 'cell' },
  { id: 'formula', layer: 'basis' }, { id: 'stmt', layer: 'basis' }, { id: 'u2', layer: 'book' }, { id: 'u1', layer: 'book' },
  { id: 'p1', layer: 'book' }, { id: 'run', layer: 'source' },
]
const edges = [
  { source: 'act', target: 'spec' }, { source: 'spec', target: 'ins' }, { source: 'ins', target: 'cell' },
  { source: 'cell', target: 'formula' }, { source: 'cell', target: 'stmt' }, { source: 'stmt', target: 'u1' },
  { source: 'formula', target: 'u1' }, { source: 'formula', target: 'u2' }, { source: 'u1', target: 'p1' },
  { source: 'p1', target: 'run' },
]

test('layered: left to right in the order of the layers, a layer split where its nodes point to one another', () => {
  const l = layered(nodes, edges, LAYERS)
  const x = (id: string) => l.at[id].x
  assert.ok(x('act') < x('spec') && x('spec') < x('cell') && x('cell') < x('formula') && x('formula') < x('u1') && x('u1') < x('run'))
  assert.ok(x('spec') < x('ins') && x('ins') < x('cell'))          // the instruction one step right of its specification
  assert.ok(x('u1') < x('p1') && x('p1') < x('run'))                 // a policy one step right of its undertaking
  for (const n of nodes) assert.ok(l.at[n.id].x + NODE_W <= l.width && l.at[n.id].y + NODE_H <= l.height)
})

test('layered: within a column, a node follows the nodes that point to it', () => {
  const cols = columns(nodes, edges, LAYERS)
  const book = cols.filter(c => c.layer === 'book')
  // the book splits in two: the undertakings, then the policy under one of them
  assert.deepEqual(book.map(c => c.ids), [['u2', 'u1'], ['p1']])
  // u1 is pointed to by formula (place 0) and the statement (place 1); u2 by formula only, so u2 comes first (above)
  // a node no earlier node points to keeps its order, after those that are pointed to
  assert.deepEqual(columns([{ id: 'a', layer: 'law' }, { id: 'b', layer: 'spec' }, { id: 'c', layer: 'spec' }],
    [{ source: 'a', target: 'c' }], LAYERS)[1].ids, ['c', 'b'])
})

test('network: the same trace always lands the same way, every node in view, none on top of another', () => {
  const a = network(nodes, edges, LAYERS), b = network(nodes, edges, LAYERS)
  assert.deepEqual(a, b)
  const pts = nodes.map(n => a.at[n.id])
  for (const q of pts) assert.ok(q.x >= 0 && q.y >= 0 && q.x + NODE_W <= a.width && q.y + NODE_H <= a.height)
  for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++)
    assert.ok(Math.abs(pts[i].x - pts[j].x) >= NODE_W || Math.abs(pts[i].y - pts[j].y) >= NODE_H, `${nodes[i].id} on ${nodes[j].id}`)
  // a larger trace too: one undertaking with forty policies under it
  const big = [...nodes, ...Array.from({ length: 40 }, (_, i) => ({ id: `q${i}`, layer: 'book' }))]
  const bigEdges = [...edges, ...Array.from({ length: 40 }, (_, i) => ({ source: 'u1', target: `q${i}` }))]
  const net = network(big, bigEdges, LAYERS), c = net.at
  // it stays near the frame its node count gives — not spread over thousands of pixels
  const f = frame(big.length)
  assert.ok(net.width <= f.w * 1.5 && net.height <= f.h * 1.5 + NODE_H * 4, `${net.width} × ${net.height} for ${f.w} × ${f.h}`)
  for (let i = 0; i < big.length; i++) for (let j = i + 1; j < big.length; j++) {
    const p = c[big[i].id], q = c[big[j].id]
    assert.ok(Math.abs(p.x - q.x) >= NODE_W || Math.abs(p.y - q.y) >= NODE_H, `${big[i].id} on ${big[j].id}`)
  }
})

test('an edge leaves the right side of its source and enters the left side of its target', () => {
  assert.equal(edgePath({ x: 0, y: 0 }, { x: 300, y: 100 }), `M ${NODE_W} ${NODE_H / 2} C ${(NODE_W + 300) / 2} ${NODE_H / 2}, ${(NODE_W + 300) / 2} ${100 + NODE_H / 2}, 300 ${100 + NODE_H / 2}`)
})

test('expanded groups go to the server as group:times, unexpanded ones not at all', () => {
  assert.equal(expandParams({ 'policies-abc': 2, policies: 0 }), 'expand=policies-abc%3A2')
  assert.equal(expandParams({}), '')
})
