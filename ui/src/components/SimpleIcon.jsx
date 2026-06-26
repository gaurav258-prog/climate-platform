/**
 * Minimalist BCG/McKinsey style icons
 * Simple geometric SVG shapes for regulatory reporting module
 */
export default function SimpleIcon({ type, className = 'w-10 h-10 stroke-current stroke-1.5' }) {
  const s = className

  if (type === 'bars') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="12" width="3" height="9" />
      <rect x="10" y="6" width="3" height="15" />
      <rect x="17" y="3" width="3" height="18" />
    </svg>
  )

  if (type === 'check') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" />
      <path d="M7 12 L11 16 L17 8" />
    </svg>
  )

  if (type === 'trend') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <path d="M3 21 L8 13 L13 16 L21 5" />
    </svg>
  )

  if (type === 'cal') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="4" width="18" height="17" rx="1" />
      <line x1="3" y1="9" x2="21" y2="9" />
    </svg>
  )

  if (type === 'stack') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="3" width="18" height="4" />
      <rect x="3" y="9" width="18" height="4" />
      <rect x="3" y="15" width="18" height="4" />
    </svg>
  )

  if (type === 'compare') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <rect x="3" y="6" width="7" height="12" />
      <rect x="14" y="3" width="7" height="15" />
    </svg>
  )

  if (type === 'alert') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <path d="M12 3 L21 18 H3 Z" />
    </svg>
  )

  if (type === 'file') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <path d="M4 4 L4 20 Q4 21 5 21 L19 21 Q20 21 20 20 L20 9 L14 3 L5 3 Q4 3 4 4" />
    </svg>
  )

  if (type === 'branch') return (
    <svg className={s} viewBox="0 0 24 24" fill="none">
      <circle cx="6" cy="4" r="2" />
      <circle cx="6" cy="20" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M6 6 L6 18 M6 12 L18 12" />
    </svg>
  )

  return null
}
