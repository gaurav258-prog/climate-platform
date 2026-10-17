// The intake page's two small charts, in the product's own colours: a ring for a share (how much of something is in
// place) and one bar split into its parts (valid / with problems, located / not located). Text stays in ink; the
// coloured mark beside each legend entry carries the meaning, and every mark names itself on hover.

export function Gauge({ share, center, caption, color, label }: {
  share: number | null; center: string; caption: string; color: string; label: string
}) {
  const r = 34, c = 2 * Math.PI * r
  const v = share == null ? 0 : Math.max(0, Math.min(1, share))
  return (
    <div className="flex flex-col items-center shrink-0" role="img" aria-label={label} title={label}>
      <svg width="88" height="88" viewBox="0 0 88 88" aria-hidden="true">
        <circle cx="44" cy="44" r={r} fill="none" stroke="var(--color-panel-2)" strokeWidth="8" />
        {v > 0 && <circle cx="44" cy="44" r={r} fill="none" stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${Math.max(v * c, 4)} ${c}`} transform="rotate(-90 44 44)" />}
        <text x="44" y="49" textAnchor="middle" fontSize="16" fontWeight="600" fill="var(--color-ink)" className="tabular-nums">{center}</text>
      </svg>
      <div className="text-[11.5px] text-[var(--color-mute)] mt-1 text-center">{caption}</div>
    </div>
  )
}

export type Part = { label: string; value: number; color: string; onClick?: () => void }

export function SplitBar({ parts, label }: { parts: Part[]; label: string }) {
  const total = parts.reduce((a, p) => a + p.value, 0)
  return (
    <div>
      <div className="flex h-3 gap-[2px] rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img" aria-label={label}>
        {total > 0 && parts.filter(p => p.value > 0).map(p => p.onClick
          ? <button key={p.label} type="button" onClick={p.onClick} aria-label={p.label} title={p.label}
              className="h-full cursor-pointer hover:opacity-80 transition" style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />
          : <div key={p.label} title={p.label} className="h-full" style={{ width: `${(p.value / total) * 100}%`, background: p.color }} />)}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-[11.5px] text-[var(--color-mute)] tabular-nums">
        {parts.map(p => (
          <span key={p.label} className="inline-flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />{p.label}
          </span>
        ))}
      </div>
    </div>
  )
}
