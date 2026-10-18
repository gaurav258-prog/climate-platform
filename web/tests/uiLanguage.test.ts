// The UI standard's guard (2026-10-16): no screen gets more internal language, raw codes, code-font sentences, inline
// server explanations or typed figures than the baseline recorded when the standard came in — and the baseline only
// goes down.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { BASELINE, CITATION, DOTTED, FIGURE, FIXED, NOT_A_CODE, WORDS, citations, dottedCodes, scan, scanText, sources, type Counts } from './uiLanguage.ts'

const base: Record<string, Counts> = JSON.parse(readFileSync(BASELINE, 'utf8'))
const ZERO: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0, figure: 0, citation: 0 }
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

// E-next: a dotted code on screen, and the items of a list printed through .join().
test('a dotted code on screen is internal language (E-next)', () => {
  // The old catastrophe-capital page and the asset drawer: a permission key in the code font.
  assert.equal(page('return <p>Submitting needs the <span className="mono">pricing.approve</span> permission.</p>').internal, 1)
  assert.equal(page("return <Hint hint='emit risk.decision.approved to your registered endpoints' />").internal, 1)
  assert.equal(page("toast.error('Needs approvals.create.'); return null").internal, 1)              // a sentence's full stop
})

test("'e.g.', decimals, versions, addresses, domains and file names are not codes", () => {
  for (const s of ['e.g. EUR', 'i.e. the book', 'a rate of 0.05', 'version v2.1', 'admin@alpenrueck.demo', 'first.last@company.com',
    'https://tellumen.eu/docs/start', 'company.com', 'www.eiopa.europa.eu', 'holdings.xlsx', 'the 2024.pdf', 'Del. Reg. 2015/35',
    'S.27.01.01', 'FN-IN-450a.2', 'Done. Next step', 'Node.js'])
    assert.deepEqual(dottedCodes(s), [], s)
  assert.deepEqual(page('return <input placeholder="company.com" />'), ZERO)
})

test('each name that is not a code says why, and its example has the shape of one', () => {
  for (const n of NOT_A_CODE) {
    assert.ok(n.why.split(' ').length >= 8, `NOT_A_CODE ${n.last}: give the reason`)
    assert.ok((n.example.match(DOTTED) ?? []).length === 1 && dottedCodes(n.example).length === 0, `NOT_A_CODE ${n.last}: its example must be a dotted name it exempts`)
  }
})

test('a server list joined on screen is read item by item (E-next)', () => {
  // The old catastrophe-capital line: what the standard formula still needs, server sentences joined inline.
  assert.equal(page("return <p><b>Incomplete.</b> {s.incomplete?.join(' ')}</p>").apiProse, 1)
  assert.equal(page("return <span>{x.roles.join(', ')}</span>").raw, 1)                               // roles → role
  assert.equal(page("return <span>{x.statuses.join(', ')}</span>").raw, 1)                            // statuses → status
  assert.equal(page("return <span>{[x.region, x.status].filter(Boolean).join(' · ')}</span>").raw, 1)
  assert.equal(page("return <span>{x.rows.slice(0, 3).map(v => `${v.key} (${v.reason})`).join('; ')}</span>").raw, 1)
  assert.equal(page("return <span>{x.rows.slice(0, 3).map(v => `${v.key} (${v.reason})`).join('; ')}</span>").apiProse, 1)
  assert.equal(page("return <span>{(x.notes ?? []).join('; ')}</span>").apiProse, 1)
  assert.equal(page("return <span>{[...x.gaps, ...x.reasons].join(', ')}</span>").apiProse, 2)
  assert.equal(page("return <b title={x.codes.join(', ')}>3 codes</b>").raw, 1)                       // a code in a tooltip is still a code
})

test('a list of names, labels or numbers joined on screen stays quiet', () => {
  assert.deepEqual(page("return <span>{x.hazards.map(hazardLabel).join(', ')}</span>"), ZERO)          // a label helper renders them
  assert.deepEqual(page("return <span>{x.entities.map(e => e.name).join(', ')}</span>"), ZERO)
  assert.deepEqual(page("return <span>{[x.region, x.country].filter(Boolean).join(', ')}</span>"), ZERO)
  assert.deepEqual(page("return <span>{x.years.join(' · ')}</span>"), ZERO)
  assert.deepEqual(page("return <b title={x.reasons.join(' · ')}>Low confidence</b>"), ZERO)          // the pop-up's own text
})

test('each field kept as customer words says what it holds, and its file still prints it', () => {
  for (const w of WORDS) {
    assert.ok(w.why.split(' ').length >= 8, `WORDS ${w.file} ${w.field}: say what it holds`)
    assert.ok(scan(w.file).kept.has(w.field), `WORDS ${w.file} ${w.field}: the file no longer prints it — remove the entry`)
  }
  assert.equal(page("return <span>{x.tier}</span>").raw, 1)                                           // only in its own file
})

// E-next, the product owner's decision of 2026-10-18: a legal citation sits one click away, not on the main screen.
test('a legal citation on the main screen is counted (E-next)', () => {
  // The old catastrophe-capital page: template and regulation numbers in its section hints, an article in a sentence.
  assert.equal(page('return <SectionHead hint="S.27.01.01 · before and after risk mitigation">Capital by peril</SectionHead>').citation, 1)
  assert.equal(page("return <SectionHead hint={x.version_name ?? 'Del. Reg. 2015/35'}>Standard formula</SectionHead>").citation, 1)
  assert.equal(page('return <p>Without a postal code the zones are grouped (Art. 90b): an upper bound.</p>').citation, 1)
  assert.equal(page('return <label>Products (Annex III point 2)</label>').citation, 1)
  assert.equal(page("return <p>{ok ? 'Held as Article 5(3) requires.' : 'Directive (EU) 2022/2464 applies.'}</p>").citation, 2)
  assert.equal(page('return <p>SASB FN-IN-450a.2 by region</p>').citation, 1)
  assert.equal(page('return <p>An Article 8(1) disclosure</p>').citation, 1)                         // a paragraph is a citation
})

test('a citation one click away, or a category name, stays quiet', () => {
  assert.deepEqual(page("return <InfoButton details={{ title: 'Standard formula', sections: [{ heading: 'Legal basis', body: 'Delegated Regulation (EU) 2015/35, Articles 90b and 119 to 126' }] }} />"), ZERO)
  assert.deepEqual(page("const ABOUT = [{ heading: 'Legal basis', body: 'Reported on template S.27.01.01.' }]; return null"), ZERO)
  assert.deepEqual(page('return <Drawer label="Methods and legal basis"><p>Grouped zones (Art. 90b)</p></Drawer>'), ZERO)
  assert.deepEqual(scanText('src/pages/Example.tsx', "function Form({ children }: any) { return <Dialog title='Risk'>{children}</Dialog> }\n"
    + "export default function P() { return <Form><label>Art. 10(2) — every criterion</label></Form> }").counts, ZERO)   // a dialog wrapper
  assert.deepEqual(scanText('src/pages/Example.tsx', "import { Form } from '../components/eudr/EudrForms'\n"
    + "export default function P() { return <Form><label>Art. 11(1) — mitigation</label></Form> }").counts, ZERO)      // …imported
  assert.deepEqual(page("return <p>No fund is classified Article 8 or 9 yet. <b>Art. 6</b> · Pillar 3 · SFDR · Solvency II</p>"), ZERO)
  for (const s of ['Artificial reefs', 'Annexed land', 'the arts 2024', 'Regulation of the EU']) assert.deepEqual(citations(s), [], s)
  assert.ok(CITATION.flags.includes('g'))
})
