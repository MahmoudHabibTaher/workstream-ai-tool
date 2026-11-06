// The Review queue as data: grouping, what sits under a task, and the text each node shows.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  binaryLine, diffTitle, type Entry, entryChildren, fileChildren, gateChildren, groupChildren, itemChildren, queueNodes,
  type Review, type ReviewNode, reviewShown,
} from '../../src/logic/review.ts'

const entry = (task: string, state: string, fields: Partial<Entry> = {}): Entry =>
  ({ workstream: 'alpha', task, title: `Title ${task}`, state, files: 2, added: 3, removed: 1, hasEvidence: true, ...fields })

const sha = 'b'.repeat(40)
const review = (fields: Partial<Review> = {}): Review => ({
  task: 'T1', evidence: null, range: { kind: 'branch', from: sha, to: 'task/t1' },
  files: [{ path: 'a.txt', added: 1, removed: 0 }, { path: 'img.png', added: null, removed: null }],
  checks: {
    state: 'branch', commit: null, evidenceText: '# T1 evidence', evidenceStatus: 'done', reason: '',
    gates: [{ name: 'evidence', ok: true, blocking: true }, { name: 'verify', ok: false, blocking: false, detail: 'none ran' }],
    items: [{ n: 1, item: 'it works', proof: '`ok` printed' }, { n: 2, item: 'it is fast', proof: '' }],
  },
  ...fields,
})

test('the queue lists branch work before landed work, whatever order it came in', () => {
  const nodes = queueNodes('/p', { tasks: [entry('L1', 'landed'), entry('B1', 'branch'), entry('L2', 'landed'), entry('B2', 'branch')] })
  assert.deepEqual(nodes.map(n => reviewShown(n).label), ['On a branch', 'Landed'])
  const tasks = nodes.map(n => groupChildren(n as Extract<ReviewNode, { kind: 'group' }>).map(c => (c as Extract<ReviewNode, { kind: 'entry' }>).entry.task))
  assert.deepEqual(tasks, [['B1', 'B2'], ['L1', 'L2']])
  assert.deepEqual(nodes.map(n => reviewShown(n).description), ['2', '2'])
})

test('an empty group is left out, and an empty queue says so', () => {
  assert.deepEqual(queueNodes('/p', { tasks: [entry('L1', 'landed')] }).map(n => reviewShown(n).label), ['Landed'])
  assert.deepEqual(queueNodes('/p', { tasks: [] }).map(n => reviewShown(n).label), ['Nothing to review.'])
})

test('a queue row names its workstream, its diffstat, and missing evidence', () => {
  const [group] = queueNodes('/p', { tasks: [entry('B1', 'branch', { hasEvidence: false, files: 1 })] })
  const [row] = groupChildren(group as Extract<ReviewNode, { kind: 'group' }>)
  assert.deepEqual(reviewShown(row), {
    label: 'B1 Title B1', description: 'alpha · 1 file +3 −1 · no evidence', collapsible: true,
    tip: [{ lines: ['B1 Title B1', 'alpha · 1 file +3 −1 · no evidence'] }],
  })
})

const rowOf = (e: Entry) => ({ kind: 'entry' as const, id: 'x', root: '/p', entry: e })

test('under a branch task: range, gate summary, acceptance with proof, evidence, files', () => {
  const nodes = entryChildren(rowOf(entry('T1', 'branch')), review())
  assert.deepEqual(nodes.map(n => n.kind), ['message', 'gates', 'items', 'evidence', 'files'])
  assert.deepEqual(nodes.map(n => reviewShown(n).label), [
    `branch: ${'b'.repeat(10)}...task/t1`, 'Would land, with 1 warning', 'Acceptance and proof', 'Evidence', 'Files',
  ])
  const gates = gateChildren(nodes[1] as Extract<ReviewNode, { kind: 'gates' }>)
  assert.deepEqual(gates.map(g => [reviewShown(g).label, reviewShown(g).description]), [['evidence', undefined], ['verify', 'none ran']])
  const items = itemChildren(nodes[2] as Extract<ReviewNode, { kind: 'items' }>)
  assert.equal(reviewShown(nodes[2]).description, '1/2 quoted')
  assert.deepEqual(items.map(i => [reviewShown(i).label, reviewShown(i).description]), [['1. it works', '`ok` printed'], ['2. it is fast', 'Nothing quoted.']])
  assert.deepEqual(reviewShown(items[1]).tip, [{ heading: 'Acceptance', lines: ['it is fast'] }, { heading: 'Proof', lines: ['Nothing quoted.'] }])
  assert.equal((nodes[3] as Extract<ReviewNode, { kind: 'evidence' }>).onBranch, true)
  const files = fileChildren(nodes[4] as Extract<ReviewNode, { kind: 'files' }>)
  assert.deepEqual(files.map(f => [reviewShown(f).label, reviewShown(f).description]), [['a.txt', '+1 −0'], ['img.png', 'binary']])
})

test('a landed task says its gates ran when it landed; a blocked one says why', () => {
  const landed = review({ range: { kind: 'merge', from: `${sha}^1`, to: sha }, evidence: '/p/ws/evidence/T1.md' })
  landed.checks = { ...landed.checks!, state: 'landed', commit: sha, gates: [], evidenceStatus: 'blocked', reason: 'no key' }
  const nodes = entryChildren(rowOf(entry('T1', 'landed')), landed)
  assert.deepEqual(nodes.map(n => reviewShown(n).label).slice(0, 3), [
    `merge: ${'b'.repeat(10)}^1..${'b'.repeat(10)}`, `Landed as ${'b'.repeat(10)}. Its gates ran when it landed.`, 'Blocked: no key',
  ])
  const evidence = nodes.find(n => n.kind === 'evidence') as Extract<ReviewNode, { kind: 'evidence' }>
  assert.deepEqual([evidence.onBranch, evidence.path], [false, '/p/ws/evidence/T1.md'])
})

test('no evidence, no items and a git error each say so', () => {
  const bare = review({ files: [], error: 'git diff: bad revision' })
  bare.checks = { ...bare.checks!, evidenceText: null, items: [] }
  assert.deepEqual(entryChildren(rowOf(entry('T1', 'branch')), bare).map(n => reviewShown(n).label), [
    `branch: ${'b'.repeat(10)}...task/t1`, 'git diff: bad revision', 'Would land, with 1 warning', 'This task lists no acceptance items.', 'No evidence file yet.',
  ])
})

test('a diff is titled by its path and both revisions; a binary file says it opens nothing', () => {
  assert.equal(diffTitle('a.txt', 'T1', 'c'.repeat(40), 'd'.repeat(40)), `a.txt (T1: ${'c'.repeat(10)} ↔ ${'d'.repeat(10)})`)
  assert.equal(binaryLine('img.png'), 'img.png is binary, so no diff opens.')
})
