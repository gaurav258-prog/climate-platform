import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Search, ChevronRight } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import { HEADING } from '../components/Details'
import { DOCS, DOC_CATEGORIES, categoryLabel, type DocArticle, type DocCategory } from '../content/docs'
import SectionTabs, { HELP_TABS } from '../components/SectionTabs'
import { blocks, spans } from './docs/markdown'

const ABOUT = [{ heading: HEADING.shows, body: 'How the software works, how to get your data in, and how a disclosure is produced and governed — written for your risk, data and compliance teams.' }]

export default function Docs() {
  const { profile } = useAuth()
  const sector = profile?.org?.type ?? ''
  const [params] = useSearchParams()
  const [q, setQ] = useState('')
  // deep-link support: ?doc=<slug> opens that article straight away (e.g. from Support's guide cards)
  const [slug, setSlug] = useState<string>(() => params.get('doc') ?? 'welcome')
  useEffect(() => { const d = params.get('doc'); if (d) setSlug(d) }, [params])

  // Sector-aware: hide articles gated to a different sector.
  const visible = useMemo(() => DOCS.filter(d => !d.sectors || d.sectors.includes(sector)), [sector])
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase()
    if (!s) return visible
    return visible.filter(d => (d.title + ' ' + d.summary + ' ' + d.body).toLowerCase().includes(s))
  }, [visible, q])

  const active = visible.find(d => d.slug === slug) ?? visible[0]
  const byCat = (cat: DocCategory) => filtered.filter(d => d.category === cat)

  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={HELP_TABS} />
      <PageHeader eyebrow="Help" title="Documentation" lead="How the software works, and how to get the most from it." about={ABOUT} />

      <div className="grid lg:grid-cols-[minmax(0,300px)_1fr] gap-6 items-start">
        {/* index */}
        <div className="space-y-4 lg:sticky lg:top-4">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-faint)]" />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search the docs…"
              className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg pl-9 pr-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
          </div>
          {DOC_CATEGORIES.filter(c => byCat(c.key).length > 0).map(cat => (
            <div key={cat.key}>
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-faint)] mb-1.5 px-1">{cat.label}</div>
              <div className="space-y-0.5">
                {byCat(cat.key).map(d => (
                  <button key={d.slug} onClick={() => setSlug(d.slug)}
                    className={`w-full text-left rounded-lg px-2.5 py-2 text-[13px] transition flex items-center gap-2 ${active?.slug === d.slug
                      ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)] font-medium'
                      : 'text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-panel)]'}`}>
                    {active?.slug === d.slug && <span className="w-0.5 h-3.5 rounded-full bg-[var(--color-sky)] shrink-0" />}
                    <span className="leading-snug">{d.title}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          {filtered.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)] px-1">No article matches "{q}".</div>}
        </div>

        {/* article */}
        <Card className="p-7 max-w-[760px]">
          {active ? (<>
            <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-sky)] flex items-center gap-1.5 mb-2"><BookOpen size={12} /> {categoryLabel(active.category)}</div>
            <h2 className="display text-2xl font-semibold leading-tight">{active.title}</h2>
            <p className="text-[13.5px] text-[var(--color-mute)] mt-1.5 mb-5">{active.summary}</p>
            <div className="border-t border-[var(--color-line)] pt-5"><Markdown body={active.body} /></div>
            <Related current={active} pool={visible} onGo={setSlug} />
          </>) : <div className="text-[var(--color-faint)] text-sm">Select an article.</div>}
        </Card>
      </div>
    </div>
  )
}

function Related({ current, pool, onGo }: { current: DocArticle; pool: DocArticle[]; onGo: (s: string) => void }) {
  const more = pool.filter(d => d.category === current.category && d.slug !== current.slug).slice(0, 3)
  if (more.length === 0) return null
  return (
    <div className="mt-7 pt-5 border-t border-[var(--color-line)]">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-faint)] mb-2">More in {categoryLabel(current.category)}</div>
      <div className="space-y-1">
        {more.map(d => (
          <button key={d.slug} onClick={() => onGo(d.slug)} className="flex items-center gap-1.5 text-[13px] text-[var(--color-sky)] hover:underline">
            <ChevronRight size={13} /> {d.title}
          </button>
        ))}
      </div>
    </div>
  )
}

/* ── the help centre's markdown (docs/markdown.ts reads the blocks); **bold** and `code` inline ── */
function inline(text: string): ReactNode[] {
  return spans(text).map((p, i) =>
    p.kind === 'b' ? <strong key={i} className="text-[var(--color-ink)] font-semibold">{p.text}</strong>
      : p.kind === 'i' ? <em key={i}>{p.text}</em>
        : p.kind === 'code' ? <code key={i} className="mono text-[12px] px-1 py-0.5 rounded bg-[var(--color-bg-2)] border border-[var(--color-line)]">{p.text}</code>
          : <span key={i}>{p.text}</span>)
}

function Markdown({ body }: { body: string }) {
  return (
    <div>
      {blocks(body).map((b, k) => {
        if (b.kind === 'h4') return <h4 key={k} className="text-[14px] font-semibold text-[var(--color-ink)] mt-5 mb-1.5">{inline(b.text)}</h4>
        if (b.kind === 'h3') return <h3 key={k} className="display text-[17px] font-semibold text-[var(--color-ink)] mt-6 mb-2">{inline(b.text)}</h3>
        if (b.kind === 'quote') return <div key={k} className="my-4 rounded-lg border-l-2 border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_7%,transparent)] px-4 py-2.5 text-[13px] text-[var(--color-soft,var(--color-mute))] leading-relaxed">{inline(b.text)}</div>
        if (b.kind === 'ol') return <ol key={k} className="list-decimal ml-5 my-3 space-y-1.5 text-[13.5px] text-[var(--color-mute)] leading-relaxed marker:text-[var(--color-faint)]">{b.items.map((it, j) => <li key={j}>{inline(it)}</li>)}</ol>
        if (b.kind === 'ul') return <ul key={k} className="ml-1 my-3 space-y-1.5 text-[13.5px] text-[var(--color-mute)] leading-relaxed">{b.items.map((it, j) => <li key={j} className="flex gap-2.5"><span className="mt-2 w-1 h-1 rounded-full bg-[var(--color-sky)] shrink-0" /><span>{inline(it)}</span></li>)}</ul>
        return <p key={k} className="text-[13.5px] text-[var(--color-mute)] leading-relaxed my-3">{inline(b.text)}</p>
      })}
    </div>
  )
}
