// The note on a file read with a column mapping names each converted field (UI standard): it used to print a currency
// conversion as the field's key and nothing after it ('appraised_value_eur: '), reading rates the report never carries.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { conversionText } from '../src/components/mappingWords.ts'

test('a conversion reads as the field\'s name and what was done to it', () => {
  assert.equal(conversionText({ field: 'appraised_value_eur', label: 'Appraised value', kind: 'scale', factor: 1000 }), 'Appraised value × 1,000')
  assert.equal(conversionText({ field: 'appraised_value_eur', label: 'Appraised value', kind: 'currency', currency: 'USD' }), 'Appraised value in USD')
  assert.equal(conversionText({ field: 'appraised_value_eur', label: 'Appraised value', kind: 'currency', currency_column: 'Ccy' }),
    'Appraised value: currency per row from “Ccy”')
  assert.doesNotMatch(conversionText({ field: 'appraised_value_eur', kind: 'scale', factor: 1000 }), /_/)
})

test('the server sends what the note reads: a label on every conversion, the currency or its column', () => {
  const server = readFileSync(new URL('../../services/intake/mapping.py', import.meta.url), 'utf8')
  const sent = server.split('\n').filter(l => l.includes('report["conversions"].append'))
  assert.equal(sent.length, 4)
  for (const l of sent) assert.match(l, /"label": _label\(t\)/)
  assert.match(server, /"currency": report\["field_currency"\]\[t\]/)
  assert.match(server, /"currency_column": spec\["currency_column"\]/)
})
