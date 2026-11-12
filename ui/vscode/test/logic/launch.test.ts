import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Check, Preset } from '../../src/cli.ts'
import { agents, argvOptions, blockedChoices, blockedLine, HEALTH_CHECKS, lastFirst, lastOf, levels, SETTING_AGENT, verdict } from '../../src/logic/launch.ts'

const check = (id: string, ok: boolean, blocking: boolean): Check => ({ id, ok, blocking, message: `${id} said so` })
const preset: Preset = { agent: 'one', label: 'One', command: 'one-cli', effortLevels: ['low', 'high'], permissionChoices: ['ask'] }

test('a failing blocking check blocks; a failing warning is passed on; a passing one is neither', () => {
  const found = verdict([check('validate', true, true), check('claim', false, true), check('baseline', false, false), check('skills', true, false)])
  assert.deepEqual(found.blocking.map(c => c.id), ['claim'])
  assert.deepEqual(found.warnings.map(c => c.id), ['baseline'])
  assert.equal(blockedLine('Run alpha', found.blocking), 'Run alpha is blocked by 1 check')
})

test('the blocked list puts blocking rows first, then warnings, then passes, each with its icon', () => {
  const checks = [check('skills', true, false), check('baseline', false, false), check('validate', false, true), check('wave', true, true), check('claim', false, true)]
  assert.deepEqual(blockedChoices(checks).map(c => [c.label, c.description, c.value]), [
    ['$(error) validate', 'validate said so', 'validate'],
    ['$(error) claim', 'claim said so', 'claim'],
    ['$(warning) baseline', 'baseline said so', 'baseline'],
    ['$(pass) skills', 'skills said so', 'skills'],
    ['$(pass) wave', 'wave said so', 'wave'],
  ])
  assert.equal(blockedLine('Run alpha', verdict(checks).blocking), 'Run alpha is blocked by 2 checks')
  assert.deepEqual(HEALTH_CHECKS, ['validate', 'claim'])
})

test('the agents are the presets, then the setting when it is set', () => {
  assert.deepEqual(agents([preset], []).map(a => a.id), ['one'])
  assert.deepEqual(agents([preset], ['/bin/echo', 'x']).map(a => [a.id, a.detail]), [['one', 'one-cli'], [SETTING_AGENT, '/bin/echo x']])
  assert.deepEqual(agents([], ['']), [])
})

test('the last choice comes first, and nothing else moves', () => {
  assert.deepEqual(lastFirst(['a', 'b', 'c'], v => v, 'c'), ['c', 'a', 'b'])
  assert.deepEqual(lastFirst(['a', 'b', 'c'], v => v, 'a'), ['a', 'b', 'c'])
  assert.deepEqual(lastFirst(['a', 'b'], v => v, 'gone'), ['a', 'b'])
  assert.deepEqual(lastFirst(['a', 'b'], v => v, undefined), ['a', 'b'])
  assert.deepEqual(levels(['low']), ['', 'low'])
})

test('stored state is read field by field, and junk is dropped', () => {
  assert.deepEqual(lastOf(undefined), {})
  assert.deepEqual(lastOf('x'), {})
  assert.deepEqual(lastOf({ target: 'terminal', agent: 3, effort: '', extra: 'x' }), { target: 'terminal', effort: '' })
})

test("a built argv is the terminal's process and its arguments, unparsed", () => {
  assert.deepEqual(argvOptions(['one-cli', '--x', 'a "b" $(c)'], '/r', 'n'), { name: 'n', shellPath: 'one-cli', shellArgs: ['--x', 'a "b" $(c)'], cwd: '/r' })
  assert.equal(argvOptions([], '/r', 'n'), undefined)
})
