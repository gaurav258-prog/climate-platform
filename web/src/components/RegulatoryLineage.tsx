import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, FileCheck2, Layers, ScrollText, CheckCircle2, AlertTriangle, CircleHelp } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../lib/api'
import { frameworkLabel } from '../lib/hazards'
import { Card } from './ui'
import { HEADING, InfoButton, MessageLine, type DetailSection } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog } from './Dialog'
import { STATUS_TONE, fmtDate } from './filing/words'

// From the law to a filing, read from what the filing froze: the act and its quoted legal basis (is the official text
// held, is the quote found in it word for word) → the specification frozen with the filing (unchanged since? approved by
// two people?) → each template the filing prints and how its rows, columns or items are filled → the frozen record.
// The data-side trace (a figure → its exposures → the sources) is the next card.

interface Axis { n: number; by_source: Record<string, number> }
interface Tpl { id: string; name: string; structure: string; rows?: Axis; columns?: Axis; items?: Axis }
interface Fam {
  family: string; version: string | null; note?: string; frozen_before_specs?: boolean
  act?: { celex: string | null; title: string; status: string; article: string | null; templates_in: string | null; quote: string | null; text_held: boolean; quote_found_in: string | null }
  spec?: { changed_since: boolean | null; applies?: { from?: string | null; until?: string | null } | null
    signoff_of_frozen_file: { approved: boolean; one_person: boolean; signed: { role: string; by: string; signed_at: string }[] } | null }
  templates?: Tpl[]; interpretations?: { subject: string; reading: string; basis: string }[]
  template_detail?: { id: string; rows: { axis: string; id: string; label: string; source: string }[] }
}
interface Data { filing: { framework: string; period_label: string; status: string; payload_sha256: string | null; hash_verified: boolean | null }
  families: Fam[]; elections: { key: string; stated: boolean }[] }

// how a template's cell is filled (services/regspec bindings: the kind before ':')
const FILL: Record<string, { label: string; color: string }> = {
  computed: { label: 'Computed', color: 'var(--color-sky)' }, input: { label: 'You provide', color: 'var(--color-viz, #a78bfa)' },
  'n/a': { label: 'Not applicable', color: 'var(--color-line-2)' }, unbound: { label: 'Not yet bound', color: 'var(--color-bad)' },
}
const ACT_STATUS: Record<string, string> = { adopted: 'Adopted', proposed: 'Proposed', draft: 'Draft', repealed: 'Repealed' }
const ROLE: Record<string, string> = { regulatory: 'Regulatory review', engineering: 'Engineering review' }
const AXIS: Record<string, string> = { rows: 'Row', columns: 'Column', items: 'Item' }
const kind = (s: string) => s.split(':')[0]
// the readings the specification declares where the regulation is silent, each with its basis (for the pop-up)
const readings = (f: Fam) => (f.interpretations ?? []).map(i => `${i.subject}: ${i.reading} (${i.basis})`)

// a yes / no / not known reading, as a chip
const Check = ({ ok, yes, no, unknown = 'Not known' }: { ok: boolean | null | undefined; yes: string; no: string; unknown?: string }) =>
  <StatusChip tone={ok === true ? 'good' : ok === false ? 'warn' : 'neutral'} label={ok === true ? yes : ok === false ? no : unknown} />

function Step({ icon: Icon, title, children, about }: { icon: typeof BookOpen; title: string; children: React.ReactNode; about?: DetailSection[] }) {
  return (
    <div className="min-w-0 space-y-2 rounded-xl border border-[var(--color-line)] p-3">
      <div className="flex items-center gap-1.5 text-[12px] font-medium text-[var(--color-mute)]"><Icon size={13} className="text-[var(--color-blue)]" /> {title}
        {about && about.length > 0 && <InfoButton compact details={{ title, sections: about }} />}</div>
      {children}
    </div>
  )
}

export default function RegulatoryLineage({ filingId }: { filingId: string }) {
  const [tpl, setTpl] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['reg-lineage', filingId, tpl], queryFn: () =>
    api.get<Data>(`/v1/filings/${filingId}/regulatory-lineage${tpl ? `?template=${tpl}` : ''}`) })
  if (q.isLoading) return <Card className="p-4 text-[12.5px] text-[var(--color-faint)]">Reading the filing's frozen record…</Card>
  if (!q.data) return <Card className="p-4"><MessageLine m={{ label: apiMessage(q.error, 'Not available'), detail: apiDetail(q.error) }} className="text-[12.5px] text-[var(--color-mute)]" /></Card>
  const d = q.data
  const stated = d.elections.filter(e => e.stated).length
  return (
    <div className="space-y-3">
      {d.families.length === 0 && <Card className="p-4 text-[12.5px] text-[var(--color-mute)]">This filing froze no specification.</Card>}
      {d.families.map(f => (
        <Card key={f.family} className="p-4 space-y-3">
          {f.version == null
            ? <div className="text-[12.5px] text-[var(--color-mute)] flex items-center gap-1.5">No specification was frozen for part of this report
                {f.note && <InfoButton compact details={{ title: 'No specification frozen', sections: [{ heading: HEADING.shows, body: f.note }] }} />}</div>
            : <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1.4fr_auto_1fr] items-stretch text-[12.5px]">
                <Step icon={ScrollText} title="Law" about={[
                  ...(f.act?.celex ? [{ heading: 'Official reference', body: `CELEX ${f.act.celex}` }] : []),
                  ...(f.act?.article ? [{ heading: 'Legal basis', body: f.act.article }] : []),
                  ...(f.act?.quote ? [{ heading: 'As quoted', body: <blockquote className="italic border-l border-[var(--color-line-2)] pl-2 m-0">{f.act.quote}</blockquote> }] : []),
                  ...(f.act?.quote_found_in ? [{ heading: 'Found in', body: f.act.quote_found_in }] : [])]}>
                  <div className="font-medium text-[var(--color-ink)]">{f.act?.title}</div>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusChip tone="neutral" label={ACT_STATUS[f.act?.status ?? ''] ?? 'Status not known'} />
                    <Check ok={f.act?.text_held} yes="Official text held" no="Official text not held" />
                    {f.act?.quote && <Check ok={!!f.act.quote_found_in} yes="Quote found word for word" no="Quote not found" />}
                  </div>
                </Step>
                <ArrowRight size={14} className="hidden lg:block self-center text-[var(--color-faint)]" />
                <Step icon={BookOpen} title="Specification" about={(f.spec?.signoff_of_frozen_file?.signed ?? []).length
                  ? [{ heading: 'Signed off', body: <ul className="space-y-0.5">{f.spec!.signoff_of_frozen_file!.signed.map(sg => <li key={sg.role + sg.signed_at}>{`${ROLE[sg.role] ?? 'Review'} · ${sg.by} · ${fmtDate(sg.signed_at)}`}</li>)}</ul> }] : undefined}>
                  {f.frozen_before_specs
                    ? <div className="text-[12px] text-[var(--color-faint)]">Frozen before specifications were recorded with filings: the one in use then.</div>
                    : <div className="flex flex-wrap gap-1.5">
                        {f.spec?.applies?.from && <StatusChip tone="neutral" label={`In force from ${fmtDate(f.spec.applies.from)}`} />}
                        <Check ok={f.spec?.changed_since === false ? true : f.spec?.changed_since === true ? false : null} yes="Unchanged since this filing" no="Changed since this filing" />
                        <Check ok={f.spec?.signoff_of_frozen_file?.approved} yes={f.spec?.signoff_of_frozen_file?.one_person ? 'Approved by one person' : 'Approved by two people'} no="Not approved" />
                      </div>}
                </Step>
                <ArrowRight size={14} className="hidden lg:block self-center text-[var(--color-faint)]" />
                <Step icon={Layers} title="Templates printed" about={[{ heading: HEADING.read, body: 'Each bar shows how the template is filled: computed by the platform, provided by you, not applicable, or not yet bound to a figure. Select a template for each row, column or item.' }]}>
                  <div className="space-y-1.5">{(f.templates ?? []).map(t => <TemplateBar key={t.id} t={t} onOpen={() => setTpl(t.id)} />)}</div>
                </Step>
                <ArrowRight size={14} className="hidden lg:block self-center text-[var(--color-faint)]" />
                <Step icon={FileCheck2} title="This filing" about={(f.interpretations ?? []).length ? [{ heading: 'Readings the specification declares',
                  body: <ul className="space-y-1.5">{readings(f).map((r, n) => <li key={n}>{r}</li>)}</ul> }] : undefined}>
                  <div className="font-medium text-[var(--color-ink)]">{frameworkLabel(d.filing.framework)} · {d.filing.period_label}</div>
                  <div className="flex flex-wrap gap-1.5">
                    <StatusChip value={d.filing.status} tone={STATUS_TONE[d.filing.status]} />
                    <Check ok={d.filing.hash_verified} yes="Matches its fingerprint" no="Does not match its fingerprint" />
                    {d.elections.length > 0 && <StatusChip tone={stated === d.elections.length ? 'good' : 'warn'} label={`${stated} of ${d.elections.length} interpretations stated`} />}
                    {(f.interpretations ?? []).length > 0 && <StatusChip tone="neutral" label={`${f.interpretations!.length} declared readings`} />}
                  </div>
                </Step>
              </div>}
          {f.template_detail && tpl === f.template_detail.id && <TemplateDetail t={f.template_detail} title={(f.templates ?? []).find(x => x.id === tpl)?.name ?? 'Template'} onClose={() => setTpl(null)} />}
        </Card>))}
    </div>
  )
}

// One template as a stacked bar of how its cells are filled.
function TemplateBar({ t, onOpen }: { t: Tpl; onOpen: () => void }) {
  const counts: Record<string, number> = {}
  for (const a of ['rows', 'columns', 'items'] as const) for (const [k, n] of Object.entries(t[a]?.by_source ?? {})) counts[kind(k)] = (counts[kind(k)] ?? 0) + n
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  return (
    <button type="button" onClick={onOpen} className="w-full text-left rounded-md border border-[var(--color-line)] hover:border-[var(--color-sky)] px-2 py-1.5 transition">
      <div className="truncate text-[12px] text-[var(--color-ink)]">{t.name}</div>
      <div className="mt-1 flex h-1.5 rounded-full overflow-hidden bg-[var(--color-line)]" role="img"
        aria-label={Object.entries(counts).map(([k, n]) => `${n} ${(FILL[k]?.label ?? 'other').toLowerCase()}`).join(', ')}>
        {Object.entries(counts).map(([k, n]) => <div key={k} title={`${n} ${FILL[k]?.label ?? 'Other'}`} style={{ width: `${(100 * n) / Math.max(1, total)}%`, background: FILL[k]?.color ?? 'var(--color-faint)' }} />)}
      </div>
    </button>
  )
}

// Each row, column or item of one template, as printed, with how it is filled.
function TemplateDetail({ t, title, onClose }: { t: NonNullable<Fam['template_detail']>; title: string; onClose: () => void }) {
  const Icon = (k: string) => k === 'computed' || k === 'input' ? CheckCircle2 : k === 'unbound' ? AlertTriangle : CircleHelp
  return (
    <Dialog title={title} onClose={onClose} className="max-w-3xl">
      <div className="flex flex-wrap gap-3 mb-2 text-[11.5px] text-[var(--color-mute)]">
        {Object.entries(FILL).map(([k, v]) => <span key={k} className="inline-flex items-center gap-1.5"><span className="w-2 h-2 rounded-full" style={{ background: v.color }} />{v.label}</span>)}
      </div>
      <div className="overflow-x-auto max-h-[60vh] overflow-y-auto">
        <table className="w-full text-[12px] min-w-[520px]">
          <thead><tr className="text-left text-[11px] text-[var(--color-faint)]"><th className="pr-3 font-medium">Where</th><th className="pr-3 font-medium">Printed</th><th className="font-medium">How it is filled</th></tr></thead>
          <tbody>{t.rows.map(r => {
            const k = kind(r.source), I = Icon(k)
            return (
              <tr key={r.axis + r.id} className="border-t border-[var(--color-line-2)] align-top">
                <td className="py-1 pr-3 whitespace-nowrap text-[var(--color-mute)]">{AXIS[r.axis] ?? 'Item'} {r.id}</td>
                <td className="py-1 pr-3 text-[var(--color-ink)]">{r.label.split(' > ').slice(-1)[0]}</td>
                <td className="py-1"><span className="inline-flex items-center gap-1" style={{ color: FILL[k]?.color ?? 'var(--color-faint)' }}><I size={12} />{FILL[k]?.label ?? 'Other'}</span></td>
              </tr>)
          })}</tbody>
        </table>
      </div>
    </Dialog>
  )
}
