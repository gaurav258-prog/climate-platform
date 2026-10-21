// E304: a projected loss card read "null vs today" when today's figure was €0 — a change exists only against a base.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { changeVs } from '../src/lib/change.ts'

test('a change is shown against a base, and is null when there is none', () => {
  assert.equal(changeVs(108, 100), '+8%')
  assert.equal(changeVs(90, 100), '-10%')
  assert.equal(changeVs(0, 0), null)
  assert.equal(changeVs(5, 0), null)
  assert.equal(changeVs(null, 100), null)
  assert.equal(changeVs(100, null), null)
})

test('the loss page shows its change chip only when there is a change', () => {
  const src = readFileSync(new URL('../src/pages/Loss.tsx', import.meta.url), 'utf8')
  assert.ok(!/\bpct\(/.test(src), 'the loss page computes changes with lib/change.changeVs')
  assert.ok(/changeVs\(/.test(src))
})
