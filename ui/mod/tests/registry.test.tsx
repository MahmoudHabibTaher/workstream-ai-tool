import { expect, mock, test } from 'claude-code/testing'

const ROOT = '/repo'
const SURFACES = ['terminal', 'desktop', 'vscode', 'mobile'] as const

const PANE = {
  plugin: 'ws-pane',
  component: 'Pane',
  requestId: 'ws-pane',
  props: {
    title: 'Workstreams',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

function row(id: string, status: string, done: number, total: number, dependsOn: string[] = []) {
  const progress = { total, todo: total - done, 'in-progress': 0, blocked: 0, done, deferred: 0 }
  return { id, title: id, summary: '', status, dependsOn, progress, progressStale: false }
}

const SNAPSHOT = {
  snapshotVersion: 1,
  repoRoot: ROOT,
  integrationBranch: 'trunk',
  registry: [
    row('old_review', 'done', 4, 4),
    row('workstream_pane', 'active', 3, 8, ['workstream_bookkeeping']),
    row('enrichment_matching', 'planned', 0, 24),
  ],
  watch: [`${ROOT}/ws.json`],
  revisions: { registry: 'r', tasks: {} },
  health: [
    { kind: 'invalid', level: 'error', workstream: 'enrichment_matching', task: null, message: 'bad', actions: [] },
  ],
  git: { branch: 'trunk' },
}

type Calls = { argv: string[][]; cwd: (string | undefined)[]; opened: number }

// Stands for the engine beneath the mod: `ws root` answers ROOT inside a project, and
// `ws snapshot` prints SNAPSHOT.
function engine(on: any, inProject = true, hasWs = true): Calls {
  const calls: Calls = { argv: [], cwd: [], opened: 0 }
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'ws-pane' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => {
    calls.opened += 1
    return { value: { isPlaced: true } }
  })
  on('process.run', (_: unknown, e: { argv: string[]; init?: { cwd?: string } }) => {
    calls.argv.push([...e.argv])
    calls.cwd.push(e.init?.cwd)
    if (!hasWs) throw new Error('spawn ws ENOENT')
    if (e.argv[1] === 'root' && !inProject) {
      return { value: { exitCode: 1, stdout: '', stderr: 'not a project', isStdoutTruncated: false, isStderrTruncated: false } }
    }
    const stdout = e.argv[1] === 'root' ? `${ROOT}\n` : JSON.stringify(SNAPSHOT)
    return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
  })
  return calls
}

// The input a typed `/ws-pane <args>` carries.
function typed(args: string) {
  return { command: 'ws-pane', args, origin: { kind: 'composer' as const }, presentation: { isFullscreen: false, columns: 100 } }
}

async function start($: any) {
  await $.session.start({ cwd: `${ROOT}/.claude/worktrees/agent-x`, surface: 'desktop', isInteractive: true })
}

test('/ws-pane in a worktree reads the root ws names, and lists open workstreams on every surface', async ($, on) => {
  const calls = engine(on)
  await start($)

  const ran = await $.command.run(typed(''))
  expect(ran.text).toBe(`Workstreams pane opened for ${ROOT}.`)
  expect(calls.opened).toBe(1)
  expect(calls.argv[0]).toEqual(['ws', 'root'])
  expect(calls.argv[1]).toEqual(['ws', 'snapshot'])
  expect(calls.cwd[1]).toBe(ROOT)

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ key: 'ws:workstream_pane' }))?.text).toContain('active · 3/8 · after workstream_bookkeeping')
    expect((await ui.find({ key: 'ws:enrichment_matching' }))?.text).toContain('1 error')
    expect(await ui.find({ key: 'ws:old_review' })).toBeUndefined()
    await ui.unmount()
  }
})

test('the done toggle shows closed workstreams', async ($, on) => {
  engine(on)
  await start($)
  await $.command.run(typed(''))

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ key: 'toggle-done' }))?.text).toContain('Show done (1)')
    await ui.press({ key: 'toggle-done' })
    expect((await ui.find({ key: 'ws:old_review' }))?.text).toContain('done · 4/4')
    await ui.press({ key: 'toggle-done' })
    await ui.unmount()
  }
})

test('outside a project the command opens nothing', async ($, on) => {
  const calls = engine(on, false)
  await start($)

  const ran = await $.command.run(typed(''))
  expect(ran.text).toContain('is not a workstream project')
  expect(calls.opened).toBe(0)
  expect(calls.argv.length).toBe(1)
})

test('a missing ws says so, not that this is no project', async ($, on) => {
  const calls = engine(on, true, false)
  await start($)

  const ran = await $.command.run(typed(''))
  expect(ran.text).toContain('ws is not on the PATH')
  expect(calls.opened).toBe(0)
})

test('an explicit root is asked from there', async ($, on) => {
  const calls = engine(on)
  await start($)

  const ran = await $.command.run(typed(`${ROOT}/`))
  expect(ran.text).toBe(`Workstreams pane opened for ${ROOT}.`)
  expect(calls.argv[0]).toEqual(['ws', 'root'])
  expect(calls.cwd[0]).toBe(ROOT)
})
