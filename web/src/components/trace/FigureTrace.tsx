import { useMemo, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, apiDetail, apiMessage } from '../../lib/api'
import { pressable } from '../../lib/pressable'
import { NODE_H, NODE_W, edgePath, expandParams, layered, network } from '../../lib/traceLayout'
import { Dialog } from '../Dialog'
import { DetailsBody, HEADING, InfoButton, MessageLine, type Message } from '../Details'
import { StatusChip } from '../StatusChip'
import { LAYER, PERIL, cellValue, details, sub, title, type TraceNode } from './traceWords'

// One filed figure as a graph, from the law to what the calculation read (GET /v1/filings/{id}/trace): the reporting
// templates' law and the specification frozen with the filing, the instruction naming the cell, the figure, the formula
// line and the statements it rests on (who attested them), the book it was computed from — a group's undertakings, in
// or left out — and the run that read the book. Layers by default; a network layout on request. Each node opens its
// source; a "more" node shows more of its group. Read from the frozen filing only.

interface Trace {
  supported: boolean; msg?: Message
  filing: { currency: string; period_label?: string | null }
  cell?: Record<string, any> & { tie?: { ties: boolean; traced_n: number } | null }
  layers: string[]; nodes: TraceNode[]; edges: { source: string; target: string }[]
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Where this figure comes from: the law and the template it is printed under, how it was computed and the statements it rests on, the book it was computed from, and what the calculation read.' },
  { heading: HEADING.read, body: 'Read left to right. Select any box for its source: the law as quoted, a statement with who attested it, a policy. A box with a number of more opens the rest of its group. A green dot is checked; amber needs a look; a faded box is left out of the figure.' },
  { heading: HEADING.sources, body: 'The frozen report only: its specification, its calculation, its attested values and the book it froze. Nothing is computed again.' },
]

// the side of the trace a node belongs to: the regulation, the data, or the figure and its formula
const SIDE: Record<string, string> = {
  act: 'var(--color-viz, #a78bfa)', spec: 'var(--color-viz, #a78bfa)', instruction: 'var(--color-viz, #a78bfa)',
  tables: 'var(--color-viz, #a78bfa)', cell: 'var(--color-ink)', formula: 'var(--color-mute)',
}
const TONE: Record<string, string> = { good: 'var(--color-good)', warn: 'var(--color-warn)', out: 'var(--color-faint)' }
const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s)

export default function FigureTrace({ filingId, cell, onClose }: { filingId: string; cell: string; onClose: () => void }) {
  const [expand, setExpand] = useState<Record<string, number>>({})
  const [mode, setMode] = useState<'layers' | 'network'>('layers')
  const [open, setOpen] = useState<TraceNode | null>(null)
  const extra = expandParams(expand)
  const q = useQuery({
    queryKey: ['trace', filingId, cell, extra], placeholderData: keepPreviousData,
    queryFn: () => api.get<Trace>(`/v1/filings/${filingId}/trace?cell=${encodeURIComponent(cell)}${extra ? `&${extra}` : ''}`),
  })
  const d = q.data
  const formula = d?.nodes.find(n => n.kind === 'formula')
  const peril = PERIL[formula?.facts?.peril ?? ''] ?? null
  const noun = d?.nodes.some(n => n.kind === 'exposure') ? 'exposures' : 'policies'
  const select = (n: TraceNode) => n.kind === 'more' ? setExpand(e => ({ ...e, [n.facts!.group]: (e[n.facts!.group] ?? 0) + 1 })) : setOpen(n)
  return (
    <>
      <Dialog title="Trace of this figure" onClose={onClose} className="sm:max-w-6xl">
        {q.isLoading ? <div className="text-[12.5px] text-[var(--color-faint)]">Tracing…</div>
          : !d ? <MessageLine m={{ label: apiMessage(q.error, 'This figure could not be traced'), detail: apiDetail(q.error) }} className="text-[12.5px] text-[var(--color-mute)]" />
          : !d.supported ? (d.msg ? <MessageLine m={d.msg} className="text-[12.5px] text-[var(--color-mute)]" /> : null)
          : (
            <div className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="display text-[22px] tabular-nums">{cellValue(d.cell ?? {})}</span>
                <span className="text-[12.5px] text-[var(--color-mute)]">{[d.cell?.column_label, d.cell?.row_label, peril, d.filing.period_label].filter(Boolean).join(' · ')}</span>
                {d.cell?.tie && <StatusChip tone={d.cell.tie.ties ? 'good' : 'warn'}
                  label={d.cell.tie.ties ? `Adds up to its ${d.cell.tie.traced_n} ${noun}` : `Does not add up to its ${noun}`} />}
                <InfoButton compact details={{ title: 'Trace of this figure', sections: ABOUT }} />
                <div className="ml-auto inline-flex rounded-lg border border-[var(--color-line-2)] overflow-hidden text-[11.5px]" role="group" aria-label="Layout">
                  {(['layers', 'network'] as const).map(v => (
                    <button key={v} type="button" onClick={() => setMode(v)} aria-pressed={mode === v}
                      className={`px-2.5 py-0.5 ${mode === v ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)] hover:text-[var(--color-ink)]'}`}>
                      {v === 'layers' ? 'Layers' : 'Network'}</button>))}
                </div>
              </div>
              <Legend />
              <Graph d={d} mode={mode} onSelect={select} busy={q.isFetching} />
            </div>)}
      </Dialog>
      {open && (
        <Dialog title={title(open)} onClose={() => setOpen(null)} className="max-w-xl">
          <NodeSource n={open} />
        </Dialog>)}
    </>
  )
}

function Legend() {
  const dot = (c: string) => <span className="w-2 h-2 rounded-full inline-block" style={{ background: c }} />
  return (
    <div className="flex flex-wrap items-center gap-3 text-[11px] text-[var(--color-faint)]">
      <span className="inline-flex items-center gap-1.5"><span className="w-3 h-1 rounded-sm" style={{ background: SIDE.act }} />The regulation</span>
      <span className="inline-flex items-center gap-1.5"><span className="w-3 h-1 rounded-sm" style={{ background: 'var(--color-sky)' }} />Your data and statements</span>
      <span className="inline-flex items-center gap-1.5">{dot(TONE.good)}Checked</span>
      <span className="inline-flex items-center gap-1.5">{dot(TONE.warn)}Needs a look</span>
      <span className="inline-flex items-center gap-1.5">{dot(TONE.out)}Left out</span>
    </div>
  )
}

function Graph({ d, mode, onSelect, busy }: { d: Trace; mode: 'layers' | 'network'; onSelect: (n: TraceNode) => void; busy: boolean }) {
  const [hot, setHot] = useState<string | null>(null)
  const layout = useMemo(() => (mode === 'layers' ? layered : network)(d.nodes, d.edges, d.layers), [d, mode])
  // each layer's name above its first column
  const heads = mode === 'layers'
    ? d.layers.map(l => ({ l, x: Math.min(...d.nodes.filter(n => n.layer === l).map(n => layout.at[n.id].x)) })).filter(h => Number.isFinite(h.x))
    : []
  const top = heads.length ? 18 : 0
  return (
    <div className={`overflow-auto max-h-[64vh] rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] ${busy ? 'opacity-70' : ''}`}>
      <svg width={layout.width} height={layout.height + top} viewBox={`0 ${-top} ${layout.width} ${layout.height + top}`} role="group" aria-label="Trace of this figure">
        {heads.map(h => <text key={h.l} x={h.x} y={-4} fontSize={10} fill="var(--color-faint)" style={{ letterSpacing: '.08em', textTransform: 'uppercase' }}>{LAYER[h.l]}</text>)}
        {d.edges.map((e, i) => {
          const a = layout.at[e.source], b = layout.at[e.target]
          if (!a || !b) return null
          const lit = hot != null && (e.source === hot || e.target === hot)
          return <path key={i} d={edgePath(a, b)} fill="none" stroke={lit ? 'var(--color-sky)' : 'var(--color-line-2)'} strokeWidth={lit ? 1.6 : 1} />
        })}
        {d.nodes.map(n => {
          const p = layout.at[n.id]
          const t = title(n), s = sub(n)
          const side = SIDE[n.kind] ?? 'var(--color-sky)'
          const out = n.tone === 'out'
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`} className="cursor-pointer outline-none" opacity={out ? 0.55 : 1}
              {...pressable(() => onSelect(n), { label: `${t}: ${s}` })}
              onMouseEnter={() => setHot(n.id)} onMouseLeave={() => setHot(null)} onFocus={() => setHot(n.id)} onBlur={() => setHot(null)}>
              <rect width={NODE_W} height={NODE_H} rx={8} fill="var(--color-panel)" strokeDasharray={n.kind === 'more' || out ? '4 3' : undefined}
                stroke={hot === n.id ? 'var(--color-sky)' : 'var(--color-line-2)'} strokeWidth={hot === n.id ? 2 : 1} />
              <rect x={0} y={6} width={3} height={NODE_H - 12} rx={1.5} fill={side} />
              {n.tone && <circle cx={NODE_W - 10} cy={10} r={3.5} fill={TONE[n.tone]} />}
              <text x={11} y={19} fontSize={11.5} fontWeight={n.kind === 'cell' ? 600 : 400} fill="var(--color-ink)">{trunc(t, 25)}</text>
              <text x={11} y={35} fontSize={10.5} fill="var(--color-faint)">{trunc(s, 31)}</text>
            </g>)
        })}
      </svg>
    </div>
  )
}

// A node's source: the law as quoted (and whether it is found word for word in the stored official text), then its facts.
function NodeSource({ n }: { n: TraceNode }) {
  const sections = details(n).map(s => ({
    heading: s.heading,
    body: Array.isArray(s.body) ? <ul className="space-y-1 list-disc pl-4">{s.body.map((b, i) => <li key={i}>{b}</li>)}</ul> : s.body,
  }))
  const q = n.quote
  return (
    <div className="space-y-4">
      {q && (
        <section className="space-y-1.5">
          <blockquote className="italic border-l-2 border-[var(--color-line-2)] pl-3 m-0 text-[13px] text-[var(--color-ink)] whitespace-pre-line">{q.text}</blockquote>
          <StatusChip tone={q.found_in ? 'good' : 'warn'} label={q.found_in ? 'Found word for word in the official text held' : 'Not found in the official texts held'} />
          {q.found_in_title && <div className="text-[12px] text-[var(--color-mute)]">{q.found_in_title}</div>}
        </section>)}
      <DetailsBody sections={sections} />
    </div>
  )
}
