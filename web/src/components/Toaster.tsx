import { useEffect, useState } from 'react'
import { CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'
import { subscribe, dismiss, type ToastItem } from '../lib/toast'

// Renders the toast stack (bottom-right), theme-aware, using the design tokens. Mounted once at
// the app root. Toasts slide in, auto-dismiss, and can be dismissed by hand. Replaces alert().

const STYLE: Record<ToastItem['kind'], { icon: typeof Info; accent: string; role: string }> = {
  error:   { icon: AlertTriangle, accent: 'var(--color-bad)',  role: 'alert' },
  success: { icon: CheckCircle2,  accent: 'var(--color-good)', role: 'status' },
  info:    { icon: Info,          accent: 'var(--color-sky)',  role: 'status' },
}

export default function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([])
  useEffect(() => subscribe(setItems), [])
  if (items.length === 0) return null
  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[min(92vw,380px)]" aria-live="polite">
      {items.map(t => {
        const s = STYLE[t.kind]
        const Icon = s.icon
        return (
          <div key={t.id} role={s.role}
            className="toast-in flex items-start gap-2.5 rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] shadow-lg px-3.5 py-3"
            style={{ borderLeft: `3px solid ${s.accent}` }}>
            <Icon size={16} style={{ color: s.accent }} className="shrink-0 mt-0.5" />
            <div className="flex-1 text-[12.5px] leading-snug text-[var(--color-ink)] break-words">{t.message}</div>
            <button onClick={() => dismiss(t.id)} aria-label="Dismiss"
              className="shrink-0 text-[var(--color-faint)] hover:text-[var(--color-ink)] transition -mr-0.5 -mt-0.5"><X size={14} /></button>
          </div>
        )
      })}
    </div>
  )
}
