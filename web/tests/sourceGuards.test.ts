// Guards over the web source and the production bundle.
//   E184: an API error was shown as "[object Object]" (String(e.body)) — errors reach the screen through apiMessage.
//   E185: the demo tenants' passwords sat in the production bundle — they load only on a dev server or a demo build.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { DEMO_ROLE_PASSWORDS } from '../src/lib/demoLogin.ts'

const SRC = new URL('../src/', import.meta.url).pathname
const DIST = new URL('../dist/', import.meta.url).pathname

function files(dir: string, ext: RegExp): string[] {
  return readdirSync(dir).flatMap(n => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? files(p, ext) : ext.test(n) ? [p] : []
  })
}

test('no screen turns an API error body into text by hand', () => {
  const bad = files(SRC, /\.tsx?$/).filter(f => /String\((e|err|error)\.body/.test(readFileSync(f, 'utf8')))
  assert.deepEqual(bad, [])
})

test('the demo passwords appear only in their own module', () => {
  const pw = Object.values(DEMO_ROLE_PASSWORDS)
  const bad = files(SRC, /\.tsx?$/).filter(f => !f.endsWith('lib/demoLogin.ts') && pw.some(p => readFileSync(f, 'utf8').includes(p)))
  assert.deepEqual(bad, [])
})

// The gate and CI build for production (npm run build, no VITE_DEMO_LOGIN) right before these tests run.
test('a production build carries no demo password', { skip: !existsSync(DIST) && 'no build on this machine' }, () => {
  const pw = Object.values(DEMO_ROLE_PASSWORDS)
  const bad = files(DIST, /\.js$/).filter(f => pw.some(p => readFileSync(f, 'utf8').includes(p)))
  assert.deepEqual(bad, [], 'the demo passwords are in the production bundle')
})
