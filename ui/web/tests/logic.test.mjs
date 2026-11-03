// The page's pure helpers. `make test` runs these where Node exists and skips them where it
// doesn't; nothing that ships needs it.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  ageOf, badgesOf, commitLine, fileNote, findingsFor, gateSummary, hrefs, lanes, neighbourFile, neighbours, offers, parseDiff,
  parseRoute, percent, rangeLine, splitRows, statLine, statusActions, waveLine,
} from '../../../src/workstream/assets/web/logic.js'

const task = (id, fields) => ({ id, phase: 1, priority: 10, status: 'todo', blockedBy: [], mode: 'background', ...fields })

test('the wave line says what state the queue is in', () => {
  assert.equal(waveLine({ state: 'finished' }), 'Queue finished')
  assert.equal(waveLine({ state: 'stuck', open: ['a', 'b'] }), 'Stuck: 2 open, none actionable')
  assert.equal(waveLine({ state: 'ready', phase: 2, ids: ['a'], leftovers: [] }), 'Phase 2: 1 ready')
  assert.equal(waveLine({ state: 'ready', phase: 2, ids: ['a'], leftovers: ['z'] }), 'Phase 2: 1 ready · 1 left over')
  assert.equal(waveLine(undefined), '')
})

test('ages read in the largest sensible unit', () => {
  const now = Date.parse('2026-11-03T12:00:00Z')
  assert.equal(ageOf('2026-11-03T11:30:00Z', now), '30m')
  assert.equal(ageOf('2026-11-03T02:00:00Z', now), '10h')
  assert.equal(ageOf('2026-10-30T12:00:00Z', now), '4d')
  assert.equal(ageOf('2026-11-03T13:00:00Z', now), '0m')
})

test('badges come from the task and the wave', () => {
  const tasks = [task('A', { status: 'done' }), task('B', { blockedBy: ['A', 'C'] }), task('C', { status: 'in-progress', startedAt: '2026-11-03T11:00:00Z' })]
  const now = Date.parse('2026-11-03T12:00:00Z')
  const texts = t => badgesOf(t, tasks, { ids: ['C'] }, now).map(b => b.text)
  assert.deepEqual(texts(tasks[1]), ['waits on C'])
  assert.deepEqual(texts(tasks[2]), ['★ ready', 'claimed 1h'])
  assert.deepEqual(texts(task('D', { mode: 'foreground', needsUserDecision: true })), ['foreground', 'needs decision'])
})

test('lanes go by phase, then priority', () => {
  const found = lanes([task('B', { phase: 2 }), task('C', { priority: 20 }), task('A', { priority: 5 })])
  assert.deepEqual(found.map(l => [l.phase, l.tasks.map(t => t.id)]), [[1, ['A', 'C']], [2, ['B']]])
})

test('closed rows are split from open ones', () => {
  const { open, closed } = splitRows([{ status: 'active' }, { status: 'done' }, { status: 'paused' }, { status: 'abandoned' }])
  assert.deepEqual([open.length, closed.length], [2, 2])
})

test('only what a finding lists is offered', () => {
  const health = [
    { workstream: 'w', task: 'T', level: 'warning', actions: [{ action: 'unclaim', workstream: 'w', task: 'T' }] },
    { workstream: null, task: null, level: 'warning', actions: [] },
    { workstream: 'x', task: null, level: 'error', actions: [] },
  ]
  assert.equal(offers(health, 'w', 'unclaim', 'T'), true)
  assert.equal(offers(health, 'w', 'unclaim', 'U'), false)
  assert.equal(offers(health, 'x', 'unclaim', 'T'), false)
  assert.equal(findingsFor(health, 'w').length, 2)
})

test('a status allows the writes ws act does', () => {
  assert.deepEqual(statusActions('planned'), ['pause'])
  assert.deepEqual(statusActions('active'), ['pause'])
  assert.deepEqual(statusActions('paused'), ['resume'])
  assert.deepEqual(statusActions('done'), [])
  assert.deepEqual(statusActions('abandoned'), [])
})

test('a commit line names the workstream, action and task', () => {
  assert.equal(commitLine('w', 'pause', null), 'w: pause')
  assert.equal(commitLine('w', 'unclaim', 'T'), 'w: unclaim T')
})

test('percent stays in range', () => {
  assert.equal(percent(1, 4), 25)
  assert.equal(percent(0, 0), 0)
  assert.equal(percent(9, 4), 100)
})

test('every address parses back to its screen', () => {
  assert.deepEqual(parseRoute('#/'), { screen: 'registry' })
  assert.deepEqual(parseRoute(''), { screen: 'registry' })
  assert.deepEqual(parseRoute('#/nonsense'), { screen: 'registry' })
  assert.deepEqual(parseRoute(hrefs.queue()), { screen: 'queue' })
  assert.deepEqual(parseRoute(hrefs.health()), { screen: 'health' })
  assert.deepEqual(parseRoute(hrefs.budget()), { screen: 'budget' })
  assert.deepEqual(parseRoute(hrefs.lanes('a b')), { screen: 'lanes', ws: 'a b' })
  assert.deepEqual(parseRoute(hrefs.task('w', 'T-1')), { screen: 'task', ws: 'w', task: 'T-1' })
  assert.deepEqual(parseRoute(hrefs.doc('w', 'plan')), { screen: 'doc', ws: 'w', doc: 'plan' })
  assert.deepEqual(parseRoute(hrefs.doc('w', 'other')), { screen: 'lanes', ws: 'w' })
  assert.deepEqual(parseRoute(hrefs.review('w', 'T')), { screen: 'review', ws: 'w', task: 'T', file: null })
  assert.deepEqual(parseRoute(hrefs.review('w', 'T', 'src/a b/c.py')), { screen: 'review', ws: 'w', task: 'T', file: 'src/a b/c.py' })
})

test('a diff keeps its line numbers on each side', () => {
  const text = [
    'diff --git a/f b/f', 'index 1..2 100644', '--- a/f', '+++ b/f',
    '@@ -10,3 +10,3 @@ def f():', ' same', '-old', '+new', '\\ No newline at end of file',
    '@@ -50 +50,2 @@', ' tail', '+added', '',
  ].join('\n')
  const { header, hunks } = parseDiff(text)
  assert.equal(header.length, 4)
  assert.deepEqual(hunks[0].lines.map(l => [l.kind, l.old, l.new]), [
    ['ctx', 10, 10], ['del', 11, null], ['add', null, 11], ['meta', null, null],
  ])
  assert.deepEqual(hunks[1].lines.map(l => [l.kind, l.old, l.new]), [['ctx', 50, 50], ['add', null, 51]])
  assert.equal(hunks[0].header, '@@ -10,3 +10,3 @@ def f():')
})

test('a removed or added line that looks like a header stays a line', () => {
  const { hunks } = parseDiff('@@ -1,2 +1,2 @@\n--- not a header\n+++ nor this\n')
  assert.deepEqual(hunks[0].lines.map(l => l.kind), ['del', 'add'])
})

test('a diff with no hunks is only its header', () => {
  const { header, hunks } = parseDiff('diff --git a/x b/x\nBinary files a/x and b/x differ\n')
  assert.deepEqual([header.length, hunks.length], [2, 0])
  assert.equal(fileNote(header), 'binary, no text diff')
  assert.equal(parseDiff('').hunks.length, 0)
  assert.equal(parseDiff(null).hunks.length, 0)
})

test('the header says when a file came or went', () => {
  assert.equal(fileNote(['new file mode 100644']), 'new file')
  assert.equal(fileNote(['deleted file mode 100644']), 'deleted file')
  assert.equal(fileNote(['index 1..2']), null)
})

test('gates add up to one line', () => {
  const gate = (ok, blocking) => ({ ok, blocking })
  assert.equal(gateSummary([gate(true, true)]).kind, 'good')
  assert.deepEqual(gateSummary([gate(false, false), gate(true, true)]), { kind: 'warn', text: 'Would land, with 1 warning' })
  assert.deepEqual(gateSummary([gate(false, true), gate(false, true), gate(false, false)]), { kind: 'bad', text: '2 checks would stop this landing' })
})

test('range and stat lines read plainly', () => {
  const sha = 'a'.repeat(40)
  assert.equal(rangeLine({ kind: 'none' }), 'No diff: this task has no commit or branch yet.')
  assert.equal(rangeLine({ kind: 'branch', from: sha, to: 'task/x' }), `branch: ${'a'.repeat(10)}...task/x`)
  assert.equal(rangeLine({ kind: 'merge', from: `${sha}^1`, to: sha }), `merge: ${'a'.repeat(10)}^1..${'a'.repeat(10)}`)
  assert.equal(statLine({ added: 2, removed: 1 }), '+2 −1')
  assert.equal(statLine({ added: null, removed: null }), 'binary')
})

test('moving through the queue and the files stops at the ends', () => {
  const tasks = [{ workstream: 'w', task: 'A' }, { workstream: 'w', task: 'B' }, { workstream: 'x', task: 'A' }]
  assert.deepEqual(neighbours(tasks, 'w', 'B'), { previous: tasks[0], next: tasks[2], entry: tasks[1] })
  assert.deepEqual(neighbours(tasks, 'w', 'A').previous, null)
  assert.deepEqual(neighbours(tasks, 'z', 'A').entry, null)
  const files = [{ path: 'a' }, { path: 'b' }]
  assert.equal(neighbourFile(files, 'a', 1), 'b')
  assert.equal(neighbourFile(files, 'b', 1), null)
  assert.equal(neighbourFile(files, 'a', -1), null)
})
