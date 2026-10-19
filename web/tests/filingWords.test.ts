// The Pillar 3 form's tabs group its templates by the template each section prints, never by words in its title: a
// section once titled 'Template 9.3 - Summary table - BTAR %' sat under the Qualitative tab because its title holds the
// word 'table' (E-next). Every template of the governing Pillar 3 specifications lands on its own tab.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { EARLIER, p3Group } from '../src/components/filing/words.ts'

const dir = new URL('../../data/reference/regspec/bank_p3esg/', import.meta.url)
const specs = readdirSync(dir).filter(f => f.endsWith('.json')).map(f => JSON.parse(readFileSync(new URL(f, dir), 'utf8')))
const expected = (id: string) => id.startsWith('TAB') ? 'qual' : (n => n <= 4 ? 'trans' : n === 5 ? 'phys' : 'tax')(parseInt(id.slice(1), 10))

test('every Pillar 3 template sits on the tab of its template id', () => {
  assert.ok(specs.length > 0)
  for (const spec of specs) for (const t of spec.templates) assert.equal(p3Group(t.id, t.title), expected(t.id), `${spec.version} ${t.id} ${t.title}`)
})

test('a summary table is a Taxonomy template, not a qualitative table', () => {
  assert.equal(p3Group('T9_3', 'Template 9.3 - Summary table - BTAR %'), 'tax')
  assert.equal(p3Group(null, 'Template 9.3 - Summary table - BTAR %'), 'tax')            // no id: its number decides
  assert.equal(p3Group(null, 'Table 2 - Qualitative information on Social risk'), 'qual')
})

test('a section frozen under the earlier report shape has its own tab', () => {
  assert.equal(p3Group(null, `${EARLIER} · Credit risk`), 'earlier')
})
