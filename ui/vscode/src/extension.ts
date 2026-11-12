// Activation: read the `ws` argv setting, find the window's projects, load their snapshots, then
// draw the Workstreams, Tasks, Task, Graph, Overview, Review, Health and Budget trees, the Problems panel and the status bar and keep them current. Every fact comes from the CLI
// through cli.ts; nothing here works one out.
import * as vscode from 'vscode'

import { chatHost } from './chat.ts'
import { type Cli, execRun, makeCli, type Run } from './cli.ts'
import { nativeUi, registerCommands, type Ui } from './commands.ts'
import { type Started as Launched, terminalHost } from './launch.ts'
import { type FlowUi, nativeFlowUi } from './launchFlow.ts'
import { type ConfirmText, contextValue, type Picked } from './logic/actions.ts'
import { listRows, taskLanes } from './logic/detail.ts'
import { claimedTask, claimLine } from './logic/format.ts'
import { debounce } from './logic/debounce.ts'
import { activeWorkstream, statusText } from './logic/registry.ts'
import { start, type Started } from './logic/start.ts'
import { Store } from './logic/store.ts'
import { BUDGET_VIEW, BudgetTree, HEALTH_VIEW, HealthDiagnostics, HealthTree } from './views/health.ts'
import {
  OPEN_EVIDENCE, OPEN_FILE, openEvidence, openFile, type Opened, REVIEW_VIEW, ReviewDocuments, ReviewTree, SCHEME,
} from './views/review.ts'
import { GRAPH_VIEW, GraphTree } from './views/graph.ts'
import { OVERVIEW_VIEW, OverviewTree } from './views/overview.ts'
import { TASK_VIEW, TaskTree } from './views/task.ts'
import { SELECT_TASK, type TaskNode, TASKS_VIEW, TasksTree } from './views/tasks.ts'
import { LIST_VIEW, SELECT_WORKSTREAM, type WorkstreamNode, WorkstreamsTree } from './views/workstreams.ts'
import { Watchers } from './watch.ts'

const REFRESH = 'workstreams.refresh'
const SHOW_DONE = 'workstreams.showDone'
const HIDE_DONE = 'workstreams.hideDone'
const SHOW_DONE_KEY = 'workstreams.showDone'
// Set while a workstream is selected; the Tasks, Task, Graph and Overview views show only then (plan T2).
const SELECTED_KEY = 'workstreams.selected'
// The selected workstream's and task's contextValues, which the linked views' title menus match
// as the item menus match `viewItem`; empty when nothing is selected or the selection isn't drawn.
const SELECTED_ITEM_KEY = 'workstreams.selectedItem'
const SELECTED_TASK_ITEM_KEY = 'workstreams.selectedTaskItem'
// Set while some root has a snapshot; the welcome views tell "no project" from "nothing here".
const HAS_PROJECT_KEY = 'workstreams.hasProject'
const DEBOUNCE_MS = 300
// The status bar redraws a claim's age this often.
const AGE_MS = 60_000

// What activate returns: the state the views draw, every argv run and every message shown, so
// the integration test can see what the extension did. `reloads` says why each reload ran.
// `asked` holds each confirm box's text and `launched` each launch; `ui` answers the boxes, and
// the test may replace it, since a modal can't be clicked from the extension API. `opened` holds
// what each review file or evidence click opened, or why it opened nothing. `health`, `diagnostics`
// and `budget` are the Health tree, its Problems panel entries and the Budget tree. `list`, `tasks`
// and `task` are the Workstreams, Tasks and Task trees, and `graph` and `overview` the Graph and
// Overview trees, all linked through the store's selection. `picked` is the selected workstream's
// and task's items as last drawn, which a linked view's title menu acts on. `flowUi` answers the
// launch flow's quick picks, `terminalHost` makes its terminals and `chatHost` is what the chat
// targets ask of VS Code; the test may replace all three.
export type Api = {
  ready: Promise<Started>
  ran: string[][]
  shown: string[]
  reloads: ('watch' | 'button' | 'act')[]
  asked: ConfirmText[]
  launched: Launched[]
  opened: Opened[]
  ui: Ui
  flowUi: FlowUi
  terminalHost: typeof terminalHost
  chatHost: typeof chatHost
  store?: Store
  list?: WorkstreamsTree
  tasks?: TasksTree
  task?: TaskTree
  graph?: GraphTree
  overview?: OverviewTree
  review?: ReviewTree
  health?: HealthTree
  diagnostics?: HealthDiagnostics
  budget?: BudgetTree
  statusBar?: vscode.StatusBarItem
  picked: Picked<WorkstreamNode, TaskNode>
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
  const api = { ran, shown, reloads: [], asked: [], launched: [], opened: [], ui: nativeUi, flowUi: nativeFlowUi, terminalHost, chatHost, picked: {}, settled: () => pending } as unknown as Api

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
    const list = new WorkstreamsTree(store)
    const tasks = new TasksTree(store)
    const task = new TaskTree(store)
    const tasksView = vscode.window.createTreeView(TASKS_VIEW, { treeDataProvider: tasks, showCollapseAll: true })
    const taskView = vscode.window.createTreeView(TASK_VIEW, { treeDataProvider: task })
    const graph = new GraphTree(store)
    const overview = new OverviewTree(store)
    const graphView = vscode.window.createTreeView(GRAPH_VIEW, { treeDataProvider: graph, showCollapseAll: true })
    const overviewView = vscode.window.createTreeView(OVERVIEW_VIEW, { treeDataProvider: overview, showCollapseAll: true })
    // A selection names its workstream and task in the views' titles, and shows the linked views.
    store.onSelect(() => {
      tasksView.description = store.selected?.ws
      taskView.description = store.selectedTask
      graphView.description = store.selected?.ws
      overviewView.description = store.selected?.ws
      void vscode.commands.executeCommand('setContext', SELECTED_KEY, Boolean(store.selected))
      pending = pending.then(pick)
    })
    // The selected workstream's item from the root snapshot and the selected task's from the
    // workstream's own, built as the Workstreams and Tasks views build them, with the same offers.
    const pick = async () => {
      const picked: Api['picked'] = {}
      const selected = store.selected
      const snapshot = selected && store.snapshots[selected.root]
      if (selected && snapshot) {
        const row = listRows(selected.root, snapshot, true).find(r => r.row.id === selected.ws)
        if (row) picked.workstream = { ...row, kind: 'workstream' }
        const id = store.selectedTask
        const got = row && id ? await store.workstream(selected.root, selected.ws) : undefined
        const task = got?.value && taskLanes(selected.root, selected.ws, got.value, Date.now()).flatMap(l => l.tasks).find(t => t.task.id === id)
        if (task) picked.task = { ...task, kind: 'task' }
      }
      api.picked = picked
      const w = picked.workstream
      await vscode.commands.executeCommand('setContext', SELECTED_ITEM_KEY, w ? contextValue(w.kind, w.writes, w.launches) : '')
      await vscode.commands.executeCommand('setContext', SELECTED_TASK_ITEM_KEY, picked.task ? contextValue('task', picked.task.writes) : '')
    }
    // A jump selects the task, then shows it in the Tasks view once that has drawn it.
    const selectTask = async (root: string, ws: string, id: string) => {
      store.selectTask(root, ws, id)
      if (!tasksView.visible) return
      const phases = await tasks.getChildren()
      for (const phase of phases) if (phase.kind === 'phase') await tasks.getChildren(phase)
      const node = tasks.drawnTask(root, ws, id)
      if (node) await Promise.resolve(tasksView.reveal(node, { select: true, focus: false })).catch(() => undefined)
    }
    const review = new ReviewTree(store)
    const docs = new ReviewDocuments(cli, store)
    const health = new HealthTree(store)
    const diagnostics = new HealthDiagnostics(store)
    const budget = new BudgetTree(cli, store)
    const budgetView = vscode.window.createTreeView(BUDGET_VIEW, { treeDataProvider: budget })
    budget.setVisible(budgetView.visible)
    const say = (text: string, error?: boolean) => {
      shown.push(text)
      if (error) void vscode.window.showErrorMessage(text)
      else void vscode.window.showInformationMessage(text)
    }
    const statusBar = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50)
    statusBar.name = 'Workstreams'
    statusBar.command = `${LIST_VIEW}.focus`
    const watchers = new Watchers(() => reload.poke())
    const reloadNow = async () => {
      api.reloads.push('watch')
      await store.reload()
    }
    const reload = debounce(() => (pending = reloadNow()), DEBOUNCE_MS)

    const paint = async () => {
      watchers.watch(store.refreshPaths())
      await diagnostics.refresh()
      await vscode.commands.executeCommand('setContext', HAS_PROJECT_KEY, Object.keys(store.snapshots).length > 0)
      await pick()
      await paintStatus()
    }
    // The active workstream's claimed task and its age, or its wave line when nothing is claimed.
    const paintStatus = async () => {
      const active = activeWorkstream(store.roots, store.snapshots)
      if (!active) {
        statusBar.hide()
        return
      }
      const got = await store.workstream(active.root, active.row.id)
      const claimed = claimedTask(got.value?.tasks ?? [])
      statusBar.text = `$(checklist) ${claimed
        ? claimLine(active.row.id, claimed, active.errors, Date.now())
        : statusText(active.row.id, got.value?.wave, active.errors)}`
      statusBar.tooltip = 'Show the Workstreams view'
      statusBar.show()
    }
    store.onChange(() => void (pending = pending.then(paint)))
    pending = paint()
    const ageTimer = setInterval(() => void (pending = pending.then(paintStatus)), AGE_MS)

    context.subscriptions.push(
      vscode.window.createTreeView(LIST_VIEW, { treeDataProvider: list }),
      tasksView,
      taskView,
      graphView,
      overviewView,
      vscode.commands.registerCommand(SELECT_WORKSTREAM, (node: WorkstreamNode) => store.select(node.root, node.row.id)),
      vscode.commands.registerCommand(SELECT_TASK, (root: string, ws: string, id: string) => selectTask(root, ws, id)),
      vscode.window.createTreeView(REVIEW_VIEW, { treeDataProvider: review, showCollapseAll: true }),
      vscode.window.createTreeView(HEALTH_VIEW, { treeDataProvider: health }),
      budgetView,
      budgetView.onDidChangeVisibility(e => budget.setVisible(e.visible)),
      diagnostics,
      vscode.languages.registerCodeActionsProvider({ scheme: 'file' }, diagnostics, { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }),
      vscode.workspace.registerTextDocumentContentProvider(SCHEME, docs),
      vscode.commands.registerCommand(OPEN_FILE, async (node: Parameters<typeof openFile>[2]) => {
        api.opened.push(await openFile(cli, docs, node, say))
      }),
      vscode.commands.registerCommand(OPEN_EVIDENCE, async (node: Parameters<typeof openEvidence>[0]) => {
        api.opened.push(await openEvidence(node))
      }),
      statusBar,
      { dispose: () => clearInterval(ageTimer) },
      watchers,
      { dispose: reload.dispose },
      vscode.commands.registerCommand(REFRESH, async () => {
        api.reloads.push('button')
        budget.refresh()
        await (pending = store.reload())
        await pending
      }),
      vscode.commands.registerCommand(SHOW_DONE, () => setShowDone(true)),
      vscode.commands.registerCommand(HIDE_DONE, () => setShowDone(false)),
      ...registerCommands(cli, store, async () => {
        api.reloads.push('act')
        await (pending = store.reload())
      }, {
        get ui() { return api.ui },
        get flowUi() { return api.flowUi },
        state: context.workspaceState,
        asked: api.asked,
        launched: api.launched,
        say,
        picked: () => api.picked,
      }),
    )
    const setShowDone = async (on: boolean) => {
      store.setShowDone(on)
      await vscode.commands.executeCommand('setContext', SHOW_DONE_KEY, on)
    }
    void vscode.commands.executeCommand('setContext', SHOW_DONE_KEY, false)
    void vscode.commands.executeCommand('setContext', SELECTED_KEY, false)
    Object.assign(api, { store, list, tasks, task, graph, overview, review, health, diagnostics, budget, statusBar })
    return started
  }

  const started = folders.length ? start(cli, folders).then(show) : Promise.resolve<Started>({ roots: [], snapshots: {}, errors: {} })
  api.ready = started.then(draw)
  return api
}

export function deactivate(): void {}
