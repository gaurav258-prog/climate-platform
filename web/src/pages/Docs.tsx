import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { BookOpen, Search, ChevronRight } from 'lucide-react'
import { useAuth } from '../lib/auth'
import { Card, PageHeader } from '../components/ui'
import { DOCS, DOC_CATEGORIES, type DocArticle } from '../content/docs'
import SectionTabs, { HELP_TABS } from '../components/SectionTabs'

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
  const byCat = (cat: string) => filtered.filter(d => d.category === cat)

  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={HELP_TABS} />
      <PageHeader eyebrow="Help · documentation" title="Documentation"
        lead="How the software works, how to get your data in, and how a disclosure is produced and governed — written for your risk, data and compliance teams." />

      <div className="grid lg:grid-cols-[minmax(0,300px)_1fr] gap-6 items-start">
        {/* index */}
        <div className="space-y-4 lg:sticky lg:top-4">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-faint)]" />
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Search the docs…"
              className="w-full bg-[var(--color-bg-2)] border border-[var(--color-line)] rounded-lg pl-9 pr-3 py-2 text-[13px] outline-none focus:border-[var(--color-sky)]" />
          </div>
          {DOC_CATEGORIES.filter(c => byCat(c).length > 0).map(cat => (
            <div key={cat}>
              <div className="mono text-[10.5px] uppercase tracking-[0.18em] text-[var(--color-faint)] mb-1.5 px-1">{cat}</div>
              <div className="space-y-0.5">
                {byCat(cat).map(d => (
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
            <div className="mono text-[10px] uppercase tracking-[0.16em] text-[var(--color-sky)] flex items-center gap-1.5 mb-2"><BookOpen size={12} /> {active.category}</div>
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
      <div className="mono text-[9px] uppercase tracking-[0.18em] text-[var(--color-faint)] mb-2">More in {current.category}</div>
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

/* ── minimal markdown: ##/### headings, - bullets, 1. ordered, > callout, **bold**, `code`, paragraphs ── */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = []
  // split on **bold** and `code`, keeping delimiters
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  parts.forEach((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) out.push(<strong key={i} className="text-[var(--color-ink)] font-semibold">{p.slice(2, -2)}</strong>)
    else if (/^`[^`]+`$/.test(p)) out.push(<code key={i} className="mono text-[12px] px-1 py-0.5 rounded bg-[var(--color-bg-2)] border border-[var(--color-line)]">{p.slice(1, -1)}</code>)
    else if (p) out.push(<span key={i}>{p}</span>)
  })
  return out
}

function Markdown({ body }: { body: string }) {
  const lines = body.replace(/^\n+/, '').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let para: string[] = []
  const flushPara = () => {
    if (para.length) { blocks.push(<p key={`p${blocks.length}`} className="text-[13.5px] text-[var(--color-mute)] leading-relaxed my-3">{inline(para.join(' '))}</p>); para = [] }
  }
  while (i < lines.length) {
    const ln = lines[i]
    if (ln.trim() === '') { flushPara(); i++; continue }
    if (ln.startsWith('### ')) { flushPara(); blocks.push(<h4 key={i} className="text-[14px] font-semibold text-[var(--color-ink)] mt-5 mb-1.5">{inline(ln.slice(4))}</h4>); i++; continue }
    if (ln.startsWith('## ')) { flushPara(); blocks.push(<h3 key={i} className="display text-[17px] font-semibold text-[var(--color-ink)] mt-6 mb-2">{inline(ln.slice(3))}</h3>); i++; continue }
    if (ln.startsWith('> ')) {
      flushPara(); const buf: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) { buf.push(lines[i].slice(2)); i++ }
      blocks.push(<div key={i} className="my-4 rounded-lg border-l-2 border-[var(--color-sky)] bg-[color-mix(in_oklab,var(--color-sky)_7%,transparent)] px-4 py-2.5 text-[13px] text-[var(--color-soft,var(--color-mute))] leading-relaxed">{inline(buf.join(' '))}</div>); continue
    }
    if (/^\d+\.\s/.test(ln)) {
      flushPara(); const items: string[] = []
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) { items.push(lines[i].replace(/^\d+\.\s/, '')); i++ }
      blocks.push(<ol key={i} className="list-decimal ml-5 my-3 space-y-1.5 text-[13.5px] text-[var(--color-mute)] leading-relaxed marker:text-[var(--color-faint)]">{items.map((it, k) => <li key={k}>{inline(it)}</li>)}</ol>); continue
    }
    if (ln.startsWith('- ')) {
      flushPara(); const items: string[] = []
      while (i < lines.length && lines[i].startsWith('- ')) { items.push(lines[i].slice(2)); i++ }
      blocks.push(<ul key={i} className="ml-1 my-3 space-y-1.5 text-[13.5px] text-[var(--color-mute)] leading-relaxed">{items.map((it, k) => <li key={k} className="flex gap-2.5"><span className="mt-2 w-1 h-1 rounded-full bg-[var(--color-sky)] shrink-0" />{inline(it)}</li>)}</ul>); continue
    }
    para.push(ln); i++
  }
  flushPara()
  return <div>{blocks}</div>
}
