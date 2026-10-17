// The UI standard's automatic guard (product owner, 2026-10-16): what a screen shows is customer language, short,
// and not in the code font. This scans every page, component and content file for three kinds of breach in the text
// it puts on screen — JSX text, display props (title, label, lead, hint, sub, …), toast messages:
//   internal   internal language: a snake_case code, an E-number, a file path, an API path, engineering jargon
//   raw        a code rendered as-is: {x.status}, {r.kind}, {f.framework} … straight into the page
//   monoProse  a sentence set in the code font (an element whose class has `mono` holding four words or more)
//   apiProse   a server explanation printed inline: {x.note}, {r.basis}, {e.reason} … — it belongs in the pop-up
// Counts are held per file in ui-language-baseline.json — the breaches the product had when the standard came in.
// The guard (uiLanguage.test.ts) fails when a file has more than its baseline, and when a fix leaves it with fewer
// (lower the baseline, so it only ever goes down):  node tests/uiLanguage.ts --write
import ts from 'typescript'
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

export const INTERNAL = /\b[a-z]+_[a-z0-9_]+\b|\bE\d{2,3}\b|\.(?:py|json|tsx?)\b|\/v1\/|named gap|append-only|golden (?:source|model)|product owner|\bseeded\b|\bstub\b|\blineage\b|sha-?256|\bH3\b/i
const DISPLAY = new Set(['title', 'label', 'lead', 'hint', 'placeholder', 'aria-label', 'sub', 'eyebrow', 'summary', 'what', 'alt', 'heading', 'body'])
const RAW = new Set(['status', 'kind', 'category', 'role', 'tier', 'severity', 'framework', 'scenario', 'curve_key', 'method',
  'layer_key', 'h3_cell', 'hazard', 'headline_hazard', 'top_hazard', 'code', 'action_key', 'org_type', 'sector', 'plan',
  'key', 'version'])
const PROSE = new Set(['note', 'basis', 'reason', 'gap', 'message', 'description', 'source', 'evidence', 'methodology',
  'review', 'caution', 'detail', 'rule', 'why', 'notice', 'citation', 'scope_note', 'basis_note', 'hint'])

export type Counts = { internal: number; raw: number; monoProse: number; apiProse: number }
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

const words = (s: string) => (s.match(/[A-Za-z]{2,}/g) ?? []).length      // words, not punctuation or numbers

export function scan(rel: string): { counts: Counts; hits: string[] } {
  const text = readFileSync(join(ROOT, rel), 'utf8')
  const src = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const counts: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0 }
  const hits: string[] = []
  const line = (n: ts.Node) => src.getLineAndCharacterOfPosition(n.getStart(src)).line + 1
  const shown = (s: string | null, n: ts.Node) => {
    if (s && INTERNAL.test(s)) { counts.internal++; hits.push(`${rel}:${line(n)} internal "${s.trim().slice(0, 60)}"`) }
  }
  const content = rel.startsWith('src/content/')
  const visit = (n: ts.Node) => {
    if (content && (ts.isStringLiteral(n) || ts.isNoSubstitutionTemplateLiteral(n) || ts.isTemplateExpression(n))) shown(literal(n), n)
    else if (ts.isJsxText(n)) shown(n.text, n)
    else if (ts.isJsxAttribute(n) && DISPLAY.has(n.name.getText(src))) {
      const v = n.initializer
      shown(v && ts.isJsxExpression(v) ? literal(v.expression) : literal(v), n)
    } else if (ts.isPropertyAssignment(n) && DISPLAY.has(n.name.getText(src).replace(/['"]/g, ''))) shown(literal(n.initializer), n)
    else if (ts.isCallExpression(n) && /^toast\.(success|error|info|warn)/.test(n.expression.getText(src))) shown(literal(n.arguments[0]), n)
    else if (ts.isJsxExpression(n) && n.expression && (ts.isJsxElement(n.parent) || ts.isJsxFragment(n.parent))) {
      const e = n.expression
      const name = ts.isPropertyAccessExpression(e) ? e.name.text : null
      if (name && RAW.has(name)) { counts.raw++; hits.push(`${rel}:${line(n)} raw {${e.getText(src).slice(0, 40)}}`) }
      else if (name && PROSE.has(name)) { counts.apiProse++; hits.push(`${rel}:${line(n)} apiProse {${e.getText(src).slice(0, 40)}}`) }
      else shown(literal(e), n)
    }
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
    if (counts.internal || counts.raw || counts.monoProse || counts.apiProse) out[f] = counts
  }
  return out
}

if (process.argv.includes('--write')) {
  const all = scanAll()
  writeFileSync(BASELINE, JSON.stringify(all, null, 1) + '\n')
  const t = Object.values(all).reduce((a, c) => ({ internal: a.internal + c.internal, raw: a.raw + c.raw, monoProse: a.monoProse + c.monoProse, apiProse: a.apiProse + c.apiProse }), { internal: 0, raw: 0, monoProse: 0, apiProse: 0 })
  console.log(`baseline written: ${Object.keys(all).length} files —`, t)
}
