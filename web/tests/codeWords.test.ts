// The oversight, calendar, supervisor-map, control-register and site screens name every code they print (UI standard,
// 2026-10-16). These tests hold their words to the server's own lists, so a code the server gains is never printed
// as-is, and pin two defects found on the way:
//   the supervisor map's region tooltip is set as HTML — it printed the country code and "(grid cell, outside EU
//   statistical regions)", and inserted region and organisation names unescaped;
//   the control register printed each stored test item as its keys ("framework: bank_tcfd · r2_oos: 0.31"), and the
//   technical cause of a test that could not run (the server now names every stored item: tests/unit/test_oversight_messages.py).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { CALENDAR_KIND, CONTROL_TRIGGER, CONTROL_TYPE, CRITICALITY, FREQUENCY, IRRIGATION, PEER_FLAG, PROFILE_FRAMEWORK, SITE_TYPE, countryName, frequencyWord, percent, placeLine } from '../src/lib/codeWords.ts'
import { regionTooltip, type Region } from '../src/components/exposureMapWords.ts'

const repo = (p: string) => readFileSync(new URL(`../../${p}`, import.meta.url), 'utf8')
const names = JSON.parse(repo('data/reference/messages.en.json')).names as Record<string, Record<string, string>>
const keys = (o: object) => Object.keys(o).sort()
// a Python tuple of strings after `marker` in a server file
const tuple = (src: string, marker: string) => {
  const at = src.indexOf(marker)
  assert.ok(at >= 0, `${marker} not found`)
  return [...src.slice(at).match(/\(([^)]*)\)/)![1].matchAll(/"([^"]+)"/g)].map(m => m[1]).sort()
}
const CODE = /\b[a-z]+_[a-z0-9_]+\b/

test('frequencies and peer flags are the catalogue’s own names', () => {
  assert.deepEqual(FREQUENCY, names.frequency)
  assert.deepEqual(PEER_FLAG, names.peer_flag)
  assert.equal(frequencyWord('on change'), 'On change')         // already in words
  assert.equal(frequencyWord('one_off'), null)                  // a code with no name is never printed
})

test('site types and water management cover the server’s vocabularies', () => {
  const fields = repo('services/ingest/fields.py')
  assert.deepEqual(keys(SITE_TYPE), tuple(fields, '"site_type": Vocab('))
  assert.deepEqual(keys(IRRIGATION), tuple(fields, '"irrigation": Vocab('))
})

test('every filing a supervision profile expects has a name', () => {
  const profiles = JSON.parse(repo('data/reference/supervision_profiles.json')) as { sectors: Record<string, { frameworks?: string[] }> }
  const expected = [...new Set(Object.values(profiles.sectors).flatMap(s => (typeof s === 'object' && s.frameworks) || []))].sort()
  assert.deepEqual(keys(PROFILE_FRAMEWORK), expected)
})

test('third-party criticality, calendar kinds, control types and test triggers cover the server’s lists', () => {
  assert.deepEqual(keys(CRITICALITY), tuple(repo('services/intelligence/third_parties.py'), 'CRITICALITY = '))
  const calendar = repo('services/governance/reg_calendar.py')
  assert.deepEqual(keys(CALENDAR_KIND), [...calendar.matchAll(/"kind": "([a-z_]+)"/g)].map(m => m[1]).sort())
  const register = JSON.parse(repo('data/reference/reporting_controls.json')) as { controls: { type: string }[] }
  assert.deepEqual(keys(CONTROL_TYPE), [...new Set(register.controls.map(c => c.type))].sort())
  const triggers = [...repo('api/routers/controls.py').matchAll(/trigger="([a-z]+)"/g), ...repo('services/governance/controls.py').matchAll(/trigger="([a-z]+)"/g)]
  assert.deepEqual(keys(CONTROL_TRIGGER), [...new Set(triggers.map(m => m[1]))].sort())
})

test('a share prints with at most one decimal, never as a float (the peer median read 33.599999999999994%)', () => {
  assert.equal(percent(33.599999999999994), '33.6%')
  assert.equal(percent(21.4), '21.4%')
  assert.equal(percent(100), '100%')
  assert.equal(percent(null), '—')
  const src = readFileSync(new URL('../src/pages/SupervisorBenchmark.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(src, /\$\{v\}%/, 'the peer benchmark prints a raw share')
})

test('a place reads in words, the same place never twice', () => {
  assert.equal(placeLine('EU', 'EU'), 'European Union')
  assert.equal(placeLine('Valencia', 'ES'), 'Valencia, Spain')
  assert.equal(placeLine(null, null), '—')
})

test('a country code reads as the country; a name stays a name', () => {
  assert.equal(countryName('IN'), 'India')
  assert.equal(countryName('de'), 'Germany')
  assert.equal(countryName('Bavaria'), 'Bavaria')
  assert.equal(countryName(null), null)
})

const region = (over: Partial<Region>): Region => ({ key: 'k', name: 'India · 30.1°N 75.3°E', country: 'IN', kind: 'h3', geometry: { type: 'Point', coordinates: [0, 0] },
  n_sites: 2, value_eur: 1000, max_score: 61.4, mean_score: 47.25, worst_hazard: 'heat_chronic', entities: ['Bank A'], ...over })

test('the map tooltip names the place in words, never a code', () => {
  const t = regionTooltip(region({}))
  assert.match(t, /India · 30\.1°N 75\.3°E<\/b> · Grid cell/)
  assert.doesNotMatch(t, /· IN\b|outside EU statistical regions|heat_chronic|47\.25/)
  assert.match(regionTooltip(region({ name: 'Darmstadt', country: 'DE', kind: 'nuts3' })), /Darmstadt · Germany<\/b> · Region/)
})

test('the map tooltip shows a name with markup as text', () => {
  const t = regionTooltip(region({ name: '<img src=x onerror=alert(1)>', entities: ['A & B <script>x()</script>'] }))
  assert.doesNotMatch(t, /<img|<script/)
  assert.match(t, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.match(t, /A &amp; B &lt;script&gt;/)
})

test('the control register prints each test item by its catalogue message, never its keys', () => {
  const src = readFileSync(new URL('../src/components/ControlRegister.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(src, /Object\.entries\(x\)/, 'the register prints a stored item as key: value')
  assert.match(src, /x\.msg\?\.label/)
  assert.match(repo('services/governance/controls.py'), /"detail": named\(lt\["detail"\]\)/)
})

test('the decide panel says whether a decision goes to a second approver from the organisation’s rule', () => {
  // one decide panel for every signal (a forward crossing, a tested loss): components/DecideForm.tsx
  const src = readFileSync(new URL('../src/components/DecideForm.tsx', import.meta.url), 'utf8')
  assert.doesNotMatch(src, /needs a second approval/, 'the panel claims every decision needs a second approval')
  assert.match(src, /secondApprover\(policy, value\)/)
  for (const page of ['../src/pages/Decisions.tsx', '../src/components/LossSignals.tsx'])
    assert.match(readFileSync(new URL(page, import.meta.url), 'utf8'), /<DecideForm /, `${page} decides through its own panel`)
  assert.match(repo('services/intelligence/forward_decisions.py'), /return \(value_eur or 0\) >= pol\["threshold_eur"\]/)
})
