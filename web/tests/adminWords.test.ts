// A governed change that waits for a second person is never announced as applied (E267): Methodology compared the
// answer with 'pending' while the server answers 'pending_approval', and the reporting basis never looked at it, so a
// change still waiting for approval said "Interpretation updated." / "Saved — every filing now uses this basis."
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { savedWords } from '../src/pages/admin/words.ts'

test('a change sent for approval is not reported as saved', () => {
  assert.match(savedWords('pending_approval', 'Saved.'), /approval/)
  assert.doesNotMatch(savedWords('pending_approval', 'Saved.'), /Saved/)
  assert.equal(savedWords('applied', 'Saved.'), 'Saved.')
})

test('the status the words test for is the one the server sends', () => {
  const server = readFileSync(new URL('../../services/governance/config_governance.py', import.meta.url), 'utf8')
  assert.match(server, /"status": "pending_approval"/)
  assert.match(server, /"status": "applied"/)
})

test('every governed save on the control center goes through savedWords', () => {
  for (const f of ['Basis', 'Methodology', 'Governance']) {
    const src = readFileSync(new URL(`../src/pages/admin/${f}.tsx`, import.meta.url), 'utf8')
    assert.match(src, /savedWords\(/, `${f}.tsx announces a governed save without savedWords`)
    assert.doesNotMatch(src, /status === 'pending'(?!_)/, `${f}.tsx tests for a status the server never sends`)
  }
})
