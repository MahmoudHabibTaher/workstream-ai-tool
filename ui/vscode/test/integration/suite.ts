// Runs inside VS Code's extension host. No test framework: `run` throws on the first failure,
// which @vscode/test-electron reports as a failed run.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { join, sep } from 'node:path'

import * as vscode from 'vscode'

import type { Api } from '../../src/extension.ts'
import type { HealthNode } from '../../src/logic/health.ts'
import type { ReviewNode } from '../../src/logic/review.ts'
import type { WorkstreamNode } from '../../src/views/workstreams.ts'

const BRANCH_CLI = ['python3', '-B', '-m', 'workstream']

export async function run(): Promise<void> {
  const which = process.env.WS_TEST_CASE
  const folder = realpathSync(process.env.WS_TEST_FOLDER ?? '')
  const extension = vscode.extensions.getExtension<Api>('workstream.workstreams')
  assert.ok(extension, 'the extension is installed in this window')
  const api = await extension.activate()
  const started = await api.ready
  const folders = (vscode.workspace.workspaceFolders ?? []).map(f => realpathSync(f.uri.fsPath))
  assert.deepEqual(folders, [folder])

  if (which === 'project') {
    // The branch's CLI, not the `ws` on PATH: the configured argv ran, and that interpreter,
    // given this host's environment, imports `workstream` from this checkout's src.
    const src = realpathSync(process.env.WS_TEST_SRC ?? '')
    const imported = execFileSync('python3', ['-B', '-c', 'import workstream; print(workstream.__file__)'], { encoding: 'utf8' })
    assert.ok(realpathSync(imported.trim()).startsWith(src + sep), `workstream came from ${imported.trim()}, not ${src}`)
    assert.deepEqual(api.ran.slice(0, 2), [[...BRANCH_CLI, 'root'], [...BRANCH_CLI, 'snapshot']])
    assert.deepEqual(api.shown, [])
    assert.deepEqual(started.roots.map(r => realpathSync(r)), [folder])
    const snapshot = started.snapshots[started.roots[0]]
    assert.equal(snapshot.snapshotVersion, 1)
    const registry = snapshot.registry as { id: string }[]
    assert.deepEqual(registry.map(row => row.id), ['alpha', 'beta'])
    assert.match(snapshot.revisions.registry, /^[0-9a-f]{64}$/)
    await linkedViews(api, started.roots[0])
    await graphAndOverview(api, started.roots[0])
    await writes(api, started.roots[0])
    await launches(api, started.roots[0])
    await healthAndBudget(api, started.roots[0])
  } else if (which === 'review') {
    assert.deepEqual(api.shown, [])
    await reviewQueue(api, started.roots[0])
  } else if (which === 'plain') {
    assert.deepEqual(api.ran, [[...BRANCH_CLI, 'root']])
    assert.equal(api.shown.length, 1)
    assert.match(api.shown[0], /is not a workstream project/)
    assert.equal(started.message?.level, 'info')
    assert.deepEqual(started.roots, [])
    assert.deepEqual(await api.list?.getChildren(), [])
  } else if (which === 'missing') {
    assert.equal(api.ran.length, 1)
    assert.deepEqual(api.ran[0].slice(1), ['root'])
    assert.equal(api.shown.length, 1)
    assert.match(api.shown[0], /did not start.*workstreams\.wsCommand/)
    assert.equal(started.message?.level, 'error')
  } else {
    assert.fail(`unknown case ${String(which)}`)
  }
  console.log(`ok ${which}: ran ${JSON.stringify(api.ran)}, shown ${JSON.stringify(api.shown)}`)
}

// Any of the trees, as the test reads it: a node's children and the item VS Code would draw.
type Provider<T> = { getChildren(node?: T): vscode.ProviderResult<T[]>; getTreeItem(node: T): vscode.TreeItem | Thenable<vscode.TreeItem> }
type Item<T = unknown> = { node: T; item: vscode.TreeItem; children: Item<T>[] }

// The whole tree as VS Code would draw it: every node, its item and its children.
async function walk<T>(tree: Provider<T>, node?: T): Promise<Item<T>[]> {
  const found: Item<T>[] = []
  for (const child of (await tree.getChildren(node)) ?? []) {
    const item = await tree.getTreeItem(child)
    const children = item.collapsibleState === vscode.TreeItemCollapsibleState.None || item.collapsibleState === undefined ? [] : await walk(tree, child)
    found.push({ node: child, item, children })
  }
  return found
}

const label = (i: Item) => String(i.item.label)
const line = (i: Item) => `${label(i)} | ${String(i.item.description ?? '')}`
// An item and its children's labels, as the Task view draws them.
const outline = (items: Item[]) => items.map(i => (i.children.length ? [label(i), i.children.map(label)] : label(i)))
const click = async (i: Item | undefined) => {
  const command = i?.item.command
  assert.ok(command, `no command on ${i ? label(i) : 'nothing'}`)
  await vscode.commands.executeCommand(command.command, ...(command.arguments ?? []))
}
const byName = <T>(items: Item<T>[], name: string) => {
  const got = items.find(i => label(i as Item) === name)
  assert.ok(got, `no ${name} in ${JSON.stringify(items.map(i => label(i as Item)))}`)
  return got
}

async function until<T>(what: string, get: () => Promise<T | undefined>, ms = 20_000): Promise<T> {
  const end = Date.now() + ms
  for (;;) {
    const got = await get()
    if (got !== undefined) return got
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`)
    await new Promise(r => setTimeout(r, 200))
  }
}

// Plan D-VIEWS: selecting a workstream in Workstreams draws its tasks in Tasks; selecting a task
// draws its sections in Task, where a dependency jumps to that task and a file opens.
async function linkedViews(api: Api, root: string): Promise<void> {
  const { list, tasks, task } = api
  assert.ok(list && tasks && task)
  await api.settled()
  const top = await walk(list)
  // Open workstreams only, each a flat row with done/total, status and errors.
  assert.deepEqual(top.map(label), ['alpha'])
  assert.match(String(top[0].item.description), /^0\/3 · active · \d+ errors?$/)
  assert.equal(top[0].item.collapsibleState, vscode.TreeItemCollapsibleState.None)
  // Nothing selected, so Tasks and Task draw nothing.
  assert.deepEqual(await walk(tasks), [])
  assert.deepEqual(await walk(task), [])
  console.log(`workstreams: ${JSON.stringify(top.map(line))}; before a selection Tasks and Task are empty`)

  // 1. Selecting alpha: Tasks draws its wave line, then its phases in order, tasks by priority,
  // each with its status, phase and what it is waiting on.
  await click(top[0])
  assert.deepEqual(api.store?.selected, { root, ws: 'alpha' })
  const lanes = await walk(tasks)
  assert.deepEqual(lanes.map(label), ['Phase 1: 1 ready', 'Phase 1', 'Phase 2'])
  assert.deepEqual(lanes.slice(1).map(line), ['Phase 1 | 0/2', 'Phase 2 | 0/1'])
  assert.deepEqual(lanes[1].children.map(line), ['A-1 First | todo · Phase 1', 'A-2 Second | todo · Phase 1'])
  assert.deepEqual(lanes[2].children.map(line), ['A-3 Third | todo · Phase 2 · waiting on A-1'])
  assert.deepEqual(await walk(task), [])
  console.log(`tasks after selecting alpha: ${JSON.stringify(lanes.map(i => [line(i), i.children.map(line)]))}`)

  // A task's tooltip is text: the summary's link and HTML come out escaped, and nothing is trusted.
  const tip = lanes[1].children[0].item.tooltip as vscode.MarkdownString
  assert.ok(tip instanceof vscode.MarkdownString)
  assert.ok(!tip.isTrusted)
  assert.equal(tip.supportHtml, false)
  assert.ok(!tip.value.includes('[x](command:'), tip.value)
  assert.ok(!tip.value.includes('<b>'), tip.value)
  assert.match(tip.value, /Acceptance/)
  assert.match(tip.value, /it(&nbsp;| )works/)
  console.log(`tooltip: ${JSON.stringify(tip.value)}`)

  // 2. Selecting A-1: Task draws its title, state, summary, what it unblocks, its files and acceptance.
  await click(lanes[1].children[0])
  assert.equal(api.store?.selectedTask, 'A-1')
  let shown = await walk(task)
  assert.deepEqual(outline(shown), [
    'A-1: First', 'todo · Phase 1 · ★ ready',
    ['Summary', ['see [x](command:workbench.action.quit) <b>now</b>']],
    ['Unblocks', ['A-3']], ['Files', ['notes.txt']], ['Acceptance', ['it works']],
  ])
  console.log(`task A-1: ${JSON.stringify(outline(shown))}`)

  // 3. A dependency jumps: Unblocks A-3 draws A-3, whose Depends on A-1 jumps back.
  await click(byName(shown, 'Unblocks').children[0])
  assert.equal(api.store?.selectedTask, 'A-3')
  shown = await walk(task)
  assert.deepEqual(outline(shown), ['A-3: Third', 'todo · Phase 2 · waiting on A-1', ['Depends on', ['A-1']]])
  console.log(`after the jump to A-3: ${JSON.stringify(outline(shown))}`)
  await click(byName(shown, 'Depends on').children[0])
  assert.equal(api.store?.selectedTask, 'A-1')
  shown = await walk(task)
  assert.equal(label(shown[0]), 'A-1: First')

  // 4. A file opens in an editor, from the snapshot's repo root.
  const file = byName(shown, 'Files').children[0]
  assert.equal(file.item.command?.command, 'vscode.open')
  await click(file)
  const editor = await until('notes.txt in an editor', async () => {
    const doc = vscode.window.activeTextEditor?.document
    return doc && realpathSync(doc.uri.fsPath) === realpathSync(join(root, 'notes.txt')) ? doc : undefined
  })
  assert.equal(editor.getText(), 'notes\n')
  console.log(`file: opened ${editor.uri.fsPath}`)

  // The status bar: the active workstream's wave line and error count, focusing the list.
  assert.match(api.statusBar?.text ?? '', /^\$\(checklist\) alpha: Phase 1: 1 ready · \d+ errors?$/)
  assert.equal(api.statusBar?.command, 'workstreams.list.focus')
  console.log(`status bar: ${api.statusBar?.text}`)

  // Show done adds the closed one after the open ones; Hide done takes it away again.
  await vscode.commands.executeCommand('workstreams.showDone')
  assert.deepEqual((await walk(list)).map(label), ['alpha', 'beta'])
  assert.match(line((await walk(list))[1]), /^beta \| 0\/0 · abandoned/)
  await vscode.commands.executeCommand('workstreams.hideDone')
  assert.deepEqual((await walk(list)).map(label), ['alpha'])

  // A claim from a shell reaches Tasks and Task with no Refresh pressed: the watchers reload, and
  // the selection survives it.
  const before = api.reloads.length
  execFileSync(BRANCH_CLI[0], [...BRANCH_CLI.slice(1), 'claim', 'A-1', '-w', 'alpha'], { cwd: root, encoding: 'utf8' })
  const claimed = await until('the claim in the Tasks view', async () => {
    const a1 = byName(await walk(tasks), 'Phase 1').children[0]
    return a1 && String(a1.item.description) === 'in-progress · Phase 1' ? line(a1) : undefined
  })
  assert.ok(api.reloads.length > before)
  assert.ok(api.reloads.slice(before).every(why => why === 'watch'), JSON.stringify(api.reloads))
  assert.equal(api.store?.selectedTask, 'A-1')
  shown = await walk(task)
  assert.match(label(shown[1]), /^in-progress · Phase 1/)
  assert.ok(byName(shown, 'Claim'))
  console.log(`after the claim: ${claimed}; task ${JSON.stringify(outline(shown))}; reloads ${JSON.stringify(api.reloads.slice(before))}`)
}

// Plan D-VIEWS: with alpha selected (and A-1 claimed by linkedViews), Graph draws the tasks from
// `blockedBy` and `unblocks`, and a node selects its task; Overview draws the documents, the
// registry row, the open claims, scope, verify commands and baseline, and a document opens.
async function graphAndOverview(api: Api, root: string): Promise<void> {
  const { graph, overview, task } = api
  assert.ok(graph && overview && task)
  assert.deepEqual(api.store?.selected, { root, ws: 'alpha' })

  // 1. Graph: A-1 unblocks A-3, so A-3 sits under it; A-2 waits on nothing, so it is a root.
  const nodes = await walk(graph)
  const tree = (items: Item[]): unknown[] => items.map(i => (i.children.length ? [line(i), tree(i.children)] : line(i)))
  console.log(`graph: ${JSON.stringify(tree(nodes))}`)
  assert.deepEqual(nodes.map(label), ['A-1 First', 'A-2 Second'])
  assert.match(line(nodes[0]), /^A-1 First \| in-progress/)
  assert.deepEqual(nodes[0].children.map(label), ['A-3 Third'])
  assert.match(line(nodes[0].children[0]), /^A-3 Third \| todo/)
  assert.deepEqual(nodes[1].children, [])
  const ids = (items: Item[]): string[] => items.flatMap(i => [String(i.item.id), ...ids(i.children)])
  assert.equal(new Set(ids(nodes)).size, 3)

  // Selecting a node selects its task, which the Task view draws.
  await click(nodes[0].children[0])
  assert.equal(api.store?.selectedTask, 'A-3')
  assert.equal(label((await walk(task))[0]), 'A-3: Third')
  await click(nodes[0])
  assert.equal(api.store?.selectedTask, 'A-1')
  assert.equal(label((await walk(task))[0]), 'A-1: First')
  console.log('graph: clicking A-3 then A-1 selected each in the Task view')

  // 2. Overview: its sections, every fact from the CLI's snapshot.
  const sections = await walk(overview)
  console.log(`overview: ${JSON.stringify(outline(sections))}`)
  const headings = sections.map(label)
  for (const h of ['Documents', 'Registry', 'Open claims', 'Baseline']) assert.ok(headings.includes(h), `${h} in ${JSON.stringify(headings)}`)
  assert.ok(headings.indexOf('Documents') < headings.indexOf('Registry'))
  const registry = byName(sections, 'Registry').children.map(label)
  assert.equal(registry[0], 'alpha: Alpha')
  assert.ok(registry.includes('sample'), JSON.stringify(registry))
  assert.ok(registry.some(l => /^active/.test(l)), JSON.stringify(registry))
  assert.ok(registry.some(l => /^0\/3 done · 1 claimed$/.test(l)), JSON.stringify(registry))
  const claims = byName(sections, 'Open claims').children
  assert.equal(claims.length, 1)
  assert.match(label(claims[0]), /^A-1/)
  assert.ok(byName(sections, 'Baseline').children.length >= 1)

  // A claim jumps to its task; a document opens in an editor.
  await click(claims[0])
  assert.equal(api.store?.selectedTask, 'A-1')
  const doc = byName(sections, 'Documents').children[0]
  assert.equal(doc.item.command?.command, 'vscode.open')
  const target = (doc.item.command?.arguments?.[0] as vscode.Uri).fsPath
  assert.ok(realpathSync(target).startsWith(realpathSync(join(root, 'workstreams', 'alpha')) + sep), target)
  await click(doc)
  const editor = await until(`${target} in an editor`, async () => {
    const d = vscode.window.activeTextEditor?.document
    return d && realpathSync(d.uri.fsPath) === realpathSync(target) ? d : undefined
  })
  assert.equal(editor.getText(), readFileSync(target, 'utf8'))
  console.log(`overview: ${label(doc)} opened ${editor.uri.fsPath}`)
}

const git = (root: string, ...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
const context = (i: Item | undefined) => String(i?.item.contextValue ?? '')

// The alpha row, and its first phase's tasks in the Tasks view, as drawn now.
async function drawn(api: Api) {
  const { list, tasks } = api
  assert.ok(list && tasks)
  const top = await walk(list)
  const lanes = await walk(tasks)
  return { alpha: top[0] as Item<WorkstreamNode>, tasks: lanes.find(i => label(i) === 'Phase 1')?.children ?? [] }
}

async function writes(api: Api, root: string): Promise<void> {
  const tree = api.list
  assert.ok(tree)
  // The claim left the queue dirty, which act refuses; commit it as an orchestrator would.
  git(root, 'commit', '-qam', 'claim A-1')
  await vscode.commands.executeCommand('workstreams.refresh')
  await api.settled()

  // Commands follow the snapshot's offers: alpha (active) offers pause and the launches, a fresh
  // claim offers no unclaim, and a closed row offers nothing.
  let now = await drawn(api)
  assert.match(context(now.alpha), /^workstream act:pause( act:sync)? launch$/)
  assert.deepEqual(now.tasks.map(context), ['task', 'task'])
  await vscode.commands.executeCommand('workstreams.showDone')
  const beta = (await walk(tree))[1]
  assert.equal(context(beta), 'workstream')
  await vscode.commands.executeCommand('workstreams.hideDone')
  console.log(`offers: alpha ${JSON.stringify(context(now.alpha))}, tasks ${JSON.stringify(now.tasks.map(context))}, beta ${JSON.stringify(context(beta))}`)

  // A claim two days old with no worktree is stale, and its finding offers unclaim on that task only.
  const queue = join(root, 'workstreams', 'alpha', 'tasks_list.json')
  const data = JSON.parse(readFileSync(queue, 'utf8')) as { tasks: { id: string; startedAt?: string }[] }
  const a1 = data.tasks.find(t => t.id === 'A-1')
  assert.ok(a1?.startedAt)
  a1.startedAt = new Date(Date.now() - 48 * 3600_000).toISOString().replace(/\.\d+Z$/, 'Z')
  writeFileSync(queue, JSON.stringify(data, null, 2) + '\n')
  git(root, 'commit', '-qam', 'an old claim')
  now = await until('unclaim offered on A-1', async () => {
    const got = await drawn(api)
    return context(got.tasks[0]) === 'task act:unclaim' ? got : undefined
  })
  assert.deepEqual(now.tasks.map(context), ['task act:unclaim', 'task'])
  console.log(`after the claim went stale: tasks ${JSON.stringify(now.tasks.map(line))} offer ${JSON.stringify(now.tasks.map(context))}`)

  // 1. A confirmed pause commits through ws act, and the tree shows paused.
  const asked: string[] = []
  api.ui = { confirm: async text => { asked.push(`${text.message} | ${text.detail}`); return true }, reason: async () => undefined }
  const before = git(root, 'rev-parse', 'HEAD')
  const ranBefore = api.ran.length
  await vscode.commands.executeCommand('workstreams.pause', now.alpha.node)
  assert.deepEqual(asked, ['Pause alpha? | This commits "alpha: pause" on main.'])
  const act = api.ran.slice(ranBefore).find(argv => argv.includes('act'))
  assert.ok(act)
  assert.deepEqual(act.slice(BRANCH_CLI.length, BRANCH_CLI.length + 4), ['act', 'pause', '-w', 'alpha'])
  const pinned = now.alpha.node.revisions
  assert.deepEqual(act.slice(BRANCH_CLI.length + 4), ['--expect-registry', pinned.registry, '--expect-tasks', pinned.tasks.alpha])
  assert.equal(git(root, 'rev-parse', 'HEAD~1'), before)
  assert.equal(git(root, 'log', '-1', '--format=%s'), 'alpha: pause (ws act)')
  assert.equal(git(root, 'status', '--porcelain'), '')
  const paused = await until('alpha paused in the tree', async () => {
    const got = await drawn(api)
    return /^0\/3 · paused · /.test(String(got.alpha?.item.description)) ? got : undefined
  })
  assert.match(context(paused.alpha), /^workstream act:resume( act:sync)? launch$/)
  console.log(`pause: ran ${JSON.stringify(act)}; HEAD ${git(root, 'log', '-1', '--format=%h %s')}; shown ${JSON.stringify(api.shown.at(-1))}; tree ${line(paused.alpha)} ${JSON.stringify(context(paused.alpha))}`)

  // 2. A commit from a shell while the box is open: confirming shows act's stale-view refusal,
  // and neither HEAD, the working tree nor the Workstreams view moves.
  const registryFile = join(root, 'workstreams', 'workstreams.json')
  let head = ''
  let status = ''
  api.ui = {
    confirm: async text => {
      asked.push(`${text.message} | ${text.detail}`)
      const reg = JSON.parse(readFileSync(registryFile, 'utf8')) as { workstreams: { id: string; summary?: string }[] }
      const alpha = reg.workstreams.find(w => w.id === 'alpha')
      assert.ok(alpha)
      alpha.summary = 'edited from a shell'
      writeFileSync(registryFile, JSON.stringify(reg, null, 2) + '\n')
      git(root, 'commit', '-qam', 'from a shell')
      head = git(root, 'rev-parse', 'HEAD')
      status = git(root, 'status', '--porcelain')
      return true
    },
    reason: async () => undefined,
  }
  await vscode.commands.executeCommand('workstreams.resume', paused.alpha.node)
  assert.equal(asked.at(-1), 'Resume alpha? | This commits "alpha: resume" on main.')
  assert.match(api.shown.at(-1) ?? '', /^refused: stale view: the registry changed since it was drawn/)
  assert.equal(git(root, 'rev-parse', 'HEAD'), head)
  assert.equal(git(root, 'log', '-1', '--format=%s'), 'from a shell')
  assert.equal(git(root, 'status', '--porcelain'), status)
  await api.settled()
  const after = await drawn(api)
  assert.match(String(after.alpha.item.description), /^0\/3 · paused · /)
  console.log(`stale: shown ${JSON.stringify(api.shown.at(-1))}; HEAD ${git(root, 'log', '-1', '--format=%h %s')} unchanged; status ${JSON.stringify(status)}; tree ${line(after.alpha)}`)

  // A box opened on a row drawn before the latest reload says the write will be refused.
  api.ui = { confirm: async text => { asked.push(`${text.message} | ${text.detail}`); return true }, reason: async () => undefined }
  await vscode.commands.executeCommand('workstreams.resume', paused.alpha.node)
  assert.match(asked.at(-1) ?? '', /This has changed since the tree drew it, so the write will be refused\./)
  assert.match(api.shown.at(-1) ?? '', /^refused: stale view/)
  assert.equal(git(root, 'rev-parse', 'HEAD'), head)
}

async function launches(api: Api, root: string): Promise<void> {
  await api.settled()
  const alpha = (await drawn(api)).alpha.node
  const config = vscode.workspace.getConfiguration('workstreams')
  const reasons: string[] = []
  let answer: string | undefined
  api.ui = { confirm: async () => false, reason: async id => { reasons.push(id); return answer } }

  // 4. With an agent command, Run starts it as the terminal's process: the prompt is one argument.
  await config.update('agentCommand', ['/bin/echo', 'agent:'], vscode.ConfigurationTarget.Global)
  const terminals = vscode.window.terminals.length
  await vscode.commands.executeCommand('workstreams.run', alpha)
  const run = api.launched.at(-1)
  assert.equal(run?.target, 'terminal')
  assert.ok(run?.terminal)
  assert.equal(vscode.window.terminals.length, terminals + 1)
  const options = run.terminal.creationOptions as vscode.TerminalOptions
  assert.equal(options.shellPath, '/bin/echo')
  assert.deepEqual(options.shellArgs, ['agent:', 'Use the ws-run skill to run workstream alpha.'])
  assert.equal(realpathSync(String(options.cwd)), realpathSync(root))
  console.log(`run: terminal ${JSON.stringify(run.terminal.name)} shellPath ${options.shellPath} shellArgs ${JSON.stringify(options.shellArgs)} cwd ${String(options.cwd)}`)

  // Abandon asks for the reason first, and the reason rides in the same one argument.
  answer = 'it\'s "done" elsewhere; $(nothing runs)'
  await vscode.commands.executeCommand('workstreams.abandon', alpha)
  assert.deepEqual(reasons, ['alpha'])
  const abandon = api.launched.at(-1)?.terminal?.creationOptions as vscode.TerminalOptions
  assert.deepEqual(abandon.shellArgs, ['agent:', `Use the ws-coordinate skill to abandon workstream alpha: ${answer}`])
  console.log(`abandon: shellArgs ${JSON.stringify(abandon.shellArgs)}`)

  // 5. With no agent command, Run copies the prompt and starts nothing.
  await config.update('agentCommand', undefined, vscode.ConfigurationTarget.Global)
  const launched = api.launched.length
  const open = vscode.window.terminals.length
  await vscode.commands.executeCommand('workstreams.run', alpha)
  assert.equal(api.launched.at(-1)?.target, 'clipboard')
  assert.equal(await vscode.env.clipboard.readText(), 'Use the ws-run skill to run workstream alpha.')
  assert.equal(vscode.window.terminals.length, open)
  console.log(`run, no agent: shown ${JSON.stringify(api.shown.at(-1))}; clipboard ${JSON.stringify(await vscode.env.clipboard.readText())}`)

  // Abandon asks first: no reason, nothing copied; a reason, its prompt copied.
  answer = undefined
  await vscode.commands.executeCommand('workstreams.abandon', alpha)
  assert.deepEqual(reasons, ['alpha', 'alpha'])
  assert.equal(api.launched.length, launched + 1)
  assert.equal(await vscode.env.clipboard.readText(), 'Use the ws-run skill to run workstream alpha.')
  answer = 'superseded'
  await vscode.commands.executeCommand('workstreams.abandon', alpha)
  assert.equal(api.launched.at(-1)?.target, 'clipboard')
  assert.equal(await vscode.env.clipboard.readText(), 'Use the ws-coordinate skill to abandon workstream alpha: superseded')
  assert.equal(vscode.window.terminals.length, open)
  console.log(`abandon, no agent: reasons asked ${reasons.length}; clipboard ${JSON.stringify(await vscode.env.clipboard.readText())}`)
}

type HItem = { node: HealthNode; item: vscode.TreeItem; children: HItem[] }

async function walkHealth(tree: NonNullable<Api['health']>, node?: HealthNode): Promise<HItem[]> {
  const found: HItem[] = []
  for (const child of await tree.getChildren(node)) {
    const item = tree.getTreeItem(child)
    const children = item.collapsibleState === vscode.TreeItemCollapsibleState.None ? [] : await walkHealth(tree, child)
    found.push({ node: child, item, children })
  }
  return found
}

const STALE = /^A-1 .*/
const staleIn = (items: HItem[]) => items.flatMap(i => i.children).find(i => i.node.kind === 'finding' && i.node.finding.kind === 'stale-claim')

async function healthAndBudget(api: Api, root: string): Promise<void> {
  const tree = api.health
  assert.ok(tree)
  await api.settled()
  const asked: string[] = []
  api.ui = { confirm: async text => { asked.push(`${text.message} | ${text.detail}`); return true }, reason: async () => undefined }

  // 1. A-1's stale claim is in the Health tree, offering unclaim, and in the Problems panel at
  // line 1 of alpha's tasks file.
  const top = await walkHealth(tree)
  const finding = staleIn(top)
  assert.ok(finding, JSON.stringify(top.map(i => [String(i.item.label), i.children.map(c => String(c.item.label))])))
  assert.match(String(finding.item.label), STALE)
  assert.equal(String(finding.item.description), 'stale-claim · alpha A-1')
  assert.equal(finding.item.contextValue, 'finding act:unclaim')
  console.log(`health tree: ${JSON.stringify(top.map(i => [`${String(i.item.label)} | ${String(i.item.description)}`, i.children.map(c => `${String(c.item.label)} | ${String(c.item.description)} | ${String(c.item.contextValue)}`)]))}`)
  const queue = vscode.Uri.file(join(root, 'workstreams', 'alpha', 'tasks_list.json'))
  const stale = (diags: vscode.Diagnostic[]) => diags.find(d => d.source === 'workstreams' && d.code === 'stale-claim')
  const diagnostic = await until('the stale claim in the Problems panel', async () => stale(vscode.languages.getDiagnostics(queue)))
  assert.equal(diagnostic.message, String(finding.item.label))
  assert.equal(diagnostic.range.start.line, 0)
  assert.equal(diagnostic.severity, vscode.DiagnosticSeverity.Warning)
  console.log(`diagnostics on ${queue.fsPath}: ${JSON.stringify(vscode.languages.getDiagnostics(queue).map(d => [d.range.start.line, vscode.DiagnosticSeverity[d.severity], d.code, d.message]))}`)

  // 2. Its quick fix runs the same Unclaim command, so the same confirm, then ws act unclaims.
  // The lightbulb asks for code actions on an open document, so open it as a click would.
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(queue), { preview: true })
  const fixes = await vscode.commands.executeCommand<vscode.CodeAction[]>('vscode.executeCodeActionProvider', queue, new vscode.Range(0, 0, 0, 0))
  const fix = fixes.find(a => a.title === 'Unclaim A-1')
  assert.ok(fix?.command, JSON.stringify(fixes.map(a => a.title)))
  assert.equal(fix.command.command, 'workstreams.unclaim')
  const before = git(root, 'rev-parse', 'HEAD')
  const ranBefore = api.ran.length
  await vscode.commands.executeCommand(fix.command.command, ...(fix.command.arguments ?? []))
  assert.deepEqual(asked, ['Unclaim A-1? | This commits "alpha: unclaim A-1" on main.'])
  const act = api.ran.slice(ranBefore).find(argv => argv.includes('act'))
  assert.ok(act)
  assert.deepEqual(act.slice(BRANCH_CLI.length, BRANCH_CLI.length + 6), ['act', 'unclaim', '-w', 'alpha', '--task', 'A-1'])
  assert.equal(git(root, 'rev-parse', 'HEAD~1'), before)
  assert.equal(git(root, 'log', '-1', '--format=%s'), 'alpha: unclaim A-1 (ws act)')
  assert.equal(git(root, 'status', '--porcelain'), '')
  const a1 = (JSON.parse(readFileSync(queue.fsPath, 'utf8')) as { tasks: { id: string; status: string }[] }).tasks.find(t => t.id === 'A-1')
  assert.equal(a1?.status, 'todo')
  console.log(`quick fix: ${JSON.stringify(fixes.map(a => a.title))} ran ${JSON.stringify(act)}; asked ${JSON.stringify(asked)}; HEAD ${git(root, 'log', '-1', '--format=%h %s')}; shown ${JSON.stringify(api.shown.at(-1))}`)

  // 3. The finding went, so its diagnostic and its tree item clear.
  await until('the diagnostic to clear', async () => (stale(vscode.languages.getDiagnostics(queue)) ? undefined : true))
  await api.settled()
  assert.equal(staleIn(await walkHealth(tree)), undefined)
  console.log(`after the unclaim: diagnostics ${JSON.stringify(vscode.languages.getDiagnostics(queue).map(d => d.message))}; health ${JSON.stringify((await walkHealth(tree)).map(i => [String(i.item.label), i.children.map(c => String(c.item.label))]))}`)

  // 4. Budget: nothing ran audit while its view was out of sight, not even a Refresh. Shown, it
  // runs once and draws each role's used against limit as the CLI printed them.
  const audits = () => api.ran.filter(argv => argv.slice(BRANCH_CLI.length).join(' ') === 'audit context --json').length
  assert.equal(audits(), 0)
  await vscode.commands.executeCommand('workstreams.refresh')
  assert.equal(audits(), 0)
  await vscode.commands.executeCommand('workstreams.budget.focus')
  const rows = await until('the budget rows', async () => api.budget?.rows[root])
  assert.equal(audits(), 1)
  const expected = JSON.parse(execFileSync(BRANCH_CLI[0], [...BRANCH_CLI.slice(1), 'audit', 'context', '--json'], { cwd: root, encoding: 'utf8' })) as { role: string; tokens: number; budget: number }[]
  assert.deepEqual(rows.map(r => [r.role, r.tokens, r.budget]), expected.map(r => [r.role, r.tokens, r.budget]))
  const budget = api.budget
  assert.ok(budget)
  const drawnRows = (await budget.getChildren()).map(n => budget.getTreeItem(n))
  assert.deepEqual(drawnRows.map(i => String(i.label)), expected.map(r => r.role))
  for (const [i, r] of expected.entries()) {
    assert.match(String(drawnRows[i].description), new RegExp(`^${r.tokens.toLocaleString('en-US')} / ${r.budget.toLocaleString('en-US')} · \\d+%`))
  }
  console.log(`budget: audit ran ${audits()} time(s) once shown; rows ${JSON.stringify(drawnRows.map(i => `${String(i.label)} | ${String(i.description)}`))}`)
  await vscode.commands.executeCommand('workbench.view.explorer')
  await until('the budget view hidden', async () => (audits() === 1 ? true : undefined))
  await vscode.commands.executeCommand('workstreams.refresh')
  assert.equal(audits(), 1)
  console.log(`budget hidden: a Refresh ran audit ${audits()} time(s) in all`)
}

type RItem = { node: ReviewNode; item: vscode.TreeItem; children: RItem[] }

// The Review tree, every node opened, as VS Code would draw it.
async function walkReview(tree: NonNullable<Api['review']>, node?: ReviewNode): Promise<RItem[]> {
  const found: RItem[] = []
  for (const child of await tree.getChildren(node)) {
    const item = tree.getTreeItem(child)
    const children = item.collapsibleState === vscode.TreeItemCollapsibleState.None ? [] : await walkReview(tree, child)
    found.push({ node: child, item, children })
  }
  return found
}

const rlabel = (i: RItem) => String(i.item.label)
const rline = (i: RItem) => `${rlabel(i)} | ${String(i.item.description ?? '')}`
const byLabel = (items: RItem[], name: string) => {
  const got = items.find(i => rlabel(i) === name)
  assert.ok(got, `no ${name} in ${JSON.stringify(items.map(rlabel))}`)
  return got
}

type ShowJson = { path: string; side: string; rev: string; text: string | null; binary: boolean }

async function reviewQueue(api: Api, root: string): Promise<void> {
  const tree = api.review
  assert.ok(tree)
  await api.settled()
  const cli = (...args: string[]) => execFileSync(BRANCH_CLI[0], [...BRANCH_CLI.slice(1), ...args], { cwd: root, encoding: 'utf8' })

  // 2. Branch work first, then landed work.
  const top = await walkReview(tree)
  assert.deepEqual(top.map(rlabel), ['On a branch', 'Landed'])
  assert.deepEqual(top.map(g => g.children.map(rlabel)), [['R-1 On a branch'], ['R-2 Landed']])
  const queue = JSON.parse(cli('review', '--queue')) as { tasks: { task: string; state: string }[] }
  assert.deepEqual(queue.tasks.map(t => [t.task, t.state]), [['R-1', 'branch'], ['R-2', 'landed']])
  console.log(`queue: ${JSON.stringify(top.map(g => [rline(g), g.children.map(rline)]))}`)

  const r1 = top[0].children[0].children
  console.log(`R-1: ${JSON.stringify(r1.map(i => [rline(i), i.children.map(rline)]))}`)
  assert.match(rlabel(r1[0]), /^branch: [0-9a-f]{10}\.\.\.task\/r-1$/)
  assert.match(rlabel(r1[1]), /would stop this landing|Would land|Every check passes/)
  assert.ok(r1[1].children.length > 0)

  // 5. Each acceptance item shows its proof, or that it has none; the proof stays text.
  const items = byLabel(r1, 'Acceptance and proof')
  assert.deepEqual(items.children.map(rline), [
    '1. the sides match | `diff` printed "same" <b>bold</b> [x](command:workbench.action.quit)',
    '2. a binary file says so | Nothing quoted.',
  ])
  const tip = items.children[0].item.tooltip as vscode.MarkdownString
  assert.ok(!tip.isTrusted)
  assert.equal(tip.supportHtml, false)
  assert.ok(!tip.value.includes('](command:'), tip.value)
  assert.ok(!tip.value.includes('<b>'), tip.value)
  console.log(`proof tooltip: ${JSON.stringify(tip.value)}`)

  // 3. A file of a branch task, opened after main moved: the diff editor's sides are
  // `ws review --show` old and new, and the old side is the merge base, not main's tip.
  const files = byLabel(r1, 'Files').children
  assert.deepEqual(files.map(rline), ['added.txt | +1 −0', 'blob.bin | binary', 'shared.txt | +1 −1', 'workstreams/alpha/evidence/R-1.md | +20 −0'])
  const show = (path: string, side: string) => JSON.parse(cli('review', 'R-1', '-w', 'alpha', '--show', path, '--side', side)) as ShowJson
  const openDiff = async (file: RItem) => {
    const command = file.item.command
    assert.ok(command)
    await vscode.commands.executeCommand(command.command, ...(command.arguments ?? []))
    const opened = api.opened.at(-1)
    assert.ok(opened?.kind === 'diff', JSON.stringify(opened))
    const tab = await until(`the diff of ${rlabel(file)}`, async () => {
      const input = vscode.window.tabGroups.activeTabGroup.activeTab?.input
      return input instanceof vscode.TabInputTextDiff && input.modified.toString() === opened.right.toString() ? input : undefined
    })
    const left = (await vscode.workspace.openTextDocument(tab.original)).getText()
    const right = (await vscode.workspace.openTextDocument(tab.modified)).getText()
    return { title: opened.title, left, right, tab }
  }
  const shared = await openDiff(byLabel(files, 'shared.txt'))
  const [old, now] = [show('shared.txt', 'old'), show('shared.txt', 'new')]
  assert.equal(shared.left, old.text)
  assert.equal(shared.right, now.text)
  assert.equal(shared.left, 'one\ntwo\nthree\n')
  assert.equal(shared.right, 'one\nTWO\nthree\n')
  const mainTip = git(root, 'show', 'main:shared.txt')
  assert.notEqual(shared.left.trim(), mainTip)
  assert.equal(old.rev, git(root, 'merge-base', 'main', 'task/r-1'))
  assert.equal(shared.tab.original.scheme, 'ws-review')
  console.log(`shared.txt: tab ${JSON.stringify(shared.title)}; left ${JSON.stringify(shared.left)} = --show old ${JSON.stringify(old.text)} at ${old.rev}; right ${JSON.stringify(shared.right)} = --show new ${JSON.stringify(now.text)}; main's tip ${JSON.stringify(mainTip)}`)

  // 4. An added file's old side is empty; a binary file opens no diff and says so.
  const added = await openDiff(byLabel(files, 'added.txt'))
  assert.equal(show('added.txt', 'old').text, null)
  assert.deepEqual([added.left, added.right], ['', 'a new file\n'])
  console.log(`added.txt: left ${JSON.stringify(added.left)}, right ${JSON.stringify(added.right)}`)
  const before = vscode.window.tabGroups.all.flatMap(g => g.tabs).length
  const blob = byLabel(files, 'blob.bin').item.command
  assert.ok(blob)
  await vscode.commands.executeCommand(blob.command, ...(blob.arguments ?? []))
  assert.deepEqual(api.opened.at(-1), { kind: 'binary', text: 'blob.bin is binary, so no diff opens.' })
  assert.equal(api.shown.at(-1), 'blob.bin is binary, so no diff opens.')
  assert.equal(vscode.window.tabGroups.all.flatMap(g => g.tabs).length, before)
  assert.equal(show('blob.bin', 'new').binary, true)
  console.log(`blob.bin: shown ${JSON.stringify(api.shown.at(-1))}; tabs ${before} before and after`)

  // 5. The evidence opens in the editor: a branch's from the branch, read-only; a landed one's
  // as the file itself.
  const openEvidence = async (item: RItem) => {
    const command = item.item.command
    assert.ok(command)
    await vscode.commands.executeCommand(command.command, ...(command.arguments ?? []))
    const opened = api.opened.at(-1)
    assert.ok(opened?.kind === 'evidence', JSON.stringify(opened))
    const editor = await until('the evidence in an editor', async () => {
      const active = vscode.window.activeTextEditor
      return active?.document.uri.toString() === opened.uri.toString() ? active : undefined
    })
    return editor.document
  }
  const branchEvidence = await openEvidence(byLabel(r1, 'Evidence'))
  assert.equal(branchEvidence.uri.scheme, 'ws-review')
  assert.equal(branchEvidence.getText(), git(root, 'show', 'task/r-1:workstreams/alpha/evidence/R-1.md') + '\n')
  console.log(`R-1 evidence: ${branchEvidence.uri.toString()} (${branchEvidence.languageId}), ${branchEvidence.getText().length} chars, same as the branch's file`)

  const r2 = top[1].children[0].children
  console.log(`R-2: ${JSON.stringify(r2.map(i => [rline(i), i.children.map(rline)]))}`)
  assert.match(rlabel(r2[1]), /^Landed as [0-9a-f]{10}\. Its gates ran when it landed\.$/)
  assert.deepEqual(byLabel(r2, 'Acceptance and proof').children.map(rline), ['1. it landed | `git log` shows it'])
  const landedEvidence = await openEvidence(byLabel(r2, 'Evidence'))
  assert.equal(landedEvidence.uri.scheme, 'file')
  assert.equal(realpathSync(landedEvidence.uri.fsPath), realpathSync(join(root, 'workstreams', 'alpha', 'evidence', 'R-2.md')))
  console.log(`R-2 evidence: ${landedEvidence.uri.fsPath}`)
}
