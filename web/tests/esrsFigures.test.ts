// Every figure an undertaking states for its ESRS statement can be stated on the ESRS page: the page groups the figures
// by their key, and a group list that matched only some prefixes left the climate-related remuneration figure
// (esrs2.gov3.*) in no group, so it could not be stated there (E255). Each provided concept of the registry falls in a
// group, and the groups are the page's own.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { GROUPS, groupOf } from '../src/components/esrs/words.ts'

const reg = JSON.parse(readFileSync(new URL('../../data/reference/esrs/concepts.json', import.meta.url), 'utf8'))
const provided = Object.entries(reg.concepts as Record<string, { lane: string }>).filter(([, c]) => c.lane === 'provided').map(([k]) => k)

test('every figure the undertaking states falls in a named group of the page', () => {
  assert.ok(provided.length > 0)
  const other = GROUPS[GROUPS.length - 1].label
  for (const k of provided) assert.notEqual(groupOf(k), other, `${k} falls in no named group`)
})

test('a figure of a new prefix still shows, in the last group', () => {
  assert.equal(groupOf('e9.something.new'), GROUPS[GROUPS.length - 1].label)
})
