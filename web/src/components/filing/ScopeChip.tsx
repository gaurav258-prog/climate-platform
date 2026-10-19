import { scopeOf, SCOPE_WORD } from './words'

// Who a filing or obligation is for: one legal entity on its own (solo), a group consolidated over its subtree, or a
// fund (a financial product's SFDR template). A whole-organisation filing needs no chip.
const TONE = { solo: 'var(--color-sky)', consolidated: 'var(--color-viz, #a78bfa)', product: 'var(--color-good)' } as const

export function ScopeChip({ role, scope, name }: { role?: string | null; scope?: string; name?: string | null }) {
  const r = scopeOf(role, scope)
  if (r === 'whole_org') return null
  const c = TONE[r]
  return (
    <span className="text-[11px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap" style={{ color: c, background: `color-mix(in oklab, ${c} 14%, transparent)` }}>
      {SCOPE_WORD[r]}{name ? ` · ${name}` : ''}
    </span>
  )
}
