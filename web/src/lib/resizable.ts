import { useState, useCallback, useEffect } from 'react'

// A persisted, drag-to-resize width. Used by the left nav (side='left', handle on its right edge) and the
// right-hand drawers (side='right', handle on their left edge). Width is clamped to [min,max] and stored in
// localStorage under `key`, so the user's chosen size survives reloads and applies everywhere that panel opens.
export function useResizableWidth(key: string, def: number, min: number, max: number, side: 'left' | 'right' = 'left') {
  const [width, setWidth] = useState<number>(() => {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v >= min && v <= max ? v : def
  })

  useEffect(() => { localStorage.setItem(key, String(Math.round(width))) }, [key, width])

  const startResize = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
    const startX = clientX
    const startW = width
    const move = (ev: MouseEvent | TouchEvent) => {
      const cx = 'touches' in ev ? ev.touches[0].clientX : ev.clientX
      const delta = side === 'left' ? cx - startX : startX - cx
      setWidth(Math.min(max, Math.max(min, startW + delta)))
    }
    const up = () => {
      document.removeEventListener('mousemove', move)
      document.removeEventListener('mouseup', up)
      document.removeEventListener('touchmove', move)
      document.removeEventListener('touchend', up)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
    document.addEventListener('mousemove', move)
    document.addEventListener('mouseup', up)
    document.addEventListener('touchmove', move, { passive: false })
    document.addEventListener('touchend', up)
  }, [width, min, max, side])

  return { width, setWidth, startResize }
}

// double-click a handle to reset to default
export function useResetOnDouble(setWidth: (n: number) => void, def: number) {
  return useCallback(() => setWidth(def), [setWidth, def])
}
