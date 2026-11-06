import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import { commitLine, confirmText, contextValue, launches, moved, rowWrites, taskWrites } from '../../src/logic/actions.ts'
import type { Finding, Row, Task } from '../../src/logic/format.ts'
import { needsReason, promptText, terminalOptions, WHY } from '../../src/logic/launch.ts'
import { type Node, phaseChildren, workstreamChildren, workstreams, type WsSnapshot } from '../../src/logic/registry.ts'

const row = (id: string, status: string, actions: string[] = []): Row => ({ id, status, actions })
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

test('launches are offered on open workstreams only', () => {
  assert.equal(launches(row('a', 'active')), true)
  assert.equal(launches(row('a', 'paused')), true)
  assert.equal(launches(row('a', 'planned')), true)
  assert.equal(launches(row('a', 'done')), false)
  assert.equal(launches(row('a', 'abandoned')), false)
})

test('the contextValue names each offer as a word the menus match', () => {
  assert.equal(contextValue('workstream', ['pause', 'sync'], true), 'workstream act:pause act:sync launch')
  assert.equal(contextValue('task', ['unclaim']), 'task act:unclaim')
  assert.equal(contextValue('workstream', [], false), 'workstream')
  // The same regexes package.json's menus use.
  const has = (value: string, word: string) => new RegExp(`(^| )${word}( |$)`).test(value)
  assert.ok(has('workstream act:pause launch', 'act:pause'))
  assert.ok(!has('workstream act:pause launch', 'act:resume'))
  assert.ok(has('workstream act:pause launch', 'launch'))
  assert.ok(!has('workstream act:pause', 'launch'))
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
    registry: [row('alpha', 'active', ['pause']), row('beta', 'abandoned')], health: [stale],
  }
  const [alpha] = workstreams('/p', snap, false) as Extract<Node, { kind: 'workstream' }>[]
  assert.deepEqual([alpha.writes, alpha.launch, alpha.revisions], [['pause'], true, snap.revisions])
  const beta = workstreams('/p', snap, true)[1] as Extract<Node, { kind: 'workstream' }>
  assert.deepEqual([beta.writes, beta.launch], [[], false])
  const task = (id: string): Task => ({ id, phase: 1, priority: 10, status: 'in-progress', blockedBy: [] })
  const ws: WsSnapshot = { ...snap, revisions: { registry: 'R2', tasks: { alpha: 'T2' } }, tasks: [task('A-1'), task('A-2')] }
  const phase = workstreamChildren('/p', 'alpha', ws).find(n => n.kind === 'phase') as Extract<Node, { kind: 'phase' }>
  const tasks = phaseChildren(phase, Date.now()) as Extract<Node, { kind: 'task' }>[]
  assert.deepEqual(tasks.map(t => [t.task.id, t.writes, t.revisions.registry]), [['A-1', ['unclaim'], 'R2'], ['A-2', [], 'R2']])
})

test('one prompt table, the web UI text, with the reason filled into abandon', () => {
  assert.equal(promptText('run', 'alpha'), 'Use the ws-run skill to run workstream alpha.')
  assert.equal(promptText('coordinate', 'alpha'), 'Use the ws-coordinate skill on workstream alpha.')
  assert.equal(promptText('close', 'alpha'), 'Use the ws-coordinate skill to close workstream alpha.')
  assert.equal(promptText('abandon', 'alpha'), `Use the ws-coordinate skill to abandon workstream alpha: ${WHY}`)
  assert.equal(promptText('abandon', 'alpha', 'it\'s "done" elsewhere; $(rm -rf)'), 'Use the ws-coordinate skill to abandon workstream alpha: it\'s "done" elsewhere; $(rm -rf)')
  assert.deepEqual(['run', 'coordinate', 'close', 'abandon'].map(k => needsReason(k as 'run')), [false, false, false, true])
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
