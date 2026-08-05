import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Eyebrow, Card } from '../components/ui'
import { hazardLabel } from '../lib/hazards'

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
      <div>
        <Eyebrow>Agriculture · trust &amp; assurance</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Models &amp; validation</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Every crop×origin we tested, and whether climate robustly drives its yield. We publish a euro only above an
          out-of-sample fit floor of r² ≥ {floor}; the rest are shown tested-and-held, with the r², so you see exactly
          what we earned and what we withheld.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Mini n={fits.length} label="crop × origin tested" />
        <Mini n={published.length} label="published" tone="good" />
        <Mini n={held.length} label="tested &amp; held" tone="slate" />
      </div>

      <FitTable title={`Published — climate drives yield (r² ≥ ${floor})`} fits={published} floor={floor} showGrade />
      <FitTable title="Tested & held — shown honestly, € withheld" fits={held} floor={floor} />
    </div>
  )
}

function FitTable({ title, fits, floor, showGrade }: { title: string; fits: Fit[]; floor: number; showGrade?: boolean }) {
  if (fits.length === 0) return null
  return (
    <Card className="p-5">
      <div className="text-[13px] font-semibold mb-3">{title}</div>
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

function Mini({ n, label, tone = 'ink' }: { n: number; label: string; tone?: 'ink' | 'good' | 'slate' }) {
  const c = { ink: 'var(--color-ink)', good: 'var(--color-good)', slate: 'var(--color-slate)' }[tone]
  return (
    <Card className="p-4"><div className="display text-2xl font-semibold" style={{ color: c }}>{n}</div>
      <div className="text-[11px] text-[var(--color-mute)] mt-1" dangerouslySetInnerHTML={{ __html: label }} /></Card>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
