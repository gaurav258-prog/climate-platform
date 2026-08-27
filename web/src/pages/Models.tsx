import { useQuery } from '@tanstack/react-query'
import { FlaskConical, CheckCircle2, PauseCircle } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import { hazardLabel } from '../lib/hazards'
import ReviewTabs from '../components/ReviewTabs'

interface Fit {
  commodity: string; origin: string; hazard_driver: string; r2: number; r2_oos: number | null
  n_years: number; publishes: boolean; confidence_grade: string | null
  challenger_verdict?: string | null; challenger_pct?: number | null; challenger_champion_pct?: number | null
  challenger_ref_score?: number | null; challenger_mad_pp?: number | null; challenger_tol_pp?: number | null
}
interface Models { ranged_fits: Fit[]; ranged_publish_floor: number }

const VERDICT_CLS: Record<string, string> = {
  agree: 'text-[var(--color-good)]', partial: 'text-[var(--color-warn)]', diverge: 'text-[var(--color-bad)]',
}
const VERDICT_LABEL: Record<string, string> = { agree: 'agrees', partial: 'partial', diverge: 'diverges', insufficient: 'n/a' }

const COUNTRY: Record<string, string> = {
  MA: 'Morocco', TN: 'Tunisia', DZ: 'Algeria', ES: 'Spain', IR: 'Iran', TR: 'Turkey', SY: 'Syria',
  AR: 'Argentina', KZ: 'Kazakhstan', US: 'United States', ZA: 'South Africa', IN: 'India', BR: 'Brazil',
}
const GRADE_CLS: Record<string, string> = {
  A: 'text-[var(--color-good)]', B: 'text-[var(--color-good)]', C: 'text-[var(--color-warn)]',
}

export default function Models() {
  const q = useQuery({ queryKey: ['models'], queryFn: () => api.get<Models>('/v1/supply/models') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const floor = q.data.ranged_publish_floor
  const fits = [...q.data.ranged_fits].sort((a, b) => b.r2 - a.r2)
  const published = fits.filter(f => f.publishes)
  const held = fits.filter(f => !f.publishes)

  return (
    <div className="fadeup space-y-7">
      <ReviewTabs />
      <PageHeader eyebrow="Agriculture · trust & assurance" title="Models & validation"
        lead={`Every crop×origin we tested, and whether climate robustly drives its yield. We publish a euro only above an out-of-sample fit floor of r² ≥ ${floor}; the rest are shown tested-and-held, with the r², so you see exactly what we earned and what we withheld.`} />

      <HeroBanner
        eyebrow="Models & validation"
        title="What climate robustly drives — and what we withheld."
        lead={`We publish a euro only above an out-of-sample fit floor of r² ≥ ${floor}; the rest are shown tested-and-held, with the r².`}
        stat={[
          { label: 'crop × origin tested', value: fits.length, icon: FlaskConical, tone: 'var(--color-sky)' },
          { label: 'published', value: published.length, icon: CheckCircle2, tone: '#4FA46E' },
          { label: 'tested & held', value: held.length, icon: PauseCircle },
        ]} />

      <FitTable title={`Published — climate drives yield (r² ≥ ${floor})`} fits={published} floor={floor} showGrade />
      <FitTable title="Tested & held — shown honestly, € withheld" fits={held} floor={floor} />
    </div>
  )
}

function FitTable({ title, fits, floor, showGrade }: { title: string; fits: Fit[]; floor: number; showGrade?: boolean }) {
  if (fits.length === 0) return null
  return (
    <Card className="p-5">
      <SectionHead className="mb-3">{title}</SectionHead>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="font-normal py-2 pr-3">Crop</th><th className="font-normal pr-3">Origin</th>
              <th className="font-normal pr-3">Driver</th><th className="font-normal pr-3 text-right">r² (in)</th>
              <th className="font-normal pr-3 text-right">r² (out)</th><th className="font-normal pr-3 text-right">years</th>
              {showGrade && <th className="font-normal pr-3 text-right">challenger</th>}
              {showGrade && <th className="font-normal text-right">grade</th>}
            </tr>
          </thead>
          <tbody>
            {fits.map((f, i) => (
              <tr key={i} className="border-t border-[var(--color-line)]">
                <td className="py-2 pr-3 text-[var(--color-ink)]">{f.commodity}</td>
                <td className="pr-3 text-[var(--color-mute)]">{COUNTRY[f.origin] ?? f.origin}</td>
                <td className="pr-3 mono text-[11px] text-[var(--color-mute)]">{hazardLabel(f.hazard_driver)}</td>
                <td className={`pr-3 text-right mono ${f.r2 >= floor ? 'text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}`}>{f.r2.toFixed(2)}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{f.r2_oos != null ? f.r2_oos.toFixed(2) : '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-faint)]">{f.n_years}</td>
                {showGrade && (
                  <td className={`pr-3 text-right mono text-[11px] ${VERDICT_CLS[f.challenger_verdict || ''] ?? 'text-[var(--color-faint)]'}`}
                    title={f.challenger_verdict && f.challenger_pct != null
                      ? `Independent isotonic method @ score ${f.challenger_ref_score}: champion ${f.challenger_champion_pct}% vs challenger ${f.challenger_pct}% (mean divergence ${f.challenger_mad_pp}pp vs tolerance ${f.challenger_tol_pp}pp)`
                      : 'no independent challenger'}>
                    {f.challenger_verdict ? (VERDICT_LABEL[f.challenger_verdict] ?? f.challenger_verdict) : '—'}
                  </td>
                )}
                {showGrade && <td className={`text-right mono font-semibold ${GRADE_CLS[f.confidence_grade || ''] ?? 'text-[var(--color-mute)]'}`}>{f.confidence_grade ?? '—'}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
