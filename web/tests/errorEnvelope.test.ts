// A refusal reaches the screen through apiMessage / apiDetail (lib/api.ts), which read every shape the API answers —
// {error: {error, message, detail}} first. The contracts upload read the words from the top of the body,
// (err.body as { message?: string })?.message, where the API never puts them, so every refused upload said only
// "Upload failed." whatever the reason (E294).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'

const SRC = new URL('../src/', import.meta.url).pathname
const files = (dir: string): string[] => readdirSync(dir).flatMap(n => {
  const p = join(dir, n)
  return statSync(p).isDirectory() ? files(p) : /\.tsx?$/.test(n) ? [p] : []
})
// a body typed as holding only a top-level message, and its message read
export const TOP_ONLY = /\.body as \{ message\?: [^;}]*\}\s*\)\??\.message/

test('the check finds a refusal read from the top of the body only', () => {
  assert.ok(TOP_ONLY.test("toast.error(err instanceof ApiError ? (err.body as { message?: string })?.message ?? 'Upload failed.' : 'Upload failed.')"))
  assert.ok(!TOP_ONLY.test('const b = e.body as { message?: string; error?: { message?: string } } | string | undefined'))
})

test('no screen reads a refusal from the top of the error body only', () => {
  const bad = files(SRC).filter(f => TOP_ONLY.test(readFileSync(f, 'utf8')))
  assert.deepEqual(bad, [])
})

// A refused download (lib/api.ts download) built its error from the raw response text, so the toast printed the whole
// JSON envelope instead of the reason (E340). Every ApiError is built from the parsed body.
export const RAW_BODY = /new ApiError\([^)]*await res\.text\(\)\)/

test('the check finds an error built from the raw response text', () => {
  assert.ok(RAW_BODY.test('if (!res.ok) throw new ApiError(res.status, await res.text())'))
  assert.ok(!RAW_BODY.test("throw new ApiError(res.status, (data as { detail?: unknown })?.detail ?? data ?? text)"))
})

test('no request builds its error from the raw response text', () => {
  const bad = files(SRC).filter(f => RAW_BODY.test(readFileSync(f, 'utf8')))
  assert.deepEqual(bad, [])
})
