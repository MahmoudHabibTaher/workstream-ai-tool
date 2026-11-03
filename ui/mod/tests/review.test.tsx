import { expect, mock, test } from 'claude-code/testing'

const ROOT = '/repo'
const WS = 'demo'
const SURFACES = ['terminal', 'desktop', 'vscode', 'mobile'] as const
const TYPED = { command: 'ws-pane', args: '', origin: { kind: 'composer' as const }, presentation: { isFullscreen: false, columns: 100 } }
const PANE = {
  plugin: 'ws-pane',
  component: 'Pane',
  requestId: 'ws-pane',
  props: { title: 'Workstreams', isFocused: false, bodyColumns: 80, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const TASK = {
  id: 'T-01', phase: 1, priority: 10, status: 'done', title: 't', summary: 's', acceptanceText: [], verifyCommands: [{ label: 'v', command: 'v' }],
  files: [], notes: '', mode: 'background', requires: [], blockedBy: [], needsUserDecision: false, startedAt: null,
}
const SNAPSHOT = {
  snapshotVersion: 1, repoRoot: ROOT, integrationBranch: 'trunk',
  registry: [{
    id: WS, title: WS, summary: '', status: 'active', dependsOn: [],
    progress: { total: 1, todo: 0, 'in-progress': 0, blocked: 0, done: 1, deferred: 0 }, progressStale: false,
  }],
  watch: [`${ROOT}/ws.json`],
  revisions: { registry: 'r', tasks: {} }, health: [], git: { branch: 'trunk' }, tasks: [TASK],
  wave: { state: 'finished', phase: null, ids: [], open: [], leftovers: [] }, paths: {},
}
const EVIDENCE = `${ROOT}/ws-pane/${WS}/evidence/T-01.md`
const DIFF = 'diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,2 +1,2 @@\n-old\n+new\n same\n'

type Stub = { evidence: string | null; kind: string; truncated: boolean; reviews: string[][] }

function engine(on: any, stub: Stub) {
  mock.clock(on)
  on('command.register', () => ({ value: { command: 'ws-pane' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('fs.stat', () => ({ value: { kind: 'file', size: 1, mtimeMs: 1, isLink: false } }))
  on('fs.read', () => ({ value: '# T-01 evidence' }))
  on('process.run', (_: unknown, e: { argv: string[] }) => {
    if (e.argv[1] === 'root') return result(`${ROOT}\n`)
    if (e.argv[1] !== 'review') return result(JSON.stringify(SNAPSHOT))
    stub.reviews.push([...e.argv.slice(2)])
    const file = e.argv[e.argv.indexOf('--file') + 1]
    return result(JSON.stringify({
      task: 'T-01',
      evidence: stub.evidence,
      range: { from: 'abc^1', to: 'abc', kind: stub.kind },
      files: [{ path: 'a.py', added: 3, removed: 1 }, { path: 'b.png', added: null, removed: null }],
      ...(e.argv.includes('--file') ? { hunks: { path: file, text: DIFF, truncated: stub.truncated } } : {}),
    }))
  })
}

function result(stdout: string) {
  return { value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }
}

async function openReview($: any, surface: (typeof SURFACES)[number]) {
  await $.session.start({ cwd: ROOT, surface: 'desktop', isInteractive: true })
  await $.command.run(TYPED)
  const ui = await $.ui.mount({ ...PANE, surface })
  await ui.press({ key: `ws:${WS}` })
  await ui.press({ key: 'task:T-01' })
  await ui.press({ key: 'review:T-01' })
  return ui
}

for (const surface of SURFACES) {
  test(`review draws the evidence, the diffstat and a file's diff, with its cut note (${surface})`, async ($, on) => {
    const stub: Stub = { evidence: EVIDENCE, kind: 'merge', truncated: true, reviews: [] }
    engine(on, stub)
    const ui = await openReview($, surface)

    expect(stub.reviews[0]).toEqual(['T-01', '-w', WS])
    expect((await ui.find({ type: 'Markdown' }))?.text).toContain('T-01 evidence')
    expect(await ui.find({ type: 'Text', text: /^merge: abc\^1\.\.abc$/ })).toBeDefined()
    expect((await ui.find({ key: 'file:a.py' }))?.text).toContain('+3 -1')
    expect((await ui.find({ key: 'file:b.png' }))?.text).toContain('binary')
    expect(await ui.find({ type: 'Code' })).toBeUndefined()

    await ui.press({ key: 'file:a.py' })
    expect(stub.reviews[1]).toEqual(['T-01', '-w', WS, '--file', 'a.py'])
    const drawn = (await ui.find({ type: 'Code' }))?.text
    expect(drawn).toContain('+new')
    expect(drawn?.startsWith('@@')).toBe(true)
    expect(await ui.find({ type: 'Text', text: /Cut at a hunk boundary/ })).toBeDefined()
    expect(await ui.find({ type: 'Markdown' })).toBeUndefined()

    await ui.press({ key: 'evidence' })
    expect(await ui.find({ type: 'Code' })).toBeUndefined()
    expect((await ui.find({ type: 'Markdown' }))?.text).toContain('T-01 evidence')
    await ui.unmount()
  })
}

test('a whole diff has no cut note, and no evidence file says so', async ($, on) => {
  engine(on, { evidence: null, kind: 'commit', truncated: false, reviews: [] })
  const ui = await openReview($, 'desktop')

  expect(await ui.find({ type: 'Text', text: /^No evidence file\.$/ })).toBeDefined()
  await ui.press({ key: 'file:a.py' })
  expect(await ui.find({ type: 'Text', text: /Cut at a hunk boundary/ })).toBeUndefined()
  await ui.unmount()
})

test('a task with no range says so', async ($, on) => {
  engine(on, { evidence: null, kind: 'none', truncated: false, reviews: [] })
  const ui = await openReview($, 'mobile')

  expect(await ui.find({ type: 'Text', text: /^No diff:/ })).toBeDefined()
  await ui.unmount()
})
