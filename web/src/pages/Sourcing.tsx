import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { Eyebrow, Card, Stat, StatusPill } from '../components/ui'

interface Plot {
  plot_id: string; commodity: string; eudr_covered: boolean; plot_name: string; region: string | null
  country: string | null; lat: number; lon: number; spend_eur: number; eudr_determination: string | null
  top_hazard: string | null; hazard_score: number | null
}
interface Portfolio { plots: Plot[] }

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const hz = (s: number | null) => s == null ? 'var(--color-faint)' : s >= 60 ? 'var(--color-bad)' : s >= 40 ? 'var(--color-warn)' : 'var(--color-good)'

export default function Sourcing() {
  const q = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })
  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !q.data) return <Center>Could not load — is the API on :8001?</Center>
  const plots = [...q.data.plots].sort((a, b) => (b.spend_eur ?? 0) - (a.spend_eur ?? 0))
  const totalSpend = plots.reduce((s, p) => s + (p.spend_eur ?? 0), 0)
  const eudrPlots = plots.filter(p => p.eudr_covered).length

  return (
    <div className="fadeup space-y-7">
      <div>
        <Eyebrow>Agriculture · your book</Eyebrow>
        <h1 className="display text-3xl font-semibold mt-2 mb-1">Sourcing book</h1>
        <p className="text-[var(--color-mute)] text-sm max-w-2xl">
          Every plot you source from — geolocated, scored on live hazard, and (where EUDR-covered) checked against
          satellite forest-loss.
        </p>
      </div>

      <div className="grid sm:grid-cols-3 gap-4">
        <Stat big={plots.length} label="sourcing plots" />
        <Stat big={eur(totalSpend)} label="annual spend" />
        <Stat big={eudrPlots} label="EUDR-covered plots" />
      </div>

      <Card className="p-5">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th>
                <th className="font-normal pr-3">Location</th><th className="font-normal pr-3 text-right">Spend</th>
                <th className="font-normal pr-3">Hazard</th><th className="font-normal">EUDR</th>
              </tr>
            </thead>
            <tbody>
              {plots.map(p => (
                <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                  <td className="py-2.5 pr-3 text-[var(--color-ink)]">{p.plot_name}</td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 mono text-[11px] text-[var(--color-mute)]">{p.region ?? '—'} · {p.country ?? '—'}</td>
                  <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(p.spend_eur)}</td>
                  <td className="pr-3">
                    {p.hazard_score != null
                      ? <span className="mono text-[12px]" style={{ color: hz(p.hazard_score) }}>{p.top_hazard} {p.hazard_score.toFixed(0)}</span>
                      : <span className="mono text-[11px] text-[var(--color-faint)]">unscored</span>}
                  </td>
                  <td>{p.eudr_covered ? <StatusPill status={p.eudr_determination} /> : <span className="mono text-[11px] text-[var(--color-faint)]">n/a</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
