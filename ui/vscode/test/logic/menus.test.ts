// The menus package.json contributes, read as VS Code would: each `when` clause is evaluated
// against an item's contextValue (built by the same code the trees use) or the linked views'
// context keys. A menu item shows only where the snapshot offers it. Both runners start in the
// package's folder, so package.json is read from there.
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import { contextValue, openCommandOf, OPENS, pickedTarget } from '../../src/logic/actions.ts'
import { listRows, taskLanes } from '../../src/logic/detail.ts'
import type { WsSnapshot } from '../../src/logic/registry.ts'

type Entry = { command: string; when: string; group: string }
const pkg = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf8')) as {
  contributes: { menus: Record<string, Entry[]>; commands: { command: string }[]; viewsWelcome: { view: string; when?: string }[]; views: { workstreams: { id: string }[] } }
}
const menus = pkg.contributes.menus

// A when clause of `&&`-joined terms: `key`, `!key`, `key == value` and `key =~ /re/`.
function holds(when: string, keys: Record<string, string | boolean>): boolean {
  return when.split(' && ').every(term => {
    let m = /^(\S+) =~ \/(.*)\/$/.exec(term)
    if (m) return new RegExp(m[2]).test(String(keys[m[1]] ?? ''))
    m = /^(\S+) == (\S+)$/.exec(term)
    if (m) return String(keys[m[1]] ?? '') === m[2]
    if (term.startsWith('!')) return !keys[term.slice(1)]
    return Boolean(keys[term])
  })
}

const shown = (menu: string, keys: Record<string, string | boolean>) =>
  menus[menu].filter(e => holds(e.when, keys)).map(e => e.command.replace('workstreams.', ''))
const item = (view: string, viewItem: string) => shown('view/item/context', { view: `workstreams.${view}`, viewItem })

const revisions = { registry: 'r1', tasks: { alpha: 't1', beta: 't2', gamma: 't3' } }
const stale = { level: 'warning', workstream: 'alpha', task: 'A-1', actions: [{ action: 'unclaim', workstream: 'alpha', task: 'A-1' }] }
const snapshot = {
  revisions,
  registry: [
    { id: 'alpha', status: 'active', actions: ['pause'] },
    { id: 'beta', status: 'paused', actions: ['resume', 'sync'] },
    { id: 'gamma', status: 'done', actions: [] },
  ],
  health: [stale],
} as unknown as Snapshot
const wsSnapshot = {
  revisions,
  tasks: [
    { id: 'A-1', phase: 1, priority: 1, status: 'in-progress', blockedBy: [], startedAt: '2026-11-01T00:00:00Z' },
    { id: 'A-2', phase: 1, priority: 2, status: 'todo', blockedBy: [] },
  ],
  health: [stale],
} as unknown as WsSnapshot

const rows = Object.fromEntries(listRows('/p', snapshot, true).map(r => [r.row.id, r]))
const rowItem = (id: string) => contextValue('workstream', rows[id].writes, rows[id].launch)
const tasks = taskLanes('/p', 'alpha', wsSnapshot, Date.parse('2026-11-03T00:00:00Z')).flatMap(l => l.tasks)
const taskItem = (id: string) => {
  const t = tasks.find(r => r.task.id === id)
  assert.ok(t)
  return contextValue('task', t.writes)
}
const opens = OPENS.map(name => openCommandOf(name).replace('workstreams.', ''))

test('a workstream item shows its own writes, the launches while open, and the documents', () => {
  assert.deepEqual(item('list', rowItem('alpha')), ['run', 'coordinate', 'close', 'abandon', 'pause', ...opens])
  assert.deepEqual(item('list', rowItem('beta')), ['run', 'coordinate', 'close', 'abandon', 'resume', 'sync', ...opens])
  // A closed row offers no write and no launch; its documents still open.
  assert.deepEqual(item('list', rowItem('gamma')), opens)
})

test('a task item shows Unclaim only where a finding offers it', () => {
  assert.deepEqual(item('tasks', taskItem('A-1')), ['unclaim'])
  assert.deepEqual(item('tasks', taskItem('A-2')), [])
  assert.deepEqual(item('health', 'finding act:unclaim'), ['unclaim'])
  assert.deepEqual(item('health', 'finding'), [])
  // The same words in a view the write menus don't name show nothing (D009).
  assert.deepEqual(item('graph', 'graphTask'), [])
  assert.deepEqual(item('task', taskItem('A-1')), [])
})

test('a review file and the evidence show their Open entries, nothing else does', () => {
  assert.deepEqual(item('review', 'file'), ['openReviewFile'])
  assert.deepEqual(item('review', 'evidence'), ['openEvidence'])
  assert.deepEqual(item('review', 'entry'), [])
  assert.deepEqual(item('list', 'message'), [])
  assert.deepEqual(item('list', 'root'), [])
})

test('the linked views\' titles offer what the selected items offer', () => {
  for (const view of ['tasks', 'task', 'graph', 'overview']) {
    const title = (selectedItem: string, selectedTaskItem: string) =>
      shown('view/title', { view: `workstreams.${view}`, 'workstreams.selectedItem': selectedItem, 'workstreams.selectedTaskItem': selectedTaskItem })
    assert.deepEqual(title(rowItem('alpha'), taskItem('A-1')),
      ['refresh', 'run', 'coordinate', 'close', 'abandon', 'pause', 'unclaim', ...opens], view)
    assert.deepEqual(title(rowItem('alpha'), taskItem('A-2')), ['refresh', 'run', 'coordinate', 'close', 'abandon', 'pause', ...opens], view)
    assert.deepEqual(title(rowItem('gamma'), ''), ['refresh', ...opens], view)
    // Nothing drawn for the selection: Refresh only.
    assert.deepEqual(title('', ''), ['refresh'], view)
  }
  // The other views' titles never act on the selection.
  for (const view of ['list', 'review', 'health', 'budget']) {
    const got = shown('view/title', { view: `workstreams.${view}`, 'workstreams.selectedItem': rowItem('alpha'), 'workstreams.selectedTaskItem': taskItem('A-1') })
    assert.deepEqual(got.filter(c => c !== 'showDone' && c !== 'hideDone'), ['refresh'], view)
  }
})

test('a title write goes to the picked item, which carries the drawn revisions', () => {
  const picked = { workstream: rows.alpha, task: tasks[0] }
  assert.equal(pickedTarget('pause', picked), rows.alpha)
  assert.equal(pickedTarget('unclaim', picked), tasks[0])
  assert.deepEqual(rows.alpha.revisions, revisions)
  assert.deepEqual(tasks[0].revisions, revisions)
  assert.equal(pickedTarget('unclaim', { workstream: rows.alpha }), undefined)
})

test('the menus group Run, Workstream, Task and Open, and every command exists and stays out of the palette', () => {
  const known = new Set(pkg.contributes.commands.map(c => c.command))
  const hidden = new Set(menus.commandPalette.filter(e => e.when === 'false').map(e => e.command))
  const group = (command: string) => {
    const n = command.replace('workstreams.', '')
    if (['run', 'coordinate', 'close', 'abandon'].includes(n)) return '1_run'
    if (['pause', 'resume', 'sync'].includes(n)) return '2_workstream'
    if (n === 'unclaim') return '3_task'
    return '4_open'
  }
  for (const entry of [...menus['view/item/context'], ...menus['view/title']]) {
    assert.ok(known.has(entry.command), entry.command)
    if (entry.command === 'workstreams.refresh' || entry.command.endsWith('Done')) continue
    assert.ok(hidden.has(entry.command), entry.command)
    assert.equal(entry.group.split('@')[0], group(entry.command), entry.command)
  }
})

test('every view has a welcome', () => {
  const welcomed = new Set(pkg.contributes.viewsWelcome.map(w => w.view))
  assert.deepEqual(pkg.contributes.views.workstreams.map(v => v.id).filter(id => !welcomed.has(id)), [])
})
