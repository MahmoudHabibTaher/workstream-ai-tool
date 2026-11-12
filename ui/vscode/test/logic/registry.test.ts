import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import { makeCli, type Ran } from '../../src/cli.ts'
import { debounce, type Timers } from '../../src/logic/debounce.ts'
import type { Task } from '../../src/logic/format.ts'
import { activeWorkstream, statusText, type WsSnapshot } from '../../src/logic/registry.ts'
import { Store } from '../../src/logic/store.ts'

const base = { snapshotVersion: 1, revisions: { registry: 'r', tasks: {} } }
const SNAP: Snapshot = {
  ...base,
  registry: [
    { id: 'old', status: 'done', progress: { done: 2, total: 2 } },
    { id: 'alpha', title: 'Alpha', summary: 'the [x](command:evil) <b>sum</b>', status: 'active', progress: { done: 1, total: 3 } },
    { id: 'gone', status: 'abandoned' },
    { id: 'beta', status: 'paused', progress: { done: 0, total: 0 } },
  ],
  health: [{ level: 'error', workstream: 'alpha' }, { level: 'error', workstream: 'alpha' }, { level: 'warning', workstream: 'beta' }],
  refresh: [{ path: '/p/reg.json', recursive: false }, { path: '/p/ws/alpha', recursive: true }],
}
const t = (id: string, fields: Partial<Task> = {}): Task => ({ id, phase: 1, priority: 10, status: 'todo', blockedBy: [], ...fields })
const WS: WsSnapshot = {
  ...base,
  tasks: [t('A-3', { phase: 2, priority: 30, blockedBy: ['A-1'] }), t('A-2', { priority: 20, mode: 'foreground' }), t('A-1', { status: 'done', title: 'First' })],
  wave: { state: 'ready', phase: 1, ids: ['A-2'], leftovers: [] },
  paths: { plan: '/p/ws/alpha/PLAN.md', handoff: '/p/ws/alpha/session_handoff.md', evidence: {} },
}

test('the status bar names the first active workstream, its wave line and its errors', () => {
  const active = activeWorkstream(['/q', '/p'], { '/p': SNAP })
  assert.equal(active?.row.id, 'alpha')
  assert.equal(statusText('alpha', WS.wave, 2), 'alpha: Phase 1: 1 ready · 2 errors')
  assert.equal(statusText('alpha', undefined, 0), 'alpha')
  assert.equal(activeWorkstream(['/p'], { '/p': { ...base, registry: [{ id: 'b', status: 'paused' }] } }), undefined)
})

// Timers run by hand, so the test controls when time passes.
function fakeTimers() {
  let next = 0
  const due = new Map<number, () => void>()
  const timers: Timers = { set: fn => (due.set(++next, fn), next), clear: h => void due.delete(h as number) }
  const tick = async () => {
    const fns = [...due.values()]
    due.clear()
    for (const fn of fns) fn()
    await new Promise(r => setImmediate(r))
  }
  return { timers, tick, pending: () => due.size }
}

test('a burst of events makes one reload', async () => {
  const { timers, tick, pending } = fakeTimers()
  let runs = 0
  const d = debounce(async () => void runs++, 300, timers)
  d.poke(); d.poke(); d.poke()
  assert.equal(pending(), 1)
  await tick()
  assert.equal(runs, 1)
  await tick()
  assert.equal(runs, 1)
})

test('an event during a reload makes exactly one more', async () => {
  const { timers, tick } = fakeTimers()
  let runs = 0
  let release = () => {}
  const d = debounce(() => { runs++; return new Promise<void>(r => (release = r)) }, 300, timers)
  d.poke()
  await tick()
  d.poke(); d.poke()
  await tick()
  assert.equal(runs, 1)
  release()
  await new Promise(r => setImmediate(r))
  await tick()
  assert.equal(runs, 2)
  d.dispose()
  d.poke()
  await tick()
  assert.equal(runs, 2)
})

test('the store reads a workstream once per reload, and reload reads every root again', async () => {
  const calls: string[][] = []
  const cli = makeCli(['ws'], async argv => {
    calls.push(argv)
    return { exitCode: 0, stdout: JSON.stringify(argv.includes('-w') ? WS : SNAP), stderr: '' } satisfies Ran
  })
  const store = new Store(cli, { roots: ['/p'], snapshots: { '/p': SNAP }, errors: {} })
  let changes = 0
  store.onChange(() => changes++)
  await store.workstream('/p', 'alpha')
  await store.workstream('/p', 'alpha')
  assert.deepEqual(calls, [['ws', 'snapshot', '-w', 'alpha']])
  await store.reload()
  await store.workstream('/p', 'alpha')
  assert.deepEqual(calls.slice(1), [['ws', 'snapshot'], ['ws', 'snapshot', '-w', 'alpha']])
  assert.equal(changes, 1)
  assert.deepEqual(store.refreshPaths(), SNAP.refresh)
  store.setShowDone(true)
  assert.equal(changes, 2)
})

test('the store keeps the linked views\' selection across a reload, and a new workstream clears the task', async () => {
  const cli = makeCli(['ws'], async argv => ({ exitCode: 0, stdout: JSON.stringify(argv.includes('-w') ? WS : SNAP), stderr: '' }))
  const store = new Store(cli, { roots: ['/p'], snapshots: { '/p': SNAP }, errors: {} })
  let selects = 0
  let changes = 0
  store.onSelect(() => selects++)
  store.onChange(() => changes++)
  store.select('/p', 'alpha')
  assert.deepEqual([store.selected, store.selectedTask, selects], [{ root: '/p', ws: 'alpha' }, undefined, 1])
  store.select('/p', 'alpha')
  assert.equal(selects, 1)
  store.selectTask('/p', 'alpha', 'A-2')
  assert.deepEqual([store.selectedTask, selects], ['A-2', 2])
  await store.reload()
  assert.deepEqual([store.selected, store.selectedTask, changes], [{ root: '/p', ws: 'alpha' }, 'A-2', 1])
  store.select('/p', 'beta')
  assert.deepEqual([store.selected, store.selectedTask, selects], [{ root: '/p', ws: 'beta' }, undefined, 3])
  store.selectTask('/q', 'gamma', 'G-1')
  assert.deepEqual([store.selected, store.selectedTask, selects], [{ root: '/q', ws: 'gamma' }, 'G-1', 4])
  assert.equal(changes, 1)
})
