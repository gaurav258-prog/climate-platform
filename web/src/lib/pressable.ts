import type { KeyboardEvent } from 'react'

// Makes a clickable element that is not a <button> — a card, a stat tile, a table row, a map shape — reachable with
// Tab and operable with Enter / Space, so everything a mouse can open a keyboard can open too (and an overlay opened
// from it has somewhere to return focus). Spread it in place of onClick: `<div {...pressable(open)}>`. With no
// handler it returns nothing, so a conditionally clickable element stays inert.
//
// `row`: a table row keeps its row semantics (no role="button"); `expanded`: the element toggles a disclosure;
// `label`: an accessible name where the element has no readable text (an SVG shape).
export function pressable(onPress: (() => unknown) | '' | 0 | false | null | undefined, opts: { row?: boolean; expanded?: boolean; label?: string } = {}) {
  if (!onPress) return {}
  return {
    tabIndex: 0,
    role: opts.row ? undefined : 'button',
    'aria-expanded': opts.expanded,
    'aria-label': opts.label,
    onClick: onPress,
    onKeyDown: (e: KeyboardEvent) => {
      // only the element itself — Enter in a field or on a button inside it keeps its own meaning
      if (e.target !== e.currentTarget) return
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPress() }
    },
  }
}
