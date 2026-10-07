// E174: a page that starts a run must wait for that run, not stop at the run that was already there.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { arrivedRun } from '../src/lib/runWait.ts'

test('the run already there is not the run that was started', () => {
  assert.equal(arrivedRun('old', 'old', true), null)
})

test('a newer run is the one that was started', () => {
  assert.equal(arrivedRun('new', 'old', true), 'new')
})

test('the first run ever arrives too', () => {
  assert.equal(arrivedRun('first', null, true), 'first')
  assert.equal(arrivedRun(null, null, true), null)
})

test('nothing arrives when nothing was started', () => {
  assert.equal(arrivedRun('new', 'old', false), null)
})
