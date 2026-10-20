// The support centre's clock and words (E277): the page called its target a first-response target but ran the
// clock until the ticket was resolved, so a ticket answered in time showed "SLA breached" while it stayed open; and its
// target table named the priorities Critical / High / Medium / Low while the form offered Low / Normal / High / Urgent.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CATEGORIES, PRIORITIES, STATUSES, clock, clockWords } from '../src/pages/support/words.ts'

const HOUR = 3600000
const raised = Date.parse('2026-10-01T09:00:00Z')

test('the clock stops at the first reply: an answered ticket is never late, however long it stays open', () => {
  const urgent = { status: 'open', priority: 'urgent', created_at: new Date(raised).toISOString(), first_response_at: null }
  assert.equal(clock(urgent, raised + 1 * HOUR).state, 'ok')
  assert.equal(clock(urgent, raised + 3 * HOUR).state, 'risk')
  assert.equal(clock(urgent, raised + 5 * HOUR).state, 'breached')
  const answered = { ...urgent, first_response_at: new Date(raised + 2 * HOUR).toISOString() }
  assert.equal(clock(answered, raised + 500 * HOUR).state, 'met')
  assert.equal(clockWords(clock(answered, raised + 500 * HOUR)), null)
  assert.equal(clock({ ...urgent, status: 'resolved' }, raised + 500 * HOUR).state, 'met')
})

test('the targets, the form and the ticket list use one list of priorities: the ones the server accepts', () => {
  const portal = readFileSync(new URL('../../api/routers/portal.py', import.meta.url), 'utf8')
  const accepted = portal.match(/priority: str = Field\("normal", pattern="\^\(([a-z|]+)\)\$"\)/)?.[1].split('|')
  assert.deepEqual(PRIORITIES.map(p => p.key).sort(), accepted?.sort())
  const categories = portal.match(/CATEGORIES = \[([^\]]+)\]/)?.[1].match(/"([a-z_]+)"/g)?.map(x => x.slice(1, -1))
  assert.deepEqual(CATEGORIES.map(c => c.key).sort(), categories?.sort())
  const statuses = portal.match(/status: str = Field\(\.\.\., pattern="\^\(([a-z_|]+)\)\$"\)/)?.[1].split('|')
  assert.deepEqual(Object.keys(STATUSES).sort(), statuses?.sort())
  const page = readFileSync(new URL('../src/pages/Support.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(page, /SLA_TARGETS|SLA_HOURS|'Critical'|'Medium'/, 'Support.tsx keeps its own priority list again')
})

test('the names are the ones the platform support queue shows for the same tickets', () => {
  const names = JSON.parse(readFileSync(new URL('../../data/reference/messages.en.json', import.meta.url), 'utf8')).names
  for (const c of CATEGORIES) assert.equal(c.name, names['admin.support_category'][c.key], c.key)
  for (const p of PRIORITIES) assert.equal(p.name, names['admin.support_priority'][p.key], p.key)
  for (const [k, s] of Object.entries(STATUSES)) assert.equal(s.name, names['admin.support_status'][k], k)
})
