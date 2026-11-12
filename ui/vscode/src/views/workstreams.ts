// The Workstreams view: the registry's rows, one per workstream, grouped by root when the window has
// more than one. Picking a row selects it in the store, which the Tasks view draws (plan T2). It
// arranges what the store holds; the store holds only what the CLI printed.
import * as vscode from 'vscode'

import { contextValue } from '../logic/actions.ts'
import { listRows, type ListRow } from '../logic/detail.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'

export const LIST_VIEW = 'workstreams.list'
export const SELECT_WORKSTREAM = 'workstreams.selectWorkstream'

export type WorkstreamNode = ListRow & { kind: 'workstream' }

export type ListNode =
  | { kind: 'root'; id: string; root: string }
  | WorkstreamNode
  | { kind: 'message'; id: string; text: string; error: boolean }

export const ICONS: Record<string, string> = {
  active: 'play-circle', planned: 'circle-outline', paused: 'debug-pause', done: 'pass', abandoned: 'circle-slash',
  todo: 'circle-outline', 'in-progress': 'sync', blocked: 'error', deferred: 'clock',
}

export class WorkstreamsTree implements vscode.TreeDataProvider<ListNode> {
  private emitter = new vscode.EventEmitter<ListNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event

  private store: Store

  constructor(store: Store) {
    this.store = store
    store.onChange(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: ListNode): vscode.TreeItem {
    switch (node.kind) {
      case 'root': {
        const item = new vscode.TreeItem(node.root, vscode.TreeItemCollapsibleState.Expanded)
        item.id = node.id
        item.contextValue = 'root'
        return item
      }
      case 'message': {
        const item = new vscode.TreeItem(node.text)
        item.id = node.id
        item.iconPath = new vscode.ThemeIcon(node.error ? 'error' : 'info')
        item.contextValue = 'message'
        return item
      }
      case 'workstream': {
        const item = new vscode.TreeItem(node.label)
        item.id = node.id
        item.description = node.description
        item.tooltip = tooltip(node.tip)
        item.iconPath = new vscode.ThemeIcon(ICONS[node.row.status] ?? 'circle-outline')
        item.contextValue = contextValue(node.kind, node.writes, node.launch)
        item.command = { command: SELECT_WORKSTREAM, title: 'Select', arguments: [node] }
        return item
      }
    }
  }

  getChildren(node?: ListNode): ListNode[] {
    const store = this.store
    const rowsOf = (root: string): ListNode[] => {
      const snapshot = store.snapshots[root]
      return snapshot ? listRows(root, snapshot, store.showDone).map(row => ({ ...row, kind: 'workstream' as const })) : []
    }
    if (!node) {
      const errors: ListNode[] = Object.entries(store.errors).map(([root, text]) => ({ kind: 'message', id: `error:${root}`, text: `${root}: ${text}`, error: true }))
      const live = store.roots.filter(root => store.snapshots[root])
      if (live.length === 1) return [...errors, ...rowsOf(live[0])]
      return [...errors, ...live.map((root): ListNode => ({ kind: 'root', id: `root:${root}`, root }))]
    }
    return node.kind === 'root' ? rowsOf(node.root) : []
  }
}
