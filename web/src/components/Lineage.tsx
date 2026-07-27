import { useMemo, useState } from 'react'
import {
  ReactFlow, Background, Handle, Position, BackgroundVariant,
  type Node, type Edge, type NodeProps,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { ArrowDown, ArrowUp } from 'lucide-react'

type StageData = { title: string; sub: string; kind: 'source' | 'compute' | 'output' | 'act' }

// The platform data flow, inputs → outputs. Toggle re-orients it top-down (how the number is
// BUILT) or bottom-up (how a filing TRACES back to raw satellite pixels).
const STAGES: StageData[] = [
  { title: 'Satellite & agency feeds', sub: 'Copernicus/ERA5 · NASA/USGS · Hansen GFC', kind: 'source' },
  { title: 'H3 feature stores', sub: 'per-hazard, ~0.7 km² cells', kind: 'compute' },
  { title: 'Canonical scores', sub: '0–100 drought / heat, append-only', kind: 'compute' },
  { title: 'Projected onto your plots', sub: 'joined by H3 cell', kind: 'compute' },
  { title: 'Volume-at-risk + determination', sub: '€ at risk · deforestation-free check', kind: 'output' },
  { title: 'EUDR DDS · CSRD filing', sub: 'the submittable statement', kind: 'act' },
]
const KIND_COLOR: Record<StageData['kind'], string> = {
  source: 'var(--color-blue)', compute: 'var(--color-sky)', output: 'var(--color-good)', act: 'var(--color-warn)',
}

function StageNode({ data }: NodeProps) {
  const d = data as unknown as StageData
  const c = KIND_COLOR[d.kind]
  return (
    <div className="card px-4 py-3 w-[268px]" style={{ borderColor: `color-mix(in oklab, ${c} 45%, var(--color-line))` }}>
      <Handle type="target" position={Position.Top} style={{ opacity: 0, width: 1, height: 1 }} />
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ background: c }} />
        <span className="mono text-[9px] uppercase tracking-widest" style={{ color: c }}>{d.kind}</span>
      </div>
      <div className="text-[14px] font-semibold text-[var(--color-ink)] mt-1 leading-tight">{d.title}</div>
      <div className="text-[11.5px] text-[var(--color-mute)] mt-0.5 leading-snug">{d.sub}</div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, width: 1, height: 1 }} />
    </div>
  )
}
const nodeTypes = { stage: StageNode }

export default function Lineage() {
  const [dir, setDir] = useState<'down' | 'up'>('down')
  const GAP = 104, N = STAGES.length

  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = STAGES.map((s, i) => ({
      id: String(i), type: 'stage', data: s as unknown as Record<string, unknown>,
      position: { x: 0, y: (dir === 'down' ? i : N - 1 - i) * GAP },
      draggable: false, selectable: false,
    }))
    const edges: Edge[] = []
    for (let i = 0; i < N - 1; i++) {
      // the higher-on-screen node is always the source, so arrows read in the chosen direction.
      const [a, b] = dir === 'down' ? [i, i + 1] : [i + 1, i]
      edges.push({
        id: `${a}-${b}`, source: String(a), target: String(b), animated: true,
        style: { stroke: 'color-mix(in oklab, var(--color-sky) 55%, var(--color-line-2))', strokeWidth: 1.5 },
      })
    }
    return { nodes, edges }
  }, [dir, N])

  return (
    <div className="relative h-[560px] rounded-2xl overflow-hidden border border-[var(--color-line)] bg-[var(--color-bg-2)]">
      <div className="absolute z-10 top-3 left-4 right-4 flex items-center justify-between">
        <div>
          <div className="mono text-[10px] uppercase tracking-[0.2em] text-[var(--color-blue)]">Lineage</div>
          <div className="text-[13px] text-[var(--color-mute)]">
            {dir === 'down' ? 'How the number is built — satellite → filing' : 'How a filing traces back — filing → satellite pixels'}
          </div>
        </div>
        <div className="flex gap-1 card p-1">
          <button onClick={() => setDir('down')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] transition ${dir === 'down' ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>
            <ArrowDown size={13} /> Top-down
          </button>
          <button onClick={() => setDir('up')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] transition ${dir === 'up' ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]'}`}>
            <ArrowUp size={13} /> Bottom-up
          </button>
        </div>
      </div>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.28 }}
        proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false}
        panOnScroll zoomOnScroll={false} minZoom={0.5} maxZoom={1.3}>
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1b2740" />
      </ReactFlow>
    </div>
  )
}
