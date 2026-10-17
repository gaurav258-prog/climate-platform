// The UI standard (2026-10-16): short lines stay on the main screen, explanations move into the details pop-up, and a
// gap names what is missing in customer words rather than printing internal keys.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { isShort, textOf } from '../src/lib/brevity.ts'
import { gapMethodKeys } from '../src/lib/methodGap.ts'

test('a descriptor of six words or fewer stays on the screen; a sentence does not', () => {
  assert.equal(isShort('every asset and peril, recorded'), true)
  assert.equal(isShort('every asset and peril, recorded and never edited'), false)
  assert.equal(isShort(42), true)
  assert.equal(isShort(null), true)
})

test('the words of a node include its nested elements', () => {
  const node = createElement('span', null, 'Losses from ', createElement('b', null, 'river flood'), ' today')
  assert.equal(textOf(node).replace(/\s+/g, ' ').trim(), 'Losses from river flood today')
  assert.equal(isShort(node, 3), false)
})

test('a gap names its method keys once, without their breakdowns', () => {
  assert.deepEqual(gapMethodKeys('not stated: method.damage_ratio (flood/H), method.damage_ratio (flood/M), method.at_risk_level'),
    ['method.damage_ratio', 'method.at_risk_level'])
  assert.deepEqual(gapMethodKeys('the asset has no location'), [])
})
