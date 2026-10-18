// The UI standard's automatic guard (product owner, 2026-10-16): what a screen shows is customer language, short,
// and not in the code font. This scans every page, component and content file for six kinds of breach in the text
// it puts on screen — JSX text and expressions, display props (title, label, lead, hint, sub, …), toast messages.
// An expression is read through to everything it can show: string literals, every part of a template string, both
// branches of ?:, both sides of ?? || and +, the right of && — and the fields it prints, alone or inside ${…} (E196),
// or as the items of a list it joins ({sf.incomplete?.join(' ')}, [a.region, a.status].filter(Boolean).join(' · ')) (E-next):
//   internal   internal language: a snake_case or dotted code (pricing.approve, E-next), an E-number, a file path, an API
//              path, engineering jargon
//   raw        a code rendered as-is: {x.status}, `${f.framework} · ${f.template}` … straight onto the screen
//   monoProse  a sentence set in the code font (an element whose class has `mono` holding four words or more)
//   apiProse   a server explanation printed inline: {x.note}, {r.basis}, {e.reason} … — it belongs in the pop-up
//   figure     a figure typed into a headline value instead of read from data: '51.4M', '~0.7 km²', '1998–2026' in
//              Stat big, StatCard / HeroMetric value or a StatGrid item's value (E196); fixed values in FIXED below
//   citation   a legal citation on the main screen — an article, annex, regulation, template number or standard code
//              ('Art. 90b', 'Del. Reg. 2015/35', 'S.27.01.01') — it belongs one click away (CITATION below) (E-next)
// Counts are held per file in ui-language-baseline.json — the breaches the product had when the standard came in.
// The guard (uiLanguage.test.ts) fails when a file has more than its baseline, and when a fix leaves it with fewer
// (lower the baseline, so it only ever goes down):  node tests/uiLanguage.ts --write
import ts from 'typescript'
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { join, relative } from 'node:path'

export const INTERNAL = /\b[a-z][a-z0-9]*_[a-z0-9_]+\b|\bE\d{2,3}\b|\.(?:py|json|tsx?)\b|\/v1\/|named gap|append-only|golden (?:source|model)|product owner|\bseeded\b|\bstub\b|\blineage\b|sha-?256|\bH3\b/i
// A dotted code — a permission, action, event or message key: lowercase words of two letters or more joined by dots
// (pricing.approve, risk.decision.approved). Not 'e.g.' or 'i.e.' (one-letter words), a decimal or version (0.05,
// v2.1), an e-mail or web address (after @ or /), or a word ending a sentence. A file name or a domain has the same
// shape, so a last word in NOT_A_CODE is not a code.
export const DOTTED = /(?<![\w@./:\\-])[a-z][a-z0-9_]+(?:\.[a-z][a-z0-9_]+)+(?![\w@/:\\-]|\.\w)/g
export const NOT_A_CODE: { last: RegExp; example: string; why: string }[] = [
  { last: /^(?:csv|xlsx|xls|pdf|json|zip|html|htm|xhtml|xbrl|xml|png|geojson)$/, example: 'holdings.xlsx',
    why: 'A file name: the formats the product reads and writes (its upload accept= lists and the names it gives downloads).' },
  { last: /^(?:com|org|net|edu|gov|int|mil)$/, example: 'company.com',
    why: 'A domain, as an example of what to type: the generic top-level domains of RFC 1591.' },
  { last: /^[a-z]{2}$/, example: 'tellumen.eu',
    why: 'A domain: a country-code top-level domain is the two letters of ISO 3166-1 (RFC 1591). The codes that end in two letters (EET answer keys, q_sust_obj.no) are snake_case, which INTERNAL flags.' },
]
export const dottedCodes = (s: string) => (s.match(DOTTED) ?? []).filter(t => !NOT_A_CODE.some(n => n.last.test(t.split('.').pop()!)))
const internal = (s: string) => INTERNAL.test(s) || dottedCodes(s).length > 0
const DISPLAY = new Set(['title', 'label', 'lead', 'hint', 'placeholder', 'aria-label', 'sub', 'eyebrow', 'summary', 'what', 'alt', 'heading', 'body'])
const RAW = new Set(['status', 'kind', 'category', 'role', 'tier', 'severity', 'framework', 'scenario', 'curve_key', 'method',
  'layer_key', 'h3_cell', 'hazard', 'headline_hazard', 'top_hazard', 'code', 'action_key', 'org_type', 'sector', 'plan',
  'key', 'version', 'template'])
const PROSE = new Set(['note', 'basis', 'reason', 'gap', 'message', 'description', 'source', 'evidence', 'methodology',
  'review', 'caution', 'detail', 'rule', 'why', 'notice', 'citation', 'scope_note', 'basis_note', 'hint', 'incomplete'])
// A field read by its name above that, in one file, holds customer words — each with what it holds and where that is
// set (the guard's test checks each still names a field its file prints). Keep this list short.
export const WORDS: { file: string; field: string; why: string }[] = [
  { file: 'src/components/FundPositions.tsx', field: 'sector',
    why: "The issuer's sector in the customer's words ('Banking', 'Electric utilities'): api/routers/funds.py stores the sector a holding's upload states." },
  { file: 'src/pages/Kri.tsx', field: 'gaps',
    why: "The readiness gaps are the labels of the regulator's core KRIs that have no value yet (services/governance/kri_regmap.py annotate)." },
  { file: 'src/pages/PriorFilings.tsx', field: 'basis_note',
    why: 'The preparation basis the customer types when confirming a prior filing (services/governance/prior_filings.py confirm).' },
  { file: 'src/pages/SupervisorMandates.tsx', field: 'tier',
    why: "A mandate check's tier is the tier's label from data/reference/regulatory_mandates.json (services/supervision/mandates.py evaluate)." },
  { file: 'src/pages/respondent/Mandates.tsx', field: 'tier',
    why: "A mandate check's tier is the tier's label from data/reference/regulatory_mandates.json (services/supervision/mandates.py evaluate)." },
]

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

// A legal citation: an article, an annex, a regulation's number, a reporting template's number or a standard's metric
// code. The product owner's decision of 2026-10-18: the main screen says it in plain words; a citation belongs one click
// away — the ⓘ pop-up (a details={…} pop-up, its { heading, body } sections), a dialog or a side drawer — and in
// filings and exports. Names customers use as categories stay: an 'Article 8' or 'Article 9' fund (SFDR's product
// categories, CATEGORY), Pillar 3, SFDR, Solvency II.
export const CITATION = new RegExp([
  String.raw`\bArt(?:icles?|s)?\.?\s?\d+[a-z]?`,                                  // Art. 90b, Arts 119-126, Article 5(3)
  String.raw`\bAnnex(?:es)?\s(?:[IVXL]+|\d+)\b`,                                  // Annex III, Annex XIII
  String.raw`\b(?:Regulation|Directive|Decision|Reg\.|Dir\.|ITS|RTS)\s(?:\((?:EU|EC|EEC)\)\s)?(?:No\.?\s?)?\d{2,4}\/\d+`, // Del. Reg. 2015/35
  String.raw`\b[SE]\.\d{2}\.\d{2}\.\d{2}\b`,                                      // S.27.01.01
  String.raw`\b[A-Z]{2}-[A-Z]{2}-\d{3}[a-z]\.\d+\b`,                              // SASB FN-IN-450a.2
].join('|'), 'g')
export const CATEGORY = /^Art(?:icle|\.)\s?[689]$/                               // an 'Article 8 fund', not Article 8(1)
export const citations = (s: string) => [...s.matchAll(CITATION)]
  .filter(m => !(CATEGORY.test(m[0]) && !/^\s?\(/.test(s.slice(m.index! + m[0].length)))).map(m => m[0])
const AWAY = new Set(['Dialog', 'Drawer'])                                         // one click away, like the pop-up

// The components of a file that render a Dialog or Drawer as their root (eudr/EudrForms' Form): what they hold is one
// click away too, here and in every file that imports them.
const wrapping = new Map<string, Set<string>>()
function wrappers(rel: string, text?: string): Set<string> {
  if (wrapping.has(rel)) return wrapping.get(rel)!
  const own = new Set<string>()
  wrapping.set(rel, own)                                                           // a cycle of imports adds nothing
  let body = text
  if (body === undefined) { try { body = readFileSync(join(ROOT, rel), 'utf8') } catch { return own } }
  const src = ts.createSourceFile(rel, body, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const tags = new Set(AWAY)
  for (const st of src.statements) {                                               // what it imports from its own files
    if (!ts.isImportDeclaration(st) || !ts.isStringLiteral(st.moduleSpecifier) || !st.moduleSpecifier.text.startsWith('.')) continue
    const from = relative(ROOT, join(ROOT, rel, '..', st.moduleSpecifier.text)) + '.tsx'
    const names = st.importClause?.namedBindings && ts.isNamedImports(st.importClause.namedBindings) ? st.importClause.namedBindings.elements : []
    const theirs = wrappers(from)
    for (const n of names) if (theirs.has((n.propertyName ?? n.name).text)) tags.add(n.name.text)
  }
  const tag = (e: ts.Node | undefined): string | null => {
    while (e && ts.isParenthesizedExpression(e)) e = e.expression
    return !e ? null : ts.isJsxElement(e) ? e.openingElement.tagName.getText(src) : ts.isJsxSelfClosingElement(e) ? e.tagName.getText(src) : null
  }
  const roots = (f: ts.FunctionLikeDeclaration) => {
    if (!f.body) return []
    if (!ts.isBlock(f.body)) return [tag(f.body)]
    const out: (string | null)[] = []
    const ret = (n: ts.Node): void => { if (ts.isReturnStatement(n)) { if (n.expression && n.expression.kind !== ts.SyntaxKind.NullKeyword) out.push(tag(n.expression)) } else if (!ts.isFunctionLike(n)) ts.forEachChild(n, ret) }
    ret(f.body)
    return out
  }
  const fns: [string, ts.FunctionLikeDeclaration][] = []
  for (const st of src.statements) {
    if (ts.isFunctionDeclaration(st) && st.name) fns.push([st.name.text, st])
    if (ts.isVariableStatement(st)) for (const d of st.declarationList.declarations)
      if (ts.isIdentifier(d.name) && d.initializer && (ts.isArrowFunction(d.initializer) || ts.isFunctionExpression(d.initializer))) fns.push([d.name.text, d.initializer])
  }
  for (let grew = true; grew;) {                                                  // a wrapper of a wrapper, in the same file
    grew = false
    for (const [name, f] of fns) {
      const r = roots(f)
      if (!own.has(name) && r.length && r.every(t => t !== null && (tags.has(t) || own.has(t)))) { own.add(name); grew = true }
    }
  }
  for (const n of own) tags.add(n)
  wrapping.set(rel, own)
  awayTags.set(rel, tags)
  return own
}
const awayTags = new Map<string, Set<string>>()

export type Counts = { internal: number; raw: number; monoProse: number; apiProse: number; figure: number; citation: number }
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
// itself). A call (label(x.status), fmt(n)) is a rendering, not a field printed as-is — except .join(), which prints
// a list's items as they are (lists, below).
type Shown = { texts: [string, ts.Node][]; fields: ts.PropertyAccessExpression[]; lists: ts.PropertyAccessExpression[]; jsx: ts.Node[] }
function onScreen(e: ts.Node | undefined, out: Shown = { texts: [], fields: [], lists: [], jsx: [] }): Shown {
  if (!e) return out
  const t = literal(e)
  if (t !== null && !ts.isParenthesizedExpression(e)) out.texts.push([t, e])
  if (ts.isTemplateExpression(e)) for (const s of e.templateSpans) onScreen(s.expression, out)
  else if (ts.isCallExpression(e) && method(e) === 'join') items(callee(e), out)
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

// The items of a list that .join() prints (E-next): a list field ({sf.incomplete?.join(' ')}), each item of an array
// literal ([a.region, a.status]), what a .map(r => …) returns, through .filter / .slice / .concat / ?? / ?: — a .map
// with a named function (hazardLabel) renders its items. A list field counts by what it holds (reasons → reason).
const method = (e: ts.CallExpression) => ts.isPropertyAccessExpression(e.expression) ? e.expression.name.text : null
const callee = (e: ts.CallExpression) => (e.expression as ts.PropertyAccessExpression).expression
function items(e: ts.Node, out: Shown): void {
  if (ts.isParenthesizedExpression(e) || ts.isAsExpression(e) || ts.isNonNullExpression(e)) items(e.expression, out)
  else if (ts.isPropertyAccessExpression(e)) out.lists.push(e)
  else if (ts.isArrayLiteralExpression(e)) for (const x of e.elements) ts.isSpreadElement(x) ? items(x.expression, out) : onScreen(x, out)
  else if (ts.isConditionalExpression(e)) { items(e.whenTrue, out); items(e.whenFalse, out) }
  else if (ts.isBinaryExpression(e) && [ts.SyntaxKind.QuestionQuestionToken, ts.SyntaxKind.BarBarToken].includes(e.operatorToken.kind)) { items(e.left, out); items(e.right, out) }
  else if (ts.isCallExpression(e) && ['filter', 'slice', 'concat'].includes(method(e) ?? '')) {
    items(callee(e), out)
    if (method(e) === 'concat') e.arguments.forEach(a => items(a, out))
  } else if (ts.isCallExpression(e) && method(e) === 'map' && e.arguments[0] && ts.isArrowFunction(e.arguments[0])) {
    const f = e.arguments[0]
    if (!ts.isBlock(f.body)) onScreen(f.body, out)
    else { const ret = (n: ts.Node): void => { if (ts.isReturnStatement(n)) onScreen(n.expression, out); else if (!ts.isFunctionLike(n)) ts.forEachChild(n, ret) }; ret(f.body) }
  }
}
// A list field's name, and the singular it holds: reasons → reason, statuses → status, categories → category.
const holds = (name: string) => [name, name.replace(/ies$/, 'y'), name.replace(/es$/, ''), name.replace(/s$/, '')]

const words = (s: string) => (s.match(/[A-Za-z]{2,}/g) ?? []).length      // words, not punctuation or numbers

export function scan(rel: string): { counts: Counts; hits: string[]; kept: Set<string> } {
  const text = readFileSync(join(ROOT, rel), 'utf8')
  return scanText(rel, text)
}

export function scanText(rel: string, text: string): { counts: Counts; hits: string[]; kept: Set<string> } {
  const src = ts.createSourceFile(rel, text, ts.ScriptTarget.Latest, true, rel.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)
  const counts: Counts = { internal: 0, raw: 0, monoProse: 0, apiProse: 0, figure: 0, citation: 0 }
  const hits: string[] = []
  const customer = new Set(WORDS.filter(w => w.file === rel).map(w => w.field)), kept = new Set<string>()   // WORDS
  const read = new Set<ts.Node>()                                     // each text and field is counted once
  const line = (n: ts.Node) => src.getLineAndCharacterOfPosition(n.getStart(src)).line + 1
  const shown = (s: string | null, n: ts.Node) => {
    if (read.has(n)) return
    read.add(n)
    if (s && internal(s)) { counts.internal++; hits.push(`${rel}:${line(n)} internal "${s.trim().slice(0, 60)}"`) }
    const c = s && !away(n) ? citations(s) : []
    if (c.length) { counts.citation++; hits.push(`${rel}:${line(n)} citation "${c.join(' · ')}" in "${s!.trim().slice(0, 50)}"`) }
  }
  // Text one click away: inside a Dialog or Drawer, a details={…} pop-up, a { heading, body } section or a
  // { title, sections } pop-up, or a value typed Details / DetailSection.
  const named = (o: ts.ObjectLiteralExpression, k: string) => o.properties.some(p => p.name?.getText(src) === k)
  wrapping.delete(rel); wrappers(rel, text)                                       // this text, not the file on disk
  const tags = awayTags.get(rel)!
  const away = (n: ts.Node): boolean => {
    for (let p = n.parent; p; p = p.parent) {
      if (ts.isJsxElement(p) && tags.has(p.openingElement.tagName.getText(src))) return true
      if (ts.isJsxSelfClosingElement(p) && tags.has(p.tagName.getText(src))) return true
      if ((ts.isJsxAttribute(p) || ts.isPropertyAssignment(p)) && p.name.getText(src) === 'details') return true
      if (ts.isObjectLiteralExpression(p) && ((named(p, 'heading') && named(p, 'body')) || (named(p, 'title') && named(p, 'sections')))) return true
      if ((ts.isVariableDeclaration(p) || ts.isFunctionLike(p)) && p.type && /\bDetails?\b|\bDetailSection\b/.test(p.type.getText(src))) return true
    }
    return false
  }
  // Read an expression that reaches the screen. Inline (a JSX child) a server explanation is a breach too; in a display
  // prop or a toast it may be the pop-up's own body, so only codes printed as-is count there.
  const reach = (e: ts.Node | undefined, inline: boolean): Shown => {
    const r = onScreen(e)
    for (const [s, n] of r.texts) shown(s, n)
    for (const f of [...r.fields, ...r.lists]) {
      if (read.has(f)) continue
      read.add(f)
      const names = r.lists.includes(f) ? holds(f.name.text) : [f.name.text]
      if (customer.has(f.name.text)) { kept.add(f.name.text); continue }
      if (names.some(n => RAW.has(n))) { counts.raw++; hits.push(`${rel}:${line(f)} raw {${f.getText(src).slice(0, 40)}}`) }
      else if (inline && names.some(n => PROSE.has(n))) { counts.apiProse++; hits.push(`${rel}:${line(f)} apiProse {${f.getText(src).slice(0, 40)}}`) }
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
  return { counts, hits, kept }
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
