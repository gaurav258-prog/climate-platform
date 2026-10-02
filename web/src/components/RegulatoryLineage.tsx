import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, BookOpen, FileCheck2, Layers, ScrollText } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { Card } from './ui'

// The regulatory lineage of a filing, read from what it froze: the act and its quoted legal basis (and whether the
// official text is held and the quote found in it) → the specification version frozen with the filing (its file hash,
// whether it changed since, its four-eyes sign-off) → each template the filing prints and how every row, column or item
// is filled → the frozen record (its hash, the interpretations stated, the readings the specification declares).
// The data-side trace (a figure → its exposures → the golden source → the feeds) is the Lineage tab.

interface Tpl { id: string; code: string | null; title: string; ref: string; structure: string
  rows?: { n: number; by_source: Record<string, number> }; columns?: { n: number; by_source: Record<string, number> }; items?: { n: number; by_source: Record<string, number> } }
interface Fam {
  family: string; version: string | null; note?: string; frozen_before_specs?: boolean
  act?: { celex: string | null; title: string; status: string; article: string | null; templates_in: string | null; quote: string | null; text_held: boolean; quote_found_in: string | null }
  spec?: { sha256_frozen: string | null; sha256_now: string; changed_since: boolean | null; signoff_at_freeze: { approved?: boolean; one_person?: boolean; needs?: string[] }
    signoff_of_frozen_file: { approved: boolean; one_person: boolean; signed: { role: string; by: string; signed_at: string; sole_reviewer: boolean }[] } | null }
  templates?: Tpl[]; interpretations?: { subject: string; reading: string; basis: string }[]
  template_detail?: { id: string; rows: { axis: string; id: string; label: string; source: string; kind?: string }[] }
}
interface Data { filing: { framework: string; period_label: string; status: string; payload_sha256: string | null; hash_verified: boolean | null }
  families: Fam[]; elections: { key: string; label: string; value: unknown; stated: boolean }[] }

const SRC: Record<string, string> = { computed: 'var(--color-sky)', input: 'var(--color-viz,#a78bfa)', 'n/a': 'var(--color-faint)', unbound: 'var(--color-bad)' }
const ok = (b: boolean | null | undefined, yes: string, no: string, unknown = 'not known') =>
  <span style={{ color: b === true ? 'var(--color-good)' : b === false ? 'var(--color-warn)' : 'var(--color-faint)' }}>{b === true ? yes : b === false ? no : unknown}</span>

function Col({ icon: Icon, title, children }: { icon: typeof BookOpen; title: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0 space-y-2">
      <div className="flex items-center gap-1.5 mono text-[10px] uppercase tracking-wide text-[var(--color-faint)]"><Icon size={12} /> {title}</div>
      {children}
    </div>
  )
}

export default function RegulatoryLineage({ filingId }: { filingId: string }) {
  const [tpl, setTpl] = useState<string | null>(null)
  const q = useQuery({ queryKey: ['reg-lineage', filingId, tpl], queryFn: () =>
    api.get<Data>(`/v1/filings/${filingId}/regulatory-lineage${tpl ? `?template=${tpl}` : ''}`) })
  if (q.isLoading) return <Card className="p-4 text-[12.5px] text-[var(--color-faint)]">Reading the filing's frozen record…</Card>
  if (!q.data) return <Card className="p-4 text-[12.5px] text-[var(--color-mute)]">{apiMessage(q.error, 'The regulatory lineage is not available.')}</Card>
  const d = q.data
  return (
    <div className="space-y-3">
      {d.families.length === 0 && <Card className="p-4 text-[12.5px] text-[var(--color-mute)]">This filing froze no specification.</Card>}
      {d.families.map(f => (
        <Card key={f.family} className="p-4 space-y-3">
          {f.version == null ? <div className="text-[12.5px] text-[var(--color-mute)]">{f.family}: {f.note}</div> : <>
            <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1.4fr_auto_1fr] items-start text-[12px]">
              <Col icon={ScrollText} title="Law">
                <div className="font-medium">{f.act?.title}</div>
                <div className="mono text-[10.5px] text-[var(--color-faint)]">CELEX {f.act?.celex ?? '—'} · {f.act?.status}</div>
                {f.act?.article && <div className="text-[var(--color-mute)]">{f.act.article}</div>}
                {f.act?.quote && <blockquote className="text-[11px] italic text-[var(--color-faint)] border-l border-[var(--color-line-2)] pl-2 line-clamp-4">{f.act.quote}</blockquote>}
                <div className="text-[11px]">Official text {ok(f.act?.text_held, 'held', 'not held')} · quote {ok(f.act?.quote ? !!f.act?.quote_found_in : null, `found word for word${f.act?.quote_found_in ? ` (${f.act.quote_found_in})` : ''}`, 'not found')}</div>
              </Col>
              <ArrowRight size={14} className="hidden lg:block mt-6 text-[var(--color-faint)]" />
              <Col icon={BookOpen} title="Specification">
                <div className="font-medium mono">{f.family} · {f.version}</div>
                {f.frozen_before_specs
                  ? <div className="text-[11px] text-[var(--color-faint)]">Frozen before specifications were stamped on filings — the version in use then.</div>
                  : <>
                    <div className="mono text-[10.5px] text-[var(--color-faint)]">file {f.spec?.sha256_frozen?.slice(0, 12)}…</div>
                    <div className="text-[11px]">File {ok(f.spec?.changed_since === false ? true : f.spec?.changed_since === true ? false : null, 'unchanged since', 'changed since this filing')}</div>
                    <div className="text-[11px]">Sign-off of this file {ok(f.spec?.signoff_of_frozen_file?.approved, f.spec?.signoff_of_frozen_file?.one_person ? 'approved (one person, both roles)' : 'approved, four eyes', 'not approved')}</div>
                    {(f.spec?.signoff_of_frozen_file?.signed ?? []).map(sg => <div key={sg.role + sg.signed_at} className="mono text-[10px] text-[var(--color-faint)]">{sg.role} · {sg.by} · {sg.signed_at.slice(0, 10)}</div>)}
                  </>}
              </Col>
              <ArrowRight size={14} className="hidden lg:block mt-6 text-[var(--color-faint)]" />
              <Col icon={Layers} title="Templates printed">
                <div className="space-y-1">{(f.templates ?? []).map(t => {
                  const axes = (['rows', 'columns', 'items'] as const).filter(a => t[a])
                  return (
                    <button key={t.id} type="button" onClick={() => setTpl(tpl === t.id ? null : t.id)} aria-pressed={tpl === t.id}
                      className={`w-full text-left rounded-md border px-2 py-1 ${tpl === t.id ? 'border-[var(--color-sky)]' : 'border-[var(--color-line)] hover:border-[var(--color-line-2)]'}`}>
                      <div className="truncate">{t.code ?? t.id} · <span className="text-[var(--color-mute)]">{t.title}</span></div>
                      <div className="flex flex-wrap gap-x-3 mono text-[10px]">{axes.map(a => (
                        <span key={a} className="text-[var(--color-faint)]">{a} {t[a]!.n}: {Object.entries(t[a]!.by_source).map(([k, n]) => <span key={k} style={{ color: SRC[k] }}> {n} {k}</span>)}</span>))}</div>
                    </button>)
                })}</div>
              </Col>
              <ArrowRight size={14} className="hidden lg:block mt-6 text-[var(--color-faint)]" />
              <Col icon={FileCheck2} title="Filing">
                <div className="font-medium">{d.filing.framework} · {d.filing.period_label} · {d.filing.status}</div>
                <div className="text-[11px]">Frozen record {ok(d.filing.hash_verified, 'hash verifies', 'hash does not verify')}</div>
                <div className="mono text-[10px] text-[var(--color-faint)]">{d.filing.payload_sha256?.slice(0, 16)}…</div>
                <div className="text-[11px] text-[var(--color-mute)]">{d.elections.filter(e => e.stated).length} of {d.elections.length} interpretation(s) stated by the organisation</div>
                {(f.interpretations ?? []).length > 0 && <div className="text-[11px] text-[var(--color-mute)]">{f.interpretations!.length} reading(s) declared by the specification</div>}
              </Col>
            </div>
            {f.template_detail && <TemplateDetail t={f.template_detail} />}
            {(f.interpretations ?? []).length > 0 && (
              <details className="text-[11.5px] text-[var(--color-mute)]"><summary className="cursor-pointer text-[var(--color-faint)]">Readings the specification declares</summary>
                <ul className="mt-1 space-y-1.5">{f.interpretations!.map((i, n) => <li key={n}><span className="text-[var(--color-ink)]">{i.subject}:</span> {i.reading} <span className="text-[var(--color-faint)]">— {i.basis}</span></li>)}</ul></details>)}
          </>}
        </Card>))}
    </div>
  )
}

function TemplateDetail({ t }: { t: NonNullable<Fam['template_detail']> }) {
  return (
    <div className="overflow-x-auto max-h-[360px] overflow-y-auto border-t border-[var(--color-line)] pt-2">
      <table className="w-full text-[11.5px] min-w-[620px]">
        <thead><tr className="text-left mono text-[10px] uppercase text-[var(--color-faint)]"><th className="pr-3">{t.id}</th><th className="pr-3">Printed</th><th>How it is filled</th></tr></thead>
        <tbody>{t.rows.map(r => (
          <tr key={r.axis + r.id} className="border-t border-[var(--color-line-2)] align-top">
            <td className="py-1 pr-3 mono whitespace-nowrap">{r.axis.slice(0, -1)} {r.id}</td>
            <td className="py-1 pr-3 text-[var(--color-mute)]">{r.label.split(' > ').slice(-1)[0]}</td>
            <td className="py-1 mono" style={{ color: SRC[r.source.split(':')[0]] }}>{r.source}</td>
          </tr>))}</tbody>
      </table>
    </div>
  )
}
