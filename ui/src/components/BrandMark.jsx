// Tellumen mark: a hexagon (the H3 cell) holding a lumen (light) — "light on the
// Earth". Bold stroke + bright core so it reads at small nav sizes. Self-contained
// colours so it works on light or dark.
export default function BrandMark({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ display: 'block' }}>
      <defs>
        <linearGradient id="bm-hex" x1="24" y1="4" x2="24" y2="44" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1560c4" />
          <stop offset="1" stopColor="#06152e" />
        </linearGradient>
        <radialGradient id="bm-lumen" cx="24" cy="22" r="15" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.35" stopColor="#9fd4ff" />
          <stop offset="0.7" stopColor="#3aa0ff" stopOpacity="0.35" />
          <stop offset="1" stopColor="#3aa0ff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <polygon points="44,24 34,41.3 14,41.3 4,24 14,6.7 34,6.7"
        fill="url(#bm-hex)" stroke="#6cb8ff" strokeWidth="3" strokeLinejoin="round" />
      <circle cx="24" cy="22" r="12" fill="url(#bm-lumen)" />
      <circle cx="24" cy="21" r="4.6" fill="#f2f9ff" />
    </svg>
  )
}
