// The KRI screens say only what is so (E-next): the headline says every indicator is within appetite only when some
// indicator is graded (a set with no band was announced as all within appetite), and saving a band that needs a second
// person's approval says it was sent for approval — never that the band was updated.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { bandSaved, heroTitle } from '../src/pages/kri/words.ts'

test('a set with no graded indicator is not called within appetite', () => {
  assert.equal(heroTitle({ red: 0, amber: 0, ok: 0 }), 'No appetite band is set on these indicators yet.')
  assert.equal(heroTitle({ red: 0, amber: 0, ok: 3 }), 'Every graded indicator is within appetite.')
  assert.equal(heroTitle({ red: 2, amber: 1, ok: 3 }), '2 indicators in breach.')
  assert.equal(heroTitle({ red: 0, amber: 1, ok: 3 }), '1 indicator in warning.')
})

test('a band sent for approval is not reported as updated', () => {
  assert.match(bandSaved('pending_approval'), /approval/)
  assert.doesNotMatch(bandSaved('pending_approval'), /updated/)
  assert.equal(bandSaved('applied'), 'Appetite band updated.')
})
