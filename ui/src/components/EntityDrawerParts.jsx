import { X, ChevronDown, MapPin, Check, X as XMark } from 'lucide-react'
import { useState } from 'react'
import RiskAtom from './RiskAtom'
import HelpLink from './HelpLink'

// Shared drill-through drawer pieces — used by AssetDrawer (banking), and the
// real estate / asset management drawers. Every vertical drills into an
// entity the same way (headline risk + per-hazard model provenance + EU
// Taxonomy status + a facts table), so this is ONE implementation instead of
// three copies drifting apart.

export function DrawerShell({ title, subtitle, loading, onClose, children }) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
      <aside className="fixed right-0 top-0 z-50 flex h-full w-[420px] flex-col overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 flex items-start justify-between border-b border-gray-200 bg-white/90 px-5 py-4 backdrop-blur">
          <div className="min-w-0">
            {!loading ? (
              <>
                <h2 className="truncate text-[17px] font-semibold text-[#1d1d1f]">{title}</h2>
                <p className="mt-0.5 text-[12px] text-gray-500">{subtitle}</p>
              </>
            ) : <h2 className="text-[15px] text-gray-400">loading…</h2>}
          </div>
          <button onClick={onClose} className="rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700"><X size={18} /></button>
        </header>
        {!loading && <div className="space-y-5 px-5 py-5">{children}</div>}
      </aside>
    </>
  )
}

/** Headline risk + per-hazard model provenance, expandable per row. */
export function RiskSection({ risks, models, emptyNote = "This entity's cell has not been scored — surfaced honestly, never a silent zero." }) {
  const [openHz, setOpenHz] = useState(null)
  const headline = risks.slice().sort((x, y) => y.score - x.score)[0]
  return (
    <section className="rounded-2xl bg-[#f5f5f7] p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-gray-400">Physical risk</div>
          <div className="text-[13px] text-gray-600">{headline ? `driven by ${headline.hazard_type}` : 'no scored hazard'}</div>
        </div>
        {headline
          ? <RiskAtom score={headline.score} bucket={headline.risk_bucket} size="lg" showLabel />
          : <RiskAtom score={null} bucket={null} size="lg" />}
      </div>
      <div className="mt-4 space-y-2">
        {risks.length ? risks.map(r => {
          const m = models.find(x => x.model_version === r.model_version)
          const open = openHz === r.hazard_type
          return (
            <div key={r.hazard_type} className="overflow-hidden rounded-lg bg-white">
              <button onClick={() => setOpenHz(open ? null : r.hazard_type)}
                className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-gray-50">
                <div>
                  <div className="flex items-center gap-1 text-[13px] font-medium capitalize text-[#1d1d1f]">
                    {r.hazard_type.replace('_', ' ')}
                    <ChevronDown size={13} className={`text-gray-400 transition ${open ? 'rotate-180' : ''}`} />
                  </div>
                  <div className="font-mono text-[10px] text-gray-400">{r.model_version} · {String(r.scored_at).slice(0, 10)}</div>
                </div>
                <RiskAtom score={r.score} bucket={r.risk_bucket} size="md" />
              </button>
              {open && (
                <div className="border-t border-gray-100 px-3 py-2.5 text-[11px]">
                  {m ? (
                    <>
                      <div className="text-gray-500">Out-of-sample skill:{' '}
                        <span className="font-semibold text-[#1d1d1f]">{m.auc != null ? `LOEO AUC ${m.auc.toFixed(3)}` : 'physics-based'}</span>
                        {m.avg_precision != null ? ` · AP ${m.avg_precision.toFixed(3)}` : ''}
                        {m.training_cell_count ? ` · ${m.training_cell_count.toLocaleString()} cells` : ''}
                      </div>
                      {m.validation_note && <p className="mt-1.5 leading-snug text-gray-500">{m.validation_note}</p>}
                    </>
                  ) : <p className="text-gray-400">model metadata unavailable</p>}
                </div>
              )}
            </div>
          )
        }) : <p className="text-[12px] text-gray-400">{emptyNote}</p>}
      </div>
    </section>
  )
}

const TAXONOMY_BADGE = {
  eligible: 'bg-amber-50 text-amber-700',
  not_eligible: 'bg-gray-100 text-gray-500',
  not_assessed: 'bg-gray-100 text-gray-400',
}
const TAXONOMY_LABEL = { eligible: 'Eligible', not_eligible: 'Not eligible', not_assessed: 'Not assessed' }

function EvidenceRow({ verified, note }) {
  return (
    <div className="flex items-start gap-1.5">
      {verified
        ? <Check size={12} className="mt-0.5 shrink-0 text-emerald-600" />
        : <XMark size={12} className="mt-0.5 shrink-0 text-gray-300" />}
      <span className={`text-[11px] leading-snug ${verified ? 'text-gray-600' : 'text-gray-400'}`}>{note}</span>
    </div>
  )
}

/** EU Taxonomy status shown WITH its reasoning -- never a bare enum. "Eligible" cites the exact
 * Annex I section; "not eligible"/"not assessed" say why, and never silently claim "aligned"
 * without the technical-screening + safeguards data that would require (see
 * ml/regulatory/eu_taxonomy_classifier.py's docstring). `reasoning` (if supplied) shows exactly
 * which of the two remaining conditions has real supplied evidence vs. is still unverified —
 * a tenant who uploads EPC/minimum-safeguards data sees that progress, not a static disclaimer. */
export function TaxonomySection({ status, activityRef, dnshFlag, reasoning, onGoto }) {
  const s = status || 'not_assessed'
  return (
    <section>
      <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">EU Taxonomy alignment</h3>
      <div className="rounded-2xl border border-gray-200 p-3">
        <div className="flex items-center justify-between">
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${TAXONOMY_BADGE[s] || TAXONOMY_BADGE.not_assessed}`}>
            {TAXONOMY_LABEL[s] || s}
          </span>
        </div>
        {activityRef && <p className="mt-2 text-[11px] leading-snug text-gray-500">{activityRef}</p>}
        {s !== 'not_assessed' && reasoning && (
          <div className="mt-2.5 space-y-1.5 border-t border-gray-100 pt-2.5">
            <EvidenceRow verified={reasoning.substantial_contribution_verified} note={reasoning.substantial_contribution_note} />
            <EvidenceRow verified={reasoning.minimum_safeguards_verified} note={reasoning.minimum_safeguards_note} />
          </div>
        )}
        {s !== 'not_assessed' && (
          <p className="mt-2 text-[11px] leading-snug text-gray-400">
            Never "aligned" — that also needs do-no-significant-harm verified across all five other
            environmental objectives, which this platform doesn't assess (see <HelpLink onGoto={onGoto} section="method">Methodology</HelpLink>).
          </p>
        )}
        {dnshFlag && (
          <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1.5 text-[11px] leading-snug text-amber-800">{dnshFlag}</p>
        )}
      </div>
    </section>
  )
}

export function Facts({ title, rows }) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] uppercase tracking-wide text-gray-400">{title}</h3>
      <div className="divide-y divide-gray-100 rounded-2xl border border-gray-200">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between px-3 py-2 text-[13px]">
            <span className="text-gray-500">{k}</span>
            <span className="font-medium text-[#1d1d1f]">{v}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

export function ProvenanceFooter({ h3Cell }) {
  return (
    <div className="flex items-center gap-1.5 rounded-xl border border-gray-200 px-3 py-2 text-[11px] text-gray-500">
      <MapPin size={13} className="text-gray-400" />
      <span className="font-mono">{h3Cell}</span>
      <span className="text-gray-300">·</span>
      <span>projected from canonical_scores</span>
    </div>
  )
}
