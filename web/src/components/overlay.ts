import { useEffect, useRef } from 'react'

// Shared behaviour of the two overlay primitives (Dialog, Drawer): Escape closes, focus moves into the panel on open
// and returns to where it was on close. Open overlays form a stack, so when one opens over another (a gate dialog
// over the task drawer) Escape closes only the top one.
const stack: object[] = []

export function useOverlay<T extends HTMLElement>(onClose: () => void) {
  const box = useRef<T>(null)
  // the latest onClose, without re-running the open/close effect (callers pass a new function every render, and
  // re-running would pull focus back to the panel in the middle of the user's work)
  const close = useRef(onClose)
  // what had focus when the overlay was asked for — read at first render, before an autoFocus field inside takes it
  const opener = useRef(document.activeElement as HTMLElement | null)
  useEffect(() => { close.current = onClose }, [onClose])
  useEffect(() => {
    const me = {}
    stack.push(me)
    const before = opener.current
    // an autoFocus field inside the panel has already taken focus — leave it there
    if (!box.current?.contains(document.activeElement)) box.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || stack[stack.length - 1] !== me) return
      e.stopPropagation(); close.current()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      stack.splice(stack.indexOf(me), 1)
      before?.focus?.()
    }
  }, [])
  return box
}
