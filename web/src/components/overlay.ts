import { useEffect, useRef } from 'react'

// Shared behaviour of the two overlay primitives (Dialog, Drawer): Escape closes, focus moves into the panel on open,
// Tab and Shift+Tab stay inside the panel while it is open (it is aria-modal — the page behind is not reachable), and
// focus returns to where it was on close. Open overlays form a stack, so when one opens over another (a gate dialog
// over the task drawer) Escape closes only the top one.
const stack: object[] = []

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]), [contenteditable="true"]'
// the panel's tabbable elements in order, skipping anything not rendered (display:none / hidden ancestors)
function tabbables(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(el => el.getClientRects().length > 0)
}

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
      if (stack[stack.length - 1] !== me) return
      if (e.key === 'Escape') { e.stopPropagation(); close.current(); return }
      // focus trap: wrap Tab at the panel's edges, and pull focus back in if it has left the panel
      const panel = box.current
      if (e.key !== 'Tab' || !panel) return
      const items = tabbables(panel)
      if (items.length === 0) { e.preventDefault(); panel.focus(); return }
      const first = items[0], last = items[items.length - 1], at = document.activeElement
      if (!panel.contains(at)) { e.preventDefault(); (e.shiftKey ? last : first).focus() }
      else if (e.shiftKey && (at === first || at === panel)) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus() }
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
