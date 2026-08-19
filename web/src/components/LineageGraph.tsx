// Static audit-trail graph — renders a filing cell's lineage as a branching node tree:
//   Reported figure → contributing assets → the golden source → the source feeds.
// Deterministic SVG (positions computed in JS, so no fragile measurement), colour-coded by node type.

interface Source { key: string; name: string; status: string | null }
interface Contributor { asset_id: string; asset_name: string; value_eur: number | null; granular: { model_version: string | null } | null }
interface Props { hazardLabel: string; exposed: number | null; contributors: Contributor[]; sources: Source[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`
const feedDot = (s: string | null) => s === 'fresh' || s === 'live' ? '#34d399' : s === 'overdue' || s === 'failed' ? '#fb7185' : s === 'due_soon' ? '#e8b24c' : '#94a3b8'

const NODE_W = 168
const NODE_H = 30
const GAP_Y = 10
const COL_X = [8, 220, 432, 620]   // reported · assets · golden · feeds

export default function LineageGraph({ hazardLabel, exposed, contributors, sources }: Props) {
  const assets = contributors.slice(0, 6)
  const moreAssets = contributors.length - assets.length
  const model = assets.find(a => a.granular?.model_version)?.granular?.model_version ?? 'canonical_scores'

  // node lists per column with their center-y
  const colY = (n: number, h: number) => {
    const total = n * NODE_H + (n - 1) * GAP_Y
    const start = (h - total) / 2
    return Array.from({ length: n }, (_, i) => start + i * (NODE_H + GAP_Y) + NODE_H / 2)
  }
  const rows = Math.max(assets.length + (moreAssets > 0 ? 1 : 0), sources.length, 1)
  const H = Math.max(140, rows * (NODE_H + GAP_Y) + 20)
  const W = COL_X[3] + NODE_W + 8

  const assetNodes = assets.length + (moreAssets > 0 ? 1 : 0)
  const aY = colY(assetNodes, H)
  const sY = colY(Math.max(sources.length, 1), H)
  const cellY = H / 2, goldY = H / 2

  const cx = (col: number) => COL_X[col]
  const path = (x1: number, y1: number, x2: number, y2: number) => {
    const mx = (x1 + x2) / 2
    return `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`
  }

  return (
    <div className="overflow-x-auto">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="min-w-[720px]">
        {/* connectors: cell→assets, assets→golden, golden→feeds */}
        {aY.slice(0, assets.length).map((y, i) => (
          <path key={`ca${i}`} d={path(cx(0) + NODE_W, cellY, cx(1), y)} stroke="var(--color-line-2)" fill="none" strokeWidth={1} />
        ))}
        {aY.slice(0, assets.length).map((y, i) => (
          <path key={`ag${i}`} d={path(cx(1) + NODE_W, y, cx(2), goldY)} stroke="var(--color-line-2)" fill="none" strokeWidth={1} />
        ))}
        {sY.slice(0, sources.length).map((y, i) => (
          <path key={`gf${i}`} d={path(cx(2) + NODE_W, goldY, cx(3), y)} stroke="var(--color-line-2)" fill="none" strokeWidth={1} />
        ))}

        {/* column labels */}
        {['Reported', 'Assets', 'Golden source', 'Feeds'].map((l, i) => (
          <text key={l} x={cx(i)} y={12} className="mono" fontSize={8} fill="var(--color-faint)" style={{ letterSpacing: '.1em', textTransform: 'uppercase' }}>{l}</text>
        ))}

        {/* reported cell */}
        <Node x={cx(0)} y={cellY} fill="#0e749022" stroke="#38bec9" label={hazardLabel} sub={eur(exposed)} />
        {/* assets */}
        {assets.map((a, i) => <Node key={a.asset_id} x={cx(1)} y={aY[i]} fill="var(--color-panel-2)" stroke="var(--color-line-2)" label={a.asset_name} sub={eur(a.value_eur)} />)}
        {moreAssets > 0 && <Node x={cx(1)} y={aY[assets.length]} fill="transparent" stroke="var(--color-line)" label={`+ ${moreAssets} more`} sub="" />}
        {/* golden source */}
        <Node x={cx(2)} y={goldY} fill="#15803d22" stroke="#34d399" label="canonical_scores" sub={model} />
        {/* feeds */}
        {sources.length === 0
          ? <Node x={cx(3)} y={sY[0]} fill="transparent" stroke="var(--color-line)" label="not mapped" sub="" />
          : sources.map((s, i) => <Node key={s.key} x={cx(3)} y={sY[i]} fill="var(--color-panel-2)" stroke={feedDot(s.status)} label={s.name} sub={s.status ?? ''} dot={feedDot(s.status)} />)}
      </svg>
    </div>
  )
}

function Node({ x, y, fill, stroke, label, sub, dot }: { x: number; y: number; fill: string; stroke: string; label: string; sub: string; dot?: string }) {
  const trunc = (t: string, n: number) => t.length > n ? t.slice(0, n - 1) + '…' : t
  return (
    <g>
      <rect x={x} y={y - NODE_H / 2} width={NODE_W} height={NODE_H} rx={6} fill={fill} stroke={stroke} strokeWidth={1} />
      {dot && <circle cx={x + 8} cy={y - 5} r={2.5} fill={dot} />}
      <text x={x + (dot ? 15 : 8)} y={y - 2} fontSize={9.5} fill="var(--color-ink)">{trunc(label, 22)}</text>
      {sub && <text x={x + 8} y={y + 9} fontSize={8} className="mono" fill="var(--color-faint)">{trunc(sub, 26)}</text>}
    </g>
  )
}
