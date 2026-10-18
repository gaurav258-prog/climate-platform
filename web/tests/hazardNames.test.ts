// A hazard has one customer name everywhere (UI standard, 2026-10-16): the server's message catalogue names hazards in
// the text it renders (data/reference/messages.en.json, names.hazard — e.g. a concentration flag "led by …"), and every
// screen names them through lib/hazards.ts. The two must say the same words, so a flag and the chart beside it agree.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { HAZARD_LABEL, hazardLabel } from '../src/lib/hazards.ts'

const catalogue = JSON.parse(readFileSync(new URL('../../data/reference/messages.en.json', import.meta.url), 'utf8'))
const server: Record<string, string> = catalogue.names.hazard

test('the server names every hazard a screen names', () => {
  assert.deepEqual(Object.keys(HAZARD_LABEL).filter(k => !(k in server)), [])
})

test('the server and the screens use the same words for each hazard', () => {
  for (const [key, name] of Object.entries(server)) assert.equal(name, hazardLabel(key), key)
})
