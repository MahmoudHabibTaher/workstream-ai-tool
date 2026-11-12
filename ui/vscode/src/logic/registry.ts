// The Registry tree as plain data: which nodes sit under which, and the text each one shows. The
// view turns these into TreeItems; nothing here imports `vscode`, so `node --test` covers it.
import type { Revisions, Snapshot } from '../cli.ts'
import { launches, rowWrites, taskWrites, type Write } from './actions.ts'
import {
  badgesOf, blockedLine, DOC_NAMES, type DocName, errorCount, type Finding, lanes, type Row, splitRows, type Task,
  type Wave, waveLine,
} from './format.ts'

// A snapshot task with the graph facts the CLI adds (`unblocks`, `waitingOn`) and the queue fields
// the detail views show. The extension never works these out for itself.
export type SnapTask = Task & {
  unblocks?: string[]
  waitingOn?: string[]
  files?: string[]
  notes?: string
  claimedBy?: string | null
}

// The queue's scope, as `ws snapshot -w` gives it; each field only when the queue has it.
export type Scope = { inScope?: string[]; outOfScope?: string[]; rule?: string }

// One `baseline.keys` entry: a verify key's recorded run.
export type BaselineKey = {
  key: string
  source?: string
  parser?: string | null
  command?: string | null
  exit?: number | null
  findings?: number
  recordedAt?: string | null
  commit?: string | null
}

// What `ws verify` judges the workstream against: its keys in key order, and the errors reading it gave.
export type Baseline = { keys?: BaselineKey[]; errors?: string[] }

// A workstream's own snapshot (`ws snapshot -w <id>`) adds its tasks, wave, scope, baseline and
// file paths. `repoRoot` is what a task's `files` are relative to.
export type WsSnapshot = Snapshot & {
  repoRoot?: string
  tasks?: SnapTask[]
  wave?: Wave
  scope?: Scope | null
  baseline?: Baseline
  paths?: Record<string, unknown>
}

// Workstream and task nodes keep the revisions of the snapshot they were drawn from, which a
// write pins (plan T7), and the writes the snapshot offers on them.

// A tooltip as sections: each heading is the extension's own constant, each line is repo text,
// which the view appends as text, never as markup.
export type Tip = { heading?: string; lines: string[] }[]

export type Node =
  | { kind: 'root'; id: string; root: string }
  | { kind: 'workstream'; id: string; root: string; row: Row; errors: number; revisions: Revisions; writes: Write[]; launch: boolean }
  | { kind: 'wave'; id: string; text: string }
  | { kind: 'phase'; id: string; root: string; ws: string; phase: number; tasks: Task[]; all: Task[]; wave?: Wave; revisions: Revisions; health: Finding[] }
  | { kind: 'task'; id: string; root: string; ws: string; task: Task; badges: string[]; revisions: Revisions; writes: Write[] }
  | { kind: 'documents'; id: string; root: string; ws: string; docs: { name: DocName; path: string }[] }
  | { kind: 'document'; id: string; root: string; ws: string; name: DocName; path: string }
  | { kind: 'message'; id: string; text: string; error: boolean }

export const DOC_LABELS: Record<DocName, string> = { plan: 'Plan', progress: 'Progress', decisions: 'Decisions', handoff: 'Handoff' }

const key = (...parts: (string | number)[]) => JSON.stringify(parts)

function rows(snapshot: Snapshot): Row[] {
  return (snapshot.registry as Row[] | undefined) ?? []
}

function health(snapshot: Snapshot): Finding[] {
  return (snapshot.health as Finding[] | undefined) ?? []
}

// The registry's rows in registry order, open ones first; closed ones only with Show done.
export function workstreams(root: string, snapshot: Snapshot, showDone: boolean): Node[] {
  const { open, closed } = splitRows(rows(snapshot))
  const shown = showDone ? [...open, ...closed] : open
  const found = health(snapshot)
  return shown.map(row => ({
    kind: 'workstream', id: key(root, row.id), root, row, errors: errorCount(found, row.id), revisions: snapshot.revisions,
    writes: rowWrites(row, found), launch: launches(row),
  }))
}

// Under a workstream: its wave line, its phases in order, then its documents.
export function workstreamChildren(root: string, ws: string, snapshot: WsSnapshot): Node[] {
  const tasks = snapshot.tasks ?? []
  const found: Node[] = []
  const line = waveLine(snapshot.wave)
  if (line) found.push({ kind: 'wave', id: key(root, ws, 'wave'), text: line })
  for (const lane of lanes(tasks)) {
    found.push({ kind: 'phase', id: key(root, ws, 'phase', lane.phase), root, ws, phase: lane.phase, tasks: lane.tasks, all: tasks, wave: snapshot.wave, revisions: snapshot.revisions, health: health(snapshot) })
  }
  const paths = snapshot.paths ?? {}
  const docs = DOC_NAMES.filter(name => typeof paths[name] === 'string').map(name => ({ name, path: paths[name] as string }))
  if (docs.length) found.push({ kind: 'documents', id: key(root, ws, 'documents'), root, ws, docs })
  return found
}

// A phase's tasks, already in priority order, each with its badges.
export function phaseChildren(node: Extract<Node, { kind: 'phase' }>, now: number): Node[] {
  return node.tasks.map(task => ({
    kind: 'task', id: key(node.root, node.ws, 'task', task.id), root: node.root, ws: node.ws, task,
    badges: badgesOf(task, node.all, node.wave, now).map(b => b.text), revisions: node.revisions, writes: taskWrites(node.health, node.ws, task.id),
  }))
}

export function documentChildren(node: Extract<Node, { kind: 'documents' }>): Node[] {
  return node.docs.map(doc => ({ kind: 'document', id: key(node.root, node.ws, 'doc', doc.name), root: node.root, ws: node.ws, ...doc }))
}

export type Shown = { label: string; description?: string; tip?: Tip; collapsible: boolean }

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

export function rowDescription(row: Row, errors: number): string {
  const progress = row.progress ? `${row.progress.done}/${row.progress.total}` : ''
  return [row.status, progress, errors ? plural(errors, 'error') : ''].filter(Boolean).join(' · ')
}

// What a node shows: label, description and tooltip. Every string here is plain text.
export function shown(node: Node): Shown {
  switch (node.kind) {
    case 'root':
      return { label: node.root, collapsible: true }
    case 'workstream': {
      const { row } = node
      const tip: Tip = [{ lines: [row.title ? `${row.id}: ${row.title}` : row.id] }]
      if (row.summary) tip.push({ lines: [row.summary] })
      tip.push({ lines: [rowDescription(row, node.errors)] })
      if (row.dependsOn?.length) tip.push({ heading: 'Depends on', lines: [row.dependsOn.join(', ')] })
      return { label: row.id, description: rowDescription(row, node.errors), tip, collapsible: true }
    }
    case 'wave':
      return { label: node.text, collapsible: false }
    case 'phase': {
      const done = node.tasks.filter(t => t.status === 'done').length
      return { label: `Phase ${node.phase}`, description: `${done}/${node.tasks.length}`, collapsible: true }
    }
    case 'task': {
      const { task } = node
      const tip: Tip = [{ lines: [task.title ? `${task.id}: ${task.title}` : task.id] }]
      tip.push({ lines: [[task.status, ...node.badges].join(' · ')] })
      const blocked = blockedLine(task)
      if (blocked) tip.push({ lines: [blocked] })
      if (task.summary) tip.push({ lines: [task.summary] })
      if (task.acceptanceText?.length) tip.push({ heading: 'Acceptance', lines: task.acceptanceText })
      if (task.verifyCommands?.length) {
        tip.push({ heading: 'Verify', lines: task.verifyCommands.map(v => (v.label === v.command ? v.command : `${v.label}: ${v.command}`)) })
      }
      return { label: task.title ? `${task.id} ${task.title}` : task.id, description: [task.status, ...node.badges].join(' · '), tip, collapsible: false }
    }
    case 'documents':
      return { label: 'Documents', collapsible: true }
    case 'document':
      return { label: DOC_LABELS[node.name], description: node.path.split(/[\\/]/).pop(), collapsible: false }
    case 'message':
      return { label: node.text, collapsible: false }
  }
}

// The status bar's workstream: the first active row of the first root that has one.
export function activeWorkstream(roots: string[], snapshots: Record<string, Snapshot>): { root: string; row: Row; errors: number } | undefined {
  for (const root of roots) {
    const snapshot = snapshots[root]
    if (!snapshot) continue
    const row = rows(snapshot).find(r => r.status === 'active')
    if (row) return { root, row, errors: errorCount(health(snapshot), row.id) }
  }
  return undefined
}

export function statusText(id: string, wave: Wave | undefined, errors: number): string {
  const line = waveLine(wave)
  return [`${id}${line ? `: ${line}` : ''}`, errors ? plural(errors, 'error') : ''].filter(Boolean).join(' · ')
}
