// The Overview view: the selected workstream's documents, registry row, open claims, scope, verify
// commands and baseline, as detail.ts lays them out. A document opens through `vscode.open`, and a
// claim jumps to its task through `workstreams.selectTask` (plan D-VIEWS).
import * as vscode from 'vscode'

import { listRows, overviewSections } from '../logic/detail.ts'
import type { Store } from '../logic/store.ts'
import { detailChildren, detailItem, type DetailNode, sectionNodes } from './task.ts'

export const OVERVIEW_VIEW = 'workstreams.overview'

export class OverviewTree implements vscode.TreeDataProvider<DetailNode> {
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
    return detailItem(node)
  }

  async getChildren(node?: DetailNode): Promise<DetailNode[]> {
    if (node) return detailChildren(node)
    const store = this.store
    const selected = store.selected
    if (!selected) return []
    const { root, ws } = selected
    const got = await store.workstream(root, ws)
    if (got.error !== undefined) return [{ kind: 'message', id: JSON.stringify([root, ws, 'overview-error']), text: got.error, error: true }]
    const snapshot = store.snapshots[root]
    const row = snapshot ? listRows(root, snapshot, true).find(r => r.row.id === ws)?.row : undefined
    return sectionNodes(root, ws, overviewSections(root, ws, row, got.value, this.now()))
  }
}
