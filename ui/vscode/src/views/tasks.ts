// The Tasks view: the selected workstream's wave line, then its tasks phase by phase. Picking a
// task runs `workstreams.selectTask`, which the Task view draws (plan T2, D-VIEWS).
import * as vscode from 'vscode'

import { contextValue } from '../logic/actions.ts'
import { type Lane, taskLanes, type TaskRow } from '../logic/detail.ts'
import { waveLine } from '../logic/format.ts'
import type { Tip } from '../logic/registry.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'
import { ICONS } from './workstreams.ts'

export const TASKS_VIEW = 'workstreams.tasks'
export const SELECT_TASK = 'workstreams.selectTask'

export type TaskNode = TaskRow & { kind: 'task' }

export type TasksNode =
  | { kind: 'wave'; id: string; text: string }
  | (Lane & { kind: 'phase' })
  | TaskNode
  | { kind: 'message'; id: string; text: string; error: boolean }

const key = (...parts: (string | number)[]) => JSON.stringify(parts)

// A task's tooltip: its id and title, its description and badges, and its summary, all as text.
function tipOf(row: TaskRow): Tip {
  const t = row.task
  const tip: Tip = [{ lines: [t.title ? `${t.id}: ${t.title}` : t.id] }, { lines: [[row.description, ...row.badges].join(' · ')] }]
  if (t.summary) tip.push({ lines: [t.summary] })
  if (t.acceptanceText?.length) tip.push({ heading: 'Acceptance', lines: t.acceptanceText })
  return tip
}

export class TasksTree implements vscode.TreeDataProvider<TasksNode> {
  private emitter = new vscode.EventEmitter<TasksNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event

  private store: Store
  private now: () => number
  // Each drawn node's parent, by id, so a jump can reveal a task under its phase.
  private parents = new Map<string, TasksNode | undefined>()
  private tasks = new Map<string, TaskNode>()

  constructor(store: Store, now: () => number = Date.now) {
    this.store = store
    this.now = now
    store.onChange(() => this.emitter.fire(undefined))
    store.onSelect(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: TasksNode): vscode.TreeItem {
    switch (node.kind) {
      case 'wave': {
        const item = new vscode.TreeItem(node.text)
        item.id = node.id
        item.iconPath = new vscode.ThemeIcon('pulse')
        item.contextValue = 'wave'
        return item
      }
      case 'phase': {
        const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Expanded)
        item.id = node.id
        item.description = node.description
        item.iconPath = new vscode.ThemeIcon('layers')
        item.contextValue = 'phase'
        return item
      }
      case 'task': {
        const item = new vscode.TreeItem(node.label)
        item.id = node.id
        item.description = node.description
        item.tooltip = tooltip(tipOf(node))
        item.iconPath = new vscode.ThemeIcon(ICONS[node.task.status] ?? 'circle-outline')
        item.contextValue = contextValue(node.kind, node.writes)
        item.command = { command: SELECT_TASK, title: 'Select', arguments: [node.root, node.ws, node.task.id] }
        return item
      }
      case 'message': {
        const item = new vscode.TreeItem(node.text)
        item.id = node.id
        item.iconPath = new vscode.ThemeIcon(node.error ? 'error' : 'info')
        item.contextValue = 'message'
        return item
      }
    }
  }

  async getChildren(node?: TasksNode): Promise<TasksNode[]> {
    const found = await this.children(node)
    if (!node) {
      this.parents.clear()
      this.tasks.clear()
    }
    for (const child of found) {
      this.parents.set(child.id, node)
      if (child.kind === 'task') this.tasks.set(child.id, child)
    }
    return found
  }

  getParent(node: TasksNode): TasksNode | undefined {
    return this.parents.get(node.id)
  }

  // The drawn node for a task, if the view has drawn it.
  drawnTask(root: string, ws: string, task: string): TaskNode | undefined {
    return this.tasks.get(key(root, ws, 'task', task))
  }

  private async children(node?: TasksNode): Promise<TasksNode[]> {
    if (node) return node.kind === 'phase' ? node.tasks.map(row => ({ ...row, kind: 'task' as const })) : []
    const selected = this.store.selected
    if (!selected) return []
    const { root, ws } = selected
    const got = await this.store.workstream(root, ws)
    if (got.error !== undefined) return [{ kind: 'message', id: key(root, ws, 'error'), text: got.error, error: true }]
    const found: TasksNode[] = []
    const line = waveLine(got.value.wave)
    if (line) found.push({ kind: 'wave', id: key(root, ws, 'wave'), text: line })
    for (const lane of taskLanes(root, ws, got.value, this.now())) found.push({ ...lane, kind: 'phase' })
    return found
  }
}
