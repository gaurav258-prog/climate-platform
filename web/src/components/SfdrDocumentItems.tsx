import { useState } from 'react'
import { Button } from './ui'

// One SFDR product template (RTS 2022/1288 Annexes II–V) rendered item by item, in the order the regulation prints
// it: headings, questions, tick-boxes with their blanks, charts, tables, margin definitions. Every item comes from
// the governing specification; each item to fill says whether it is computed from the fund, answered by the manager
// or still missing. Shared by the fund page (editable) and the filing form (frozen, read-only).

export interface DocItem {
  id: string; kind: string; label: string; parent: string | null; instruction?: string | null; blank?: string | null
  source: 'fixed' | 'computed' | 'input'; status: 'printed' | 'filled' | 'missing'; value?: any; needs?: string | null; note?: string | null
}

const SOURCE: Record<string, { c: string; label: string }> = {
  computed: { c: 'var(--color-good)', label: 'computed' },
  input: { c: 'var(--color-sky)', label: 'answered' },
  missing: { c: 'var(--color-warn)', label: 'needs an answer' },
}
const PLACEHOLDER = /^(\s*[xX]\s*%|\d+\s*%|Turnover|CapEx|OpEx)\s*$/   // chart print marks, not categories to fill

function Badge({ it }: { it: DocItem }) {
  if (it.source === 'fixed' || (it.kind === 'choice' && it.status === 'missing')) return null   // a box is part of its set
  if (it.status === 'printed') return <span className="mono text-[10px] shrink-0 text-[var(--color-faint)]">not required</span>
  const b = it.status === 'missing' ? SOURCE.missing : SOURCE[it.source]
  return <span className="mono text-[10px] shrink-0" style={{ color: b.c }}>{it.status === 'missing' && it.source === 'computed' ? 'no data' : b.label}</span>
}

function pct(v: unknown) { return typeof v === 'number' ? `${v}%` : '—' }

function Graph({ v }: { v: any }) {
  const rows = Object.entries(v.graph ?? {}) as [string, any][]
  return (
    <div className="overflow-x-auto mt-1">
      <table className="mono text-[11px] tabular-nums">
        <thead><tr className="text-[var(--color-faint)]">{['', 'fossil gas', 'nuclear', 'aligned (no gas & nuclear)', 'not aligned', 'KPIs stated'].map(h => <th key={h} className="text-left pr-4 font-normal">{h}</th>)}</tr></thead>
        <tbody>{rows.map(([b, g]) => (
          <tr key={b}><td className="pr-4 text-[var(--color-mute)]">{b}</td><td className="pr-4">{pct(g.fossil_gas)}</td><td className="pr-4">{pct(g.nuclear)}</td>
            <td className="pr-4">{pct(g.aligned_other)}</td><td className="pr-4">{pct(g.not_aligned)}</td><td className="pr-4 text-[var(--color-faint)]">{pct(g.kpi_coverage)}</td></tr>
        ))}</tbody>
      </table>
      {v.share_of_total != null && <div className="text-[10.5px] text-[var(--color-faint)] mt-1">This graph represents {v.share_of_total}% of the total investments.</div>}
    </div>
  )
}

function Value({ it, items }: { it: DocItem; items: DocItem[] }) {
  const v = it.value
  if (v == null) return it.needs ? <div className="text-[11px] text-[var(--color-warn)] mt-1">Needed: {it.needs}</div> : null
  if (v.graph) return <Graph v={v} />
  if (v.table) return (   // a computed table that carries its own columns (an ORSA impact analysis, a recovery-plan stress)
    <div className="overflow-x-auto mt-1">
      <table className="text-[11.5px] tabular-nums">
        <thead><tr className="text-[var(--color-faint)]">{v.table.columns.map((c: any) => <th key={c.id} className="text-left pr-4 font-normal">{c.label}</th>)}</tr></thead>
        <tbody>{v.table.rows.map((r: any, i: number) => <tr key={i}>{v.table.columns.map((c: any) => <td key={c.id} className="pr-4">{typeof r[c.id] === 'number' ? r[c.id].toLocaleString() : (r[c.id] ?? '—')}</td>)}</tr>)}</tbody>
      </table>
      {v.table.note && <div className="text-[10.5px] text-[var(--color-faint)] mt-1 max-w-3xl">{v.table.note}</div>}
    </div>
  )
  if (v.rows) {
    const cols = items.filter(c => c.parent === it.id && c.kind === 'table_column')
    return (
      <div className="overflow-x-auto mt-1"><table className="text-[11.5px] tabular-nums">
        <thead><tr className="text-[var(--color-faint)]">{cols.map(c => <th key={c.id} className="text-left pr-4 font-normal">{c.label}</th>)}</tr></thead>
        <tbody>{v.rows.map((r: any, i: number) => <tr key={i}>{cols.map(c => <td key={c.id} className="pr-4">{r[c.id] ?? '—'}</td>)}</tr>)}</tbody>
      </table></div>
    )
  }
  if (v.sectors) return (
    <div className="text-[12px] text-[var(--color-mute)] mt-1">
      {v.sectors.map((s: any) => <div key={s.sector}>{s.sector}: {s.pct}%</div>)}
      {v.fossil_fuel_pct != null && <div className="mt-1">Investments in the fossil fuel sector: {v.fossil_fuel_pct}%</div>}
    </div>
  )
  if (v.values) return (
    <div className="text-[12px] text-[var(--color-mute)] mt-1">
      {Object.entries(v.values).map(([k, n]) => <div key={k}>{items.find(c => c.id === k)?.label ?? k}: {String(n)}%</div>)}
    </div>
  )
  const parts = [v.text, v.percent != null ? `${v.percent}%` : null].filter(Boolean)
  return parts.length ? <div className="text-[12px] text-[var(--color-mute)] mt-1 whitespace-pre-wrap">{parts.join(' · ')}</div> : null
}

function Editor({ it, items, onSave, onCancel }: { it: DocItem; items: DocItem[]; onSave: (v: any) => Promise<void>; onCancel: () => void }) {
  const v = it.value ?? {}
  const [text, setText] = useState<string>(v.text ?? '')
  const [percent, setPercent] = useState<string>(v.percent != null ? String(v.percent) : '')
  const [ticked, setTicked] = useState<boolean>(!!v.ticked)
  const cats = items.filter(c => c.parent === it.id && c.kind === 'chart_label' && !PLACEHOLDER.test(c.label))
  const [vals, setVals] = useState<Record<string, string>>(Object.fromEntries(cats.map(c => [c.id, v.values?.[c.id] != null ? String(v.values[c.id]) : ''])))
  const [busy, setBusy] = useState(false)
  const input = 'block w-full mt-0.5 rounded border border-[var(--color-line-2)] bg-transparent px-2 py-1 text-[12px]'
  const build = () => {
    if (it.kind === 'choice') return { ticked, ...(it.blank === 'percent' && percent !== '' ? { percent: Number(percent) } : {}), ...(it.blank === 'text' && text ? { text } : {}) }
    if (it.kind === 'chart') return { values: Object.fromEntries(Object.entries(vals).filter(([, x]) => x !== '').map(([k, x]) => [k, Number(x)])) }
    return { ...(text ? { text } : {}), ...(it.kind === 'question' && percent !== '' ? { percent: Number(percent) } : {}) }
  }
  const save = async () => { setBusy(true); try { await onSave(build()) } finally { setBusy(false) } }
  return (
    <div className="mt-2 space-y-2 max-w-xl">
      {it.kind === 'choice' && (
        <label className="flex items-center gap-2 text-[12px]"><input type="checkbox" checked={ticked} onChange={e => setTicked(e.target.checked)} /> ticked</label>
      )}
      {it.kind === 'chart' && cats.map(c => (
        <label key={c.id} className="block text-[11.5px] text-[var(--color-mute)]">{c.label}
          <input type="number" min={0} max={100} step="0.1" value={vals[c.id]} onChange={e => setVals(s => ({ ...s, [c.id]: e.target.value }))} className={input} />
        </label>
      ))}
      {(it.kind === 'question' || it.kind === 'field' || it.blank === 'text') && (
        <textarea rows={it.kind === 'field' ? 1 : 4} value={text} onChange={e => setText(e.target.value)} className={input} placeholder="answer" />
      )}
      {(it.kind === 'question' || it.blank === 'percent') && (
        <input type="number" min={0} max={100} step="0.1" value={percent} onChange={e => setPercent(e.target.value)} className={input}
          placeholder={it.kind === 'question' ? 'percentage, where the question asks for one' : 'percentage'} />
      )}
      <div className="flex items-center gap-3">
        <Button variant="primary" onClick={save} disabled={busy}>Save</Button>
        <button onClick={onCancel} className="mono text-[11px] text-[var(--color-mute)] hover:underline">cancel</button>
      </div>
    </div>
  )
}

const HIDE = new Set(['chart_label', 'table_column'])   // shown inside their chart / table

export function DocumentItems({ items, onAnswer }: { items: DocItem[]; onAnswer?: (id: string, value: any) => Promise<void> }) {
  const [editing, setEditing] = useState<string | null>(null)
  const depth = (it: DocItem) => { let d = 0, p = it.parent; while (p) { d++; p = items.find(x => x.id === p)?.parent ?? null } return d }
  return (
    <div className="divide-y divide-[var(--color-line)]">
      {items.filter(it => !HIDE.has(it.kind)).map(it => {
        const pad = { paddingLeft: `${20 + Math.min(depth(it), 4) * 16}px` }
        if (it.kind === 'heading') return <div key={it.id} className="px-5 py-2.5 text-[13px] font-medium text-[var(--color-good)]">{it.label}</div>
        if (it.kind === 'definition') return <div key={it.id} style={pad} className="pr-5 py-2 text-[11px] text-[var(--color-faint)] border-l-2 border-[var(--color-line-2)]">{it.label}</div>
        if (it.kind === 'text') {
          // a print mark its chart fills ('This graph represents x% …') gives way to the chart's own figure
          const chart = items.find(c => c.id === it.parent && c.kind === 'chart')
          if (chart?.value && /\bx%/i.test(it.label)) return null
          return it.label ? <div key={it.id} style={pad} className="pr-5 py-2 text-[11.5px] text-[var(--color-mute)]">{it.label}</div> : null
        }
        const canEdit = onAnswer && it.source === 'input' && editing !== it.id
        return (
          <div key={it.id} style={pad} className="pr-5 py-2.5">
            <div className="flex items-start justify-between gap-3">
              <div className={`text-[12.5px] ${it.kind === 'question' ? 'text-[var(--color-ink)]' : 'text-[var(--color-mute)]'} max-w-[75%]`}>
                {it.kind === 'choice' && <span className="mono mr-1.5">{it.value?.ticked ? '☒' : '☐'}</span>}
                {it.label || (it.kind === 'chart' ? 'Asset allocation' : '')}
                {it.kind === 'choice' && it.value?.percent != null && <span className="mono text-[var(--color-ink)]"> — {it.value.percent}%</span>}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <Badge it={it} />
                {canEdit && <button onClick={() => setEditing(it.id)} className="mono text-[10.5px] text-[var(--color-sky)] hover:underline">{it.status === 'missing' ? 'answer' : 'edit'}</button>}
              </div>
            </div>
            {it.instruction && <div className="text-[10.5px] italic text-[var(--color-faint)] mt-0.5">{it.instruction}</div>}
            {it.note && <div className="text-[10.5px] text-[var(--color-faint)] mt-0.5">{it.note}</div>}
            {editing === it.id && onAnswer
              ? <Editor it={it} items={items} onCancel={() => setEditing(null)} onSave={async v => { await onAnswer(it.id, v); setEditing(null) }} />
              : it.kind !== 'choice' && <Value it={it} items={items} />}
          </div>
        )
      })}
    </div>
  )
}
