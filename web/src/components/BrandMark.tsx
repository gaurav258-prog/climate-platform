import { useId } from 'react'
import clsx from 'clsx'

// The Tellumen mark (docs/BRAND.md §4): a hexagon — the H3 cell the engine tessellates the Earth into — holding a
// rising lumen. Bold stroke + bright core so it reads at small nav sizes; self-contained colours so it works on light
// or dark. Never recolour, rotate or stretch it; minimum 20 px. public/favicon.svg carries the same geometry.
// Gradient ids are per instance: the shell renders the mark more than once, and a url(#id) that resolves into a
// hidden copy (the sidebar below md, the small-screen header above it) paints nothing.
export function BrandMark({ size = 28 }: { size?: number }) {
  const id = useId()
  const hex = `${id}-hex`, lumen = `${id}-lumen`
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden style={{ display: 'block', flexShrink: 0 }}>
      <defs>
        <linearGradient id={hex} x1="24" y1="4" x2="24" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1560c4" />
          <stop offset="1" stopColor="#06152e" />
        </linearGradient>
        <radialGradient id={lumen} cx="24" cy="22" r="15" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.35" stopColor="#9fd4ff" />
          <stop offset="0.7" stopColor="#3aa0ff" stopOpacity="0.35" />
          <stop offset="1" stopColor="#3aa0ff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <polygon points="44,24 34,41.3 14,41.3 4,24 14,6.7 34,6.7"
        fill={`url(#${hex})`} stroke="#6cb8ff" strokeWidth="3" strokeLinejoin="round" />
      <circle cx="24" cy="22" r="12" fill={`url(#${lumen})`} />
      <circle cx="24" cy="21" r="4.6" fill="#f2f9ff" />
    </svg>
  )
}

// The wordmark (docs/BRAND.md §3): one word, with "lumen" lit — Sky on dark, Signal Blue on light. The colours are the
// --brand-* tokens in index.css, which follow the theme; size and layout come from the caller.
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={clsx('display font-semibold whitespace-nowrap text-[var(--brand-tel)]', className)}>
      Tel<span className="text-[var(--brand-lumen)]">lumen</span>
    </span>
  )
}
