// The Registry tree: workstreams, then each one's wave line, phases, tasks and documents. It
// arranges what the store holds; the store holds only what the CLI printed.
import * as vscode from 'vscode'

import { contextValue } from '../logic/actions.ts'
import {
  documentChildren, type Node, phaseChildren, shown, workstreamChildren, workstreams,
} from '../logic/registry.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'

export const OPEN_DOCUMENT = 'workstreams.openDocument'

const ICONS: Record<string, string> = {
  active: 'play-circle', planned: 'circle-outline', paused: 'debug-pause', done: 'pass', abandoned: 'circle-slash',
  todo: 'circle-outline', 'in-progress': 'sync', blocked: 'error', deferred: 'clock',
}

function iconOf(node: Node): vscode.ThemeIcon | undefined {
  switch (node.kind) {
    case 'workstream': return new vscode.ThemeIcon(ICONS[node.row.status] ?? 'circle-outline')
    case 'task': return new vscode.ThemeIcon(ICONS[node.task.status] ?? 'circle-outline')
    case 'wave': return new vscode.ThemeIcon('pulse')
    case 'phase': return new vscode.ThemeIcon('layers')
    case 'documents': return new vscode.ThemeIcon('book')
    case 'document': return new vscode.ThemeIcon('markdown')
    case 'message': return new vscode.ThemeIcon(node.error ? 'error' : 'info')
    default: return undefined
  }
}

export class RegistryTree implements vscode.TreeDataProvider<Node> {
  private emitter = new vscode.EventEmitter<Node | undefined>()
  readonly onDidChangeTreeData = this.emitter.event

  private store: Store
  private now: () => number

  constructor(store: Store, now: () => number = Date.now) {
    this.store = store
    this.now = now
    store.onChange(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: Node): vscode.TreeItem {
    const s = shown(node)
    const item = new vscode.TreeItem(s.label, s.collapsible ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None)
    item.id = node.id
    item.description = s.description
    if (s.tip) item.tooltip = tooltip(s.tip)
    item.iconPath = iconOf(node)
    item.contextValue = node.kind === 'workstream' ? contextValue(node.kind, node.writes, node.launch)
      : node.kind === 'task' ? contextValue(node.kind, node.writes) : node.kind
    if (node.kind === 'workstream' && node.row.status === 'active') item.collapsibleState = vscode.TreeItemCollapsibleState.Expanded
    if (node.kind === 'document') {
      item.resourceUri = vscode.Uri.file(node.path)
      item.command = { command: OPEN_DOCUMENT, title: 'Open', arguments: [node] }
    }
    return item
  }

  async getChildren(node?: Node): Promise<Node[]> {
    const store = this.store
    if (!node) {
      const errors: Node[] = Object.entries(store.errors).map(([root, text]) => ({ kind: 'message', id: `error:${root}`, text: `${root}: ${text}`, error: true }))
      const live = store.roots.filter(root => store.snapshots[root])
      if (live.length === 1) return [...errors, ...workstreams(live[0], store.snapshots[live[0]], store.showDone)]
      return [...errors, ...live.map((root): Node => ({ kind: 'root', id: `root:${root}`, root }))]
    }
    switch (node.kind) {
      case 'root': {
        const snapshot = store.snapshots[node.root]
        return snapshot ? workstreams(node.root, snapshot, store.showDone) : []
      }
      case 'workstream': {
        const got = await store.workstream(node.root, node.row.id)
        if (got.error !== undefined) return [{ kind: 'message', id: `${node.id}:error`, text: got.error, error: true }]
        return workstreamChildren(node.root, node.row.id, got.value)
      }
      case 'phase': return phaseChildren(node, this.now())
      case 'documents': return documentChildren(node)
      default: return []
    }
  }
}

// A document opens in Markdown preview, from the path the snapshot gave.
export async function openDocument(node: Extract<Node, { kind: 'document' }>): Promise<void> {
  await vscode.commands.executeCommand('markdown.showPreview', vscode.Uri.file(node.path))
}
