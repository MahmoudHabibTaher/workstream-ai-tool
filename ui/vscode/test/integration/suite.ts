// Runs inside VS Code's extension host. No test framework: `run` throws on the first failure,
// which @vscode/test-electron reports as a failed run.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { realpathSync } from 'node:fs'
import { sep } from 'node:path'

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
