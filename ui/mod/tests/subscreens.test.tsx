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
    verifyCommands: [{ label: 'test', command: 'make test' }],
    files: [],
    notes: '',
    mode: 'background',
    requires: [],
    blockedBy: [],
    unblocks: [],
    needsUserDecision: false,
    startedAt: null,
    ...extra,
  }
}

const NOW = Date.parse('2026-11-02T12:00:00Z')
// T-01 → T-02 and T-03; T-04 waits on both T-02 and T-03, so it shows twice.
const TASKS = [
  task('T-01', 1, 10, { status: 'done', unblocks: ['T-02', 'T-03'] }),
  task('T-02', 1, 20, { status: 'in-progress', blockedBy: ['T-01'], unblocks: ['T-04'], startedAt: '2026-11-02T10:00:00Z', claimedBy: 'main' }),
  task('T-03', 1, 30, { blockedBy: ['T-01'], unblocks: ['T-04'], verifyCommands: [{ label: 'test', command: 'make test' }, { label: 'lint', command: 'make lint' }] }),
  task('T-04', 2, 40, { blockedBy: ['T-02', 'T-03'] }),
]

const ROW = {
  id: WS,
  title: WS,
  summary: '',
  status: 'active',
  dependsOn: [],
  progress: { total: 4, todo: 2, 'in-progress': 1, blocked: 0, done: 1, deferred: 0 },
  progressStale: false,
  launches: [],
}

const BASE = {
  snapshotVersion: 1,
  repoRoot: ROOT,
  integrationBranch: 'trunk',
  registry: [ROW],
  watch: [`${ROOT}/ws.json`],
  revisions: { registry: 'r', tasks: {} },
  health: [],
  git: { branch: 'trunk' },
}

const DETAIL = {
  ...BASE,
  tasks: TASKS,
  wave: { state: 'ready', phase: 1, ids: ['T-03'], open: ['T-02', 'T-03', 'T-04'], leftovers: [] },
  paths: { plan: `${ROOT}/plan.md`, decisions: `${ROOT}/decisions.md` },
  scope: { inScope: ['ui/mod'], outOfScope: ['src'], rule: 'The pane only draws.' },
  baseline: {
    keys: [{ key: 'test', command: 'make test', exit: 0, findings: 2, recordedAt: '2026-11-01T00:00:00Z', commit: 'abcdef123456' }],
    errors: ['lint: no record'],
  },
}

function engine(on: any) {
  on('command.register', () => ({ value: { command: 'workstreams' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: 'the plan' }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[1] === 'root') return result(`${ROOT}\n`)
    return result(JSON.stringify(e.argv.includes('-w') ? DETAIL : BASE))
  })
}

function result(stdout: string) {
  return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
}

async function openDetail($: any, surface: (typeof SURFACES)[number]) {
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run(TYPED)
  const ui = await $.ui.mount({ ...PANE, surface })
  await ui.press({ key: `ws:${WS}` })
  return ui
}

test('detail opens on Tasks, and the row switches between the three sub-screens', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })

  for (const surface of SURFACES) {
    const ui = await openDetail($, surface)
    expect(await ui.find({ key: 'task:T-01' })).toBeDefined()
    expect(await ui.find({ key: 'sub:graph' })).toBeDefined()
    await ui.press({ key: 'sub:graph' })
    expect(await ui.find({ key: 'task:T-01' })).toBeUndefined()
    expect(await ui.find({ key: 'graph:T-01:0' })).toBeDefined()
    await ui.press({ key: 'sub:overview' })
    expect(await ui.find({ type: 'Text', text: /^Documents/ })).toBeDefined()
    await ui.press({ key: 'sub:tasks' })
    expect(await ui.find({ key: 'task:T-01' })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})

test('the graph indents each task under what it waits on, and a second parent shows a repeat', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'sub:graph' })

  // Depth-first from the one root, by priority: T-01, T-02, T-04, T-03, T-04 again.
  const first = (await ui.find({ key: 'graph:T-01:0' }))?.text
  expect(first).toContain('T-01 done')
  expect(first).toContain('T-01 title')
  expect((await ui.find({ key: 'graph:T-02:1' }))?.text).toContain('  └ T-02')
  expect((await ui.find({ key: 'graph:T-04:2' }))?.text).toContain('    └ T-04')
  expect((await ui.find({ key: 'graph:T-03:3' }))?.text).toContain('  └ T-03')
  const repeat = (await ui.find({ key: 'graph:T-04:4' }))?.text
  expect(repeat).toContain('(shown above)')
  expect(await ui.find({ key: 'graph:T-04:5' })).toBeUndefined()

  // A graph button opens that task's page, and back returns to the Graph.
  await ui.press({ key: 'graph:T-03:3' })
  expect(await ui.find({ type: 'Text', text: /T-03 accepted/ })).toBeDefined()
  expect(await ui.find({ key: 'graph:T-01:0' })).toBeUndefined()
  await ui.press({ key: 'back' })
  expect(await ui.find({ key: 'graph:T-01:0' })).toBeDefined()
  await ui.unmount()
})

test('overview shows documents, claims, scope, verify commands and baseline', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'sub:overview' })

  expect(await ui.find({ key: 'doc:plan' })).toBeDefined()
  expect(await ui.find({ key: 'doc:decisions' })).toBeDefined()
  expect(await ui.find({ key: 'doc:progress' })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: /^T-02 by/ }))?.text).toBe('T-02 by main, 2h ago')
  expect((await ui.find({ type: 'Text', text: /only draws/ }))?.text).toBe('The pane only draws.')
  expect((await ui.find({ type: 'Text', text: /^In: / }))?.text).toBe('In: ui/mod')
  expect((await ui.find({ type: 'Text', text: /^Out: / }))?.text).toBe('Out: src')
  const code = (await ui.find({ type: 'Code' }))?.text
  expect(code).toContain('test: make test')
  expect(code).toContain('lint: make lint')
  expect((await ui.find({ type: 'Text', text: /^test exit/ }))?.text).toBe('test exit 0, 2 known findings · at abcdef1')
  expect((await ui.find({ type: 'Text', text: /no record/ }))?.text).toBe('lint: no record')

  // A document opens in the feed, and back returns to Overview.
  await ui.press({ key: 'doc:plan' })
  expect((await ui.find({ type: 'Markdown' }))?.text).toContain('the plan')
  await ui.press({ key: 'back' })
  expect(await ui.find({ key: 'doc:plan' })).toBeDefined()
  await ui.unmount()
})

test('a task page jumps along its edges: an unblocks button reaches that task, and depends on leads back', async ($, on) => {
  engine(on)
  mock.clock(on, { now: NOW })

  for (const surface of SURFACES) {
    const ui = await openDetail($, surface)
    await ui.press({ key: 'task:T-02' })
    expect(await ui.find({ type: 'Text', text: /^T-02 summary$/ })).toBeDefined()
    expect((await ui.find({ key: 'dep:T-01' }))?.text).toBe('T-01 done')
    expect((await ui.find({ key: 'unblocks:T-04' }))?.text).toBe('T-04 todo')
    expect(await ui.find({ type: 'Text', text: /claimed by main, 2h ago/ })).toBeDefined()

    await ui.press({ key: 'unblocks:T-04' })
    expect(await ui.find({ type: 'Text', text: /^T-04 summary$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^T-02 summary$/ })).toBeUndefined()
    expect(await ui.find({ key: 'dep:T-02' })).toBeDefined()
    expect(await ui.find({ key: 'dep:T-03' })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /not claimed/ })).toBeDefined()

    await ui.press({ key: 'dep:T-03' })
    expect(await ui.find({ type: 'Text', text: /^T-03 summary$/ })).toBeDefined()
    expect(await ui.find({ key: 'unblocks:T-04' })).toBeDefined()
    await ui.press({ key: 'back' })
    expect(await ui.find({ key: 'task:T-01' })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
})
