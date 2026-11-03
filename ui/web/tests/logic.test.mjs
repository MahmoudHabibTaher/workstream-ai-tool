// The page's pure helpers. `make test` runs these where Node exists and skips them where it
// doesn't; nothing that ships needs it.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  ageOf, badgesOf, commitLine, findingsFor, hrefs, lanes, offers, parseRoute, percent, splitRows, statusActions, waveLine,
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
