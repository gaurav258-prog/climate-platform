import { useState, useEffect, useMemo, useRef } from 'react'
import { Search, ArrowRight, BookOpen, LifeBuoy, ShieldCheck, CornerDownLeft } from 'lucide-react'

// Flatten the tenant's catalog into one searchable list of {label, sublabel, group, onSelect}.
// Every workflow page, every Trust & assurance doc, plus the fixed areas (Documentation,
// Service portal, Admin) — the same set a user could otherwise only find by clicking
// through the sidebar tree one level at a time.
function buildIndex(catalog, { onNavigate, onDocs, onArea, canSeePortal, canSeeAdmin }) {
  const items = []
  for (const off of catalog?.offerings || []) {
    for (const svc of off.services) {
      items.push({
        id: `svc:${off.id}:${svc.id}`, group: off.label, label: svc.label, sublabel: svc.blurb,
        onSelect: () => onNavigate(off.id, svc.id),
      })
    }
  }
  items.push({ id: 'docs:start', group: 'Documentation', label: 'Getting started', icon: BookOpen, onSelect: () => onDocs('start') })
  items.push({ id: 'docs:method', group: 'Documentation', label: 'Methodology & model cards', icon: BookOpen, onSelect: () => onDocs('method') })
  items.push({ id: 'docs:data', group: 'Documentation', label: 'Data sources', icon: BookOpen, onSelect: () => onDocs('data') })
  items.push({ id: 'docs:api', group: 'Documentation', label: 'API reference', icon: BookOpen, onSelect: () => onDocs('api') })
  items.push({ id: 'docs:reg', group: 'Documentation', label: 'Regulatory mapping', icon: BookOpen, onSelect: () => onDocs('reg') })
  if (canSeePortal) items.push({ id: 'area:portal', group: 'Support', label: 'Service portal', icon: LifeBuoy, onSelect: () => onArea('portal') })
  if (canSeeAdmin) items.push({ id: 'area:admin', group: 'Support', label: 'Admin', icon: ShieldCheck, onSelect: () => onArea('admin') })
  return items
}

export default function CommandPalette({ open, onClose, catalog, onNavigate, onDocs, onArea, canSeePortal, canSeeAdmin }) {
  const [q, setQ] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef(null)

  const index = useMemo(() => buildIndex(catalog, { onNavigate, onDocs, onArea, canSeePortal, canSeeAdmin }),
    [catalog, onNavigate, onDocs, onArea, canSeePortal, canSeeAdmin])

  const results = useMemo(() => {
    const term = q.trim().toLowerCase()
    if (!term) return index
    return index.filter(i => i.label.toLowerCase().includes(term) || i.group.toLowerCase().includes(term)
      || i.sublabel?.toLowerCase().includes(term))
  }, [q, index])

  useEffect(() => { if (open) { setQ(''); setActive(0); setTimeout(() => inputRef.current?.focus(), 0) } }, [open])
  useEffect(() => { setActive(0) }, [q])

  const select = (item) => { if (!item) return; item.onSelect(); onClose() }

  const onKeyDown = (e) => {
    if (e.key === 'Escape') { onClose(); return }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, results.length - 1)); return }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); return }
    if (e.key === 'Enter') { e.preventDefault(); select(results[active]); return }
  }

  if (!open) return null

  let lastGroup = null
  return (
    <div className="fixed inset-0 z-[9998] flex items-start justify-center bg-black/30 pt-[12vh]" onClick={onClose}>
      <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center gap-2.5 border-b border-gray-100 px-4 py-3">
          <Search size={16} className="text-gray-400" />
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)} onKeyDown={onKeyDown}
            placeholder="Search modules, methodology, support…"
            className="flex-1 text-[14px] text-[#1d1d1f] placeholder:text-gray-400 focus:outline-none" />
          <kbd className="rounded border border-gray-200 px-1.5 py-0.5 text-[10px] text-gray-400">esc</kbd>
        </div>
        <div className="max-h-[50vh] overflow-y-auto py-1.5">
          {results.length === 0 && <p className="px-4 py-6 text-center text-[13px] text-gray-400">No matches.</p>}
          {results.map((item, i) => {
            const showGroup = item.group !== lastGroup
            lastGroup = item.group
            return (
              <div key={item.id}>
                {showGroup && <div className="px-4 pt-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-400">{item.group}</div>}
                <button onClick={() => select(item)} onMouseEnter={() => setActive(i)}
                  className={`flex w-full items-center justify-between gap-3 px-4 py-2 text-left ${i === active ? 'bg-[#0071e3]/[0.06]' : ''}`}>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium text-[#1d1d1f]">{item.label}</span>
                    {item.sublabel && <span className="block truncate text-[11px] text-gray-400">{item.sublabel}</span>}
                  </span>
                  {i === active ? <CornerDownLeft size={13} className="shrink-0 text-[#0071e3]" /> : <ArrowRight size={13} className="shrink-0 text-gray-300" />}
                </button>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
