import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Download, Map as MapIcon, ShieldAlert } from 'lucide-react'
import { api } from '../lib/api'
import { Card, Eyebrow } from '../components/ui'
import MiniMap from '../components/MiniMap'
import LocationEditor from '../components/LocationEditor'

const eur = (n?: number | null) => n == null ? '—' : n >= 1e6 ? `€${(n / 1e6).toFixed(1)}m` : `€${(n / 1e3).toFixed(0)}k`
const pretty = (h?: string | null) => !h ? '—' : h.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
const hz = (s?: number | null) => s == null ? '#64748b' : s >= 60 ? '#fb7185' : s >= 40 ? '#f59e0b' : s >= 1 ? '#34d399' : '#64748b'
interface Adapt { hazard: string; label: string; actions: string[] }
interface Norm { title: string; sub: string; lat: number | null; lon: number | null
  facts: { k: string; v: string }[]; hazards: { hazard: string; score: number | null }[]; adaptation: Adapt[]
  irrigationContext?: { status: string; buffers: string[]; note?: string } | null }

export default function DetailView({ kind }: { kind: 'site' | 'plot' }) {
  const { id } = useParams()
  const q = useQuery({ queryKey: [kind, id], queryFn: () => api.get<Record<string, unknown>>(`/v1/supply/${kind}/${id}`) })
  const d = q.data
  const n = d ? normalize(kind, d) : null

  if (q.isLoading) return <Center>loading…</Center>
  if (q.error || !n) return <Center>Could not load this {kind}.</Center>

  const worst = Math.max(0, ...n.hazards.map(h => h.score ?? 0))
  const csv = () => {
    const rows = [['hazard', 'score'], ...n.hazards.map(h => [h.hazard, String(h.score ?? '')])]
    const blob = new Blob([rows.map(r => r.join(',')).join('\n')], { type: 'text/csv' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${n.title}-hazards.csv`; a.click()
  }

  return (
    <div className="fadeup space-y-6">
      <Link to={kind === 'site' ? '/operations' : '/sourcing'} className="inline-flex items-center gap-1.5 text-[13px] text-[var(--color-mute)] hover:text-[var(--color-sky)]">
        <ArrowLeft size={15} /> back to {kind === 'site' ? 'Operations' : 'Sourcing book'}
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Eyebrow>{kind === 'site' ? 'Operational site' : 'Sourcing plot'}</Eyebrow>
          <h1 className="display text-3xl font-semibold mt-2">{n.title}</h1>
          <p className="text-[var(--color-mute)] text-sm mt-1">{n.sub}</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="mono text-[12px] text-[var(--color-faint)]">worst hazard</span>
          <span className="text-3xl font-semibold mono" style={{ color: hz(worst) }}>{Math.round(worst)}</span>
        </div>
      </div>

      <LocationEditor kind={kind} id={id as string} record={(d![kind] as Record<string, unknown>) ?? {}} onChanged={() => q.refetch()} />

      <div className="grid lg:grid-cols-2 gap-5">
        {/* location + facts */}
        <div className="space-y-4">
          {n.lat != null && n.lon != null
            ? <MiniMap lat={n.lat} lon={n.lon} color={hz(worst)} />
            : <Card className="p-8 text-center text-[var(--color-faint)] text-sm">no coordinates for this {kind}</Card>}
          <Card className="p-5">
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-3">Key facts</div>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-[13px]">
              {n.facts.map((f, i) => (
                <div key={i} className="flex justify-between border-b border-[var(--color-line)] pb-1.5">
                  <span className="text-[var(--color-mute)]">{f.k}</span><span className="text-[var(--color-ink)]">{f.v}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* hazards + adaptation */}
        <div className="space-y-4">
          <Card className="p-5">
            <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-3">Hazards on this cell</div>
            <div className="space-y-2.5">
              {n.hazards.filter(h => h.score != null).map((h, i) => (
                <div key={i}>
                  <div className="flex justify-between text-[12px] mb-0.5">
                    <span className="text-[var(--color-ink)]">{pretty(h.hazard)}</span>
                    <span className="mono" style={{ color: hz(h.score) }}>{Math.round(h.score as number)}</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-[var(--color-panel-2)] overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${Math.min(100, h.score ?? 0)}%`, background: hz(h.score) }} />
                  </div>
                </div>
              ))}
              {n.hazards.filter(h => h.score != null).length === 0 && <div className="text-[13px] text-[var(--color-faint)]">not yet scored</div>}
            </div>
          </Card>

          {n.irrigationContext?.note && (
            <Card className="p-4">
              <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)] mb-1.5">
                Water management · declared {n.irrigationContext.status.replace('_', '-')}
              </div>
              <div className="text-[12.5px] text-[var(--color-mute)] leading-relaxed">{n.irrigationContext.note}</div>
            </Card>
          )}

          {n.adaptation.length > 0 && (
            <Card className="p-5">
              <div className="flex items-center gap-2 mb-3">
                <ShieldAlert size={15} className="text-[var(--color-sky)]" />
                <span className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Adaptation — what to do</span>
              </div>
              <div className="space-y-3">
                {n.adaptation.map((a, i) => (
                  <div key={i}>
                    <div className="text-[13px] font-medium mb-1" style={{ color: hz(80) }}>{a.label}</div>
                    <ul className="space-y-1">
                      {a.actions.map((act, j) => (
                        <li key={j} className="text-[12px] text-[var(--color-mute)] flex gap-2"><span className="text-[var(--color-sky)]">·</span>{act}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <div className="flex gap-3">
            <button onClick={csv} className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line-2)] px-4 py-2 text-sm text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><Download size={15} /> Export hazards (CSV)</button>
            <Link to="/riskmap" className="inline-flex items-center gap-2 rounded-lg border border-[var(--color-line-2)] px-4 py-2 text-sm text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><MapIcon size={15} /> View on risk map</Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function normalize(kind: 'site' | 'plot', d: Record<string, unknown>): Norm {
  if (kind === 'site') {
    const s = d.site as Record<string, unknown>
    return {
      title: s.name as string,
      sub: `${pretty(s.site_type as string)} · ${(s.country as string) ?? '—'}${s.address ? ` · ${s.address}` : ''}`,
      lat: (s.lat as number) ?? null, lon: (s.lon as number) ?? null,
      facts: [
        { k: 'Type', v: pretty(s.site_type as string) },
        { k: 'Country', v: (s.country as string) ?? '—' },
        { k: 'Asset value', v: eur(s.value_eur as number) },
        { k: 'Annual throughput', v: eur(s.throughput_eur as number) },
        { k: 'Business-interruption', v: eur(d.bi_at_risk_eur as number) },
        { k: 'H3 cell', v: (s.h3_cell as string) ?? '—' },
      ],
      hazards: (d.hazards as { hazard_type: string; score: number | null }[]).map(h => ({ hazard: h.hazard_type, score: h.score })),
      adaptation: (d.adaptation as Adapt[]) ?? [],
    }
  }
  const p = d.plot as Record<string, unknown>
  const risks = (d.risks as { hazard_type: string; scenario: string; time_horizon: string; score: number | null }[])
    .filter(r => r.scenario === 'baseline' && r.time_horizon === 'current')
  return {
    title: p.plot_name as string,
    sub: `${p.commodity as string} · ${(p.country as string) ?? '—'}${p.supplier ? ` · ${p.supplier}` : ''}`,
    lat: (p.lat as number) ?? null, lon: (p.lon as number) ?? null,
    facts: [
      { k: 'Commodity', v: p.commodity as string },
      { k: 'Country', v: (p.country as string) ?? '—' },
      { k: 'Annual spend', v: eur(p.spend_eur as number) },
      { k: 'EUDR status', v: pretty((p.eudr_status as string) ?? null) },
      { k: 'EUDR determination', v: pretty((p.eudr_determination as string) ?? null) },
      { k: 'H3 cell', v: (p.h3_cell as string) ?? '—' },
    ],
    hazards: risks.map(r => ({ hazard: r.hazard_type, score: r.score })),
    adaptation: (d.adaptation as Adapt[]) ?? [],
    irrigationContext: (d.irrigation_context as { status: string; buffers: string[]; note?: string } | null) ?? null,
  }
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="py-20 text-center text-[var(--color-faint)] text-sm">{children}</div>
}
