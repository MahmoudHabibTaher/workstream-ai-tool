import assert from 'node:assert/strict'
import { test } from 'node:test'

import { execRun, loadBudget, loadQueue, loadReview, loadShow, loadSnapshot, makeCli, type Ran, resolveRoots, runAct, SETTING } from '../../src/cli.ts'
import { start } from '../../src/logic/start.ts'

type Call = { argv: string[]; cwd: string }

// A stub `ws`: answers by the first argument after the command, and records each call.
function stub(answers: Record<string, Ran | ((cwd: string) => Ran)>, command = ['ws']) {
  const calls: Call[] = []
  const cli = makeCli(command, async (argv, cwd) => {
    calls.push({ argv, cwd })
    const answer = answers[argv[command.length]] ?? { exitCode: 2, stdout: '', stderr: 'unknown' }
    return typeof answer === 'function' ? answer(cwd) : answer
  })
  return { cli, calls }
}

const ok = (stdout: string): Ran => ({ exitCode: 0, stdout, stderr: '' })
const SNAP = JSON.stringify({ snapshotVersion: 1, revisions: { registry: 'r1', tasks: { alpha: 't1' } } })
const MISSING: Ran = { exitCode: 127, stdout: '', stderr: '', missing: true }

test('the configured argv comes first in every call', async () => {
  const { cli, calls } = stub({ root: ok('/p\n') }, ['python3', '-B', '-m', 'workstream'])
  await resolveRoots(cli, ['/p/sub'])
  assert.deepEqual(calls, [{ argv: ['python3', '-B', '-m', 'workstream', 'root'], cwd: '/p/sub' }])
})

test('an empty setting falls back to ws', () => {
  assert.deepEqual(makeCli([]).command, ['ws'])
})

test('roots are found per folder and deduplicated', async () => {
  const { cli } = stub({ root: cwd => (cwd === '/elsewhere' ? { exitCode: 1, stdout: '', stderr: 'no' } : ok('/p\n')) })
  assert.deepEqual(await resolveRoots(cli, ['/p', '/p/worktree', '/elsewhere']), { roots: ['/p'] })
})

test('a missing ws names the setting, and nothing else runs', async () => {
  const { cli, calls } = stub({ root: MISSING, snapshot: ok(SNAP) })
  const started = await start(cli, ['/a', '/b'])
  assert.equal(started.message?.level, 'error')
  assert.match(started.message?.text ?? '', new RegExp(SETTING.replace('.', '\\.')))
  assert.deepEqual(calls.map(c => c.argv), [['ws', 'root']])
  assert.deepEqual(started.roots, [])
})

test('a folder that is not a project says so, and nothing else runs', async () => {
  const { cli, calls } = stub({ root: { exitCode: 1, stdout: '', stderr: 'not a project' }, snapshot: ok(SNAP) })
  const started = await start(cli, ['/plain'])
  assert.deepEqual(started.message, { level: 'info', text: '/plain is not a workstream project (`ws init` sets one up); nothing opened.' })
  assert.deepEqual(calls.map(c => c.argv), [['ws', 'root']])
})

test('a project loads its snapshot from its root', async () => {
  const { cli, calls } = stub({ root: ok('/p\n'), snapshot: ok(SNAP) })
  const started = await start(cli, ['/p/worktree'])
  assert.equal(started.message, undefined)
  assert.deepEqual(started.roots, ['/p'])
  assert.equal(started.snapshots['/p'].revisions.registry, 'r1')
  assert.deepEqual(calls[1], { argv: ['ws', 'snapshot'], cwd: '/p' })
})

test('the snapshot version is checked', async () => {
  const { cli } = stub({ snapshot: ok(JSON.stringify({ snapshotVersion: 2 })) })
  assert.deepEqual(await loadSnapshot(cli, '/p'), { error: 'snapshot version 2; the extension reads 1' })
})

test('a failed or garbled snapshot is an error, not a throw', async () => {
  assert.deepEqual(await loadSnapshot(stub({ snapshot: { exitCode: 1, stdout: '', stderr: 'boom\n' } }).cli, '/p'), { error: 'boom' })
  assert.deepEqual(await loadSnapshot(stub({ snapshot: ok('nope') }).cli, '/p'), { error: 'snapshot printed no JSON' })
  assert.match((await loadSnapshot(stub({ snapshot: MISSING }).cli, '/p')).error ?? '', /workstreams\.wsCommand/)
})

test('the snapshot of one workstream', async () => {
  const { cli, calls } = stub({ snapshot: ok(SNAP) })
  await loadSnapshot(cli, '/p', 'alpha')
  assert.deepEqual(calls[0].argv, ['ws', 'snapshot', '-w', 'alpha'])
})

test('review, queue and budget argv', async () => {
  const { cli, calls } = stub({ review: ok('{}'), audit: ok('[]') })
  await loadReview(cli, '/p', 'alpha', 'T1')
  await loadReview(cli, '/p', 'alpha', 'T1', { checks: true })
  await loadReview(cli, '/p', 'alpha', 'T1', { file: 'a b.txt' })
  await loadShow(cli, '/p', 'alpha', 'T1', 'a b.txt', 'old')
  await loadQueue(cli, '/p')
  await loadBudget(cli, '/p')
  assert.deepEqual(calls.map(c => c.argv), [
    ['ws', 'review', 'T1', '-w', 'alpha'],
    ['ws', 'review', 'T1', '-w', 'alpha', '--checks'],
    ['ws', 'review', 'T1', '-w', 'alpha', '--file', 'a b.txt'],
    ['ws', 'review', 'T1', '-w', 'alpha', '--show', 'a b.txt', '--side', 'old'],
    ['ws', 'review', '--queue'],
    ['ws', 'audit', 'context', '--json'],
  ])
  assert.ok(calls.every(c => c.cwd === '/p'))
})

test('act passes the revisions it was given, and a refusal comes back as given', async () => {
  const { cli, calls } = stub({ act: { exitCode: 1, stdout: '', stderr: 'stale: the registry changed\n' } })
  const revisions = { registry: 'r1', tasks: { alpha: 't1' } }
  const got = await runAct(cli, '/p', 'alpha', { action: 'unclaim', task: 'T1' }, revisions)
  assert.deepEqual(got, { line: 'stale: the registry changed', refused: true })
  await runAct(cli, '/p', 'beta', { action: 'pause' }, revisions)
  assert.deepEqual(calls.map(c => c.argv), [
    ['ws', 'act', 'unclaim', '-w', 'alpha', '--task', 'T1', '--expect-registry', 'r1', '--expect-tasks', 't1'],
    ['ws', 'act', 'pause', '-w', 'beta', '--expect-registry', 'r1'],
  ])
})

test('execRun reports a missing program, an exit code, and never uses a shell', async () => {
  assert.equal((await execRun(['no-such-ws-program-here'], '/')).missing, true)
  const failed = await execRun([process.execPath, '-e', 'process.stderr.write("x"); process.exit(3)'], '/')
  assert.deepEqual([failed.exitCode, failed.stderr, failed.missing], [3, 'x', undefined])
  const literal = await execRun([process.execPath, '-e', 'console.log(process.argv[1])', '$(echo hi); `x`'], '/')
  assert.equal(literal.stdout.trim(), '$(echo hi); `x`')
})

test('execRun turns off git optional locks, so a read never rewrites the index', async () => {
  const ran = await execRun([process.execPath, '-e', 'console.log(process.env.GIT_OPTIONAL_LOCKS)'], '/')
  assert.equal(ran.stdout.trim(), '0')
})
