import { RAG, STATUS_WORD, level, type Kpi } from './model'

// Where an indicator sits against its appetite band: a track in three zones (within, warning, breach — in the
// direction the band says is worse) with a mark at today's value. Only for an indicator with a band and a value.
export default function AppetiteBar({ k, showLevels }: { k: Kpi; showLevels?: boolean }) {
  const { value: v, amber, red } = k
  if (v == null || (amber == null && red == null)) return null
  const lower = k.direction === 'lower_worse'
  const edges = [amber, red].filter((x): x is number => x != null)
  const top = Math.max(v, ...edges) * (k.fmt === 'pct' ? 1 : 1.25)
  const max = k.fmt === 'pct' ? Math.max(100, top) : Math.max(top, 1)
  const at = (x: number) => `${Math.max(0, Math.min(100, (100 * x) / max))}%`
  // zones in value order, each with the colour of what a value there means
  const a = amber ?? red!, r = red ?? amber!
  const zones = lower
    ? [{ from: 0, to: r, c: RAG.red }, { from: r, to: a, c: RAG.amber }, { from: a, to: max, c: RAG.ok }]
    : [{ from: 0, to: a, c: RAG.ok }, { from: a, to: r, c: RAG.amber }, { from: r, to: max, c: RAG.red }]
  const where = k.status ? STATUS_WORD[k.status] : 'Not graded'
  return (
    <div>
      <div className="relative h-1.5 rounded-full overflow-hidden bg-[var(--color-panel-2)]" role="img"
        aria-label={`${where}: warning at ${level(k, amber)}, breach at ${level(k, red)}`}>
        {zones.filter(z => z.to > z.from).map((z, i) => (
          <span key={i} className="absolute inset-y-0" style={{ left: at(z.from), width: `calc(${at(z.to)} - ${at(z.from)})`, background: z.c, opacity: 0.32 }} />
        ))}
      </div>
      <div className="relative h-0">
        <span className="absolute -top-[9px] w-[3px] h-3 rounded-full -translate-x-1/2 shadow-[0_0_0_1.5px_var(--color-panel)]"
          style={{ left: at(v), background: k.status ? RAG[k.status] : 'var(--color-ink)' }} />
      </div>
      {showLevels && (
        <div className="flex justify-between text-[11px] text-[var(--color-faint)] mt-2 tabular-nums">
          <span>{lower ? 'Lower is worse' : 'Higher is worse'}</span>
          <span>{amber != null && <>Warning {level(k, amber)}</>}{amber != null && red != null && ' · '}{red != null && <>Breach {level(k, red)}</>}</span>
        </div>
      )}
    </div>
  )
}
