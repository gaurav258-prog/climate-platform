// The help centre reads its articles whole (E279): the reader treated an indented second line of a list item as a
// new paragraph, so "Direct integration", the platform layers and the frameworks list were cut in two on screen; and
// it knew **bold** and `code` but not *italic*, so every italic phrase showed with its asterisks.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { blocks, spans } from '../src/pages/docs/markdown.ts'
import { DOCS } from '../src/content/docs.ts'

test('an indented line continues the list item above it', () => {
  const b = blocks('- **EU Taxonomy** — alignment, with the\n  minimum-safeguards checks.\n- **EUDR** — the statement.\n\n1. One\n   more.\n2. Two')
  assert.deepEqual(b, [
    { kind: 'ul', items: ['**EU Taxonomy** — alignment, with the minimum-safeguards checks.', '**EUDR** — the statement.'] },
    { kind: 'ol', items: ['One more.', 'Two'] },
  ])
})

test('no help article leaves an indented line outside its list item', () => {
  for (const d of DOCS) {
    const paragraphs = blocks(d.body).filter(b => b.kind === 'p').map(b => (b as { text: string }).text)
    for (const p of paragraphs) assert.doesNotMatch(p, /^\s|^[a-z]/, `${d.slug}: "${p.slice(0, 50)}" was cut from a list item`)
  }
})

test('bold, italic and code marks are read, so no asterisk reaches the screen', () => {
  assert.deepEqual(spans('A *(sandbox-ready)* and **bold** with `code`.'), [
    { kind: 't', text: 'A ' }, { kind: 'i', text: '(sandbox-ready)' }, { kind: 't', text: ' and ' },
    { kind: 'b', text: 'bold' }, { kind: 't', text: ' with ' }, { kind: 'code', text: 'code' }, { kind: 't', text: '.' }])
  for (const d of DOCS) {
    const texts = blocks(d.body).flatMap(b => 'items' in b ? b.items : [b.text])
    for (const t of texts) for (const s of spans(t)) assert.doesNotMatch(s.text, /\*/, `${d.slug}: a raw asterisk in "${s.text.slice(0, 40)}"`)
  }
})
