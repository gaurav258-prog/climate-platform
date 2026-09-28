import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { FileCheck2, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import { api, ApiError } from '../lib/api'
import { toast } from '../lib/toast'
import { Card, Button } from './ui'

// Template specifications (the regulatory-change route): each version of a regulation's templates, captured from the
// official text. Shows what changed from the version before, whether the implementation covers every row and column,
// and the four-eyes sign-off — a regulatory reviewer and an engineer, two different people, on the file's exact bytes.

interface Signed { role: string; email: string; signed_at: string; sha256: string }
interface Axis { added: string[]; removed: string[]; relabelled: { id: string; from: string; to: string }[] }
interface Changed { id: string; title?: { from: string; to: string }; ref?: { from: string; to: string }; rows?: Axis; columns?: Axis; z_axis?: { from: string; to: string } }
interface Diff { from: string; kind: string; templates_added: string[]; templates_removed: string[]; changed: Changed[]; unchanged: string[]; legal_basis: Record<string, { from: string; to: string }> }
interface Spec {
  framework: string; name: string; version: string; sha256: string; status: 'adopted' | 'draft'; approved: boolean; needs: string[]
  signed: Signed[]; voided_by_edit: Signed[]
  act: { celex: string | null; title: string; url: string; short?: string }
  applies: { from: string; until: string | null; basis: string }
  templates: { id: string; code: string; title: string; structure: string }[]
  coverage: { complete: boolean; missing: string[]; stale: string[]; invalid: string[] } | null
  diff_from_previous: Diff | null
  capture: { method: string; captured: string; second_pass: { by: string; date: string; result: string; checked: string } | null } | null
  interpretations: { subject: string; reading: string; basis: string; declared_by: string }[]
}

const pill = (color: string) => ({ color, background: `color-mix(in oklab, ${color} 14%, transparent)` })

function DiffView({ d }: { d: Diff }) {
  const lines: string[] = []
  Object.entries(d.legal_basis).forEach(([k, v]) => lines.push(`${k.replace('_', ' ')}: ${v.from} → ${v.to}`))
  if (d.templates_added.length) lines.push(`templates added: ${d.templates_added.join(', ')}`)
  if (d.templates_removed.length) lines.push(`templates removed: ${d.templates_removed.join(', ')}`)
  const moved = d.changed.filter(c => Object.keys(c).every(k => k === 'id' || k === 'ref')).map(c => c.id)
  if (moved.length) lines.push(`where printed moved for ${moved.length} template${moved.length === 1 ? '' : 's'} (${moved.join(', ')})`)
  d.changed.filter(c => !moved.includes(c.id)).forEach(c => {
    const parts: string[] = []
    if (c.title) parts.push('title')
    if (c.ref) parts.push('location')
    if (c.z_axis) parts.push('axis')
    ;(['rows', 'columns'] as const).forEach(a => {
      const x = c[a]; if (!x) return
      if (x.added.length) parts.push(`${a} added ${x.added.join(', ')}`)
      if (x.removed.length) parts.push(`${a} removed ${x.removed.join(', ')}`)
      if (x.relabelled.length) parts.push(`${x.relabelled.length} ${a} relabelled`)
    })
    lines.push(`${c.id}: ${parts.join('; ')}`)
  })
  return (
    <div className="mt-2 text-[11.5px] text-[var(--color-mute)]">
      <div>From <b className="text-[var(--color-ink)]">{d.from}</b>: <b className="text-[var(--color-ink)]">{d.kind}</b>{d.unchanged.length ? ` · ${d.unchanged.length} template${d.unchanged.length === 1 ? '' : 's'} carry over unchanged` : ''}</div>
      <ul className="mt-1 space-y-0.5 mono text-[10.5px]">{lines.map((l, i) => <li key={i}>· {l}</li>)}</ul>
    </div>
  )
}

export default function SpecRegister({ canSign }: { canSign: boolean }) {
  const qc = useQueryClient()
  const q = useQuery({ queryKey: ['regspec'], queryFn: () => api.get<{ specs: Spec[] }>('/v1/regspec') })
  const [open, setOpen] = useState<string | null>(null)
  const sign = async (s: Spec, role: string) => {
    try {
      await api.post(`/v1/regspec/${s.framework}/${s.version}/sign`, { role, sha256: s.sha256 })
      toast.success(`Signed as ${role}`); qc.invalidateQueries({ queryKey: ['regspec'] })
    } catch (e) { toast.error(e instanceof ApiError ? e.message : 'Could not sign.') }
  }
  if (q.isLoading) return <Card className="p-6 text-center text-[var(--color-faint)] text-sm">loading…</Card>
  if (!q.data) return <div className="text-[12.5px] text-[var(--color-bad)]">Could not load the specifications.</div>
  return (
    <div className="space-y-2.5">
      <div className="flex items-center gap-2">
        <FileCheck2 size={15} className="text-[var(--color-sky)]" />
        <span className="text-[13px] font-semibold text-[var(--color-ink)]">Template specifications</span>
        <span className="mono text-[10px] text-[var(--color-faint)]">· each version captured from the official text · signed by a regulatory reviewer and an engineer</span>
      </div>
      {q.data.specs.map(s => {
        const key = `${s.framework}/${s.version}`
        const isOpen = open === key
        return (
          <Card key={key} className="p-4">
            <div className="flex items-start justify-between gap-3 flex-wrap">
              <button onClick={() => setOpen(isOpen ? null : key)} className="min-w-0 text-left">
                <div className="text-[13.5px] font-medium text-[var(--color-ink)] inline-flex items-center gap-1.5">
                  {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}{s.name} · {s.act.short ?? s.act.title}
                </div>
                <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">
                  {s.version} · applies {s.applies.from}{s.applies.until ? ` to ${s.applies.until}` : ' onwards'} (by {s.applies.basis.replace('_', ' ')}) · {s.templates.length} templates · sha {s.sha256.slice(0, 10)}
                </div>
              </button>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="mono text-[9.5px] uppercase tracking-wide px-2 py-0.5 rounded-full" style={pill(s.status === 'draft' ? '#a78bfa' : 'var(--color-sky)')}>{s.status}</span>
                {s.coverage && <span className="mono text-[9.5px] uppercase tracking-wide px-2 py-0.5 rounded-full" style={pill(s.coverage.complete ? 'var(--color-good)' : 'var(--color-warn)')}>{s.coverage.complete ? 'fully covered' : `${s.coverage.missing.length + s.coverage.stale.length} to map`}</span>}
                <span className="mono text-[9.5px] uppercase tracking-wide px-2 py-0.5 rounded-full" style={pill(s.approved ? 'var(--color-good)' : 'var(--color-warn)')}>{s.approved ? 'signed off' : `needs ${s.needs.join(' + ')}`}</span>
              </div>
            </div>
            {s.diff_from_previous && <DiffView d={s.diff_from_previous} />}
            {isOpen && (
              <div className="mt-3 space-y-2 text-[12px]">
                <a href={s.act.url} target="_blank" rel="noopener noreferrer" className="text-[var(--color-sky)] inline-flex items-center gap-1 hover:underline"><ExternalLink size={11} /> {s.act.title}</a>
                <div className="grid sm:grid-cols-2 gap-1">
                  {s.templates.map(t => <div key={t.id} className="text-[var(--color-mute)]"><span className="mono text-[10px] text-[var(--color-faint)]">{t.code}</span> {t.title}{t.structure === 'full' ? <span className="mono text-[9px] text-[var(--color-good)]"> · rows + columns captured</span> : null}</div>)}
                </div>
                {s.capture && <div className="mono text-[10.5px] text-[var(--color-faint)]">Captured {s.capture.captured} — {s.capture.method}.{' '}
                  {s.capture.second_pass ? <span style={{ color: 'var(--color-good)' }}>Second pass {s.capture.second_pass.result} {s.capture.second_pass.date}: {s.capture.second_pass.checked}.</span> : <span style={{ color: 'var(--color-warn)' }}>No second pass yet.</span>}</div>}
                {s.interpretations.map(i => (
                  <div key={i.subject} className="rounded-lg border border-[var(--color-line)] p-2.5">
                    <div className="mono text-[9.5px] uppercase tracking-wide text-[var(--color-faint)]">Declared reading · {i.subject} · by {i.declared_by}</div>
                    <div className="text-[12px] text-[var(--color-ink)] mt-1">{i.reading}</div>
                    <div className="text-[11.5px] text-[var(--color-mute)] mt-1">Why: {i.basis}</div>
                  </div>))}
                {s.coverage && !s.coverage.complete && <div className="mono text-[10.5px] text-[var(--color-warn)]">Not covered: {[...s.coverage.missing, ...s.coverage.stale, ...s.coverage.invalid].slice(0, 12).join(', ')}</div>}
                {s.signed.map(g => <div key={g.role} className="mono text-[10.5px] text-[var(--color-good)]">Signed as {g.role} by {g.email} · {g.signed_at.slice(0, 16).replace('T', ' ')}</div>)}
                {s.voided_by_edit.length > 0 && <div className="mono text-[10.5px] text-[var(--color-faint)]">{s.voided_by_edit.length} earlier sign-off(s) no longer count — the file changed after them.</div>}
                {canSign && s.needs.length > 0 && (
                  <div className="flex gap-2 pt-1">
                    {s.needs.map(r => <Button key={r} variant="ghost" onClick={() => sign(s, r)}>Sign as {r}</Button>)}
                  </div>)}
              </div>)}
          </Card>)
      })}
    </div>
  )
}
