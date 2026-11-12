import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import {
  filePath, graph, type GraphNode, graphLabel, listRows, overviewSections, type Section, taskLanes, taskRows, taskSections,
} from '../../src/logic/detail.ts'
import type { SnapTask, WsSnapshot } from '../../src/logic/registry.ts'

const NOW = Date.parse('2026-11-12T12:00:00Z')
const base = { snapshotVersion: 1, revisions: { registry: 'r', tasks: { alpha: 't' } } }
const SNAP: Snapshot = {
  ...base,
  registry: [
    { id: 'old', status: 'done', progress: { total: 2, done: 2 } },
    { id: 'alpha', title: 'Alpha', summary: 'the <b>sum</b>', status: 'active', progress: { total: 4, done: 1, 'in-progress': 1 }, dependsOn: ['old'],
      tier: 'standard', created: '2026-11-01', startedAt: '2026-11-02', baseCommit: 'abc123', notes: 'row notes', actions: ['pause'] },
  ],
  health: [{ level: 'error', workstream: 'alpha' }],
}
const t = (id: string, fields: Partial<SnapTask> = {}): SnapTask => (
  { id, phase: 1, priority: 10, status: 'todo', blockedBy: [], unblocks: [], waitingOn: [], ...fields }
)
const WS: WsSnapshot = {
  ...base,
  repoRoot: '/p',
  tasks: [
    t('A-1', { title: 'First', status: 'done', unblocks: ['A-2', 'A-3'], files: ['src/a.ts', '/abs/b.ts'] }),
    t('A-2', { priority: 20, status: 'in-progress', claimedBy: 'task/a-2', startedAt: '2026-11-12T10:00:00Z', blockedBy: ['A-1'], unblocks: ['A-4'],
      verifyCommands: [{ label: 'test', command: 'make test' }] }),
    t('A-3', { priority: 30, blockedBy: ['A-1', 'X-9'], unblocks: ['A-4'], summary: 'three', acceptanceText: ['[a](command:x)'],
      verifyCommands: [{ label: 'test', command: 'make test' }, { label: 'make lint', command: 'make lint' }], notes: 'note' }),
    t('A-4', { phase: 2, priority: 10, blockedBy: ['A-2', 'A-3'], waitingOn: ['A-2', 'A-3'], blockedReason: 'needs a call' }),
  ],
  wave: { state: 'ready', phase: 1, ids: ['A-3'], leftovers: [] },
  scope: { rule: 'Native views only', inScope: ['ui/vscode'], outOfScope: ['webviews'] },
  baseline: {
    keys: [{ key: 'lint', source: 'project', command: 'make lint', exit: 1, findings: 2, recordedAt: '2026-11-01', commit: '0123456789abcdef' },
      { key: 'test', source: 'workstream', command: 'test', exit: 0, findings: 1 }],
    errors: ['bad record'],
  },
  paths: { plan: '/p/ws/alpha/PLAN.md', decisions: '/p/ws/alpha/DECISIONS.md', evidence: {} },
}

const plain = (sections: Section[]) => sections.map(s => ({
  heading: s.heading, items: s.items.map(i => (i.kind === 'line' ? i.text : i.kind === 'task' ? `→${i.task}:${i.label}` : `file:${i.path}:${i.label}`)),
}))

test('list rows: open ones in registry order, closed ones with Show done, each with done/total, status, claims and errors', () => {
  assert.deepEqual(listRows('/p', SNAP, false).map(r => r.label), ['alpha'])
  const rows = listRows('/p', SNAP, true)
  assert.deepEqual(rows.map(r => [r.label, r.description]), [['alpha', '1/4 · active · 1 claimed · 1 error'], ['old', '2/2 · done']])
  assert.deepEqual(rows[0].tip, [{ lines: ['alpha: Alpha'] }, { lines: ['the <b>sum</b>'] }, { lines: ['1/4 · active · 1 claimed · 1 error'] }, { heading: 'Depends on', lines: ['old'] }])
  assert.deepEqual(rows[0].writes, ['pause'])
  assert.equal(rows[0].launch, true)
  assert.equal(rows[1].launch, false)
  assert.notEqual(rows[0].id, rows[1].id)
})

test('task rows: phase by phase in priority order, the description shows status, phase and the snapshot\'s waiting on', () => {
  const lanes = taskLanes('/p', 'alpha', WS, NOW)
  assert.deepEqual(lanes.map(l => [l.label, l.description, l.tasks.map(r => r.task.id)]), [['Phase 1', '1/3', ['A-1', 'A-2', 'A-3']], ['Phase 2', '0/1', ['A-4']]])
  const rows = taskRows('/p', 'alpha', WS, NOW)
  assert.deepEqual(rows.map(r => [r.label, r.description, r.badges]), [
    ['A-1 First', 'done · Phase 1', []],
    ['A-2', 'in-progress · Phase 1', ['claimed 2h']],
    // A-3's blockedBy names an unfinished X-9, but the snapshot says it waits on nothing: no badge says otherwise.
    ['A-3', 'todo · Phase 1', ['★ ready']],
    ['A-4', 'todo · Phase 2 · waiting on A-2, A-3', []],
  ])
  assert.equal(new Set(rows.map(r => r.id)).size, rows.length)
  assert.deepEqual(rows.map(r => r.id), taskRows('/p', 'alpha', WS, NOW).map(r => r.id))
})

test('task sections: depends on and unblocks jump to known tasks, files open under the repo root, then acceptance, verify and notes', () => {
  const rows = taskRows('/p', 'alpha', WS, NOW)
  const known = new Set(rows.map(r => r.task.id))
  const [a1, a2, a3, a4] = rows
  assert.deepEqual(plain(taskSections(a1, known, WS.repoRoot, NOW)), [
    { heading: undefined, items: ['A-1: First'] }, { heading: undefined, items: ['done · Phase 1'] },
    { heading: 'Unblocks', items: ['→A-2:A-2', '→A-3:A-3'] },
    { heading: 'Files', items: ['file:/p/src/a.ts:src/a.ts', 'file:/abs/b.ts:/abs/b.ts'] },
  ])
  assert.deepEqual(plain(taskSections(a2, known, WS.repoRoot, NOW)).slice(2), [
    { heading: 'Claim', items: ['task/a-2 · 2h ago'] }, { heading: 'Depends on', items: ['→A-1:A-1'] },
    { heading: 'Unblocks', items: ['→A-4:A-4'] }, { heading: 'Verify', items: ['test: make test'] },
  ])
  assert.deepEqual(plain(taskSections(a3, known, WS.repoRoot, NOW)), [
    { heading: undefined, items: ['A-3'] }, { heading: undefined, items: ['todo · Phase 1 · ★ ready'] },
    { heading: 'Summary', items: ['three'] },
    { heading: 'Depends on', items: ['→A-1:A-1', 'X-9'] }, { heading: 'Unblocks', items: ['→A-4:A-4'] },
    { heading: 'Acceptance', items: ['[a](command:x)'] }, { heading: 'Verify', items: ['test: make test', 'make lint'] },
    { heading: 'Notes', items: ['note'] },
  ])
  assert.deepEqual(plain(taskSections(a4, known, WS.repoRoot, NOW)).slice(1, 3), [
    { heading: undefined, items: ['todo · Phase 2 · waiting on A-2, A-3'] }, { heading: undefined, items: ['Blocked: needs a call'] },
  ])
  const ids = taskSections(a3, known, WS.repoRoot, NOW).flatMap(s => [s.id, ...s.items.map(i => i.id)])
  assert.equal(new Set(ids).size, ids.length)
  assert.deepEqual(ids, taskSections(a3, known, WS.repoRoot, NOW).flatMap(s => [s.id, ...s.items.map(i => i.id)]))
})

test('a file path is joined to the repo root unless it is absolute', () => {
  assert.equal(filePath('/p/', 'a/b.ts'), '/p/a/b.ts')
  assert.equal(filePath('/p', '/x/y'), '/x/y')
  assert.equal(filePath('C:\\r', 'C:\\x'), 'C:\\x')
  assert.equal(filePath(undefined, 'a'), 'a')
})

const tree = (nodes: GraphNode[]): unknown[] => nodes.map(n => {
  const { label, description } = graphLabel(n)
  return n.children.length ? [label, description, tree(n.children)] : [label, description]
})

test('the graph grows from unblocks, shows a task twice only as a leaf, and makes a cycle a root', () => {
  const rows = taskRows('/p', 'alpha', WS, NOW)
  assert.deepEqual(tree(graph(rows)), [
    ['A-1 First', 'done', [
      ['A-2', 'in-progress · claimed 2h', [['A-4', 'todo']]],
      ['A-3', 'todo · ★ ready', [['A-4', 'todo · shown above']]],
    ]],
  ])
  const all = (nodes: GraphNode[]): string[] => nodes.flatMap(n => [n.id, ...all(n.children)])
  assert.equal(new Set(all(graph(rows))).size, all(graph(rows)).length)
  const cycle: WsSnapshot = { ...base, tasks: [t('C-1', { blockedBy: ['C-2'], unblocks: ['C-2'] }), t('C-2', { priority: 20, blockedBy: ['C-1'], unblocks: ['C-1'] })] }
  assert.deepEqual(tree(graph(taskRows('/p', 'c', cycle, NOW))), [['C-1', 'todo', [['C-2', 'todo', [['C-1', 'todo · shown above']]]]]])
  assert.deepEqual(graph([]), [])
})

test('the overview: documents, the registry row, open claims, scope, verify commands and the baseline', () => {
  const row = listRows('/p', SNAP, false)[0].row
  assert.deepEqual(plain(overviewSections('/p', 'alpha', row, WS, NOW)), [
    { heading: 'Documents', items: ['file:/p/ws/alpha/PLAN.md:Plan', 'file:/p/ws/alpha/DECISIONS.md:Decisions'] },
    { heading: 'Registry', items: ['alpha: Alpha', 'the <b>sum</b>', 'active · standard tier', '1/4 done · 1 claimed', 'Depends on old',
      'created 2026-11-01 · started 2026-11-02', 'Base abc123', 'row notes'] },
    { heading: 'Open claims', items: ['→A-2:A-2 · task/a-2 · 2h ago'] },
    { heading: 'Scope', items: ['Native views only'] }, { heading: 'In scope', items: ['ui/vscode'] }, { heading: 'Out of scope', items: ['webviews'] },
    { heading: 'Verify', items: ['test: make test', 'make lint'] },
    { heading: 'Baseline', items: ['lint: make lint · project · exit 1 · 2 findings · 2026-11-01 · 0123456789', 'test · workstream · exit 0 · 1 finding', 'Error: bad record'] },
  ])
  const bare: WsSnapshot = { ...base }
  assert.deepEqual(plain(overviewSections('/p', 'b', undefined, bare, NOW)), [
    { heading: 'Open claims', items: ['None'] }, { heading: 'Baseline', items: ['None recorded'] },
  ])
})
