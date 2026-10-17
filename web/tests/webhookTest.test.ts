// E183: a webhook test that was delivered was shown as an error.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { webhookTestOutcome } from '../src/lib/webhookTest.ts'

test('a delivered test is a success', () => {
  assert.deepEqual(webhookTestOutcome({ status: 'delivered', http_status: 200 }), { ok: true, text: 'Test delivered (HTTP 200).' })
})

test('a failed test is an error, with what the endpoint answered', () => {
  assert.equal(webhookTestOutcome({ status: 'failed', http_status: 500 }).ok, false)
  assert.match(webhookTestOutcome({ status: 'failed', http_status: null }).text, /no response/)
})
