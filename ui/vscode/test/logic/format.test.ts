// The helpers ported from the web UI's logic.js, with the cases ui/web/tests/logic.test.mjs uses.
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  ageOf, badgesOf, blockedLine, errorCount, gateSummary, lanes, rangeLine, splitRows, type Task, waveLine,
} from '../../src/logic/format.ts'

const task = (id: string, fields: Partial<Task> = {}): Task => ({ id, phase: 1, priority: 10, status: 'todo', blockedBy: [], mode: 'background', ...fields })

test('the task screen says why a task is blocked, and nothing when no reason is recorded', () => {
  assert.equal(blockedLine(task('a', { status: 'blocked', blockedReason: 'no key' })), 'Blocked: no key')
  assert.equal(blockedLine(task('b', { status: 'blocked', blockedReason: null, title: 'The title' })), '')
  assert.equal(blockedLine(task('c')), '')
})

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
  const texts = (t: Task) => badgesOf(t, tasks, { ids: ['C'] }, now).map(b => b.text)
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

test('errors are counted per workstream, warnings left out', () => {
  const health = [
    { level: 'error', workstream: 'w' }, { level: 'warning', workstream: 'w' }, { level: 'error', workstream: null }, { level: 'error', workstream: 'w' },
  ]
  assert.equal(errorCount(health, 'w'), 2)
  assert.equal(errorCount(health, 'x'), 0)
})

test('gates add up to one line', () => {
  const gate = (ok: boolean, blocking: boolean) => ({ ok, blocking })
  assert.equal(gateSummary([gate(true, true)]).kind, 'good')
  assert.deepEqual(gateSummary([gate(false, false), gate(true, true)]), { kind: 'warn', text: 'Would land, with 1 warning' })
  assert.deepEqual(gateSummary([gate(false, true), gate(false, true), gate(false, false)]), { kind: 'bad', text: '2 checks would stop this landing' })
})

test('range lines read plainly', () => {
  const sha = 'a'.repeat(40)
  assert.equal(rangeLine({ kind: 'none' }), 'No diff: this task has no commit or branch yet.')
  assert.equal(rangeLine({ kind: 'branch', from: sha, to: 'task/x' }), `branch: ${'a'.repeat(10)}...task/x`)
  assert.equal(rangeLine({ kind: 'merge', from: `${sha}^1`, to: sha }), `merge: ${'a'.repeat(10)}^1..${'a'.repeat(10)}`)
})
