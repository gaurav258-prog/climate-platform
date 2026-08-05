import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ListChecks, ArrowUpRight } from 'lucide-react'
import { api } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Card } from './ui'

// Eligibility & coverage — the step between "which regulation" and "the final form": what of your book
// actually qualifies for this disclosure, and what does not. Reads the current-basis disclosure (the golden
// source) and shows the EU-Taxonomy eligible / not-eligible split by value and position count. This is the
// honest coverage picture before a filing is prepared — nothing invented, "—" where a figure is absent.

interface TaxBlock { count: number; value_eur: number }
interface DisclosureResp { taxonomy: Record<string, TaxBlock> }

// disclosure sectors → their /v1/<prefix>/disclosure endpoint. Insurer has no taxonomy read → no card.
const PREFIX: Record<string, string> = { bank: 'bank', asset_manager: 'assetmgmt', reit: 'realestate' }
const eur = (n?: number | null) => n == null ? '—' : n >= 1e9 ? `€${(n / 1e9).toFixed(2)}bn` : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${Math.round(n / 1e3)}k`

export default function FilingCoverage() {
  const { profile } = useAuth()
  const prefix = PREFIX[profile?.org?.type ?? '']
  const q = useQuery({
    queryKey: ['fin-coverage', prefix],
    enabled: !!prefix,
    queryFn: () => api.get<DisclosureResp>(`/v1/${prefix}/disclosure?scenario=baseline&horizon=current`),
  })
  if (!prefix) return null
  const tax = q.data?.taxonomy
  const elig = tax?.eligible, notElig = tax?.not_eligible
  const totalVal = (elig?.value_eur ?? 0) + (notElig?.value_eur ?? 0)
  const totalPos = (elig?.count ?? 0) + (notElig?.count ?? 0)
  const pct = totalVal > 0 && elig ? Math.round((elig.value_eur / totalVal) * 100) : null

  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-[var(--color-line)]">
        <ListChecks size={15} className="text-[var(--color-sky)]" />
        <span className="mono text-[10.5px] tracking-[0.16em] uppercase text-[var(--color-faint)]">Eligibility &amp; coverage · what of your book qualifies</span>
      </div>

      {q.isLoading ? (
        <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">reading the book…</div>
      ) : !tax ? (
        <div className="px-5 py-6 text-[13px] text-[var(--color-faint)]">Coverage will appear once book data is loaded for this period.</div>
      ) : (
        <div className="px-5 py-4 space-y-4">
          <div className="grid sm:grid-cols-2 gap-3">
            <Split tone="var(--color-good)" label="EU-Taxonomy eligible" value={eur(elig?.value_eur)} sub={`${elig?.count ?? 0} of ${totalPos} position${totalPos === 1 ? '' : 's'}${pct != null ? ` · ${pct}% by value` : ''}`} />
            <Split tone="var(--color-mute)" label="Not eligible" value={eur(notElig?.value_eur)} sub={`${notElig?.count ?? 0} position${(notElig?.count ?? 0) === 1 ? '' : 's'} · outside the taxonomy's activities`} />
          </div>
          {pct != null && (
            <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: 'color-mix(in oklab, var(--color-mute) 22%, transparent)' }}>
              <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--color-good)' }} />
            </div>
          )}
          <p className="mono text-[10.5px] text-[var(--color-faint)] leading-relaxed">
            Eligibility only — a full <span className="text-[var(--color-mute)]">aligned %</span> additionally needs DNSH, minimum-safeguards and financial tagging from your books. Positions with no
            usable data are excluded from both sides rather than assumed. Load or refresh the book from{' '}
            <Link to="/portfolio" className="inline-flex items-center gap-0.5 text-[var(--color-sky)] hover:underline">Portfolio <ArrowUpRight size={11} /></Link>.
          </p>
        </div>
      )}
    </Card>
  )
}

function Split({ tone, label, value, sub }: { tone: string; label: string; value: string; sub: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-line)] p-4">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="w-2 h-2 rounded-full" style={{ background: tone }} />
        <span className="text-[12.5px] text-[var(--color-ink)]">{label}</span>
      </div>
      <div className="mono text-[20px] tabular-nums" style={{ color: tone }}>{value}</div>
      <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">{sub}</div>
    </div>
  )
}
