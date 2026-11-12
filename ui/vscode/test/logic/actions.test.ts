import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import { commitLine, confirmText, contextValue, launches, moved, rowWrites, taskWrites } from '../../src/logic/actions.ts'
import type { Finding, Row, Task } from '../../src/logic/format.ts'
import { needsReason, offerPrompt, terminalOptions } from '../../src/logic/launch.ts'
import { listRows, taskRows } from '../../src/logic/detail.ts'
import type { WsSnapshot } from '../../src/logic/registry.ts'

const row = (id: string, status: string, actions: string[] = [], kinds: string[] = []): Row =>
  ({ id, status, actions, launches: kinds.map(kind => ({ kind, prompt: `${kind} ${id}.` })) })
const stale: Finding = { level: 'warning', workstream: 'alpha', task: 'A-1', actions: [{ action: 'unclaim', workstream: 'alpha', task: 'A-1' }] }

test('a row offers what its actions say, never what its status suggests', () => {
  assert.deepEqual(rowWrites(row('alpha', 'active', ['pause']), []), ['pause'])
  assert.deepEqual(rowWrites(row('alpha', 'paused', ['resume', 'sync']), []), ['resume', 'sync'])
  // An active row whose snapshot offers nothing gets nothing: there is no status rule here.
  assert.deepEqual(rowWrites(row('alpha', 'active', []), []), [])
  assert.deepEqual(rowWrites({ id: 'alpha', status: 'active' }, []), [])
  // A write the extension doesn't know is left out.
  assert.deepEqual(rowWrites(row('alpha', 'active', ['explode', 'pause']), []), ['pause'])
  // A finding's task offer is the task's, not the row's; a row-wide one is the row's.
  assert.deepEqual(rowWrites(row('alpha', 'active'), [stale]), [])
  assert.deepEqual(rowWrites(row('alpha', 'active'), [{ level: 'warning', workstream: 'alpha', actions: [{ action: 'sync', workstream: 'alpha' }] }]), ['sync'])
})

test('a task offers only what a finding offers for it', () => {
  assert.deepEqual(taskWrites([stale], 'alpha', 'A-1'), ['unclaim'])
  assert.deepEqual(taskWrites([stale], 'alpha', 'A-2'), [])
  assert.deepEqual(taskWrites([stale], 'beta', 'A-1'), [])
  assert.deepEqual(taskWrites([{ level: 'warning', workstream: 'alpha', task: 'A-1' }], 'alpha', 'A-1'), [])
})

test('a row offers only the launches its snapshot lists, never what its status suggests', () => {
  assert.deepEqual(launches(row('a', 'active', [], ['run', 'coordinate', 'close', 'abandon'])), ['run', 'coordinate', 'close', 'abandon'])
  // Only the listed kinds, in menu order; a kind the extension can't start is left out.
  assert.deepEqual(launches(row('a', 'paused', [], ['abandon', 'coordinate', 'run-task'])), ['coordinate', 'abandon'])
  // An open row whose snapshot lists none offers none: there is no status rule here.
  assert.deepEqual(launches(row('a', 'active')), [])
  assert.deepEqual(launches({ id: 'a', status: 'active' }), [])
  // A closed row's snapshot lists none, so it offers none.
  assert.deepEqual(launches(row('a', 'done')), [])
  assert.deepEqual(launches(row('a', 'abandoned')), [])
})

test('the contextValue names each offer as a word the menus match', () => {
  assert.equal(contextValue('workstream', ['pause', 'sync'], ['run', 'abandon']), 'workstream act:pause act:sync launch:run launch:abandon')
  assert.equal(contextValue('task', ['unclaim']), 'task act:unclaim')
  assert.equal(contextValue('workstream', [], []), 'workstream')
  // The same regexes package.json's menus use.
  const has = (value: string, word: string) => new RegExp(`(^| )${word}( |$)`).test(value)
  const value = 'workstream act:pause launch:run launch:abandon'
  assert.ok(has(value, 'act:pause'))
  assert.ok(!has(value, 'act:resume'))
  assert.ok(has(value, 'launch:run'))
  assert.ok(has(value, 'launch:abandon'))
  assert.ok(!has(value, 'launch:coordinate'))
  assert.ok(!has('workstream act:pause', 'launch:run'))
})

test('the confirm box names the commit line and branch, and says when the view is behind', () => {
  assert.equal(commitLine('alpha', 'unclaim', 'A-1'), 'alpha: unclaim A-1')
  const plain = confirmText('alpha', 'pause', undefined, 'main', false)
  assert.equal(plain.message, 'Pause alpha?')
  assert.equal(plain.detail, 'This commits "alpha: pause" on main.')
  const behind = confirmText('alpha', 'unclaim', 'A-1', 'develop', true)
  assert.equal(behind.message, 'Unclaim A-1?')
  assert.match(behind.detail, /^This commits "alpha: unclaim A-1" on develop\.\n\nThis has changed since the tree drew it/)
})

test('moved compares the pinned revisions with the latest for that workstream', () => {
  const pinned = { registry: 'r1', tasks: { alpha: 't1', beta: 'b1' } }
  assert.equal(moved(pinned, undefined, 'alpha'), false)
  assert.equal(moved(pinned, { registry: 'r1', tasks: { alpha: 't1', beta: 'b2' } }, 'alpha'), false)
  assert.equal(moved(pinned, { registry: 'r2', tasks: { alpha: 't1' } }, 'alpha'), true)
  assert.equal(moved(pinned, { registry: 'r1', tasks: { alpha: 't2' } }, 'alpha'), true)
})

test('nodes keep the revisions they were drawn from and the offers of their snapshot', () => {
  const snap: Snapshot = {
    snapshotVersion: 1, revisions: { registry: 'R', tasks: { alpha: 'T' } },
    registry: [row('alpha', 'active', ['pause'], ['run', 'close']), row('beta', 'abandoned')], health: [stale],
  }
  const [alpha] = listRows('/p', snap, false)
  assert.deepEqual([alpha.writes, alpha.launches, alpha.revisions], [['pause'], ['run', 'close'], snap.revisions])
  const beta = listRows('/p', snap, true)[1]
  assert.deepEqual([beta.writes, beta.launches], [[], []])
  const task = (id: string): Task => ({ id, phase: 1, priority: 10, status: 'in-progress', blockedBy: [] })
  const ws: WsSnapshot = { ...snap, revisions: { registry: 'R2', tasks: { alpha: 'T2' } }, tasks: [task('A-1'), task('A-2')] }
  const tasks = taskRows('/p', 'alpha', ws, Date.now())
  assert.deepEqual(tasks.map(t => [t.task.id, t.writes, t.revisions.registry]), [['A-1', ['unclaim'], 'R2'], ['A-2', [], 'R2']])
})

test('the prompt is the snapshot offer\'s text, with the reason appended when it asks one', () => {
  const run = { kind: 'run', prompt: 'Run alpha.' }
  const abandon = { kind: 'abandon', prompt: 'Abandon alpha: ', ask: 'reason' }
  assert.equal(offerPrompt(run), 'Run alpha.')
  assert.equal(offerPrompt(run, 'ignored'), 'Run alpha.')
  assert.equal(offerPrompt(abandon, 'it\'s "done" elsewhere; $(rm -rf)'), 'Abandon alpha: it\'s "done" elsewhere; $(rm -rf)')
  assert.deepEqual([run, abandon, { kind: 'close', prompt: 'x', ask: 'other' }].map(needsReason), [false, true, false])
})

test('the terminal runs the agent argv with the prompt as one last argument, at the root', () => {
  const prompt = 'Use the ws-coordinate skill to abandon workstream alpha: "quotes" & $HOME'
  assert.deepEqual(terminalOptions(['agent', '--flag'], prompt, '/p', 'Workstreams: Abandon alpha'), {
    name: 'Workstreams: Abandon alpha', shellPath: 'agent', shellArgs: ['--flag', prompt], cwd: '/p',
  })
  assert.deepEqual(terminalOptions(['agent'], prompt, '/p', 'n')?.shellArgs, [prompt])
  assert.equal(terminalOptions([], prompt, '/p', 'n'), undefined)
  assert.equal(terminalOptions(undefined, prompt, '/p', 'n'), undefined)
  assert.equal(terminalOptions([''], prompt, '/p', 'n'), undefined)
})
