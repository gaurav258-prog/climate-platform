// A tiny dependency-free toast bus. A module-level singleton so any handler — even a helper
// defined outside a component — can raise a toast without threading a hook through call sites.
// The <Toaster/> at the app root subscribes and renders. Replaces the native alert() dialogs,
// which broke the design system and blocked the main thread.

export type ToastKind = 'error' | 'success' | 'info'
export interface ToastItem { id: number; kind: ToastKind; message: string }

type Listener = (items: ToastItem[]) => void

let items: ToastItem[] = []
let listeners: Listener[] = []
let seq = 0

function emit(message: string, kind: ToastKind, ttl: number) {
  const id = ++seq
  items = [...items, { id, kind, message }]
  listeners.forEach(l => l(items))
  if (ttl > 0) setTimeout(() => dismiss(id), ttl)
  return id
}

export function dismiss(id: number) {
  items = items.filter(i => i.id !== id)
  listeners.forEach(l => l(items))
}

export function subscribe(l: Listener) {
  listeners.push(l)
  l(items)
  return () => { listeners = listeners.filter(x => x !== l) }
}

// Errors linger longer (the user needs to read what went wrong); success/info auto-clear quickly.
export const toast = {
  error: (message: string) => emit(message, 'error', 7000),
  success: (message: string) => emit(message, 'success', 4000),
  info: (message: string) => emit(message, 'info', 4500),
}
