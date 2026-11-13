import { expect, mock, test } from 'claude-code/testing'

const ROOT = '/repo'
const WS = 'demo'
const SURFACES = ['terminal', 'desktop', 'vscode', 'mobile'] as const
const TYPED = { command: 'workstreams', args: '', origin: { kind: 'composer' as const }, presentation: { isFullscreen: false, columns: 100 } }

const PANE = {
  plugin: 'workstreams-pane',
  component: 'Pane',
  requestId: 'workstreams',
  props: {
    title: 'Workstreams',
    isFocused: false,
    bodyColumns: 80,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 30 },
    view: {},
  },
} as const

function task(id: string, phase: number, priority: number, extra: object = {}) {
  return {
    id,
    phase,
    priority,
    status: 'todo',
    title: `${id} title`,
    summary: `${id} summary`,
    acceptanceText: [`${id} accepted`],
    verifyCommands: [{ label: 'make test', command: 'make test' }],
    files: ['a.py'],
    notes: '',
    mode: 'background',
    requires: [],
    blockedBy: [],
    needsUserDecision: false,
    startedAt: null,
    ...extra,
  }
}

const NOW = Date.parse('2026-11-02T12:00:00Z')
const TASKS = [
  task('T-02', 1, 20, { mode: 'foreground', requires: ['user'], needsUserDecision: true }),
  task('T-01', 1, 10),
  task('T-03', 1, 30, { status: 'in-progress', startedAt: '2026-11-02T10:00:00Z' }),
  task('T-04', 2, 40, { blockedBy: ['T-01'] }),
]

const SNAPSHOT = {
  snapshotVersion: 1,
  repoRoot: ROOT,
  integrationBranch: 'trunk',
  registry: [
    {
      id: WS,
      title: WS,
      summary: '',
      status: 'active',
      dependsOn: [],
      progress: { total: 4, todo: 3, 'in-progress': 1, blocked: 0, done: 0, deferred: 0 },
      progressStale: false,
      launches: [{ kind: 'run', prompt: 'run-text' }],
    },
  ],
  watch: [`${ROOT}/ws.json`],
  revisions: { registry: 'r', tasks: {} },
  health: [],
  git: { branch: 'trunk' },
}

const DETAIL = {
  ...SNAPSHOT,
  tasks: TASKS,
  wave: { state: 'ready', phase: 1, ids: ['T-01'], open: ['T-01', 'T-02', 'T-03', 'T-04'], leftovers: ['T-03'] },
  paths: {
    handoff: `${ROOT}/workstreams/${WS}/session_handoff.md`,
    progress: `${ROOT}/workstreams/${WS}/PROGRESS.md`,
    decisions: `${ROOT}/workstreams/${WS}/DECISIONS.md`,
  },
}

const LINES = Array.from({ length: 300 }, (_, i) => `line ${i + 1}`).join('\n')

type World = { snapshots: number; mtime: number }

function engine(on: any): World {
  const world: World = { snapshots: 0, mtime: 1 }
  on('command.register', () => ({ value: { command: 'workstreams' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: world.mtime, isLink: false } }))
  on('fs.read', () => ({ value: LINES }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[1] === 'root') return result(`${ROOT}\n`)
    world.snapshots += 1
    return result(JSON.stringify(e.argv.includes('-w') ? DETAIL : SNAPSHOT))
  })
  return world
}

function result(stdout: string) {
  return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
}

async function open($: any) {
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run(TYPED)
}

test('detail shows the lanes in priority order, the wave line and every badge', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  await open($)

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: `ws:${WS}` })
    expect((await ui.find({ type: 'Text', text: /^phase 1:/ }))?.text).toBe('phase 1: 1 ready · 1 leftover')
    expect((await ui.find({ key: 'task:T-01' }))?.text).toContain('★ ready')
    const fg = (await ui.find({ key: 'task:T-02' }))?.text
    expect(fg).toContain('FG')
    expect(fg).toContain('needs decision')
    expect((await ui.find({ key: 'task:T-03' }))?.text).toContain('claimed 2h')
    expect((await ui.find({ key: 'task:T-04' }))?.text).toContain('waits on T-01')
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('a task row opens its page, and back returns to the lanes', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  await open($)

  const ui = await $.ui.mount({ ...PANE, surface: 'mobile' })
  await ui.press({ key: `ws:${WS}` })
  expect(await ui.find({ type: 'Text', text: /T-01 accepted/ })).toBeUndefined()
  await ui.press({ key: 'task:T-01' })
  expect(await ui.find({ type: 'Text', text: /T-01 accepted/ })).toBeDefined()
  expect((await ui.find({ type: 'Code' }))?.text).toContain('make test')
  expect(await ui.find({ key: 'task:T-02' })).toBeUndefined()
  await ui.press({ key: 'back' })
  expect(await ui.find({ type: 'Text', text: /T-01 accepted/ })).toBeUndefined()
  expect(await ui.find({ key: 'task:T-02' })).toBeDefined()
  await ui.unmount()
})

test('the feed pages a 300-line file in 120-line pages on every surface', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  await open($)

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...PANE, surface })
    await ui.press({ key: `ws:${WS}` })
    await ui.press({ key: 'feed' })
    expect((await ui.find({ type: 'Text', text: /^page / }))?.text).toBe('page 1 of 3')
    const first = (await ui.find({ type: 'Markdown' }))?.text
    expect(first).toContain('line 120')
    expect(first).not.toContain('line 121')
    await ui.press({ key: 'page-next' })
    expect((await ui.find({ type: 'Markdown' }))?.text).toContain('line 121')
    expect((await ui.find({ type: 'Text', text: /^page / }))?.text).toBe('page 2 of 3')
    await ui.press({ key: 'tab:decisions' })
    expect((await ui.find({ type: 'Text', text: /^page / }))?.text).toBe('page 3 of 3')
    await ui.press({ key: 'tab:handoff' })
    await ui.press({ key: 'back' })
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('only the launches the row offers become prompt buttons', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  await open($)

  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: `ws:${WS}` })
  expect(await ui.find({ key: 'run' })).toBeDefined()
  for (const key of ['coordinate', 'close', 'abandon']) expect(await ui.find({ key })).toBeUndefined()
  await ui.unmount()
})

test('a changed mtime re-snapshots once, an unchanged one never', async ($, on) => {
  const world = engine(on)
  const clock = mock.clock(on, { now: NOW })
  await open($)
  expect(world.snapshots).toBe(1)

  await clock.advance(9000)
  expect(world.snapshots).toBe(1)

  world.mtime = 2
  await clock.advance(9000)
  expect(world.snapshots).toBe(2)
})
