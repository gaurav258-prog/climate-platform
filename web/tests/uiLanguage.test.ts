// The UI standard's guard (2026-10-16): no screen gets more internal language, raw codes, code-font sentences or
// inline server explanations than the baseline recorded when the standard came in — and the baseline only goes down.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { BASELINE, scan, sources, type Counts } from './uiLanguage.ts'

const base: Record<string, Counts> = JSON.parse(readFileSync(BASELINE, 'utf8'))
const ZERO: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0 }
const KINDS = Object.keys(ZERO) as (keyof Counts)[]

test('no screen breaks the UI standard more than its baseline', () => {
  const worse: string[] = []
  for (const f of sources()) {
    const { counts, hits } = scan(f)
    const b = base[f] ?? ZERO
    for (const k of KINDS) if (counts[k] > b[k]) worse.push(`${f}: ${k} ${b[k]} → ${counts[k]}\n    ${hits.filter(h => h.includes(` ${k} `)).join('\n    ')}`)
  }
  assert.deepEqual(worse, [], 'Use customer words, a label (lib/labels.ts), a StatusChip, or the details pop-up (components/Details.tsx)')
})

test('a fixed screen lowers the baseline, so it only goes down', () => {
  const stale: string[] = []
  for (const [f, b] of Object.entries(base)) {
    let counts = ZERO
    try { counts = scan(f).counts } catch { /* a removed file */ }
    for (const k of KINDS) if (counts[k] < b[k]) stale.push(`${f}: ${k} ${b[k]} → ${counts[k]}`)
  }
  assert.deepEqual(stale, [], 'Lower the baseline: node tests/uiLanguage.ts --write')
})
