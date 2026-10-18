import { useState } from 'react'
import { ChevronRight, Download, FileSpreadsheet, Upload } from 'lucide-react'
import { Card, SectionHead } from '../../components/ui'
import MethodGap from '../../components/MethodGap'
import { HEADING, InfoButton } from '../../components/Details'
import { BookWithMap } from '../../components/SiteMap'
import { apiMessage, ApiError, download, upload } from '../../lib/api'
import { toast } from '../../lib/toast'
import { bucketLabel, hazardLabel, horizonLabel, modelLabel, scenarioLabel } from '../../lib/labels'
import { sevColor, sevLabel } from '../../lib/hazards'
import { balance } from '../../lib/money'
import { templatePath, uploadPath, type Cfg } from './sectors'

// The book itself: where the money at risk comes from (by hazard), and the searchable list of the book's rows beside
// their map. The book is found, not dumped: the most exposed few show until the reader searches or filters.

interface Hazard { hazard: string; score: number; bucket: string; model_version?: string; scored_at?: string; ci_lo?: number | null; ci_hi?: number | null }
interface Valuation { discounted_value_eur: number | null; is_overridden: boolean; effective_discount_pct?: number | null; original_ltv_pct?: number | null; climate_adjusted_ltv_pct?: number | null; gap?: string }
export interface Asset {
  region?: string; lat?: number; lon?: number
  headline_score: number | null; headline_bucket: string | null; headline_hazard: string | null
  hazards: Hazard[]; valuation?: Valuation
  [k: string]: unknown   // id / name / type / value live under the sector's own keys
}

const rgb = (l: number) => (l < 28 ? 'rgb(95,185,140)' : l < 50 ? 'rgb(232,178,76)' : l < 75 ? 'rgb(233,116,74)' : 'rgb(210,59,59)')
const bandOf = (sc: number | null | undefined) => sc == null ? '' : sc < 28 ? 'low' : sc < 50 ? 'elevated' : sc < 75 ? 'high' : 'severe'
const BANDS = [['severe', 'VH'], ['high', 'H'], ['elevated', 'M'], ['low', 'L']] as const
const where = (lat?: number, lon?: number) => lat == null || lon == null ? null
  : `${Math.abs(lat).toFixed(1)}°${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(1)}°${lon >= 0 ? 'E' : 'W'}`

// Money exposed by hazard, coloured by how severe; a tile filters the book below to those rows.
export function HazardExposure({ items, valueKey, onPick, active }: { items: Asset[]; valueKey: string; onPick?: (hazard: string) => void; active?: string }) {
  const m: Record<string, { eur: number; n: number; worst: number }> = {}
  for (const a of items) {
    const hz = a.headline_hazard, sc = a.headline_score
    if (!hz || sc == null) continue
    const g = (m[hz] ??= { eur: 0, n: 0, worst: 0 })
    g.eur += (a[valueKey] as number | null) ?? 0
    g.n += 1; g.worst = Math.max(g.worst, sc)
  }
  const groups = Object.entries(m).sort((a, b) => b[1].worst - a[1].worst || b[1].eur - a[1].eur)
  if (!groups.length) return null
  const details = { title: 'Where your risk comes from', sections: [
    { heading: HEADING.shows, body: 'The value of the assets whose biggest physical threat is each hazard.' },
    { heading: HEADING.read, body: 'The colour is the highest score among those assets: green moderate, amber high, red severe. Click a hazard to see its assets in the list below.' },
  ] }
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 mb-3"><SectionHead>Where your risk comes from</SectionHead><InfoButton compact details={details} /></div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {groups.map(([hz, g]) => {
          const on = active === hz
          return (
            <button key={hz} onClick={() => onPick?.(hz)} disabled={!onPick} aria-pressed={on}
              className={`rounded-lg border px-3.5 py-3 text-left transition ${onPick ? 'cursor-pointer hover:shadow-sm' : 'cursor-default'}`}
              style={{ borderColor: on ? sevColor(g.worst) : sevColor(g.worst) + '55', borderWidth: on ? 2 : 1, background: on ? sevColor(g.worst) + '12' : undefined }}>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: sevColor(g.worst) }} />
                <span className="text-[13px] text-[var(--color-ink)] leading-tight">{hazardLabel(hz)}</span>
              </div>
              <div className="display text-[21px] leading-none">{balance(g.eur)}</div>
              <div className="text-[11.5px] text-[var(--color-mute)] mt-1">{sevLabel(g.worst)} · {g.n} {g.n === 1 ? 'asset' : 'assets'}</div>
            </button>
          )
        })}
      </div>
    </Card>
  )
}

type Filters = { search: string; hazard: string; band: string }

export function BookPanel({ cfg, items, loading, failed, scenario, horizon, filters, setFilters, open, setOpen, onDetail, onImported }: {
  cfg: Cfg; items: Asset[]; loading: boolean; failed: boolean; scenario: string; horizon: string
  filters: Filters; setFilters: (f: Filters) => void; open: string | null; setOpen: (id: string | null) => void
  onDetail: (id: string) => void; onImported: () => void
}) {
  const sorted = [...items].sort((a, b) => (b.headline_score ?? -1) - (a.headline_score ?? -1))
  const hazards = [...new Set(sorted.map(a => a.headline_hazard).filter(Boolean))] as string[]
  const term = filters.search.trim().toLowerCase()
  const searching = !!(term || filters.hazard || filters.band)
  const found = sorted.filter(a => {
    if (term && !`${a[cfg.nameKey] ?? ''} ${a.region ?? ''} ${a[cfg.typeKey] ?? ''} ${hazardLabel(a.headline_hazard)}`.toLowerCase().includes(term)) return false
    if (filters.hazard && a.headline_hazard !== filters.hazard) return false
    return !filters.band || bandOf(a.headline_score) === filters.band
  })
  const shown = searching ? found : sorted.slice(0, 6)   // nothing searched: the most exposed few, never the whole list
  const input = 'bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-2.5 py-2 text-[12.5px] outline-none focus:border-[var(--color-sky)]'
  return (
    <Card className="p-0 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-[var(--color-line)]">
        <SectionHead>Your {cfg.noun}</SectionHead>
        <div className="flex items-center gap-4">
          <ImportBook cfg={cfg} onDone={onImported} />
          <button className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"
            onClick={() => download(`/v1/${cfg.prefix}/portfolio.xlsx?scenario=${scenario}&horizon=${horizon}`, `${cfg.prefix}-portfolio.xlsx`).catch(() => toast.error('Could not download the export.'))}>
            <Download size={13} /> Export
          </button>
        </div>
      </div>
      {loading ? <div className="p-10 text-center text-[var(--color-faint)] text-[13px]">Loading…</div>
        : failed ? <div className="p-8 text-center text-[13px] text-[var(--color-bad)]">The book could not be loaded. Reload, or sign in again.</div>
        : sorted.length === 0 ? <EmptyBook cfg={cfg} onDone={onImported} />
        : (<>
          <div className="px-5 py-3 border-b border-[var(--color-line)] flex flex-wrap items-center gap-2">
            <input value={filters.search} onChange={e => setFilters({ ...filters, search: e.target.value })} placeholder="Search by name, region or type"
              aria-label="Search the book" className={`flex-1 min-w-[200px] ${input} text-[13px] px-3`} />
            <select value={filters.hazard} onChange={e => setFilters({ ...filters, hazard: e.target.value })} aria-label="Biggest hazard" className={`${input} text-[var(--color-mute)]`}>
              <option value="">All hazards</option>
              {hazards.map(h => <option key={h} value={h}>{hazardLabel(h)}</option>)}
            </select>
            <select value={filters.band} onChange={e => setFilters({ ...filters, band: e.target.value })} aria-label="Severity" className={`${input} text-[var(--color-mute)]`}>
              <option value="">All severities</option>
              {BANDS.map(([k, b]) => <option key={k} value={k}>{bucketLabel(b)}</option>)}
            </select>
            {searching && <button onClick={() => setFilters({ search: '', hazard: '', band: '' })} className="text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)] px-1">Clear</button>}
          </div>
          <div className="px-5 py-2 text-[11.5px] text-[var(--color-faint)] border-b border-[var(--color-line)] tabular-nums">
            {searching ? `${found.length} of ${sorted.length} match` : `The ${shown.length} most exposed of ${sorted.length}`}
          </div>
          {shown.length === 0 ? <div className="p-8 text-center text-[13px] text-[var(--color-faint)]">Nothing matches. Change the search or filters.</div> : (
            <BookWithMap noun={cfg.noun} color={rgb} selectedId={open} onSelect={id => setOpen(open === id ? null : id)}
              points={shown.map(a => ({
                id: String(a[cfg.idKey] ?? ''), name: String(a[cfg.nameKey] ?? '—'),
                lat: a.lat as number, lon: a.lon as number, score: a.headline_score ?? null,
                sub: [a.region, a[cfg.typeKey] ? String(a[cfg.typeKey]).replace(/_/g, ' ') : null].filter(Boolean).join(' · ') || undefined,
                value: balance(a[cfg.valueKey] as number | null),
              }))}>
              <div className="divide-y divide-[var(--color-line)]">
                {shown.map(a => {
                  const id = String(a[cfg.idKey] ?? '')
                  return <Row key={id} a={a} cfg={cfg} open={open === id} onToggle={() => setOpen(open === id ? null : id)}
                    scenario={scenario} horizon={horizon} onDetail={() => onDetail(id)} />
                })}
              </div>
            </BookWithMap>
          )}
        </>)}
    </Card>
  )
}

function Row({ a, cfg, open, onToggle, scenario, horizon, onDetail }: { a: Asset; cfg: Cfg; open: boolean; onToggle: () => void; scenario: string; horizon: string; onDetail: () => void }) {
  const sc = a.headline_score
  const kind = a[cfg.typeKey] ? String(a[cfg.typeKey]).replace(/_/g, ' ') : null
  const v = a.valuation
  const facts = v ? [
    v.discounted_value_eur != null ? `Risk-adjusted value ${balance(v.discounted_value_eur)}` : null,
    v.effective_discount_pct != null ? `${v.effective_discount_pct}% climate discount` : null,
    v.is_overridden ? 'analyst override on file' : null,
    v.original_ltv_pct != null && v.climate_adjusted_ltv_pct != null ? `loan-to-value ${v.original_ltv_pct}% → ${v.climate_adjusted_ltv_pct}%` : null,
    where(a.lat, a.lon),
  ].filter(Boolean).join(' · ') : null
  return (
    <div>
      <button onClick={onToggle} aria-expanded={open} className={`w-full text-left px-4 py-1.5 flex items-center gap-3 hover:bg-[var(--color-bg-2)] transition ${open ? 'bg-[var(--color-bg-2)]' : ''}`}>
        <ChevronRight size={13} className={`shrink-0 text-[var(--color-faint)] transition-transform ${open ? 'rotate-90' : ''}`} />
        <div className="min-w-0 flex-1 flex items-baseline gap-2">
          <div className="text-[13px] text-[var(--color-ink)] truncate">{String(a[cfg.nameKey] ?? '—')}</div>
          <div className="text-[11.5px] text-[var(--color-faint)] truncate">{[a.region, kind].filter(Boolean).join(' · ') || '—'}</div>
        </div>
        <div className="text-[12px] text-[var(--color-mute)] tabular-nums shrink-0 w-20 text-right">{balance(a[cfg.valueKey] as number | null)}</div>
        <div className="shrink-0 w-32 flex justify-end">
          {sc == null ? <span className="text-[12px] text-[var(--color-faint)]">—</span>
            : <span className="inline-flex items-center gap-1.5 text-[12px] whitespace-nowrap tabular-nums" style={{ color: rgb(sc) }}>
                <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: rgb(sc) }} />
                {Math.round(sc)}/100{a.headline_bucket ? ` · ${bucketLabel(a.headline_bucket)}` : ''}
              </span>}
        </div>
      </button>
      {open && (
        <div className="px-5 pb-4 pt-1 bg-[var(--color-bg-2)]">
          <div className="text-[12px] text-[var(--color-mute)] mb-2">
            Biggest threat: <span className="text-[var(--color-ink)]">{hazardLabel(a.headline_hazard)}</span> · {scenario === 'baseline' ? 'Today' : scenarioLabel(scenario)} · {horizonLabel(horizon)}
          </div>
          <div className="grid sm:grid-cols-2 gap-x-8 gap-y-1.5">
            {(a.hazards ?? []).length === 0 && <div className="text-[12.5px] text-[var(--color-faint)]">No hazard scores for this scenario and year yet.</div>}
            {(a.hazards ?? []).map(h => (
              <div key={h.hazard} className="flex items-center justify-between gap-3 text-[12.5px] border-b border-[var(--color-line)] py-1">
                <span className="min-w-0">
                  <span className="text-[var(--color-mute)]">{hazardLabel(h.hazard)}</span>
                  {h.model_version && <span className="block text-[11px] text-[var(--color-faint)]">{modelLabel(h.model_version)}{h.scored_at ? ` · ${h.scored_at.slice(0, 10)}` : ''}</span>}
                </span>
                <span className="tabular-nums shrink-0 text-right" style={{ color: rgb(h.score) }}>
                  {Math.round(h.score)}/100 · {bucketLabel(h.bucket)}
                  {h.ci_lo != null && h.ci_hi != null && Math.round(h.ci_lo) !== Math.round(h.ci_hi) &&
                    <span className="block text-[10.5px] text-[var(--color-faint)] leading-tight">range {Math.round(h.ci_lo)}–{Math.round(h.ci_hi)}</span>}
                </span>
              </div>
            ))}
          </div>
          {facts && <div className="text-[12px] text-[var(--color-mute)] mt-3 leading-relaxed tabular-nums">{facts}</div>}
          {v?.gap && <div className="mt-2"><MethodGap gap={v.gap} what="Climate-adjusted value" /></div>}
          <button onClick={onDetail} className="mt-3 inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">
            {cfg.overrideMode === 'valuation' ? 'Full detail and valuation override' : 'Full detail and trigger'} →
          </button>
        </div>
      )}
    </div>
  )
}

// A CSV of the book: each row is located and scored on import. The refusal names what is wrong with the file.
function uploadError(e: unknown): string {
  if (e instanceof ApiError) {
    const b = e.body as { error?: { missing?: string[] } | string; missing?: string[] } | null
    const missing = (b && typeof b === 'object' && typeof b.error === 'object' ? b.error?.missing : undefined) ?? (b && typeof b === 'object' ? b.missing : undefined)
    if (Array.isArray(missing)) return `Missing columns: ${missing.join(', ')}`
  }
  return apiMessage(e, 'Import failed. Check the columns against the template.')
}

function useBookUpload(cfg: Cfg, onDone: () => void) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const send = async (file: File) => {
    setBusy(true); setMsg(null)
    try {
      const r = await upload<{ n_uploaded: number; n_skipped: number }>(uploadPath(cfg), file)
      setMsg({ text: `Imported ${r.n_uploaded} ${r.n_uploaded === 1 ? 'row' : 'rows'}${r.n_skipped ? `, ${r.n_skipped} skipped` : ''}.`, ok: true })
      onDone()
    } catch (e) {
      setMsg({ text: uploadError(e), ok: false })
    } finally { setBusy(false) }
  }
  return { busy, msg, send }
}

function TemplateButton({ cfg, big }: { cfg: Cfg; big?: boolean }) {
  const onClick = () => download(templatePath(cfg), `tellumen-${cfg.prefix}-template.xlsx`).catch(() => toast.error('Could not download the template.'))
  return big
    ? <button onClick={onClick} className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--color-line-2)] px-4 py-2 text-[13px] text-[var(--color-ink)] hover:border-[var(--color-sky)] hover:text-[var(--color-sky)] transition"><FileSpreadsheet size={14} /> Download template</button>
    : <button onClick={onClick} className="inline-flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] hover:text-[var(--color-sky)]"><FileSpreadsheet size={13} /> Template</button>
}

function FilePickButton({ busy, onPick, big }: { busy: boolean; onPick: (f: File) => void; big?: boolean }) {
  const cls = big
    ? `inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium cursor-pointer transition ${busy ? 'bg-[var(--color-panel)] text-[var(--color-faint)]' : 'bg-[var(--color-sky)] text-[#08111f] hover:bg-[var(--color-blue)]'}`
    : `inline-flex items-center gap-1.5 text-[12px] cursor-pointer ${busy ? 'text-[var(--color-faint)]' : 'text-[var(--color-mute)] hover:text-[var(--color-sky)]'}`
  return (
    <label className={cls}>
      <Upload size={big ? 14 : 13} /> {busy ? 'Uploading…' : 'Import CSV'}
      <input type="file" accept=".csv" className="hidden" disabled={busy}
        onChange={e => { const f = e.target.files?.[0]; if (f) onPick(f); e.target.value = '' }} />
    </label>
  )
}

function ImportBook({ cfg, onDone }: { cfg: Cfg; onDone: () => void }) {
  const { busy, msg, send } = useBookUpload(cfg, onDone)
  return (
    <div className="flex items-center gap-4">
      {msg && <span className={`text-[11.5px] max-w-xs truncate ${msg.ok ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`} title={msg.text}>{msg.text}</span>}
      <TemplateButton cfg={cfg} />
      <FilePickButton busy={busy} onPick={send} />
    </div>
  )
}

function EmptyBook({ cfg, onDone }: { cfg: Cfg; onDone: () => void }) {
  const { busy, msg, send } = useBookUpload(cfg, onDone)
  const details = { title: `Import your ${cfg.uploadNoun}`, sections: [
    { heading: HEADING.shows, body: 'Upload a CSV of your book. Each row is placed on our map grid and scored for every hazard, the same way a single-address check is.' },
    { heading: HEADING.read, body: 'Start from the template so the columns line up. Rows that cannot be read are skipped and counted.' },
  ] }
  return (
    <div className="p-10 text-center">
      <FileSpreadsheet size={26} className="mx-auto mb-3 text-[var(--color-faint)]" />
      <div className="text-[14px] text-[var(--color-ink)] mb-1 inline-flex items-center gap-1.5">No {cfg.noun} yet: import your {cfg.uploadNoun} <InfoButton compact details={details} /></div>
      <div className="flex items-center justify-center gap-3 mt-3">
        <FilePickButton busy={busy} onPick={send} big />
        <TemplateButton cfg={cfg} big />
      </div>
      {msg && <div className={`text-[12px] mt-4 ${msg.ok ? 'text-[var(--color-good)]' : 'text-[var(--color-bad)]'}`}>{msg.text}</div>}
    </div>
  )
}

