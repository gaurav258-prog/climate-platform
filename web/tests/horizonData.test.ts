// Horizon draws, it does not compute (E219). The front door used to type its own years (2025 / 2030 / 2050 / 2100),
// its own risk bands (28 / 50 / 75) and its own interpolation, so its "at elevated risk" count disagreed with every other
// page. The years, the scores, the at-risk flags and the at-risk level now come from GET /v1/me/globe; these files may
// not bring any of them back.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

const SRC = new URL('../src/', import.meta.url).pathname
const FILES = [join(SRC, 'pages/Horizon.tsx'), ...readdirSync(join(SRC, 'components/horizon')).map(n => join(SRC, 'components/horizon', n))]
const code = (f: string) => readFileSync(f, 'utf8').replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '')

test('no Horizon file types a calendar year — the modelled years are the server\'s stops', () => {
  const bad = FILES.flatMap(f => (code(f).match(/\b(?:19|20)\d{2}\b/g) ?? []).map(y => `${f.replace(SRC, '')}: ${y}`))
  assert.deepEqual(bad, [])
})

test('no Horizon file compares a score with a typed threshold — at risk is the server\'s flag on the stated level', () => {
  const cmp = /\b(?:score|s|l|v|cur|level)\b\s*(?:>=|<=|>|<)\s*\d+/g
  const bad = FILES.flatMap(f => (code(f).match(cmp) ?? []).map(m => `${f.replace(SRC, '')}: ${m}`))
  assert.deepEqual(bad, [])
})

test('the at-risk count and its flag are read from the response, never counted on the page', () => {
  const page = code(join(SRC, 'pages/Horizon.tsx'))
  assert.match(page, /at_risk\.by_stop|risk\?\.by_stop/)
  assert.doesNotMatch(page, /scoreAt\(|traj\[/)
})
