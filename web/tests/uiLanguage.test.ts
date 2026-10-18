// The UI standard's guard (2026-10-16): no screen gets more internal language, raw codes, code-font sentences, inline
// server explanations or typed figures than the baseline recorded when the standard came in — and the baseline only
// goes down.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { BASELINE, FIGURE, FIXED, scan, scanText, sources, type Counts } from './uiLanguage.ts'

const base: Record<string, Counts> = JSON.parse(readFileSync(BASELINE, 'utf8'))
const ZERO: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0, figure: 0 }
const KINDS = Object.keys(ZERO) as (keyof Counts)[]

test('no screen breaks the UI standard more than its baseline', () => {
  const worse: string[] = []
  for (const f of sources()) {
    const { counts, hits } = scan(f)
    const b = { ...ZERO, ...base[f] }                                  // a kind the baseline lacks is held at 0
    for (const k of KINDS) if (counts[k] > b[k]) worse.push(`${f}: ${k} ${b[k]} → ${counts[k]}\n    ${hits.filter(h => h.includes(` ${k} `)).join('\n    ')}`)
  }
  assert.deepEqual(worse, [], 'Use customer words, a label (lib/labels.ts), a StatusChip, or the details pop-up (components/Details.tsx); read a figure from data')
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

// E196: a page is read through its template strings and expressions, not only its plain literals.
const page = (body: string) => scanText('src/pages/Example.tsx', `export default function P({ s, x, ok, n }: any) {\n${body}\n}`).counts

test('a code inside a template string or expression on screen is counted (E196)', () => {
  // The old Supervisor intake line that showed 'pillar3_esg · template_5' while the guard counted the page clean.
  assert.equal(page("return <span>{s.framework === 'granular' ? 'Granular extract' : `${s.framework} · ${s.template}`}</span>").raw, 2)
  assert.equal(page("return <span>{ok ? 'Ready' : 'pillar3_esg'}</span>").internal, 1)
  assert.equal(page("return <span>{x.label ?? 'template_5'}</span>").internal, 1)
  assert.equal(page("return <span>{'Template ' + x.code}</span>").raw, 1)
  assert.equal(page("return <b title={`Filed as ${x.kind}`}>Filed</b>").raw, 1)
  assert.equal(page("toast.error(`Could not read ${x.status}`); return null").raw, 1)
  assert.equal(page("return <p>{x.methodology ?? x.note}</p>").apiProse, 2)
  assert.equal(page("return <span>{`Board pack v${x.version}`}</span>").raw, 1)
})

test('customer words around data stay quiet', () => {
  assert.deepEqual(page("return <span>{`${label(s.framework)} · ${n} rows`}</span>"), ZERO)          // a label helper, not the code
  assert.deepEqual(page("return <span>{x.status === 'open' && <b>Open</b>}</span>"), ZERO)            // a condition is not shown
  assert.deepEqual(page("return <Details title='Why' body={x.note} />"), ZERO)                         // the pop-up's own body
  assert.deepEqual(page("return <span className={`mono ${x.kind}`}>Filed</span>"), ZERO)              // not text on screen
})

test('a content file counts each display text once', () => {
  assert.equal(scanText('src/content/example.ts', "export const d = { title: 'The golden source' }").counts.internal, 1)
})

test('a figure typed into a headline value is counted (E196)', () => {
  // The old agriculture Data sources tiles, and the same in each headline shape.
  assert.equal(page('return <><Stat big="51.4M" label="satellite observations" /><Stat big="1998–2026" label="history" /></>').figure, 2)
  assert.equal(page('return <StatCard label="Grid" value="~0.7 km²" />').figure, 1)
  assert.equal(page('return <HeroMetric label="At risk" value={ok ? "€2.1bn" : "—"} />').figure, 1)
  assert.equal(page("return <StatGrid items={[{ label: 'History', value: <>28 years</> }]} />").figure, 1)
  assert.equal(page("const m: StatItem[] = [{ label: 'Covered', value: '35%' }]; return <StatGrid items={m} />").figure, 1)
  assert.equal(page('return <Stat big="append-only" label="store" />').internal, 1)                    // a headline is screen text too
})

test('a headline read from data, or fixed by definition, stays quiet', () => {
  assert.deepEqual(page('return <Stat big={fmt(n)} label="Plots" />'), ZERO)
  assert.deepEqual(page('return <StatCard label="Cell size" value={`${n} km²`} />'), ZERO)
  assert.deepEqual(page("return <StatGrid items={[{ label: 'Scored', value: `${n}%`, sub: 'of your plots' }]} />"), ZERO)
  assert.deepEqual(page('return <StatCard label="Return period" value="1-in-100" />'), ZERO)
  assert.deepEqual(page('return <><StatCard label="Scenario" value="1-in-200 years" /><Stat big="99.5%" label="Confidence" /></>'), ZERO)
  assert.deepEqual(page('return <StatCard label="Since 1998–2026" value={n} />'), ZERO)              // a label, not a headline value
})

test('each fixed value says why, and is one the check would flag without it', () => {
  for (const f of FIXED) {
    assert.ok(f.why.split(' ').length >= 8, `FIXED ${f.text}: give the reason it may be typed`)
    assert.ok(FIGURE.test(f.example) && f.text.test(f.example), `FIXED ${f.text}: its example must be a figure it exempts`)
  }
})
