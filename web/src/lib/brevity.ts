import { Children, isValidElement, type ReactNode } from 'react'

// How much text a node puts on the screen — the UI standard (2026-10-16) keeps the main screen to short lines and
// moves anything longer into the details pop-up (components/Details.tsx).

// The words a node shows.
export function textOf(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join(' ')
  if (isValidElement<{ children?: ReactNode }>(node)) return Children.toArray(node.props.children).map(textOf).join(' ')
  return ''
}

// Short enough to stay on the main screen: at most `words` words (a descriptor, not an explanation).
export const isShort = (node: ReactNode, words = 6): boolean => textOf(node).trim().split(/\s+/).filter(Boolean).length <= words
