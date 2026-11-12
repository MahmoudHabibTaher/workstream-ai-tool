// The Task view: the selected task's sections from detail.ts. A section with a heading opens to its
// items; one without sits at the top. A dependency jumps to that task through
// `workstreams.selectTask`, and a file opens through `vscode.open` (plan D-VIEWS).
import * as vscode from 'vscode'

import { type Item, type Section, taskRows, taskSections } from '../logic/detail.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'
import { SELECT_TASK } from './tasks.ts'

export const TASK_VIEW = 'workstreams.task'

export type DetailNode =
  | { kind: 'section'; id: string; root: string; ws: string; section: Section }
  | { kind: 'item'; id: string; root: string; ws: string; item: Item }
  | { kind: 'message'; id: string; text: string; error: boolean }

export class TaskTree implements vscode.TreeDataProvider<DetailNode> {
  private emitter = new vscode.EventEmitter<DetailNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event

  private store: Store
  private now: () => number

  constructor(store: Store, now: () => number = Date.now) {
    this.store = store
    this.now = now
    store.onChange(() => this.emitter.fire(undefined))
    store.onSelect(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: DetailNode): vscode.TreeItem {
    switch (node.kind) {
      case 'section': {
        const item = new vscode.TreeItem(node.section.heading ?? '', vscode.TreeItemCollapsibleState.Expanded)
        item.id = node.id
        item.contextValue = 'section'
        return item
      }
      case 'message': {
        const item = new vscode.TreeItem(node.text)
        item.id = node.id
        item.iconPath = new vscode.ThemeIcon(node.error ? 'error' : 'info')
        item.contextValue = 'message'
        return item
      }
      case 'item': {
        const it = node.item
        if (it.kind === 'line') {
          const item = new vscode.TreeItem(it.text)
          item.id = node.id
          item.tooltip = tooltip([{ lines: [it.text] }])
          item.contextValue = 'line'
          return item
        }
        const item = new vscode.TreeItem(it.label)
        item.id = node.id
        if (it.kind === 'task') {
          item.iconPath = new vscode.ThemeIcon('arrow-right')
          item.contextValue = 'dependency'
          item.command = { command: SELECT_TASK, title: 'Show Task', arguments: [node.root, node.ws, it.task] }
        } else {
          const uri = vscode.Uri.file(it.path)
          item.resourceUri = uri
          item.iconPath = vscode.ThemeIcon.File
          item.description = it.path === it.label ? undefined : it.path
          item.contextValue = 'file'
          item.command = { command: 'vscode.open', title: 'Open', arguments: [uri] }
        }
        return item
      }
    }
  }

  async getChildren(node?: DetailNode): Promise<DetailNode[]> {
    if (node) {
      if (node.kind !== 'section') return []
      return node.section.items.map(item => ({ kind: 'item', id: item.id, root: node.root, ws: node.ws, item }))
    }
    const store = this.store
    const selected = store.selected
    const task = store.selectedTask
    if (!selected || !task) return []
    const { root, ws } = selected
    const got = await store.workstream(root, ws)
    if (got.error !== undefined) return [{ kind: 'message', id: JSON.stringify([root, ws, 'task-error']), text: got.error, error: true }]
    const rows = taskRows(root, ws, got.value, this.now())
    const row = rows.find(r => r.task.id === task)
    if (!row) return []
    const known = new Set(rows.map(r => r.task.id))
    return taskSections(row, known, got.value.repoRoot, this.now()).flatMap((section): DetailNode[] => (section.heading
      ? [{ kind: 'section', id: section.id, root, ws, section }]
      : section.items.map(item => ({ kind: 'item', id: item.id, root, ws, item }))))
  }
}
