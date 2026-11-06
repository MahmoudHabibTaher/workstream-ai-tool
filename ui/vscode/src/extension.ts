// Activation: read the `ws` argv setting, find the window's projects, load their snapshots, then
// draw the Registry and Review trees and the status bar and keep them current. Every fact comes from the CLI
// through cli.ts; nothing here works one out.
import * as vscode from 'vscode'

import { type Cli, execRun, makeCli, type Run } from './cli.ts'
import { nativeUi, registerCommands, type Ui } from './commands.ts'
import type { Started as Launched } from './launch.ts'
import type { ConfirmText } from './logic/actions.ts'
import { debounce } from './logic/debounce.ts'
import { activeWorkstream, type Node, statusText } from './logic/registry.ts'
import { start, type Started } from './logic/start.ts'
import { Store } from './logic/store.ts'
import { OPEN_DOCUMENT, openDocument, RegistryTree } from './views/registry.ts'
import {
  OPEN_EVIDENCE, OPEN_FILE, openEvidence, openFile, type Opened, REVIEW_VIEW, ReviewDocuments, ReviewTree, SCHEME,
} from './views/review.ts'
import { Watchers } from './watch.ts'

export const REGISTRY_VIEW = 'workstreams.registry'
const REFRESH = 'workstreams.refresh'
const SHOW_DONE = 'workstreams.showDone'
const HIDE_DONE = 'workstreams.hideDone'
const SHOW_DONE_KEY = 'workstreams.showDone'
const DEBOUNCE_MS = 300

// What activate returns: the state the views draw, every argv run and every message shown, so
// the integration test can see what the extension did. `reloads` says why each reload ran.
// `asked` holds each confirm box's text and `launched` each launch; `ui` answers the boxes, and
// the test may replace it, since a modal can't be clicked from the extension API. `opened` holds
// what each review file or evidence click opened, or why it opened nothing.
export type Api = {
  ready: Promise<Started>
  ran: string[][]
  shown: string[]
  reloads: ('watch' | 'button' | 'act')[]
  asked: ConfirmText[]
  launched: Launched[]
  opened: Opened[]
  ui: Ui
  store?: Store
  tree?: RegistryTree
  review?: ReviewTree
  statusBar?: vscode.StatusBarItem
  settled: () => Promise<void>
}

export function activate(context: vscode.ExtensionContext): Api {
  const ran: string[][] = []
  const recorded: Run = (argv, cwd) => {
    ran.push(argv)
    return execRun(argv, cwd)
  }
  const command = vscode.workspace.getConfiguration('workstreams').get<string[]>('wsCommand', ['ws'])
  const cli: Cli = makeCli(command, recorded)
  const folders = (vscode.workspace.workspaceFolders ?? []).map(f => f.uri.fsPath)
  const shown: string[] = []
  let pending: Promise<void> = Promise.resolve()
  const api = { ran, shown, reloads: [], asked: [], launched: [], opened: [], ui: nativeUi, settled: () => pending } as unknown as Api

  const show = (started: Started): Started => {
    const message = started.message
    if (message) shown.push(message.text)
    if (message?.level === 'error') void vscode.window.showErrorMessage(message.text)
    else if (message) void vscode.window.showInformationMessage(message.text)
    for (const [root, error] of Object.entries(started.errors)) {
      shown.push(`${root}: ${error}`)
      void vscode.window.showErrorMessage(`${root}: ${error}`)
    }
    return started
  }

  const draw = (started: Started): Started => {
    const store = new Store(cli, started)
    const tree = new RegistryTree(store)
    const review = new ReviewTree(store)
    const docs = new ReviewDocuments(cli, store)
    const say = (text: string, error?: boolean) => {
      shown.push(text)
      if (error) void vscode.window.showErrorMessage(text)
      else void vscode.window.showInformationMessage(text)
    }
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50)
    statusBar.name = 'Workstreams'
    statusBar.command = `${REGISTRY_VIEW}.focus`
    const watchers = new Watchers(() => reload.poke())
    const reloadNow = async () => {
      api.reloads.push('watch')
      await store.reload()
    }
    const reload = debounce(() => (pending = reloadNow()), DEBOUNCE_MS)

    const paint = async () => {
      watchers.watch(store.refreshPaths())
      const active = activeWorkstream(store.roots, store.snapshots)
      if (!active) {
        statusBar.hide()
        return
      }
      const got = await store.workstream(active.root, active.row.id)
      statusBar.text = `$(checklist) ${statusText(active.row.id, got.value?.wave, active.errors)}`
      statusBar.tooltip = 'Show the Workstreams view'
      statusBar.show()
    }
    store.onChange(() => void (pending = pending.then(paint)))
    pending = paint()

    context.subscriptions.push(
      vscode.window.createTreeView(REGISTRY_VIEW, { treeDataProvider: tree, showCollapseAll: true }),
      vscode.window.createTreeView(REVIEW_VIEW, { treeDataProvider: review, showCollapseAll: true }),
      vscode.workspace.registerTextDocumentContentProvider(SCHEME, docs),
      vscode.commands.registerCommand(OPEN_FILE, async (node: Parameters<typeof openFile>[2]) => {
        api.opened.push(await openFile(cli, docs, node, say))
      }),
      vscode.commands.registerCommand(OPEN_EVIDENCE, async (node: Parameters<typeof openEvidence>[0]) => {
        api.opened.push(await openEvidence(node))
      }),
      statusBar,
      watchers,
      { dispose: reload.dispose },
      vscode.commands.registerCommand(REFRESH, async () => {
        api.reloads.push('button')
        await (pending = store.reload())
        await pending
      }),
      vscode.commands.registerCommand(SHOW_DONE, () => setShowDone(true)),
      vscode.commands.registerCommand(HIDE_DONE, () => setShowDone(false)),
      vscode.commands.registerCommand(OPEN_DOCUMENT, (node: Extract<Node, { kind: 'document' }>) => openDocument(node)),
      ...registerCommands(cli, store, async () => {
        api.reloads.push('act')
        await (pending = store.reload())
      }, {
        get ui() { return api.ui },
        asked: api.asked,
        launched: api.launched,
        say,
      }),
    )
    const setShowDone = async (on: boolean) => {
      store.setShowDone(on)
      await vscode.commands.executeCommand('setContext', SHOW_DONE_KEY, on)
    }
    void vscode.commands.executeCommand('setContext', SHOW_DONE_KEY, false)
    Object.assign(api, { store, tree, review, statusBar })
    return started
  }

  const started = folders.length ? start(cli, folders).then(show) : Promise.resolve<Started>({ roots: [], snapshots: {}, errors: {} })
  api.ready = started.then(draw)
  return api
}

export function deactivate(): void {}
