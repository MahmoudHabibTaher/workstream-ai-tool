// The Review queue tree, and the read-only `ws-review:` documents its files and evidence open in.
// Each side of a diff is `ws review --show` for that side, so the old side of a branch is its
// merge base, worked out by the CLI. It reads only.
import * as vscode from 'vscode'

import { type Cli, loadShow, type Side } from '../cli.ts'
import {
  binaryLine, diffTitle, entryChildren, fileChildren, gateChildren, gateMark, groupChildren, itemChildren, queueNodes,
  type ReviewNode, reviewShown,
} from '../logic/review.ts'
import type { Store } from '../logic/store.ts'
import { tooltip } from '../markdown.ts'

export const REVIEW_VIEW = 'workstreams.review'
export const SCHEME = 'ws-review'
export const OPEN_FILE = 'workstreams.openReviewFile'
export const OPEN_EVIDENCE = 'workstreams.openEvidence'

type FileNode = Extract<ReviewNode, { kind: 'file' }>
type EvidenceNode = Extract<ReviewNode, { kind: 'evidence' }>

const GATE_ICONS = { ok: 'pass', stop: 'error', warned: 'warning' } as const
const LEVEL_ICONS: Record<string, string> = { good: 'pass', warn: 'warning', bad: 'error' }

function iconOf(node: ReviewNode): vscode.ThemeIcon | undefined {
  switch (node.kind) {
    case 'group': return new vscode.ThemeIcon(node.state === 'branch' ? 'git-branch' : 'git-merge')
    case 'entry': return new vscode.ThemeIcon('checklist')
    case 'gates': return new vscode.ThemeIcon(LEVEL_ICONS[node.level] ?? 'info')
    case 'gate': return new vscode.ThemeIcon(GATE_ICONS[gateMark(node.gate)])
    case 'items': return new vscode.ThemeIcon('list-ordered')
    case 'item': return new vscode.ThemeIcon(node.item.proof ? 'quote' : 'circle-slash')
    case 'evidence': return new vscode.ThemeIcon('markdown')
    case 'files': return new vscode.ThemeIcon('files')
    case 'file': return new vscode.ThemeIcon(node.file.added === null ? 'file-binary' : 'diff')
    case 'message': return new vscode.ThemeIcon(node.error ? 'error' : 'info')
    default: return undefined
  }
}

export class ReviewTree implements vscode.TreeDataProvider<ReviewNode> {
  private emitter = new vscode.EventEmitter<ReviewNode | undefined>()
  readonly onDidChangeTreeData = this.emitter.event
  private store: Store

  constructor(store: Store) {
    this.store = store
    store.onChange(() => this.emitter.fire(undefined))
  }

  getTreeItem(node: ReviewNode): vscode.TreeItem {
    const s = reviewShown(node)
    const item = new vscode.TreeItem(s.label, s.collapsible ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None)
    item.id = node.id
    item.description = s.description
    if (s.tip) item.tooltip = tooltip(s.tip)
    item.iconPath = iconOf(node)
    item.contextValue = node.kind
    if (node.kind === 'group' && node.state === 'branch') item.collapsibleState = vscode.TreeItemCollapsibleState.Expanded
    if (node.kind === 'file') {
      item.resourceUri = vscode.Uri.from({ scheme: SCHEME, path: `/${node.file.path}` })
      item.command = { command: OPEN_FILE, title: 'Open Diff', arguments: [node] }
    }
    if (node.kind === 'evidence') item.command = { command: OPEN_EVIDENCE, title: 'Open Evidence', arguments: [node] }
    return item
  }

  async getChildren(node?: ReviewNode): Promise<ReviewNode[]> {
    const store = this.store
    if (!node) {
      const live = store.roots.filter(root => store.snapshots[root])
      if (live.length === 1) return this.queueOf(live[0])
      return live.map((root): ReviewNode => ({ kind: 'root', id: JSON.stringify(['review', root]), root }))
    }
    switch (node.kind) {
      case 'root': return this.queueOf(node.root)
      case 'group': return groupChildren(node)
      case 'entry': {
        const got = await store.review(node.root, node.entry.workstream, node.entry.task)
        if (got.error !== undefined) return [{ kind: 'message', id: `${node.id}:error`, text: got.error, error: true }]
        return entryChildren(node, got.value)
      }
      case 'gates': return gateChildren(node)
      case 'items': return itemChildren(node)
      case 'files': return fileChildren(node)
      default: return []
    }
  }

  private async queueOf(root: string): Promise<ReviewNode[]> {
    const got = await this.store.queue(root)
    if (got.error !== undefined) return [{ kind: 'message', id: JSON.stringify(['review', root, 'error']), text: got.error, error: true }]
    return queueNodes(root, got.value)
  }
}

type Ask = { kind: 'show'; root: string; ws: string; task: string; side: Side; rev: string } | { kind: 'evidence'; root: string; ws: string; task: string }

function uriOf(path: string, ask: Ask): vscode.Uri {
  const query = new URLSearchParams(Object.entries(ask)).toString()
  return vscode.Uri.from({ scheme: SCHEME, path: `/${path}`, query })
}

function askOf(uri: vscode.Uri): Ask {
  const q = new URLSearchParams(uri.query)
  const base = { root: q.get('root') ?? '', ws: q.get('ws') ?? '', task: q.get('task') ?? '' }
  if (q.get('kind') === 'evidence') return { kind: 'evidence', ...base }
  return { kind: 'show', ...base, side: q.get('side') === 'old' ? 'old' : 'new', rev: q.get('rev') ?? '' }
}

// Serves `ws-review:` documents: a side of a file from `ws review --show`, or a branch's evidence
// from `ws review --checks`. Each URI names the revision it was read at, so a cached text never
// stands for a later one.
export class ReviewDocuments implements vscode.TextDocumentContentProvider {
  private texts = new Map<string, string>()
  private cli: Cli
  private store: Store

  constructor(cli: Cli, store: Store) {
    this.cli = cli
    this.store = store
  }

  remember(uri: vscode.Uri, text: string): void {
    this.texts.set(uri.toString(), text)
  }

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const cached = this.texts.get(uri.toString())
    if (cached !== undefined) return cached
    const ask = askOf(uri)
    const path = uri.path.slice(1)
    if (ask.kind === 'evidence') {
      const got = await this.store.review(ask.root, ask.ws, ask.task)
      if (got.error !== undefined) throw new Error(got.error)
      return got.value.checks?.evidenceText ?? ''
    }
    const got = await loadShow(this.cli, ask.root, ask.ws, ask.task, path, ask.side)
    if (got.error !== undefined) throw new Error(got.error)
    if (got.value.binary) throw new Error(binaryLine(path))
    return got.value.text ?? ''
  }
}

export type Opened = { kind: 'diff'; title: string; left: vscode.Uri; right: vscode.Uri } | { kind: 'binary' | 'failed'; text: string } | { kind: 'evidence'; uri: vscode.Uri }

// A file opens the diff editor between its two sides. A binary side opens nothing and says so;
// a side the file isn't on is empty, as an added file's old side is.
export async function openFile(cli: Cli, docs: ReviewDocuments, node: FileNode, say: (text: string, error?: boolean) => void): Promise<Opened> {
  const path = node.file.path
  const [old, now] = await Promise.all((['old', 'new'] as const).map(side => loadShow(cli, node.root, node.ws, node.task, path, side)))
  const failed = old.error ?? now.error
  if (failed !== undefined || !old.value || !now.value) {
    const text = failed ?? `${path}: no answer from review --show`
    say(text, true)
    return { kind: 'failed', text }
  }
  if (old.value.binary || now.value.binary) {
    const text = binaryLine(path)
    say(text)
    return { kind: 'binary', text }
  }
  const ask = { root: node.root, ws: node.ws, task: node.task }
  const left = uriOf(path, { kind: 'show', ...ask, side: 'old', rev: old.value.rev })
  const right = uriOf(path, { kind: 'show', ...ask, side: 'new', rev: now.value.rev })
  docs.remember(left, old.value.text ?? '')
  docs.remember(right, now.value.text ?? '')
  const title = diffTitle(path, node.task, old.value.rev, now.value.rev)
  await vscode.commands.executeCommand('vscode.diff', left, right, title, { preview: true })
  return { kind: 'diff', title, left, right }
}

// Landed evidence opens the file itself; a branch's opens read-only, as the branch holds it.
export async function openEvidence(node: EvidenceNode): Promise<Opened> {
  const uri = !node.onBranch && node.path
    ? vscode.Uri.file(node.path)
    : uriOf(`${node.ws}/evidence/${node.task}.md`, { kind: 'evidence', root: node.root, ws: node.ws, task: node.task })
  await vscode.window.showTextDocument(await vscode.workspace.openTextDocument(uri), { preview: true })
  return { kind: 'evidence', uri }
}
