// Tellumen mark: a hexagon (the H3 cell) holding a rising lumen (light) —
// "light on the Earth". Self-contained colours so it reads on light or dark.
export default function BrandMark({ size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden="true" style={{ display: 'block' }}>
      <defs>
        <linearGradient id="bm-hex" x1="24" y1="3" x2="24" y2="45" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0b4a9e" />
          <stop offset="1" stopColor="#04070f" />
        </linearGradient>
        <radialGradient id="bm-lumen" cx="24" cy="17" r="15" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#bfe4ff" />
          <stop offset="0.45" stopColor="#3aa0ff" stopOpacity="0.6" />
          <stop offset="1" stopColor="#3aa0ff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <polygon points="44,24 34,41.3 14,41.3 4,24 14,6.7 34,6.7"
        fill="url(#bm-hex)" stroke="#3aa0ff" strokeOpacity="0.55" strokeWidth="1.5" strokeLinejoin="round" />
      <circle cx="24" cy="17" r="14" fill="url(#bm-lumen)" />
      <circle cx="24" cy="15.5" r="3.1" fill="#eaf6ff" />
    </svg>
  )
}
