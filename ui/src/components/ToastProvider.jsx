import { createContext, useCallback, useContext, useRef, useState } from 'react'
import { CheckCircle2, XCircle, Info, X } from 'lucide-react'

// Shared toast/notification layer — the ONE place every workflow page reports
// "your action worked" / "your action failed", instead of each page hand-rolling
// its own banner or falling back to a native alert(). Mount <ToastHost/> once at
// the app root (see App.jsx) and call useToast() from any component.
const ToastContext = createContext(null)

const STYLES = {
  success: { icon: CheckCircle2, iconColor: 'text-emerald-500', border: 'border-emerald-100', bg: 'bg-white' },
  error:   { icon: XCircle,      iconColor: 'text-red-500',     border: 'border-red-100',     bg: 'bg-white' },
  info:    { icon: Info,         iconColor: 'text-[#0071e3]',   border: 'border-gray-200',     bg: 'bg-white' },
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const nextId = useRef(0)

  const dismiss = useCallback((id) => {
    setToasts(ts => ts.filter(t => t.id !== id))
  }, [])

  const push = useCallback((type, message, opts = {}) => {
    const id = ++nextId.current
    setToasts(ts => [...ts, { id, type, message }])
    const duration = opts.duration ?? (type === 'error' ? 6000 : 4000)
    if (duration) setTimeout(() => dismiss(id), duration)
    return id
  }, [dismiss])

  const api = useRef({
    success: (msg, opts) => push('success', msg, opts),
    error: (msg, opts) => push('error', msg, opts),
    info: (msg, opts) => push('info', msg, opts),
    dismiss,
  }).current

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[9999] flex w-full max-w-sm flex-col gap-2">
        {toasts.map(t => {
          const s = STYLES[t.type] || STYLES.info
          const Icon = s.icon
          return (
            <div key={t.id}
              className={`pointer-events-auto flex items-start gap-2.5 rounded-xl border ${s.border} ${s.bg} p-3.5 shadow-lg shadow-black/[0.06] transition`}>
              <Icon size={17} className={`mt-0.5 shrink-0 ${s.iconColor}`} />
              <p className="flex-1 text-[13px] leading-snug text-[#1d1d1f]">{t.message}</p>
              <button onClick={() => dismiss(t.id)} className="shrink-0 text-gray-300 hover:text-gray-500">
                <X size={14} />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast() must be called within <ToastProvider>')
  return ctx
}
