// Runs inside VS Code's extension host. No test framework: `run` throws on the first failure,
// which @vscode/test-electron reports as a failed run.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync, realpathSync, writeFileSync } from 'node:fs'
import { join, sep } from 'node:path'

import * as vscode from 'vscode'

import type { Api } from '../../src/extension.ts'
import type { Node } from '../../src/logic/registry.ts'

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
    await registryTree(api, started.roots[0])
    await writes(api, started.roots[0])
    await launches(api, started.roots[0])
  } else if (which === 'plain') {
    assert.deepEqual(api.ran, [[...BRANCH_CLI, 'root']])
    assert.equal(api.shown.length, 1)
    assert.match(api.shown[0], /is not a workstream project/)
    assert.equal(started.message?.level, 'info')
    assert.deepEqual(started.roots, [])
    assert.deepEqual(await api.tree?.getChildren(), [])
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

type Tree = NonNullable<Api['tree']>
type Item = { node: Node; item: vscode.TreeItem; children: Item[] }

// The whole tree as VS Code would draw it: every node, its item and its children.
async function walk(tree: Tree, node?: Node): Promise<Item[]> {
  const found: Item[] = []
  for (const child of await tree.getChildren(node)) {
    const item = tree.getTreeItem(child)
    const children = item.collapsibleState === vscode.TreeItemCollapsibleState.None ? [] : await walk(tree, child)
    found.push({ node: child, item, children })
  }
  return found
}

const label = (i: Item) => String(i.item.label)
const line = (i: Item) => `${label(i)} | ${String(i.item.description ?? '')}`

async function until<T>(what: string, get: () => Promise<T | undefined>, ms = 20_000): Promise<T> {
  const end = Date.now() + ms
  for (;;) {
    const got = await get()
    if (got !== undefined) return got
    if (Date.now() > end) throw new Error(`timed out waiting for ${what}`)
    await new Promise(r => setTimeout(r, 200))
  }
}

async function registryTree(api: Api, root: string): Promise<void> {
  const tree = api.tree
  assert.ok(tree)
  await api.settled()
  const top = await walk(tree)
  // Open workstreams only; alpha opens to its wave line, phases in order, tasks by priority.
  assert.deepEqual(top.map(label), ['alpha'])
  assert.match(String(top[0].item.description), /^active · 0\/3 · \d+ errors?$/)
  const alpha = top[0].children
  assert.deepEqual(alpha.map(label), ['Phase 1: 1 ready', 'Phase 1', 'Phase 2', 'Documents'])
  assert.deepEqual(alpha[1].children.map(line), ['A-1 First | todo · ★ ready', 'A-2 Second | todo · foreground · needs decision'])
  assert.deepEqual(alpha[2].children.map(line), ['A-3 Third | todo · waits on A-1'])
  console.log(`tree: ${JSON.stringify(top.map(line))} ${JSON.stringify(alpha.map(i => [line(i), i.children.map(line)]))}`)

  // A task's tooltip is text: the summary's link and HTML come out escaped, and nothing is trusted.
  const tip = alpha[1].children[0].item.tooltip as vscode.MarkdownString
  assert.ok(tip instanceof vscode.MarkdownString)
  assert.ok(!tip.isTrusted)
  assert.equal(tip.supportHtml, false)
  assert.ok(!tip.value.includes('[x](command:'), tip.value)
  assert.ok(!tip.value.includes('<b>'), tip.value)
  assert.match(tip.value, /Acceptance/)
  assert.match(tip.value, /it(&nbsp;| )works/)
  console.log(`tooltip: ${JSON.stringify(tip.value)}`)

  // The status bar: the active workstream's wave line and error count, focusing the view.
  assert.match(api.statusBar?.text ?? '', /^\$\(checklist\) alpha: Phase 1: 1 ready · \d+ errors?$/)
  assert.equal(api.statusBar?.command, 'workstreams.registry.focus')
  console.log(`status bar: ${api.statusBar?.text}`)

  // Show done adds the closed one after the open ones; Hide done takes it away again.
  await vscode.commands.executeCommand('workstreams.showDone')
  assert.deepEqual((await walk(tree)).map(line).map(l => l.split(' | ')[0]), ['alpha', 'beta'])
  assert.match(line((await walk(tree))[1]), /^beta \| abandoned/)
  await vscode.commands.executeCommand('workstreams.hideDone')
  assert.deepEqual((await walk(tree)).map(label), ['alpha'])

  // Each document opens in Markdown preview, from the snapshot's path.
  const docs = alpha[3].children
  assert.deepEqual(docs.map(label), ['Plan', 'Progress', 'Decisions', 'Handoff'])
  for (const doc of docs) {
    const command = doc.item.command
    assert.ok(command)
    await vscode.commands.executeCommand(command.command, ...(command.arguments ?? []))
    const name = (doc.node as { path: string }).path.split(sep).pop() ?? ''
    const tab = await until(`a preview of ${name}`, async () => vscode.window.tabGroups.all.flatMap(g => g.tabs).find(t =>
      t.input instanceof vscode.TabInputWebview && t.input.viewType.includes('markdown.preview') && t.label.includes(name)))
    console.log(`document ${label(doc)}: tab ${JSON.stringify(tab.label)} (${(tab.input as vscode.TabInputWebview).viewType})`)
  }

  // A claim from a shell reaches the tree with no Refresh pressed: the watchers reload it.
  const before = api.reloads.length
  execFileSync(BRANCH_CLI[0], [...BRANCH_CLI.slice(1), 'claim', 'A-1', '-w', 'alpha'], { cwd: root, encoding: 'utf8' })
  const claimed = await until('the claim in the tree', async () => {
    const task = (await walk(tree))[0]?.children[1]?.children[0]
    return task && /^in-progress · claimed \dm$/.test(String(task.item.description)) ? line(task) : undefined
  })
  assert.ok(api.reloads.length > before)
  assert.ok(api.reloads.slice(before).every(why => why === 'watch'), JSON.stringify(api.reloads))
  console.log(`after the claim: ${claimed}; reloads ${JSON.stringify(api.reloads.slice(before))}; status bar ${api.statusBar?.text}`)
}

const git = (root: string, ...args: string[]) => execFileSync('git', args, { cwd: root, encoding: 'utf8' }).trim()
const context = (i: Item | undefined) => String(i?.item.contextValue ?? '')

// The alpha row, its first phase's tasks, and every row with Show done on, as drawn now.
async function drawn(tree: Tree) {
  const top = await walk(tree)
  return { alpha: top[0], tasks: top[0]?.children[1]?.children ?? [] }
}

async function writes(api: Api, root: string): Promise<void> {
  const tree = api.tree
  assert.ok(tree)
  // The claim left the queue dirty, which act refuses; commit it as an orchestrator would.
  git(root, 'commit', '-qam', 'claim A-1')
  await vscode.commands.executeCommand('workstreams.refresh')
  await api.settled()

  // Commands follow the snapshot's offers: alpha (active) offers pause and the launches, a fresh
  // claim offers no unclaim, and a closed row offers nothing.
  let now = await drawn(tree)
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
    const got = await drawn(tree)
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
  const pinned = (now.alpha.node as Extract<Node, { kind: 'workstream' }>).revisions
  assert.deepEqual(act.slice(BRANCH_CLI.length + 4), ['--expect-registry', pinned.registry, '--expect-tasks', pinned.tasks.alpha])
  assert.equal(git(root, 'rev-parse', 'HEAD~1'), before)
  assert.equal(git(root, 'log', '-1', '--format=%s'), 'alpha: pause (ws act)')
  assert.equal(git(root, 'status', '--porcelain'), '')
  const paused = await until('alpha paused in the tree', async () => {
    const got = await drawn(tree)
    return /^paused · /.test(String(got.alpha?.item.description)) ? got : undefined
  })
  assert.match(context(paused.alpha), /^workstream act:resume( act:sync)? launch$/)
  console.log(`pause: ran ${JSON.stringify(act)}; HEAD ${git(root, 'log', '-1', '--format=%h %s')}; shown ${JSON.stringify(api.shown.at(-1))}; tree ${line(paused.alpha)} ${JSON.stringify(context(paused.alpha))}`)

  // 2. A commit from a shell while the box is open: confirming shows act's stale-view refusal,
  // and neither HEAD, the working tree nor the Registry tree moves.
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
  const after = await drawn(tree)
  assert.match(String(after.alpha.item.description), /^paused · /)
  console.log(`stale: shown ${JSON.stringify(api.shown.at(-1))}; HEAD ${git(root, 'log', '-1', '--format=%h %s')} unchanged; status ${JSON.stringify(status)}; tree ${line(after.alpha)}`)

  // A box opened on a row drawn before the latest reload says the write will be refused.
  api.ui = { confirm: async text => { asked.push(`${text.message} | ${text.detail}`); return true }, reason: async () => undefined }
  await vscode.commands.executeCommand('workstreams.resume', paused.alpha.node)
  assert.match(asked.at(-1) ?? '', /This has changed since the tree drew it, so the write will be refused\./)
  assert.match(api.shown.at(-1) ?? '', /^refused: stale view/)
  assert.equal(git(root, 'rev-parse', 'HEAD'), head)
}

async function launches(api: Api, root: string): Promise<void> {
  const tree = api.tree
  assert.ok(tree)
  await api.settled()
  const alpha = (await drawn(tree)).alpha.node
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
