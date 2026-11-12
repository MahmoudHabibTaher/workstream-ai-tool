// The Graph view: the selected workstream's tasks as the dependency tree detail.ts grows from the
// snapshot's `blockedBy` and `unblocks`. Picking a node runs `workstreams.selectTask`, so the Task
// view draws that task (plan T2, D-VIEWS).
import * as vscode from 'vscode'

import { graph, graphLabel, type GraphNode, taskRows } from '../logic/detail.ts'
import type { Store } from '../logic/store.ts'
import { SELECT_TASK } from './tasks.ts'
import { ICONS } from './workstreams.ts'

export const GRAPH_VIEW = 'workstreams.graph'

export type GraphViewNode =
  | (GraphNode & { kind: 'node' })
  | { kind: 'message'; id: string; text: string; error: boolean }

export class GraphTree implements vscode.TreeDataProvider<GraphViewNode> {
  private emitter = new vscode.EventEmitter<GraphViewNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event

  private store: Store
  private now: () => number

  constructor(store: Store, now: () => number = Date.now) {
    this.store = store
    this.now = now
    store.onChange(() => this.emitter.fire(undefined))
    store.onSelect(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: GraphViewNode): vscode.TreeItem {
    if (node.kind === 'message') {
      const item = new vscode.TreeItem(node.text)
      item.id = node.id
      item.iconPath = new vscode.ThemeIcon(node.error ? 'error' : 'info')
      item.contextValue = 'message'
      return item
    }
    const { label, description } = graphLabel(node)
    const item = new vscode.TreeItem(label, node.children.length
      ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None)
    item.id = node.id
    item.description = description
    item.iconPath = new vscode.ThemeIcon(ICONS[node.row.task.status] ?? 'circle-outline')
    item.contextValue = node.repeat ? 'graphRepeat' : 'graphTask'
    item.command = { command: SELECT_TASK, title: 'Select', arguments: [node.row.root, node.row.ws, node.row.task.id] }
    return item
  }

  async getChildren(node?: GraphViewNode): Promise<GraphViewNode[]> {
    if (node) return node.kind === 'node' ? node.children.map(child => ({ ...child, kind: 'node' as const })) : []
    const selected = this.store.selected
    if (!selected) return []
    const { root, ws } = selected
    const got = await this.store.workstream(root, ws)
    if (got.error !== undefined) return [{ kind: 'message', id: JSON.stringify([root, ws, 'graph-error']), text: got.error, error: true }]
    return graph(taskRows(root, ws, got.value, this.now())).map(n => ({ ...n, kind: 'node' as const }))
  }
}
