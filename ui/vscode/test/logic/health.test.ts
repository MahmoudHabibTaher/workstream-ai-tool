// Health and Budget as data: grouping by level, what a finding offers, where its diagnostic goes,
// and the text each node shows.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import type { Snapshot } from '../../src/cli.ts'
import type { Finding } from '../../src/logic/format.ts'
import {
  type BudgetNode, budgetNodes, budgetShown, findingNodes, findingWrites, type HealthNode, healthNodes, healthShown, offerOf,
  quickFixTitle, tasksFileOf, workstreamsWithFindings,
} from '../../src/logic/health.ts'
import type { WsSnapshot } from '../../src/logic/registry.ts'

const revisions = { registry: 'r', tasks: { alpha: 't' } }
const stale: Finding = {
  kind: 'stale-claim', level: 'warning', workstream: 'alpha', task: 'A-1', message: 'A-1 has been in progress for 2 days',
  actions: [{ action: 'unclaim', workstream: 'alpha', task: 'A-1' }],
}
const broken: Finding = { kind: 'invalid-queue', level: 'error', workstream: 'beta', task: null, message: 'beta: bad queue', actions: [] }
const branch: Finding = { kind: 'wrong-branch', level: 'warning', workstream: null, task: null, message: 'not on main', actions: [] }
const snap = (health: Finding[], extra: Record<string, unknown> = {}): Snapshot => ({ snapshotVersion: 1, revisions, health, ...extra })
const labels = (nodes: HealthNode[]) => nodes.map(n => healthShown(n).label)

test('findings group into errors then warnings, in the CLI order, and none says so', () => {
  const nodes = healthNodes('/p', snap([stale, broken, branch]))
  assert.deepEqual(labels(nodes), ['Errors', 'Warnings'])
  assert.deepEqual(nodes.map(n => healthShown(n).description), ['1', '2'])
  const warnings = nodes[1] as Extract<HealthNode, { kind: 'level' }>
  assert.deepEqual(labels(warnings.findings), ['A-1 has been in progress for 2 days', 'not on main'])
  assert.deepEqual(labels(healthNodes('/p', snap([])))[0], 'Nothing to report.')
  assert.deepEqual(labels(healthNodes('/p', snap([], { git: { error: 'git failed' } }))), ['git failed', 'Nothing to report.'])
  assert.deepEqual(labels(healthNodes('/p', snap([{ level: 'note', workstream: null, message: 'fyi' }]))), ['note'])
})

test('a finding offers only what its actions list, and pins its snapshot', () => {
  const [node] = findingNodes('/p', snap([stale]))
  assert.deepEqual(node.writes, ['unclaim'])
  assert.deepEqual(node.revisions, revisions)
  assert.deepEqual(findingWrites(broken), [])
  assert.deepEqual(findingWrites({ ...stale, actions: [{ action: 'explode', workstream: 'alpha' }] }), [])
  assert.deepEqual(offerOf(stale, 'unclaim'), { ws: 'alpha', task: 'A-1' })
  assert.equal(offerOf(stale, 'pause'), undefined)
  assert.equal(quickFixTitle('unclaim', stale), 'Unclaim A-1')
  assert.equal(healthShown(node).description, 'stale-claim · alpha A-1')
})

test('diagnostics go to each named workstream\'s tasks file, as its own snapshot names it', () => {
  const nodes = findingNodes('/p', snap([stale, broken, branch]))
  assert.deepEqual(workstreamsWithFindings(nodes), ['alpha', 'beta'])
  // The watch order no longer matters: only paths.tasks names the file.
  const watch = ['/p/reg.json', '/p/alpha/handoff.md', '/p/alpha/tasks.json']
  const ws: WsSnapshot = { ...snap([]), watch, paths: { tasks: '/p/alpha/tasks.json', handoff: '/p/alpha/handoff.md' } }
  assert.equal(tasksFileOf(ws), '/p/alpha/tasks.json')
  assert.equal(tasksFileOf({ ...snap([]), watch, paths: { handoff: '/p/alpha/handoff.md' } }), undefined)
  assert.equal(tasksFileOf({ ...snap([]), watch }), undefined)
  assert.equal(tasksFileOf({ ...snap([]), paths: { tasks: null } }), undefined)
})

test('a budget row shows used against its limit, and says when it is over', () => {
  const nodes = budgetNodes('/p', [{ role: 'worker', tokens: 900, budget: 2500, ok: true }, { role: 'planner', tokens: 3100, budget: 3000, ok: false }])
  assert.deepEqual(nodes.map(n => [budgetShown(n).label, budgetShown(n).description]), [
    ['worker', '900 / 2,500 · 36%'], ['planner', '3,100 / 3,000 · 103% · over'],
  ])
  assert.deepEqual(budgetNodes('/p', []).map((n: BudgetNode) => budgetShown(n).label), ['No roles measured.'])
})
