// The Health tree, its findings in the Problems panel with quick fixes, and the Budget tree. The
// quick fixes call the same write commands the trees' menus do, so they open the same confirm.
// Everything shown is what the store holds or what `ws audit context --json` printed.
import * as vscode from 'vscode'

import { type Cli, loadBudget } from '../cli.ts'
import { commandOf } from '../commands.ts'
import { contextValue } from '../logic/actions.ts'
import {
  type BudgetNode, type BudgetRow, budgetNodes, budgetShown, type FindingNode, findingLabel, findingNodes, type HealthNode,
  healthNodes, healthShown, quickFixTitle, tasksFileOf, workstreamsWithFindings,
} from '../logic/health.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'

export const HEALTH_VIEW = 'workstreams.health'
export const BUDGET_VIEW = 'workstreams.budget'
export const SOURCE = 'workstreams'

function healthIcon(node: HealthNode): vscode.ThemeIcon | undefined {
  switch (node.kind) {
    case 'level': return new vscode.ThemeIcon(node.level === 'error' ? 'error' : node.level === 'warning' ? 'warning' : 'info')
    case 'finding': return new vscode.ThemeIcon(node.finding.level === 'error' ? 'error' : node.finding.level === 'warning' ? 'warning' : 'info')
    case 'message': return new vscode.ThemeIcon(node.error ? 'error' : 'pass')
    default: return undefined
  }
}

export class HealthTree implements vscode.TreeDataProvider<HealthNode> {
  private emitter = new vscode.EventEmitter<HealthNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event
  private store: Store

  constructor(store: Store) {
    this.store = store
    store.onChange(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: HealthNode): vscode.TreeItem {
    const s = healthShown(node)
    const item = new vscode.TreeItem(s.label, s.collapsible ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None)
    item.id = node.id
    item.description = s.description
    if (s.tip) item.tooltip = tooltip(s.tip)
    item.iconPath = healthIcon(node)
    item.contextValue = node.kind === 'finding' ? contextValue(node.kind, node.writes) : node.kind
    return item
  }

  async getChildren(node?: HealthNode): Promise<HealthNode[]> {
    const store = this.store
    if (!node) {
      const errors: HealthNode[] = Object.entries(store.errors).map(([root, text]) => ({ kind: 'message', id: JSON.stringify(['health', 'error', root]), text: `${root}: ${text}`, error: true }))
      const live = store.roots.filter(root => store.snapshots[root])
      if (live.length === 1) return [...errors, ...healthNodes(live[0], store.snapshots[live[0]])]
      return [...errors, ...live.map((root): HealthNode => ({ kind: 'root', id: JSON.stringify(['health', root]), root }))]
    }
    switch (node.kind) {
      case 'root': {
        const snapshot = store.snapshots[node.root]
        return snapshot ? healthNodes(node.root, snapshot) : []
      }
      case 'level': return node.findings
      default: return []
    }
  }
}

const SEVERITY: Record<string, vscode.DiagnosticSeverity> = {
  error: vscode.DiagnosticSeverity.Error, warning: vscode.DiagnosticSeverity.Warning,
}

// Each finding that names a workstream, as a diagnostic at line 1 of that workstream's tasks
// file. `refresh` rebuilds the whole set from the store, so a finding that went is cleared.
export class HealthDiagnostics implements vscode.CodeActionProvider, vscode.Disposable {
  readonly collection = vscode.languages.createDiagnosticCollection(SOURCE)
  private fixes = new Map<string, { diagnostic: vscode.Diagnostic; node: FindingNode }[]>()
  private generation = 0
  private store: Store

  constructor(store: Store) {
    this.store = store
  }

  async refresh(): Promise<void> {
    const generation = ++this.generation
    const fixes = new Map<string, { diagnostic: vscode.Diagnostic; node: FindingNode }[]>()
    for (const root of this.store.roots) {
      const snapshot = this.store.snapshots[root]
      if (!snapshot) continue
      const nodes = findingNodes(root, snapshot)
      for (const ws of workstreamsWithFindings(nodes)) {
        const got = await this.store.workstream(root, ws)
        const path = got.value ? tasksFileOf(got.value) : undefined
        if (!path) continue
        const uri = vscode.Uri.file(path).toString()
        const list = fixes.get(uri) ?? []
        for (const node of nodes.filter(n => n.finding.workstream === ws)) {
          const diagnostic = new vscode.Diagnostic(new vscode.Range(0, 0, 0, 0), findingLabel(node.finding),
            SEVERITY[node.finding.level] ?? vscode.DiagnosticSeverity.Information)
          diagnostic.source = SOURCE
          if (node.finding.kind) diagnostic.code = node.finding.kind
          list.push({ diagnostic, node })
        }
        fixes.set(uri, list)
      }
    }
    if (generation !== this.generation) return
    this.fixes = fixes
    this.collection.clear()
    for (const [uri, list] of fixes) this.collection.set(vscode.Uri.parse(uri), list.map(f => f.diagnostic))
  }

  // A finding's writes, offered on its diagnostic. Each runs the write command its menu runs.
  provideCodeActions(document: vscode.TextDocument, _range: vscode.Range, context: vscode.CodeActionContext): vscode.CodeAction[] {
    const list = this.fixes.get(document.uri.toString()) ?? []
    const actions: vscode.CodeAction[] = []
    for (const asked of context.diagnostics) {
      if (asked.source !== SOURCE) continue
      const fix = list.find(f => f.diagnostic.message === asked.message && String(f.diagnostic.code ?? '') === String(asked.code ?? ''))
      if (!fix) continue
      for (const write of fix.node.writes) {
        const action = new vscode.CodeAction(quickFixTitle(write, fix.node.finding), vscode.CodeActionKind.QuickFix)
        action.diagnostics = [asked]
        action.command = { command: commandOf(write), title: action.title, arguments: [fix.node] }
        actions.push(action)
      }
    }
    return actions
  }

  dispose(): void {
    this.collection.dispose()
  }
}

// `ws audit context --json` per root. It runs only while the view is visible: when it first comes
// into sight, and on Refresh. A Refresh while it is hidden only drops the rows, so showing it again
// reads them then.
// The store's reloads on file changes don't run it, as what it measures isn't in the workstreams.
export class BudgetTree implements vscode.TreeDataProvider<BudgetNode> {
  private emitter = new vscode.EventEmitter<BudgetNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event
  private loaded = new Map<string, Promise<{ rows?: BudgetRow[]; error?: string }>>()
  private visible = false
  // What the last run printed, per root, for the integration test.
  rows: Record<string, BudgetRow[]> = {}

  private cli: Cli
  private store: Store

  constructor(cli: Cli, store: Store) {
    this.cli = cli
    this.store = store
  }

  refresh(): void {
    this.loaded.clear()
    if (this.visible) this.emitter.fire(undefined)
  }

  setVisible(visible: boolean): void {
    this.visible = visible
    if (visible && !this.loaded.size) this.emitter.fire(undefined)
  }

  getTreeItem(node: BudgetNode): vscode.TreeItem {
    const s = budgetShown(node)
    const item = new vscode.TreeItem(s.label, s.collapsible ? vscode.TreeItemCollapsibleState.Expanded : vscode.TreeItemCollapsibleState.None)
    item.id = node.id
    item.description = s.description
    if (s.tip) item.tooltip = tooltip(s.tip)
    item.iconPath = node.kind === 'row' ? new vscode.ThemeIcon(node.row.ok ? 'pass' : 'error')
      : node.kind === 'message' ? new vscode.ThemeIcon(node.error ? 'error' : 'info') : undefined
    item.contextValue = node.kind
    return item
  }

  private rowsOf(root: string): Promise<{ rows?: BudgetRow[]; error?: string }> {
    let got = this.loaded.get(root)
    if (!got) {
      got = loadBudget(this.cli, root).then(r => {
        if (r.error !== undefined) return { error: r.error }
        if (!Array.isArray(r.value)) return { error: 'audit context printed no rows' }
        this.rows[root] = r.value as BudgetRow[]
        return { rows: r.value as BudgetRow[] }
      })
      this.loaded.set(root, got)
    }
    return got
  }

  private async under(root: string): Promise<BudgetNode[]> {
    const got = await this.rowsOf(root)
    if (got.error !== undefined) return [{ kind: 'message', id: JSON.stringify(['budget', root, 'error']), text: got.error, error: true }]
    return budgetNodes(root, got.rows ?? [])
  }

  async getChildren(node?: BudgetNode): Promise<BudgetNode[]> {
    const live = this.store.roots.filter(root => this.store.snapshots[root])
    if (!node) {
      if (live.length === 1) return this.under(live[0])
      return live.map((root): BudgetNode => ({ kind: 'root', id: JSON.stringify(['budget', root]), root }))
    }
    return node.kind === 'root' ? this.under(node.root) : []
  }
}
