import { expect, mock, test } from 'claude-code/testing'

const ROOT = '/repo'
const WS = 'demo'
const SURFACES = ['terminal', 'desktop', 'vscode', 'mobile'] as const
const TYPED = { command: 'workstreams', args: '', origin: { kind: 'composer' as const }, presentation: { isFullscreen: false, columns: 100 } }
const PANE = {
  plugin: 'workstreams-pane',
  component: 'Pane',
  requestId: 'workstreams',
  props: { title: 'Workstreams', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const TASK = {
  id: 'T-01', phase: 1, priority: 10, status: 'in-progress', title: 't', summary: 's', acceptanceText: [], verifyCommands: [{ label: 'v', command: 'v' }],
  files: [], notes: '', mode: 'background', requires: [], blockedBy: [], needsUserDecision: false, startedAt: '2026-11-01T00:00:00Z',
}
const STALE = {
  kind: 'stale-claim', level: 'warning', workstream: WS, task: 'T-01', message: 'claimed long ago',
  actions: [{ action: 'unclaim', workstream: WS, task: 'T-01' }],
}

function snapshot(status: string, health: object[], progressStale = false) {
  const progress = { total: 1, todo: 0, 'in-progress': 1, blocked: 0, done: 0, deferred: 0 }
  return {
    snapshotVersion: 1, repoRoot: ROOT, integrationBranch: 'trunk',
    registry: [{ id: WS, title: WS, summary: '', status, dependsOn: [], progress, progressStale }],
    watch: [`${ROOT}/ws.json`],
  revisions: { registry: 'REG', tasks: { [WS]: 'TASKS' } },
    health, git: { branch: 'trunk' }, tasks: [TASK],
    wave: { state: 'stuck', phase: null, ids: [], open: ['T-01'], leftovers: ['T-01'] }, paths: {},
  }
}

type World = { snap: object; acts: string[][]; refuse: string | null; fills: string[]; submits: number; toasts: string[] }

function engine(on: any, snap: object): World {
  const world: World = { snap, acts: [], refuse: null, fills: [], submits: 0, toasts: [] }
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'workstreams' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_: unknown, e: { text: string }) => {
    world.toasts.push(e.text)
    return { value: undefined }
  })
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
    if (e.argv[1] === 'act') {
      world.acts.push([...e.argv.slice(2)])
      return world.refuse ? result(1, '', world.refuse) : result(0, 'committed\n')
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

for (const surface of SURFACES) {
  test(`Confirm runs act with the snapshot's revisions, and only then (${surface})`, async ($, on) => {
    const world = engine(on, snapshot('active', [STALE]))
    const ui = await openDetail($, surface)

    await ui.press({ key: 'health' })
    expect(await ui.find({ type: 'Text', text: /stale-claim: claimed long ago/ })).toBeDefined()
    await ui.press({ key: 'act:unclaim:T-01' })
    expect(await ui.find({ type: 'Text', text: /This commits demo: unclaim T-01 on trunk/ })).toBeDefined()
    expect(world.acts.length).toBe(0)

    await ui.press({ key: 'cancel' })
    expect(world.acts.length).toBe(0)

    await ui.press({ key: 'act:unclaim:T-01' })
    await ui.press({ key: 'confirm' })
    expect(world.acts).toEqual([['unclaim', '-w', WS, '--task', 'T-01', '--expect-registry', 'REG', '--expect-tasks', 'TASKS']])
    expect(world.toasts).toEqual(['committed'])
    await ui.unmount()
  })
}

test('a refusal draws its stderr, and the next ask clears it', async ($, on) => {
  const world = engine(on, snapshot('active', []))
  world.refuse = 'refused: dirty tracking path (an orchestrator may be mid-step): x'
  const ui = await openDetail($, 'desktop')

  await ui.press({ key: 'act:pause' })
  await ui.press({ key: 'confirm' })
  expect(world.acts[0]?.slice(0, 3)).toEqual(['pause', '-w', WS])
  expect(await ui.find({ type: 'Text', text: /refused: dirty tracking path/ })).toBeDefined()
  expect(world.toasts).toEqual([])

  await ui.press({ key: 'act:pause' })
  expect(await ui.find({ type: 'Text', text: /refused: dirty tracking path/ })).toBeUndefined()
  await ui.unmount()
})

test('the confirm box hides the screen, so a pending write cannot follow a navigation', async ($, on) => {
  engine(on, snapshot('active', []))
  const ui = await openDetail($, 'desktop')

  await ui.press({ key: 'act:pause' })
  expect(await ui.find({ key: 'back' })).toBeUndefined()
  await ui.press({ key: 'cancel' })
  expect(await ui.find({ key: 'back' })).toBeDefined()
  await ui.unmount()
})

test('prompt buttons only fill the box, and nothing ever submits', async ($, on) => {
  const world = engine(on, snapshot('active', []))
  const ui = await openDetail($, 'mobile')

  for (const key of ['run', 'coordinate', 'close', 'abandon']) await ui.press({ key })
  expect(world.fills[0]).toBe(`Use the ws-run skill to run workstream ${WS}.`)
  expect(world.fills[1]).toBe(`Use the ws-coordinate skill on workstream ${WS}.`)
  expect(world.fills[2]).toContain(`close workstream ${WS}`)
  expect(world.fills[3]).toContain(`abandon workstream ${WS}`)
  expect(world.submits).toBe(0)
  expect(world.acts.length).toBe(0)
  await ui.unmount()
})

test('a write button is absent when nothing offers it', async ($, on) => {
  const world = engine(on, snapshot('active', []))
  const ui = await openDetail($, 'desktop')

  await ui.press({ key: 'task:T-01' })
  expect(await ui.find({ key: 'act:unclaim:T-01' })).toBeUndefined()
  expect(await ui.find({ key: 'act:resume' })).toBeUndefined()
  expect(await ui.find({ key: 'act:pause' })).toBeDefined()
  await ui.press({ key: 'health' })
  expect(await ui.find({ key: 'act:sync' })).toBeUndefined()
  await ui.unmount()
  expect(world.acts.length).toBe(0)
})

test('status and the snapshot bring the other write buttons', async ($, on) => {
  engine(on, snapshot('paused', [STALE], true))
  const ui = await openDetail($, 'desktop')

  expect(await ui.find({ key: 'act:pause' })).toBeUndefined()
  expect(await ui.find({ key: 'act:resume' })).toBeDefined()
  await ui.press({ key: 'task:T-01' })
  expect(await ui.find({ key: 'act:unclaim:T-01' })).toBeDefined()
  await ui.press({ key: 'health' })
  expect(await ui.find({ key: 'act:sync' })).toBeDefined()
  await ui.unmount()
})

test('a done workstream offers no write and no prompt', async ($, on) => {
  engine(on, snapshot('done', []))
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run(TYPED)
  const ui = await $.ui.mount({ ...PANE, surface: 'desktop' })
  await ui.press({ key: 'toggle-done' })
  await ui.press({ key: `ws:${WS}` })

  for (const key of ['act:pause', 'act:resume', 'dispatch', 'coordinate', 'close', 'abandon']) {
    expect(await ui.find({ key })).toBeUndefined()
  }
  await ui.unmount()
})
