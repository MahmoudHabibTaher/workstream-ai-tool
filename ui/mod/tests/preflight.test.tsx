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

// Stand-ins: the CLI owns the real texts.
const LAUNCHES = [
  { kind: 'run', prompt: `run-text ${WS}` },
  { kind: 'coordinate', prompt: `coordinate-text ${WS}` },
  { kind: 'close', prompt: `close-text ${WS}` },
  { kind: 'abandon', prompt: `abandon-text ${WS}: `, ask: 'reason' },
]

function task(id: string, status: string) {
  return {
    id, phase: 1, priority: 10, status, title: `${id} title`, summary: `${id} summary`,
    acceptanceText: [], verifyCommands: [], files: [], notes: '', mode: 'background',
    requires: [], blockedBy: [], unblocks: [], needsUserDecision: false, startedAt: null,
  }
}

function snapshot(status = 'active') {
  return {
    snapshotVersion: 1, repoRoot: ROOT, integrationBranch: 'trunk',
    registry: [{
      id: WS, title: WS, summary: '', status, dependsOn: [], progressStale: false,
      progress: { total: 2, todo: 1, 'in-progress': 0, blocked: 0, done: 1, deferred: 0 },
      launches: status === 'done' ? [] : LAUNCHES,
    }],
    watch: [`${ROOT}/ws.json`], revisions: { registry: 'r', tasks: {} }, health: [], git: { branch: 'trunk' },
    tasks: [task('T-01', 'todo'), task('T-02', 'done')],
    wave: { state: 'ready', phase: 1, ids: ['T-01'], open: ['T-01'], leftovers: [] }, paths: {},
  }
}

const OK = { id: 'validate', ok: true, blocking: true, message: 'no integrity errors' }
const WARN = { id: 'baseline', ok: false, blocking: false, message: 'no baseline for lint' }
const CLAIMED = { id: 'claim', ok: false, blocking: true, message: 'a claim is already open: T-09' }

type World = {
  snap: object
  checks: object[]
  checkExit: number
  checked: string[][]
  argvs: string[][]
  fills: string[]
  submits: number
}

function engine(on: any, snap: object = snapshot()): World {
  const world: World = { snap, checks: [OK], checkExit: 0, checked: [], argvs: [], fills: [], submits: 0 }
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'workstreams' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('prompt.fill', (_: unknown, e: { text: string }) => {
    world.fills.push(e.text)
    return { isFilled: true }
  })
  on('prompt.submit', () => {
    world.submits += 1
    return { drop: 'never' }
  })
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[1] === 'root') return result(0, `${ROOT}\n`)
    if (e.argv[1] === 'launch' && e.argv[2] === 'check') {
      world.checked.push(e.argv.slice(3))
      return world.checkExit === 0 ? result(0, JSON.stringify({ checks: world.checks })) : result(1, '', 'T-77: no such task in demo')
    }
    if (e.argv[1] === 'launch' && e.argv[2] === 'argv') {
      world.argvs.push(e.argv.slice(3))
      const pinned = e.argv[e.argv.indexOf('--task') + 1]
      return result(0, JSON.stringify({ argv: ['claude', `run-task-text ${pinned} ${WS}`], effortLevels: [], permissionChoices: [] }))
    }
    return result(0, JSON.stringify(world.snap))
  })
  return world
}

function result(exitCode: number, stdout: string, stderr = '') {
  return { value: { exitCode, stdout, stderr, isStdoutTruncated: false, isStderrTruncated: false } }
}

async function openDetail($: any, surface: (typeof SURFACES)[number]) {
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run(TYPED)
  const ui = await $.ui.mount({ ...PANE, surface })
  await ui.press({ key: `ws:${WS}` })
  return ui
}

test('a passing pre-flight shows its checks and fills the box, sending nothing', async ($, on) => {
  const world = engine(on)
  world.checks = [OK, WARN]
  for (const surface of SURFACES) {
    world.fills = []
    const ui = await openDetail($, surface)
    await ui.press({ key: 'run' })
    expect(world.checked.at(-1)).toEqual(['-w', WS, '--kind', 'run', '--json'])
    expect(world.fills).toEqual([`run-text ${WS}`])
    expect(await ui.find({ type: 'Text', text: /^Pre-flight: Run/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /ok validate · no integrity errors/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /warn baseline · no baseline for lint/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /Filled the prompt box; nothing was sent\./ })).toBeDefined()
    expect(await ui.find({ key: 'run' })).toBeDefined()
    await ui.press({ key: 'back' })
    await ui.unmount()
  }
  expect(world.submits).toBe(0)
})

test('a blocking check fills nothing and disables Run with its message, until a check again passes', async ($, on) => {
  const world = engine(on)
  world.checks = [OK, CLAIMED]
  const ui = await openDetail($, 'desktop')

  await ui.press({ key: 'run' })
  expect(world.fills).toEqual([])
  expect(await ui.find({ key: 'run' })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: /^Run \(blocked/ }))?.text).toBe('Run (blocked: a claim is already open: T-09)')
  expect(await ui.find({ type: 'Text', text: /BLOCKS claim · a claim is already open: T-09/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Blocked: nothing was filled\./ })).toBeDefined()
  // Only Run is held; Coordinate still offers itself.
  expect(await ui.find({ key: 'coordinate' })).toBeDefined()

  world.checks = [OK]
  await ui.press({ key: 'preflight:recheck' })
  expect(world.fills).toEqual([`run-text ${WS}`])
  expect(await ui.find({ key: 'run' })).toBeDefined()
  expect(world.submits).toBe(0)
  await ui.unmount()
})

test('abandon fills its prompt with a placeholder for what it asks', async ($, on) => {
  const world = engine(on)
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'abandon' })
  expect(world.checked.at(-1)).toEqual(['-w', WS, '--kind', 'abandon', '--json'])
  expect(world.fills).toEqual([`abandon-text ${WS}: <reason>`])
  await ui.unmount()
})

test('Run This Task checks with the task pinned and fills the CLI\'s prompt for it', async ($, on) => {
  const world = engine(on)
  world.checks = [OK, { ...CLAIMED, blocking: false }]
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'task:T-01' })
  await ui.press({ key: 'run-task' })

  expect(world.checked.at(-1)).toEqual(['-w', WS, '--kind', 'run-task', '--task', 'T-01', '--json'])
  expect(world.argvs.at(-1)).toEqual(['-w', WS, '--agent', 'claude-code', '--prompt-kind', 'run-task', '--task', 'T-01', '--json'])
  expect(world.fills).toEqual([`run-task-text T-01 ${WS}`])
  expect(await ui.find({ type: 'Text', text: /^Pre-flight: Run This Task/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /warn claim/ })).toBeDefined()
  expect(world.submits).toBe(0)

  // The task page's pre-flight is its own: detail shows none.
  await ui.press({ key: 'back' })
  expect(await ui.find({ type: 'Text', text: /^Pre-flight/ })).toBeUndefined()
  await ui.unmount()
})

test('Run This Task is held by a blocking check, and by a check the CLI refused', async ($, on) => {
  const world = engine(on)
  world.checks = [{ id: 'dirty', ok: false, blocking: true, message: 'tracking paths have changes' }]
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'task:T-01' })
  await ui.press({ key: 'run-task' })
  expect(world.argvs).toEqual([])
  expect(world.fills).toEqual([])
  expect(await ui.find({ key: 'run-task' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Run This Task \(blocked: tracking paths have changes\)$/ })).toBeDefined()

  world.checkExit = 1
  await ui.press({ key: 'preflight:recheck' })
  expect(await ui.find({ type: 'Text', text: /^Run This Task \(blocked: T-77: no such task in demo\)$/ })).toBeDefined()
  expect(world.fills).toEqual([])
  await ui.unmount()
})

test('a done task offers no Run This Task, an open one does', async ($, on) => {
  engine(on)
  const ui = await openDetail($, 'desktop')
  await ui.press({ key: 'task:T-02' })
  expect(await ui.find({ key: 'run-task' })).toBeUndefined()
  await ui.press({ key: 'back' })
  await ui.press({ key: 'task:T-01' })
  expect(await ui.find({ key: 'run-task' })).toBeDefined()
  await ui.unmount()
})
