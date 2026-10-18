// The UI standard's automatic guard (product owner, 2026-10-16): what a screen shows is customer language, short,
// and not in the code font. This scans every page, component and content file for five kinds of breach in the text
// it puts on screen — JSX text and expressions, display props (title, label, lead, hint, sub, …), toast messages.
// An expression is read through to everything it can show: string literals, every part of a template string, both
// branches of ?:, both sides of ?? || and +, the right of && — and the fields it prints, alone or inside ${…} (E196):
//   internal   internal language: a snake_case code, an E-number, a file path, an API path, engineering jargon
//   raw        a code rendered as-is: {x.status}, `${f.framework} · ${f.template}` … straight onto the screen
//   monoProse  a sentence set in the code font (an element whose class has `mono` holding four words or more)
//   apiProse   a server explanation printed inline: {x.note}, {r.basis}, {e.reason} … — it belongs in the pop-up
//   figure     a figure typed into a headline value instead of read from data: '51.4M', '~0.7 km²', '1998–2026' in
//              Stat big, StatCard / HeroMetric value or a StatGrid item's value (E196); fixed values in FIXED below
// Counts are held per file in ui-language-baseline.json — the breaches the product had when the standard came in.
// The guard (uiLanguage.test.ts) fails when a file has more than its baseline, and when a fix leaves it with fewer
// (lower the baseline, so it only ever goes down):  node tests/uiLanguage.ts --write
import ts from 'typescript'
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

export const INTERNAL = /\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\bE\d{2,3}\b|\.(?:py|json|tsx?)\b|\/v1\/|named gap|append-only|golden (?:source|model)|product owner|\bseeded\b|\bstub\b|\blineage\b|sha-?256|\bH3\b/i
const DISPLAY = new Set(['title', 'label', 'lead', 'hint', 'placeholder', 'aria-label', 'sub', 'eyebrow', 'summary', 'what', 'alt', 'heading', 'body'])
const RAW = new Set(['status', 'kind', 'category', 'role', 'tier', 'severity', 'framework', 'scenario', 'curve_key', 'method',
  'layer_key', 'h3_cell', 'hazard', 'headline_hazard', 'top_hazard', 'code', 'action_key', 'org_type', 'sector', 'plan',
  'key', 'version', 'template'])
const PROSE = new Set(['note', 'basis', 'reason', 'gap', 'message', 'description', 'source', 'evidence', 'methodology',
  'review', 'caution', 'detail', 'rule', 'why', 'notice', 'citation', 'scope_note', 'basis_note', 'hint'])

// A figure: a number with its unit or magnitude ('51.4M', '~0.7 km²', '€2.1bn', '35%', '28 years'), or a span of years.
export const FIGURE = new RegExp(String.raw`(?:^|[^\w.,])[~≈<>≤≥±+−-]?[€$£]?\d[\d,.]*\s?(?:%|‰|[kKMB]\b|bn\b|mn\b|m\b|t\b|kt\b|Mt\b|`
  + String.raw`km²|km2\b|km\b|m²|m2\b|ha\b|°C?|mm\b|cm\b|[KMGT]B\b|x\b|×|h\b|d\b|hours?\b|days?\b|weeks?\b|months?\b|years?\b|yrs?\b)`
  + String.raw`|[€$£]\s?\d|\b(?:19|20)\d{2}\s?[–—-]\s?(?:(?:19|20)\d{2}|\d{2})\b`)
// Values fixed by definition, not read from data — each with the reason it may be typed, and an example the check
// would flag without it (the guard's test holds both). Keep this list short.
export const FIXED: { text: RegExp; example: string; why: string }[] = [
  { text: /^1-in-\d+(?: years?)?$/, example: '1-in-200 years',
    why: 'A return period names a scenario by how often it occurs (Solvency II 1-in-200, a catastrophe PML 1-in-250): part of its definition, not a figure read from data.' },
  { text: /^99\.5 ?%$/, example: '99.5%',
    why: 'Solvency II sets the SCR at Value-at-Risk with a 99.5% confidence level over one year (Directive 2009/138/EC Art. 101(3)): a term of the law, not a figure read from data.' },
]
const FIGURE_AT: Record<string, string> = { Stat: 'big', StatCard: 'value', HeroMetric: 'value' }

export type Counts = { internal: number; raw: number; monoProse: number; apiProse: number; figure: number }
const ROOT = new URL('..', import.meta.url).pathname
export const BASELINE = join(ROOT, 'tests', 'ui-language-baseline.json')

function files(dir: string, ext: RegExp): string[] {
  return readdirSync(dir).flatMap(n => {
    const p = join(dir, n)
    return statSync(p).isDirectory() ? files(p, ext) : ext.test(n) ? [p] : []
  })
}

export function sources(): string[] {
  return [...files(join(ROOT, 'src', 'pages'), /\.tsx$/), ...files(join(ROOT, 'src', 'components'), /\.tsx$/),
    ...files(join(ROOT, 'src', 'content'), /\.ts$/)].map(f => relative(ROOT, f)).sort()
}

// The static text of a string-ish expression (template parts without their ${…}).
function literal(e: ts.Node | undefined): string | null {
  if (!e) return null
  if (ts.isStringLiteral(e) || ts.isNoSubstitutionTemplateLiteral(e)) return e.text
  if (ts.isTemplateExpression(e)) return [e.head.text, ...e.templateSpans.map(s => s.literal.text)].join(' ')
  if (ts.isParenthesizedExpression(e)) return literal(e.expression)
  return null
}

// Everything an expression can put on screen: its typed texts (string literals and templates, each with the node it
// came from), the fields it prints as they are ({x.status}, ${x.note}) and the JSX elements it holds (scan reads those
// itself). A call (label(x.status), fmt(n)) is a rendering, not a field printed as-is.
type Shown = { texts: [string, ts.Node][]; fields: ts.PropertyAccessExpression[]; jsx: ts.Node[] }
function onScreen(e: ts.Node | undefined, out: Shown = { texts: [], fields: [], jsx: [] }): Shown {
  if (!e) return out
  const t = literal(e)
  if (t !== null && !ts.isParenthesizedExpression(e)) out.texts.push([t, e])
  if (ts.isTemplateExpression(e)) for (const s of e.templateSpans) onScreen(s.expression, out)
  else if (ts.isPropertyAccessExpression(e)) out.fields.push(e)
  else if (ts.isJsxElement(e) || ts.isJsxFragment(e) || ts.isJsxSelfClosingElement(e)) out.jsx.push(e)
  else if (ts.isParenthesizedExpression(e) || ts.isAsExpression(e) || ts.isNonNullExpression(e) || ts.isSatisfiesExpression(e)) onScreen(e.expression, out)
  else if (ts.isConditionalExpression(e)) { onScreen(e.whenTrue, out); onScreen(e.whenFalse, out) }
  else if (ts.isBinaryExpression(e)) {
    const op = e.operatorToken.kind
    if (op === ts.SyntaxKind.AmpersandAmpersandToken) onScreen(e.right, out)
    else if (op === ts.SyntaxKind.QuestionQuestionToken || op === ts.SyntaxKind.BarBarToken || op === ts.SyntaxKind.PlusToken) { onScreen(e.left, out); onScreen(e.right, out) }
  }
  return out
}

const words = (s: string) => (s.match(/[A-Za-z]{2,}/g) ?? []).length      // words, not punctuation or numbers

export function scan(rel: string): { counts: Counts; hits: string[] } {
  const text = readFileSync(join(ROOT, rel), 'utf8')
  return scanText(rel, text)
}

export function scanText(rel: string, text: string): { counts: Counts; hits: string[] } {
  const src = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const counts: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0, figure: 0 }
  const hits: string[] = []
  const read = new Set<ts.Node>()                                     // each text and field is counted once
  const line = (n: ts.Node) => src.getLineAndCharacterOfPosition(n.getStart(src)).line + 1
  const shown = (s: string | null, n: ts.Node) => {
    if (read.has(n)) return
    read.add(n)
    if (s && INTERNAL.test(s)) { counts.internal++; hits.push(`${rel}:${line(n)} internal "${s.trim().slice(0, 60)}"`) }
  }
  // Read an expression that reaches the screen. Inline (a JSX child) a server explanation is a breach too; in a display
  // prop or a toast it may be the pop-up's own body, so only codes printed as-is count there.
  const reach = (e: ts.Node | undefined, inline: boolean): Shown => {
    const r = onScreen(e)
    for (const [s, n] of r.texts) shown(s, n)
    for (const f of r.fields) {
      if (read.has(f)) continue
      read.add(f)
      const name = f.name.text
      if (RAW.has(name)) { counts.raw++; hits.push(`${rel}:${line(f)} raw {${f.getText(src).slice(0, 40)}}`) }
      else if (inline && PROSE.has(name)) { counts.apiProse++; hits.push(`${rel}:${line(f)} apiProse {${f.getText(src).slice(0, 40)}}`) }
    }
    return r
  }
  // A headline value is read like any text on screen (the JSX it holds is read by visit), and a figure typed into it —
  // a literal or JSX text — is flagged (E196) unless the value is fixed by definition (FIXED).
  const figured = new Set<ts.Node>()
  const headline = (e: ts.Node | undefined) => {
    const { texts: typed, jsx } = reach(e, true)
    const inJsx = (x: ts.Node) => {
      if (ts.isJsxText(x)) typed.push([x.text, x])
      else if (ts.isJsxExpression(x)) { const r = onScreen(x.expression); typed.push(...r.texts); r.jsx.forEach(inJsx) }
      else if (ts.isJsxElement(x) || ts.isJsxFragment(x)) x.children.forEach(inJsx)
    }
    jsx.forEach(inJsx)
    for (const [s, n] of typed) {
      const v = s.trim()
      if (figured.has(n) || !FIGURE.test(v) || FIXED.some(f => f.text.test(v))) continue
      figured.add(n)
      counts.figure++; hits.push(`${rel}:${line(n)} figure "${v.slice(0, 60)}"`)
    }
  }
  // A StatGrid's items (inline, or a variable typed StatItem): every `value:` in them is a headline value.
  const items = (e: ts.Node) => {
    if (ts.isPropertyAssignment(e) && e.name.getText(src) === 'value') return headline(e.initializer)
    ts.forEachChild(e, items)
  }
  const content = rel.startsWith('src/content/')
  const visit = (n: ts.Node) => {
    if (content && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n))) shown(literal(n), n)
    else if (ts.isJsxText(n)) shown(n.text, n)
    else if (ts.isJsxAttribute(n)) {
      const prop = n.name.getText(src), tag = n.parent.parent.tagName.getText(src)
      const v = n.initializer && ts.isJsxExpression(n.initializer) ? n.initializer.expression : n.initializer
      if (DISPLAY.has(prop)) reach(v, false)
      if (FIGURE_AT[tag] === prop) headline(v)
      if (tag === 'StatGrid' && prop === 'items' && v) items(v)
    } else if (ts.isPropertyAssignment(n) && DISPLAY.has(n.name.getText(src).replace(/['"]/g, ''))) reach(n.initializer, false)
    else if (ts.isCallExpression(n) && /^toast\.(success|error|info|warn)/.test(n.expression.getText(src))) reach(n.arguments[0], false)
    else if (ts.isJsxExpression(n) && n.expression && (ts.isJsxElement(n.parent) || ts.isJsxFragment(n.parent))) reach(n.expression, true)
    else if (ts.isVariableDeclaration(n) && n.type && /\bStatItem\b/.test(n.type.getText(src)) && n.initializer) items(n.initializer)
    if (ts.isJsxElement(n)) {
      const cls = n.openingElement.attributes.properties.find(p => ts.isJsxAttribute(p) && p.name.getText(src) === 'className') as ts.JsxAttribute | undefined
      const c = cls?.initializer ? (ts.isStringLiteral(cls.initializer) ? cls.initializer.text : cls.initializer.getText(src)) : ''
      const own = n.children.filter(ts.isJsxText).map(t => t.text).join(' ')
      if (/\bmono\b/.test(c) && words(own) >= 4) { counts.monoProse++; hits.push(`${rel}:${line(n)} monoProse "${own.trim().slice(0, 60)}"`) }
    }
    ts.forEachChild(n, visit)
  }
  visit(src)
  return { counts, hits }
}

export function scanAll(): Record<string, Counts> {
  const out: Record<string, Counts> = {}
  for (const f of sources()) {
    const { counts } = scan(f)
    if (Object.values(counts).some(Boolean)) out[f] = counts
  }
  return out
}

if (process.argv.includes('--write')) {
  const all = scanAll()
  writeFileSync(BASELINE, JSON.stringify(all, null, 1) + '\n')
  const t: Record<string, number> = {}
  for (const c of Object.values(all)) for (const [k, v] of Object.entries(c)) t[k] = (t[k] ?? 0) + v
  console.log(`baseline written: ${Object.keys(all).length} files —`, t)
}
