// The Review queue as plain data: the queue `ws review --queue` printed, grouped with branch work
// first, then landed work, and under each task what `ws review --checks` said about it. The view
// turns these into TreeItems; nothing here imports `vscode`, so `node --test` covers it. It
// arranges what the CLI printed and decides nothing.
import { gateSummary, type Range, rangeLine, statLine } from './format.ts'
import type { Tip } from './registry.ts'

export type Entry = {
  workstream: string
  task: string
  title?: string
  status?: string
  state: 'branch' | 'landed' | string
  revision?: string | null
  when?: string | null
  files: number
  added: number
  removed: number
  hasEvidence: boolean
}
export type Queue = { tasks: Entry[] }

export type Gate = { name: string; ok: boolean; detail?: string; blocking: boolean }
export type Item = { n: number; item: string; proof: string }
export type Checks = {
  state: 'branch' | 'landed' | 'none' | string
  commit?: string | null
  gates: Gate[]
  evidenceText: string | null
  evidenceStatus?: string
  reason?: string
  items: Item[]
}
export type FileStat = { path: string; added: number | null; removed: number | null }
export type Review = { task: string; evidence: string | null; range: Range; files: FileStat[]; checks?: Checks; error?: string }

export const GROUPS = [
  { state: 'branch', label: 'On a branch' },
  { state: 'landed', label: 'Landed' },
] as const

export type ReviewNode =
  | { kind: 'root'; id: string; root: string }
  | { kind: 'group'; id: string; root: string; state: string; label: string; entries: Entry[] }
  | { kind: 'entry'; id: string; root: string; entry: Entry }
  | { kind: 'gates'; id: string; text: string; level: string; gates: Gate[] }
  | { kind: 'gate'; id: string; gate: Gate }
  | { kind: 'items'; id: string; items: Item[] }
  | { kind: 'item'; id: string; item: Item }
  | { kind: 'evidence'; id: string; root: string; ws: string; task: string; path: string | null; onBranch: boolean }
  | { kind: 'files'; id: string; root: string; ws: string; task: string; range: Range; files: FileStat[] }
  | { kind: 'file'; id: string; root: string; ws: string; task: string; file: FileStat }
  | { kind: 'message'; id: string; text: string; error: boolean }

const key = (...parts: (string | number)[]) => JSON.stringify(['review', ...parts])

// Branch work first, then landed work, each in the order the CLI gave; a group with nothing in it
// is left out, and an empty queue says so.
export function queueNodes(root: string, queue: Queue): ReviewNode[] {
  const found: ReviewNode[] = []
  for (const group of GROUPS) {
    const entries = queue.tasks.filter(e => e.state === group.state)
    if (entries.length) found.push({ kind: 'group', id: key(root, group.state), root, state: group.state, label: group.label, entries })
  }
  if (!found.length) return [{ kind: 'message', id: key(root, 'empty'), text: 'Nothing to review.', error: false }]
  return found
}

export function groupChildren(node: Extract<ReviewNode, { kind: 'group' }>): ReviewNode[] {
  return node.entries.map(entry => ({ kind: 'entry', id: key(node.root, entry.workstream, entry.task), root: node.root, entry }))
}

// Under one task, from its `--checks` review: the range, the gates, the acceptance with its
// proof, the evidence, then the files.
export function entryChildren(node: Extract<ReviewNode, { kind: 'entry' }>, review: Review): ReviewNode[] {
  const { root } = node
  const ws = node.entry.workstream
  const task = node.entry.task
  const id = (...parts: string[]) => key(root, ws, task, ...parts)
  const found: ReviewNode[] = [{ kind: 'message', id: id('range'), text: rangeLine(review.range), error: false }]
  if (review.error) found.push({ kind: 'message', id: id('error'), text: review.error, error: true })
  const checks = review.checks
  if (checks) {
    if (checks.state === 'landed') {
      found.push({ kind: 'message', id: id('gates'), text: `Landed as ${(checks.commit ?? '').slice(0, 10)}. Its gates ran when it landed.`, error: false })
    } else if (checks.state === 'none') {
      found.push({ kind: 'message', id: id('gates'), text: 'Not started, so nothing has been checked.', error: false })
    } else {
      const summary = gateSummary(checks.gates)
      found.push({ kind: 'gates', id: id('gates'), text: summary.text, level: summary.kind, gates: checks.gates })
    }
    if (checks.evidenceStatus === 'blocked') found.push({ kind: 'message', id: id('blocked'), text: `Blocked: ${checks.reason ?? ''}`, error: true })
    if (checks.items.length) found.push({ kind: 'items', id: id('items'), items: checks.items })
    else found.push({ kind: 'message', id: id('items'), text: 'This task lists no acceptance items.', error: false })
    if (checks.evidenceText === null) found.push({ kind: 'message', id: id('evidence'), text: 'No evidence file yet.', error: false })
    else found.push({ kind: 'evidence', id: id('evidence'), root, ws, task, path: review.evidence, onBranch: checks.state === 'branch' })
  }
  if (review.files.length) found.push({ kind: 'files', id: id('files'), root, ws, task, range: review.range, files: review.files })
  return found
}

export function gateChildren(node: Extract<ReviewNode, { kind: 'gates' }>): ReviewNode[] {
  return node.gates.map((gate, i) => ({ kind: 'gate', id: `${node.id}:${i}`, gate }))
}

export function itemChildren(node: Extract<ReviewNode, { kind: 'items' }>): ReviewNode[] {
  return node.items.map(item => ({ kind: 'item', id: `${node.id}:${item.n}`, item }))
}

export function fileChildren(node: Extract<ReviewNode, { kind: 'files' }>): ReviewNode[] {
  return node.files.map(file => ({ kind: 'file', id: `${node.id}:${file.path}`, root: node.root, ws: node.ws, task: node.task, file }))
}

export const NOTHING_QUOTED = 'Nothing quoted.'

export function gateMark(gate: Gate): 'ok' | 'stop' | 'warned' {
  return gate.ok ? 'ok' : gate.blocking ? 'stop' : 'warned'
}

export function entryDescription(entry: Entry): string {
  const files = `${entry.files} file${entry.files === 1 ? '' : 's'} +${entry.added} −${entry.removed}`
  return [entry.workstream, files, ...(entry.hasEvidence ? [] : ['no evidence'])].join(' · ')
}

export type ReviewShown = { label: string; description?: string; tip?: Tip; collapsible: boolean }

export function reviewShown(node: ReviewNode): ReviewShown {
  switch (node.kind) {
    case 'root': return { label: node.root, collapsible: true }
    case 'group': return { label: node.label, description: String(node.entries.length), collapsible: true }
    case 'entry': {
      const e = node.entry
      const label = e.title ? `${e.task} ${e.title}` : e.task
      return { label, description: entryDescription(e), collapsible: true, tip: [{ lines: [label, entryDescription(e)] }] }
    }
    case 'gates': return { label: node.text, collapsible: true }
    case 'gate': {
      const detail = !node.gate.ok && node.gate.detail ? node.gate.detail : undefined
      return { label: node.gate.name, description: detail, collapsible: false, ...(detail ? { tip: [{ lines: [node.gate.name, detail] }] } : {}) }
    }
    case 'items': return { label: 'Acceptance and proof', description: `${node.items.filter(i => i.proof).length}/${node.items.length} quoted`, collapsible: true }
    case 'item': {
      const proof = node.item.proof || NOTHING_QUOTED
      return { label: `${node.item.n}. ${node.item.item}`, description: proof, collapsible: false, tip: [{ heading: 'Acceptance', lines: [node.item.item] }, { heading: 'Proof', lines: [proof] }] }
    }
    case 'evidence': return { label: 'Evidence', description: node.onBranch ? 'from the branch' : undefined, collapsible: false }
    case 'files': return { label: 'Files', description: String(node.files.length), collapsible: true }
    case 'file': return { label: node.file.path, description: statLine(node.file), collapsible: false }
    case 'message': return { label: node.text, collapsible: false }
  }
}

// What a diff tab is called: the path and the range it compares.
export function diffTitle(path: string, task: string, oldRev: string, newRev: string): string {
  return `${path} (${task}: ${oldRev.slice(0, 10)} ↔ ${newRev.slice(0, 10)})`
}

export function binaryLine(path: string): string {
  return `${path} is binary, so no diff opens.`
}
