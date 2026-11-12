import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Check, Preset } from '../../src/cli.ts'
import {
  agents, argvOptions, blockedChoices, blockedLine, combos, HEALTH_CHECKS, lastCombo, lastFirst, lastOf, levels, repeatChoice, SETTING_AGENT, verdict,
} from '../../src/logic/launch.ts'

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

const terminal = { id: 'terminal', label: 'Terminal', needsAgent: true }
const clipboard = { id: 'clipboard', label: 'Copy the prompt', needsAgent: false }

test('the combos are every agent x effort x permissions, none first, and the setting is one row', () => {
  const all = combos(agents([preset], ['/bin/echo', 'x']))
  assert.deepEqual(all.map(c => [c.id, c.label, c.effort, c.permissions]), [
    ['one//', 'One · no effort flag · no permissions flag', '', ''],
    ['one//ask', 'One · no effort flag · ask', '', 'ask'],
    ['one/low/', 'One · low · no permissions flag', 'low', ''],
    ['one/low/ask', 'One · low · ask', 'low', 'ask'],
    ['one/high/', 'One · high · no permissions flag', 'high', ''],
    ['one/high/ask', 'One · high · ask', 'high', 'ask'],
    [SETTING_AGENT, 'workstreams.agentCommand', '', ''],
  ])
  assert.equal(all.at(-1)?.agent.detail, '/bin/echo x')
  // A preset with no levels of a kind offers only no flag for it, and its label leaves it out.
  const bare: Preset = { ...preset, agent: 'bare', label: 'Bare', effortLevels: [], permissionChoices: ['ask'] }
  assert.deepEqual(combos(agents([bare], [])).map(c => [c.id, c.label]), [['bare//', 'Bare · no permissions flag'], ['bare//ask', 'Bare · ask']])
})

test('the repeat row is the last terminal launch whole, with none kept as a real choice', () => {
  const all = combos(agents([preset], ['/bin/echo']))
  const none = repeatChoice({ target: 'terminal', agent: 'one', effort: '', permissions: 'ask' }, [terminal, clipboard], all)
  assert.equal(none?.label, '$(history) Terminal · One · no effort flag · ask')
  assert.equal(none?.description, 'last used')
  assert.equal(none?.target, terminal)
  assert.deepEqual([none?.combo.effort, none?.combo.permissions], ['', 'ask'])
  // An older state with no effort or permissions stored reads as none.
  assert.equal(repeatChoice({ target: 'terminal', agent: 'one' }, [terminal], all)?.combo.id, 'one//')
  // The agentCommand row matches on the agent alone.
  const setting = repeatChoice({ target: 'terminal', agent: SETTING_AGENT, effort: 'high', permissions: 'ask' }, [terminal], all)
  assert.equal(setting?.label, '$(history) Terminal · workstreams.agentCommand')
  assert.equal(setting?.combo.agent.argv?.[0], '/bin/echo')
  assert.equal(lastCombo(all, { agent: 'one', effort: 'high', permissions: '' })?.id, 'one/high/')
})

test('a stale or partial last choice gives no repeat row', () => {
  const all = combos(agents([preset], ['/bin/echo']))
  const last = { target: 'terminal', agent: 'one', effort: 'high', permissions: 'ask' }
  assert.ok(repeatChoice(last, [terminal], all))
  // The agentCommand setting cleared.
  assert.equal(repeatChoice({ ...last, agent: SETTING_AGENT }, [terminal], combos(agents([preset], []))), undefined)
  // A preset dropped a level, or the agent is gone.
  assert.equal(repeatChoice({ ...last, effort: 'max' }, [terminal], all), undefined)
  assert.equal(repeatChoice({ ...last, permissions: 'yolo' }, [terminal], all), undefined)
  assert.equal(repeatChoice({ ...last, agent: 'gone' }, [terminal], all), undefined)
  // The target no longer offered (a chat extension disabled), or never a terminal.
  assert.equal(repeatChoice({ ...last, target: 'claude-code' }, [terminal, clipboard], all), undefined)
  assert.equal(repeatChoice({ ...last, target: 'clipboard' }, [terminal, clipboard], all), undefined)
  // Nothing remembered.
  assert.equal(repeatChoice({}, [terminal], all), undefined)
  assert.equal(repeatChoice({ target: 'terminal' }, [terminal], all), undefined)
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
