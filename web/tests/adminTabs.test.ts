// Every link into the control center lands on the tab it names (E-next): the readiness check linked /admin?tab=team,
// the method-gap notes, Loss and Portfolio linked /admin?tab=Methodology — and the page read no tab from its address, so
// every one opened on Overview. The page now resolves ?tab= by key, label or older name; this test reads every such
// link in the screens and the server and fails on one that names no tab.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { ALL_TABS, resolveTab } from '../src/pages/admin/tabs.ts'

const root = new URL('../..', import.meta.url).pathname
const walk = (dir: string, ext: RegExp): string[] => readdirSync(dir).flatMap(n => {
  const p = join(dir, n)
  return n === 'node_modules' || n === '__pycache__' ? [] : statSync(p).isDirectory() ? walk(p, ext) : ext.test(n) ? [p] : []
})

test('every /admin?tab= link names a tab of the control center', () => {
  const files = [...walk(join(root, 'web', 'src'), /\.(tsx?|ts)$/), ...walk(join(root, 'services'), /\.py$/), ...walk(join(root, 'api'), /\.py$/)]
  const links: [string, string][] = []
  for (const f of files) for (const m of readFileSync(f, 'utf8').matchAll(/\/admin\?tab=([A-Za-z %]+)/g)) links.push([f.replace(root, ''), decodeURIComponent(m[1])])
  assert.ok(links.length >= 4, 'the known links into the control center were not found')
  const dead = links.filter(([, t]) => resolveTab(t) === null)
  assert.deepEqual(dead, [])
})

test('a tab resolves by its key, its label or an older name, in any case', () => {
  for (const t of ALL_TABS) {
    assert.equal(resolveTab(t.key), t.key)
    assert.equal(resolveTab(t.label.toUpperCase()), t.key)
  }
  assert.equal(resolveTab('Methodology'), 'methodology')
  assert.equal(resolveTab('team'), 'team')
  assert.equal(resolveTab('KRI appetite'), 'appetite')
  assert.equal(resolveTab('no such tab'), null)
})

test('the control center reads the tab from its address', () => {
  const src = readFileSync(join(root, 'web', 'src', 'pages', 'Admin.tsx'), 'utf8')
  assert.match(src, /resolveTab\(params\.get\('tab'\)\)/)
})

// "Finish setup" (/admin?setup=identity, services/governance/readiness.py) read the address once on mount, so following it
// from the Overview itself — where the readiness check sits — did nothing (E-next). The form now follows the link while
// the page is open, and the link is cleared once the form closes or another tab opens.
test('the identity form follows the setup link while the page is open', () => {
  const readiness = readFileSync(join(root, 'services', 'governance', 'readiness.py'), 'utf8')
  assert.match(readiness, /"\/admin\?setup=identity"/)
  const src = readFileSync(join(root, 'web', 'src', 'pages', 'admin', 'Identity.tsx'), 'utf8')
  assert.match(src, /params\.get\('setup'\) === 'identity'/)
  assert.doesNotMatch(src, /window\.location/)
  assert.match(src, /\}, \[linked\]\)/)
  assert.match(src, /next\.delete\('setup'\)/)
  const admin = readFileSync(join(root, 'web', 'src', 'pages', 'Admin.tsx'), 'utf8')
  assert.match(admin, /next\.delete\('setup'\)/)
})
