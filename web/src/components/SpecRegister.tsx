import { Fragment, type ReactNode, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, ExternalLink, FileCheck2 } from 'lucide-react'
import { api, apiDetail, apiMessage } from '../lib/api'
import { toast } from '../lib/toast'
import { Button, Card, SectionHead, StatGrid } from './ui'
import { HBar } from './Charts'
import { CloseButton } from './Dialog'
import { Drawer } from './Drawer'
import { StatusChip } from './StatusChip'
import { DetailsBody, HEADING, InfoButton, MessageLine, messageDetails, type DetailSection, type Message } from './Details'

// Template specifications (the regulatory-change route), to the UI standard (2026-10-16): each version of a regulation's
// templates, captured from the official text and signed off by a regulatory reviewer and an engineer — two different
// people, on the file's exact content. The main screen is each regulation's versions on one time line, coloured by
// their sign-off; a version opens in a side drawer with what changed, its coverage, its record and the sign-off itself.

const ABOUT = [
  { heading: HEADING.shows, body: 'Every version of every regulation’s templates the platform files to, as captured from the official text, and whether it has been signed off.' },
  { heading: HEADING.read, body: <ul className="list-disc pl-5 space-y-1">
    <li>Each bar is one version, from the date it applies to the date the next one takes over. A dashed bar is a draft, not adopted yet.</li>
    <li><b>Signed off</b> — a regulatory reviewer confirmed the content matches the official act, and a different person, an engineer, confirmed the platform covers every row and column.</li>
    <li><b>One person</b> — the same person signed both roles and declared they are the only reviewer. The record says it is not a four-eyes review.</li>
    <li>A sign-off is on the file’s exact content: any later edit means it must be signed again.</li>
  </ul> },
  { heading: HEADING.limits, body: 'A filing records the version it was prepared under and the sign-off of that exact content; a later version never changes it.' },
]

export default function SpecRegister({ canSign, userId }: { canSign: boolean; userId?: string }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['regspec'], queryFn: () => api.get<{ specs: Spec[] }>('/v1/regspec') })
  const [open, setOpen] = useState<string | null>(null)
  if (q.isLoading) return <Card className="p-6 text-center text-[13px] text-[var(--color-faint)]">Loading…</Card>
  if (!q.data) return <Card className="p-6 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'Could not load the specifications.')}</Card>
  const specs = q.data.specs
  const key = (s: Spec) => `${s.framework}/${s.version}`
  const count = (k: keyof typeof SIGNOFF) => specs.filter(s => signoff(s) === k).length
  const families = [...new Set(specs.map(s => s.framework))].map(f => specs.filter(s => s.framework === f))
  const today = new Date().toISOString().slice(0, 10)
  const years = specs.flatMap(s => [s.applies.from, s.applies.until].filter((x): x is string => !!x)).map(x => Number(x.slice(0, 4)))
  const y0 = Math.min(...years, Number(today.slice(0, 4))), y1 = Math.max(...years, Number(today.slice(0, 4))) + 2
  const ms = (x: string) => new Date(`${x.slice(0, 10)}T00:00:00`).getTime()
  const lo = ms(`${y0}-01-01`), hi = ms(`${y1}-01-01`)
  const pos = (x: string) => Math.min(100, Math.max(0, ((ms(x) - lo) / (hi - lo)) * 100))
  const ticks = Array.from({ length: y1 - y0 + 1 }, (_, i) => y0 + i)
  const current = specs.find(s => key(s) === open) ?? null
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5">
        <SectionHead icon={FileCheck2}>Template specifications</SectionHead>
        <InfoButton compact details={{ title: 'Template specifications', sections: ABOUT }} />
      </div>
      <StatGrid cols={4} items={[
        { label: 'Versions', value: specs.length },
        { label: SIGNOFF.two.label, value: count('two') },
        { label: SIGNOFF.one.label, value: count('one'), accent: count('one') ? SIGNOFF.one.color : undefined },
        { label: SIGNOFF.awaiting.label, value: count('awaiting'), accent: count('awaiting') ? SIGNOFF.awaiting.color : undefined },
      ]} />
      <Card className="p-5 space-y-2">
        <div className="flex flex-wrap gap-x-3 gap-y-1 justify-end">
          {Object.values(SIGNOFF).map(v => <span key={v.label} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: v.color }} />{v.label}</span>)}
          <span className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-3 h-2.5 rounded-sm border border-dashed border-[var(--color-mute)]" />Draft</span>
        </div>
        <div className="hidden md:grid grid-cols-[minmax(0,15rem)_minmax(0,1fr)] gap-4 text-[10.5px] text-[var(--color-faint)]">
          <span /><span className="relative h-3">{ticks.map(y => <span key={y} className="absolute -translate-x-1/2" style={{ left: `${pos(`${y}-01-01`)}%` }}>{y}</span>)}</span>
        </div>
        <div className="divide-y divide-[var(--color-line)]">
          {families.map(vs => (
            <div key={vs[0].framework} className="py-3 grid md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)] items-center gap-x-4 gap-y-2">
              <span className="min-w-0">
                <span className="block text-[13px] text-[var(--color-ink)] leading-snug">{vs[0].name}</span>
                <span className="block text-[11.5px] text-[var(--color-faint)] mt-0.5">{vs.length} {vs.length === 1 ? 'version' : 'versions'}</span>
              </span>
              <span className="relative h-8 block">
                {ticks.map(y => <span key={y} className="absolute top-0 bottom-0 w-px bg-[var(--color-line)]" style={{ left: `${pos(`${y}-01-01`)}%` }} />)}
                <span className="absolute top-0 bottom-0 w-0.5 bg-[var(--color-faint)]" style={{ left: `${pos(today)}%` }} title="Today" />
                {vs.map((s, i) => {
                  const from = s.applies.from ? pos(s.applies.from) : 92, to = s.applies.until ? pos(s.applies.until) : s.applies.from ? 100 : 99
                  const c = SIGNOFF[signoff(s)].color
                  return (
                    <button key={s.version} type="button" onClick={() => setOpen(key(s))} aria-label={`${s.name}, version ${i + 1}: ${SIGNOFF[signoff(s)].label}`}
                      title={s.applies.from ? `From ${day(s.applies.from)}${s.applies.until ? ` to ${day(s.applies.until)}` : ''}` : 'Draft, date not set'}
                      className="absolute top-1.5 h-5 rounded-md hover:brightness-110 hover:z-10 transition flex items-center justify-end pr-1"
                      style={{ left: `${from}%`, width: `max(10px, ${to - from}%)`, background: s.status === 'draft' ? `color-mix(in oklab, ${c} 18%, transparent)` : c,
                        border: s.status === 'draft' ? `1.5px dashed ${c}` : '1px solid var(--color-panel)' }}>
                      {(s.uncovered || s.checks?.failing) ? <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-panel)]" /> : null}
                    </button>
                  )
                })}
              </span>
            </div>
          ))}
        </div>
        <div className="text-[11.5px] text-[var(--color-faint)] inline-flex items-center gap-1">Open a version for what changed, its coverage and its sign-off <ChevronRight size={12} /></div>
      </Card>
      {current && <SpecVersion s={current} family={specs.filter(s => s.framework === current.framework)} canSign={canSign} userId={userId}
        onOpen={v => setOpen(key(v))} onClose={() => setOpen(null)} onSigned={() => qc.invalidateQueries({ queryKey: ['regspec'] })} />}
    </div>
  )
}

// One version of a template specification, opened from the spec register (UI standard, 2026-10-16): when it applies,
// what changed from the version before, whether the platform covers every row and column, how it was captured, the
// readings declared where the text is silent — and the four-eyes sign-off, with its controls exactly as the route
// requires (two different people, or one person who declares it; any edit voids earlier sign-offs).

interface Signed { role: string; role_label: string; email: string; full_name: string | null; user_id: string; signed_at: string; sole_reviewer: boolean }
interface Pass { by: string; date: string; result: string; checked: string }
type Axis = { added: number; removed: number; relabelled: number; moved: number }
interface DiffView {
  kind_label: string; templates: { added: number; removed: number; changed: number; unchanged: number }; cells: Record<'rows' | 'columns' | 'items', Axis>
  added: { code: string; title: string }[]; removed: { code: string; title: string }[]
  changed: ({ code: string; title: string; title_changed: boolean; moved: boolean } & Partial<Record<'rows' | 'columns' | 'items', Axis>>)[]
}
interface Spec {
  framework: string; name: string; version: string; sha256: string; status: 'adopted' | 'draft'; approved: boolean; needs: string[]; needs_labels: string[]
  signed: Signed[]; voided_by_edit: Signed[]; one_person: boolean
  act: { celex: string | null; title: string; url: string; short?: string }
  applies: { from: string | null; until: string | null; basis: string; basis_label: string }
  legal_basis: Record<string, string>
  templates: { id: string; code: string | null; title: string; structure: string }[]
  coverage_by_template: { code: string; title: string | null; missing: number; stale: number; invalid: number }[]
  uncovered: number | null; checks: { failing: number; message: Message | null } | null; diff: DiffView | null
  capture: ({ method: string; captured: string; second_pass: (Pass & Record<string, Pass | string>) | null }) | null
  interpretations: { subject: string; reading: string; basis: string; declared_by: string }[]
}

const SIGNOFF = {
  two: { label: 'Signed off', color: 'var(--color-good)', tone: 'good' as const },
  one: { label: 'One person signed', color: 'var(--color-warn)', tone: 'warn' as const },
  awaiting: { label: 'Awaiting sign-off', color: 'var(--color-bad)', tone: 'bad' as const },
}
const signoff = (s: Spec): keyof typeof SIGNOFF => !s.approved ? 'awaiting' : s.one_person ? 'one' : 'two'
const day = (x: string | null | undefined) => x ? new Date(`${x.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
const ROLES = ['regulatory', 'engineering']
// a role's name as the server gives it: from its sign-off, or from the roles still needed
const roleLabel = (s: Spec, r: string) => s.signed.find(g => g.role === r)?.role_label ?? s.needs_labels[s.needs.indexOf(r)] ?? ''

function Block({ title, info, children }: { title: string; info?: DetailSection[]; children: ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2"><h4 className="text-[13px] font-semibold text-[var(--color-ink)] m-0">{title}</h4>
        {info && <InfoButton compact details={{ title, sections: info }} />}</div>
      {children}
    </section>
  )
}

const Fact = ({ k, v, sub }: { k: string; v: ReactNode; sub?: ReactNode }) => (
  <div className="rounded-lg border border-[var(--color-line-2)] px-3 py-2.5 min-w-0">
    <div className="text-[11.5px] text-[var(--color-faint)]">{k}</div>
    <div className="text-[14px] font-medium text-[var(--color-ink)] mt-0.5">{v}</div>
    {sub && <div className="text-[11.5px] text-[var(--color-mute)] mt-0.5">{sub}</div>}
  </div>
)

function SpecVersion({ s, family, canSign, userId, onOpen, onClose, onSigned }: {
  s: Spec; family: Spec[]; canSign: boolean; userId?: string; onOpen: (v: Spec) => void; onClose: () => void; onSigned: () => void
}) {
  const [sole, setSole] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<Message | null>(null)
  const signedOther = s.signed.some(g => g.user_id === userId)        // this person already signed the other role
  const sign = async (role: string) => {
    setBusy(true); setErr(null)
    try {
      await api.post(`/v1/regspec/${s.framework}/${s.version}/sign`, { role, sha256: s.sha256, sole_reviewer: signedOther })
      toast.success(`Signed as ${roleLabel(s, role).toLowerCase()}`); onSigned()
    } catch (e) { setErr({ label: apiMessage(e, 'Could not sign.'), detail: apiDetail(e) }) }
    finally { setBusy(false) }
  }
  const st = signoff(s)
  const passes = s.capture?.second_pass ? [s.capture.second_pass, ...Object.values(s.capture.second_pass).filter((v): v is Pass => typeof v === 'object' && v !== null)] : []
  return (
    <Drawer label={s.name} onClose={onClose} className="w-full max-w-3xl h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5 space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[17px] font-semibold text-[var(--color-ink)] leading-snug">{s.name}</div>
          <div className="flex flex-wrap items-center gap-2 mt-1.5">
            <StatusChip label={s.status === 'draft' ? 'Draft' : 'Adopted'} tone={s.status === 'draft' ? 'neutral' : 'good'} />
            <StatusChip label={SIGNOFF[st].label} tone={SIGNOFF[st].tone} />
          </div>
        </div>
        <CloseButton onClick={onClose} />
      </div>
      {family.length > 1 && (
        <div className="flex flex-wrap gap-1.5" aria-label="Versions">
          {family.map((v, i) => (
            <button key={v.version} type="button" onClick={() => onOpen(v)}
              className={`text-[11.5px] px-2.5 py-1 rounded-full border transition ${v.version === s.version ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)] hover:text-[var(--color-ink)]'}`}>
              {i + 1}. {v.applies.from ? `From ${day(v.applies.from)}` : 'Draft'}
            </button>))}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Fact k="Applies from" v={s.applies.from ? day(s.applies.from) : 'Not set'} sub={s.applies.until ? `until ${day(s.applies.until)}` : s.applies.from ? 'onwards' : 'set on adoption'} />
        <Fact k="Decided by" v={<span className="text-[13px]">{s.applies.basis_label}</span>} />
        <Fact k="Templates" v={s.templates.length || '—'} sub={s.templates.length ? undefined : 'a rule file'} />
        <Fact k="Coverage" v={s.checks ? (s.checks.failing ? <span className="text-[var(--color-warn)]">{s.checks.failing} checks fail</span> : 'All checks pass')
          : s.uncovered == null ? 'Not mapped' : s.uncovered ? <span className="text-[var(--color-warn)]">{s.uncovered} to map</span> : 'Complete'} />
      </div>

      <Block title="Sign-off" info={[
        { heading: HEADING.read, body: 'A regulatory reviewer confirms the content matches the official act; an engineer, a different person, confirms the platform covers every row and column. Each signs the file’s exact content: an edit means signing again.' },
        { heading: HEADING.limits, body: 'If you are the only reviewer, you may sign the second role by declaring it. The record then says it is not a four-eyes review.' },
      ]}>
        <div className="grid sm:grid-cols-2 gap-3">
          {ROLES.map(r => {
            const g = s.signed.find(x => x.role === r)
            return (
              <div key={r} className="rounded-lg border px-3 py-2.5" style={{ borderColor: g ? `color-mix(in oklab, ${g.sole_reviewer ? 'var(--color-warn)' : 'var(--color-good)'} 45%, transparent)` : 'var(--color-line-2)' }}>
                <div className="text-[11.5px] text-[var(--color-faint)]">{roleLabel(s, r)}</div>
                {g ? <>
                  <div className="text-[13px] text-[var(--color-ink)] mt-0.5">{g.full_name ?? g.email}</div>
                  <div className="text-[11.5px] text-[var(--color-mute)]">{day(g.signed_at)}{g.sole_reviewer ? ' · declared the only reviewer' : ''}</div>
                </> : <div className="text-[13px] text-[var(--color-faint)] mt-0.5">Awaiting</div>}
              </div>
            )
          })}
        </div>
        {s.voided_by_edit.length > 0 && <div className="text-[11.5px] text-[var(--color-faint)] mt-2 inline-flex items-center gap-1">
          {s.voided_by_edit.length} earlier {s.voided_by_edit.length === 1 ? 'sign-off no longer counts' : 'sign-offs no longer count'}
          <InfoButton compact details={{ title: 'Earlier sign-offs', sections: [{ heading: HEADING.shows, body: 'The file changed after they were given, so they do not apply to its current content. They stay on the record.' },
            { heading: 'On the record', body: <ul className="list-disc pl-5">{s.voided_by_edit.map((g, i) => <li key={i}>{g.role_label} · {g.full_name ?? g.email} · {day(g.signed_at)}</li>)}</ul> }] }} /></div>}
        {canSign && s.needs.length > 0 && (
          <div className="pt-3 space-y-2">
            {signedOther && (
              <label className="flex items-start gap-2 text-[12.5px] text-[var(--color-mute)] max-w-[62ch]">
                <input type="checkbox" className="mt-0.5" checked={sole} onChange={e => setSole(e.target.checked)} />
                <span>I am the only reviewer. Record this as a one-person sign-off — the record will say it is not a four-eyes review.</span>
              </label>)}
            <div className="flex flex-wrap gap-2">
              {s.needs.map((r, i) => <Button key={r} variant="ghost" disabled={busy || (signedOther && !sole)} onClick={() => sign(r)}>Sign as {s.needs_labels[i].toLowerCase()}</Button>)}
            </div>
            {err && <div className="text-[12.5px] text-[var(--color-bad)]"><MessageLine m={err} /></div>}
          </div>)}
      </Block>

      {s.diff && <DiffBlock d={s.diff} />}

      {s.checks?.message && <Block title={s.checks.message.label}><DetailsBody sections={messageDetails(s.checks.message).sections} /></Block>}
      {s.coverage_by_template.length > 0 && (
        <Block title="Not yet covered" info={[{ heading: HEADING.shows, body: 'Per template, the rows, columns or items the platform does not map yet, and those it still maps that this version no longer has.' }]}>
          <HBar data={s.coverage_by_template.map(c => ({ label: c.title ?? 'A template not in this version', value: c.missing + c.stale + c.invalid, color: c.missing ? 'var(--color-warn)' : 'var(--color-slate)' }))}
            format={n => String(n)} labelWidth="w-64" height={16} />
        </Block>
      )}

      {s.interpretations.length > 0 && (
        <Block title="Declared readings" info={[{ heading: HEADING.shows, body: 'Where the official text is silent or open, the reading the platform applies, why, and who declared it.' }]}>
          <div className="space-y-2">{s.interpretations.map(i => (
            <div key={i.subject} className="rounded-lg border border-[var(--color-line-2)] p-3">
              <div className="flex items-start justify-between gap-2"><span className="text-[12.5px] font-medium text-[var(--color-ink)]">{i.subject}</span>
                <InfoButton compact details={{ title: i.subject, sections: [{ heading: 'Why', body: i.basis }, { heading: 'Declared by', body: i.declared_by }] }} /></div>
              <p className="text-[12.5px] text-[var(--color-mute)] mt-1 mb-0 leading-relaxed">{i.reading}</p>
            </div>))}</div>
        </Block>
      )}

      {s.templates.length > 0 && <Templates list={s.templates} />}

      {s.capture && (
        <Block title="How it was captured">
          <div className="text-[12.5px] text-[var(--color-mute)] leading-relaxed">{s.capture.method[0].toUpperCase() + s.capture.method.slice(1)}, {day(s.capture.captured)}.</div>
          {passes.length ? passes.map((p, i) => (
            <div key={i} className="mt-2 flex items-start gap-2 text-[12.5px]">
              <StatusChip label={p.result === 'verified' ? 'Second check passed' : `Second check: ${p.result}`} tone={p.result === 'verified' ? 'good' : 'warn'} />
              <span className="text-[var(--color-mute)] min-w-0">{day(p.date)}<InfoButton compact className="ml-1" details={{ title: 'Second check', sections: [{ heading: 'What was checked', body: p.checked }, { heading: 'By', body: p.by }] }} /></span>
            </div>)) : <div className="mt-2"><StatusChip label="No second check yet" tone="warn" /></div>}
        </Block>
      )}

      <Block title="The act">
        <a href={s.act.url} target="_blank" rel="noopener noreferrer" className="text-[13px] text-[var(--color-sky)] hover:underline inline-flex items-start gap-1.5"><ExternalLink size={13} className="mt-0.5 shrink-0" /> {s.act.title}</a>
        {(s.legal_basis.article || s.legal_basis.templates_in) && <dl className="mt-2 grid grid-cols-[8rem_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]">
          {[['Legal basis', s.legal_basis.article], ['Templates in', s.legal_basis.templates_in], ['Instructions in', s.legal_basis.instructions_in]].filter(([, v]) => v).map(([k, v]) => <Fragment key={k}><dt className="text-[var(--color-faint)]">{k}</dt><dd className="m-0 text-[var(--color-mute)]">{v}</dd></Fragment>)}
        </dl>}
        <div className="mt-2 text-[11.5px] text-[var(--color-faint)]">File fingerprint {s.sha256.slice(0, 12)}</div>
      </Block>
    </Drawer>
  )
}

const KIND = [
  { k: 'added' as const, label: 'Added', color: 'var(--color-sky)' }, { k: 'changed' as const, label: 'Changed', color: 'var(--color-warn)' },
  { k: 'removed' as const, label: 'Removed', color: 'var(--color-bad)' }, { k: 'unchanged' as const, label: 'Unchanged', color: 'var(--color-line-2)' },
]
const CELL = [['added', 'added'], ['removed', 'removed'], ['relabelled', 'reworded'], ['moved', 'renumbered']] as const

function DiffBlock({ d }: { d: DiffView }) {
  const [open, setOpen] = useState(false)
  const t = d.templates, total = t.added + t.changed + t.removed + t.unchanged
  const cells = (['rows', 'columns', 'items'] as const).map(a => ({ a, parts: CELL.map(([k, w]) => ({ n: d.cells[a][k], w })).filter(p => p.n) })).filter(x => x.parts.length)
  return (
    <Block title="What changed from the version before" info={[{ heading: HEADING.read, body: 'Templates added, changed, removed or carried over unchanged; within changed templates, rows, columns and printed items added, removed, reworded or renumbered.' }]}>
      <div className="flex items-center gap-2 mb-2"><StatusChip label={d.kind_label} tone="neutral" /></div>
      {total > 0 && <>
        <div className="flex w-full overflow-hidden rounded-full bg-[var(--color-panel-2)] h-3" role="img" aria-label={KIND.map(x => `${x.label} ${t[x.k]}`).join(', ')}>
          {KIND.filter(x => t[x.k]).map(x => <div key={x.k} title={`${x.label}: ${t[x.k]}`} style={{ width: `${(t[x.k] / total) * 100}%`, background: x.color, minWidth: 3 }} />)}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2">{KIND.map(x => <span key={x.k} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: x.color }} />{x.label} {t[x.k]}</span>)}</div>
      </>}
      {cells.length > 0 && <div className="mt-2 text-[12px] text-[var(--color-mute)] space-y-0.5">
        {cells.map(({ a, parts }) => <div key={a}><span className="capitalize text-[var(--color-ink)]">{a}</span>: {parts.map(p => `${p.n} ${p.w}`).join(' · ')}</div>)}
      </div>}
      {(d.changed.length + d.added.length + d.removed.length) > 0 && (
        <div className="mt-2">
          <button type="button" onClick={() => setOpen(v => !v)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">
            {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} By template</button>
          {open && <ul className="mt-1.5 space-y-1 text-[12px]">
            {d.added.map(x => <li key={`a${x.code}`} className="flex gap-2"><span className="w-2 h-2 mt-1.5 rounded-sm shrink-0" style={{ background: KIND[0].color }} /><span className="text-[var(--color-mute)]">{x.title}</span></li>)}
            {d.changed.map(x => <li key={`c${x.code}`} className="flex gap-2"><span className="w-2 h-2 mt-1.5 rounded-sm shrink-0" style={{ background: KIND[1].color }} /><span className="text-[var(--color-mute)]">{x.title}
              <span className="text-[var(--color-faint)]"> · {[x.title_changed && 'title', x.moved && 'location', ...(['rows', 'columns', 'items'] as const).flatMap(a => x[a] ? CELL.filter(([k]) => x[a]![k]).map(([k, w]) => `${x[a]![k]} ${a} ${w}`) : [])].filter(Boolean).join(', ') || 'wording'}</span></span></li>)}
            {d.removed.map(x => <li key={`r${x.code}`} className="flex gap-2"><span className="w-2 h-2 mt-1.5 rounded-sm shrink-0" style={{ background: KIND[2].color }} /><span className="text-[var(--color-mute)] line-through decoration-[var(--color-faint)]">{x.title}</span></li>)}
          </ul>}
        </div>)}
    </Block>
  )
}

function Templates({ list }: { list: Spec['templates'] }) {
  const [open, setOpen] = useState(false)
  return (
    <Block title={`Templates · ${list.length}`}>
      <button type="button" onClick={() => setOpen(v => !v)} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />} {open ? 'Hide' : 'Show'} the templates</button>
      {open && <ul className="mt-1.5 grid sm:grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
        {list.map(t => <li key={t.id} className="text-[var(--color-mute)] leading-snug">{t.title}{t.structure === 'full' ? <span className="text-[var(--color-good)]"> · every row and column</span> : null}</li>)}
      </ul>}
    </Block>
  )
}
