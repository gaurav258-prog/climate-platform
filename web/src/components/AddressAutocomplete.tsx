import { useEffect, useState } from 'react'
import { Loader2, Check, AlertCircle, MapPin } from 'lucide-react'
import { api } from '../lib/api'

export type Place = { display_name: string; lat: number; lon: number; precision?: string; confidence?: number; low_confidence?: boolean }

// Debounced address → ranked, SELECTABLE place candidates. The user picks the right place;
// the parent gets the exact chosen coordinates (no re-geocode drift). Shared by Operations
// (own sites) and Sourcing (supplier plots) so the interaction is identical everywhere.
export default function AddressAutocomplete({
  value, onValueChange, selected, onSelect, disabled = false, placeholder = 'Start typing a place…',
}: {
  value: string
  onValueChange: (v: string) => void
  selected: Place | null
  onSelect: (p: Place) => void
  disabled?: boolean
  placeholder?: string
}) {
  const [state, setState] = useState<'idle' | 'searching' | 'ready' | 'none'>('idle')
  const [results, setResults] = useState<Place[]>([])
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const term = value.trim()
    if (disabled || term.length < 2 || (selected && term === selected.display_name)) { setState('idle'); setResults([]); return }
    setState('searching')
    const id = setTimeout(async () => {
      try {
        const r = await api.get<{ results: Place[] }>(`/v1/supply/geocode?q=${encodeURIComponent(term)}`)
        setResults(r.results); setState(r.results.length ? 'ready' : 'none'); setOpen(r.results.length > 0)
      } catch { setResults([]); setState('none') }
    }, 450)
    return () => clearTimeout(id)
  }, [value, disabled, selected])

  const pick = (p: Place) => { onSelect(p); setOpen(false); setState('idle'); setResults([]) }

  return (
    <div>
      <div className="relative">
        <input className={inp} value={value} placeholder={placeholder} disabled={disabled}
          onChange={e => onValueChange(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={e => { if (e.key === 'Escape') setOpen(false) }} />
        {!disabled && state === 'searching' && <Loader2 size={13} className="animate-spin absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--color-faint)]" />}
        {!disabled && selected && <Check size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--color-good)]" />}
        {open && !disabled && results.length > 0 && (
          <ul className="absolute z-20 mt-1 w-full max-h-60 overflow-auto rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] shadow-xl">
            {results.map((p, i) => (
              <li key={i}>
                <button type="button" onMouseDown={e => { e.preventDefault(); pick(p) }}
                  className="w-full text-left px-3 py-2 text-[12.5px] leading-snug hover:bg-[var(--color-bg)] flex items-start gap-2">
                  <MapPin size={13} className="mt-0.5 shrink-0 text-[var(--color-sky)]" />
                  <span className="text-[var(--color-ink)]">{p.display_name}
                    <span className="mono text-[10.5px] text-[var(--color-faint)] ml-1">({p.lat.toFixed(2)}, {p.lon.toFixed(2)})</span>
                    {p.low_confidence && <span className="ml-1.5 inline-flex items-center gap-0.5 align-middle mono text-[9.5px] text-[var(--color-warn)]"><AlertCircle size={10} /> {p.precision === 'country' || p.precision === 'region' ? p.precision + '-level' : 'low confidence'}</span>}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!disabled && selected && !selected.low_confidence && <div className="mt-1.5 text-[11px] text-[var(--color-good)]">selected · {selected.lat.toFixed(3)}, {selected.lon.toFixed(3)}</div>}
      {!disabled && selected && selected.low_confidence && <div className="mt-1.5 text-[11px] flex items-center gap-1.5 text-[var(--color-warn)]"><AlertCircle size={12} /> coarse location ({selected.precision}) · confirm or use exact coordinates for a precise score</div>}
      {!disabled && !selected && state === 'none' && <div className="mt-1.5 text-[11px] flex items-center gap-1.5 text-[var(--color-warn)]"><AlertCircle size={12} /> no match — add city/country, or use coordinates</div>}
    </div>
  )
}

const inp = 'w-full bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)] disabled:opacity-50'
