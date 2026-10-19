// The help centre's small markdown subset, read into blocks the Documentation page renders: ## / ### headings,
// - bullets, 1. numbered items, > callouts and paragraphs. A list item may run onto following lines indented by
// spaces; those lines belong to the item (they were rendered as a separate paragraph, cutting items in two).

export type Block =
  | { kind: 'h3'; text: string } | { kind: 'h4'; text: string } | { kind: 'p'; text: string } | { kind: 'quote'; text: string }
  | { kind: 'ol'; items: string[] } | { kind: 'ul'; items: string[] }

const ITEM = { ol: /^\d+\.\s/, ul: /^- / } as const
const continues = (ln: string | undefined) => ln !== undefined && /^\s{2,}\S/.test(ln)

export function blocks(body: string): Block[] {
  const lines = body.replace(/^\n+/, '').split('\n')
  const out: Block[] = []
  let para: string[] = []
  const flush = () => { if (para.length) { out.push({ kind: 'p', text: para.join(' ') }); para = [] } }
  let i = 0
  while (i < lines.length) {
    const ln = lines[i]
    if (ln.trim() === '') { flush(); i++; continue }
    if (ln.startsWith('### ')) { flush(); out.push({ kind: 'h4', text: ln.slice(4) }); i++; continue }
    if (ln.startsWith('## ')) { flush(); out.push({ kind: 'h3', text: ln.slice(3) }); i++; continue }
    if (ln.startsWith('> ')) {
      flush(); const buf: string[] = []
      while (i < lines.length && lines[i].startsWith('> ')) { buf.push(lines[i].slice(2)); i++ }
      out.push({ kind: 'quote', text: buf.join(' ') }); continue
    }
    const kind = ITEM.ol.test(ln) ? 'ol' : ITEM.ul.test(ln) ? 'ul' : null
    if (kind) {
      flush(); const items: string[] = []
      while (i < lines.length && ITEM[kind].test(lines[i])) {
        let item = lines[i].replace(ITEM[kind], ''); i++
        while (continues(lines[i])) { item += ' ' + lines[i].trim(); i++ }
        items.push(item)
      }
      out.push({ kind, items }); continue
    }
    para.push(ln); i++
  }
  flush()
  return out
}

// The inline marks inside a block: **bold**, *italic* and `code`; everything else is plain text.
export type Span = { kind: 'b' | 'i' | 'code' | 't'; text: string }

export function spans(text: string): Span[] {
  return text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`)/g).filter(Boolean).map(p =>
    /^\*\*[^*]+\*\*$/.test(p) ? { kind: 'b', text: p.slice(2, -2) }
      : /^\*[^*\s][^*]*\*$/.test(p) ? { kind: 'i', text: p.slice(1, -1) }
        : /^`[^`]+`$/.test(p) ? { kind: 'code', text: p.slice(1, -1) }
          : { kind: 't', text: p })
}
