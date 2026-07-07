// Three-lane data-flow diagram: client input → Tellumen engine → disclosure
// output. Same shape for every sector — box count in lane 1 flexes to 1 or 2
// inputs, lane 2/3 are always 2 boxes. Content is plain data on `sector.flow`
// (see SolutionsPage.jsx) so it's easy to revise per vertical over time.

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
const INPUT = '#2F4C86', ENGINE = '#147159', OUTPUT = '#A66A26', ADMIN = '#6B7480'
const LINE = '#DCE0E8', INK = '#1C2430', MUTED = '#6B7480'

function FlowBox({ x, y, accent, title, sub, tag, tagColor }) {
  return (
    <g>
      <rect x={x} y={y} width={8} height={126} rx={4} fill={accent} />
      <rect x={x} y={y} width={300} height={130} rx={10} fill="white" stroke={LINE} />
      <text x={x + 24} y={y + 38} fontSize={15.5} fontWeight={700} fill={INK}>{title}</text>
      <text x={x + 24} y={y + 60} fontSize={12.5} fill={MUTED}>{sub}</text>
      {tag && (
        <text x={x + 24} y={y + 98} fontSize={11.5} fontWeight={700} fill={tagColor} fontFamily={MONO}>{tag}</text>
      )}
    </g>
  )
}

function FlowPill({ cx, cy, w, label, color }) {
  return (
    <g>
      <rect x={cx - w / 2} y={cy - 11} width={w} height={22} rx={11} fill="white" />
      <text x={cx} y={cy + 4} textAnchor="middle" fontFamily={MONO} fontSize={11.5} fontWeight={600} fill={color}>{label}</text>
    </g>
  )
}

function FlowCurve({ x1, y1, x2, y2, color, dashed, width, markerId }) {
  let d
  if (Math.abs(x1 - x2) < 2) {
    const midY = (y1 + y2) / 2
    d = `M${x1},${y1} C${x1},${y1 + (midY - y1) * 0.6} ${x2},${y2 - (y2 - midY) * 0.6} ${x2},${y2}`
  } else {
    const midX = (x1 + x2) / 2
    d = `M${x1},${y1} C${midX},${y1 - 17} ${midX},${y2 + 17} ${x2},${y2}`
  }
  return (
    <path d={d} fill="none" stroke={color} strokeWidth={width}
      strokeDasharray={dashed ? '2 6' : undefined} strokeLinecap="round"
      markerEnd={markerId ? `url(#${markerId})` : undefined} />
  )
}

export default function SectorFlowDiagram({ flow }) {
  const hasThird = flow.inputs.length > 1
  const xData = 550, xOpt = 1010

  return (
    <svg viewBox="0 0 1400 980" className="block h-auto w-full" style={{ minWidth: 920 }}>
      {/* lane bands */}
      <rect x="0" y="0" width="1400" height="300" fill="#E8ECF5" />
      <rect x="0" y="316" width="1400" height="310" fill="#E4F2EC" />
      <rect x="0" y="642" width="1400" height="338" fill="#FBF1E1" />

      {/* lane labels */}
      <text x="34" y="42" fontFamily={MONO} fontSize={15} fontWeight={700} letterSpacing="0.06em" fill={INPUT}>CLIENT INPUT</text>
      <text x="34" y="62" fontFamily={MONO} fontSize={12} fill={MUTED}>What you send us</text>
      <text x="34" y="358" fontFamily={MONO} fontSize={15} fontWeight={700} letterSpacing="0.06em" fill={ENGINE}>TELLUMEN ENGINE</text>
      <text x="34" y="378" fontFamily={MONO} fontSize={12} fill={MUTED}>Native &middot; automatic &middot; live</text>
      <text x="34" y="684" fontFamily={MONO} fontSize={15} fontWeight={700} letterSpacing="0.06em" fill={OUTPUT}>DISCLOSURE OUTPUT</text>
      <text x="34" y="704" fontFamily={MONO} fontSize={12} fill={MUTED}>Published to you</text>

      <defs>
        <marker id="flowArrowInput" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill={INPUT} /></marker>
        <marker id="flowArrowEngine" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill={ENGINE} /></marker>
        <marker id="flowArrowOutput" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill={OUTPUT} /></marker>
      </defs>

      {/* cross-lane thread: onboarding → primary output */}
      <path d="M240,220 C170,340 150,500 150,650 C150,730 350,791 550,791"
        fill="none" stroke={ADMIN} strokeWidth={2} strokeDasharray="2 6" strokeLinecap="round" />

      {hasThird && <FlowCurve x1={850} y1={155} x2={xOpt} y2={155} color={INPUT} dashed width={2} markerId="flowArrowInput" />}
      <FlowCurve x1={xData} y1={220} x2={xData} y2={406} color={INPUT} dashed width={2} markerId="flowArrowInput" />
      {hasThird && <FlowCurve x1={xOpt} y1={220} x2={xOpt} y2={406} color={INPUT} dashed width={2} markerId="flowArrowInput" />}
      <FlowCurve x1={850} y1={471} x2={1010} y2={471} color={ENGINE} width={2.5} markerId="flowArrowEngine" />
      <FlowCurve x1={xData} y1={536} x2={xData} y2={726} color={ENGINE} width={2.5} markerId="flowArrowEngine" />
      <FlowCurve x1={xOpt} y1={536} x2={xOpt} y2={726} color={ENGINE} width={2.5} markerId="flowArrowEngine" />
      <FlowCurve x1={850} y1={791} x2={1010} y2={791} color={OUTPUT} width={2.5} markerId="flowArrowOutput" />

      {/* pill labels */}
      {hasThird && <FlowPill cx={905} cy={143} w={90} label="PER HOLDING" color={INPUT} />}
      <FlowPill cx={xData + 20} cy={313} w={88} label="LOCATION" color={INPUT} />
      {hasThird && <FlowPill cx={xOpt} cy={313} w={100} label="OPTIONAL" color={INPUT} />}
      <FlowPill cx={902} cy={459} w={96} label="RISK SCORE" color={ENGINE} />
      <FlowPill cx={xData} cy={631} w={100} label="SCORED RISK" color={ENGINE} />
      <FlowPill cx={xOpt} cy={631} w={120} label="CALCULATED" color={ENGINE} />
      <FlowPill cx={905} cy={779} w={76} label="EXPORT" color={OUTPUT} />
      <FlowPill cx={150} cy={644} w={76} label="SCOPE" color={ADMIN} />

      {/* boxes: lane 1 */}
      <FlowBox x={90} y={90} accent={ADMIN} title={flow.onboarding.t} sub={flow.onboarding.s} tag={flow.onboarding.tag} tagColor={ADMIN} />
      <FlowBox x={xData} y={90} accent={INPUT} title={flow.inputs[0].t} sub={flow.inputs[0].s} tag={flow.inputs[0].tag} tagColor={INPUT} />
      {hasThird && <FlowBox x={xOpt} y={90} accent={INPUT} title={flow.inputs[1].t} sub={flow.inputs[1].s} tag={flow.inputs[1].tag} tagColor={INPUT} />}

      {/* boxes: lane 2 */}
      <FlowBox x={xData} y={406} accent={ENGINE} title={flow.engine[0].t} sub={flow.engine[0].s} tagColor={ENGINE} />
      <FlowBox x={xOpt} y={406} accent={ENGINE} title={flow.engine[1].t} sub={flow.engine[1].s} tagColor={ENGINE} />

      {/* boxes: lane 3 */}
      <FlowBox x={xData} y={726} accent={OUTPUT} title={flow.outputs[0].t} sub={flow.outputs[0].s} tag={flow.outputs[0].tag} tagColor={OUTPUT} />
      <FlowBox x={xOpt} y={726} accent={OUTPUT} title={flow.outputs[1].t} sub={flow.outputs[1].s} tag={flow.outputs[1].tag} tagColor={OUTPUT} />
    </svg>
  )
}
