// The five linked views as plain data (plan D-VIEWS): the Workstreams list's rows, the Tasks view's
// phases and rows, the Task view's sections, the Graph view's tree and the Overview's sections.
// The views turn these into TreeItems; nothing here imports `vscode`, so `node --test` covers it.
// Every fact is one the snapshot gave: `unblocks` and `waitingOn` come from the CLI, never from here.
import type { Revisions, Snapshot } from '../cli.ts'
import { launches, rowWrites, taskWrites, type Write } from './actions.ts'
import type { Launch } from './launch.ts'
import {
  ageOf, badgesOf, blockedLine, DOC_NAMES, errorCount, type Finding, lanes, type Row, splitRows, type Wave,
} from './format.ts'
import { DOC_LABELS, type SnapTask, type Tip, type WsSnapshot } from './registry.ts'

// A registry row with the rest of its fields, as the Overview shows them.
export type DetailRow = Row & {
  tier?: string
  created?: string
  startedAt?: string | null
  completedAt?: string | null
  baseCommit?: string
  notes?: string
  progress?: { total: number; done: number; 'in-progress'?: number }
}

const key = (...parts: (string | number)[]) => JSON.stringify(parts)
const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

function rows(snapshot: Snapshot): DetailRow[] {
  return (snapshot.registry as DetailRow[] | undefined) ?? []
}

function health(snapshot: Snapshot): Finding[] {
  return (snapshot.health as Finding[] | undefined) ?? []
}

// --- The Workstreams list ---

export type ListRow = {
  id: string
  root: string
  row: DetailRow
  errors: number
  label: string
  description: string
  tip: Tip
  revisions: Revisions
  writes: Write[]
  launches: Launch[]
}

// What a row shows after its id: done/total, status, claimed tasks and errors, each only when there is one.
export function rowDetails(row: DetailRow, errors: number): string[] {
  const p = row.progress
  const claimed = p?.['in-progress'] ?? 0
  return [
    p ? `${p.done ?? 0}/${p.total}` : '',
    row.status,
    claimed > 0 ? `${claimed} claimed` : '',
    errors ? plural(errors, 'error') : '',
  ].filter(Boolean)
}

// The registry's rows in registry order, open ones first; closed ones only with Show done.
export function listRows(root: string, snapshot: Snapshot, showDone: boolean): ListRow[] {
  const { open, closed } = splitRows(rows(snapshot))
  const found = health(snapshot)
  return (showDone ? [...open, ...closed] : open).map(row => {
    const errors = errorCount(found, row.id)
    const description = rowDetails(row, errors).join(' · ')
    const tip: Tip = [{ lines: [row.title ? `${row.id}: ${row.title}` : row.id] }]
    if (row.summary) tip.push({ lines: [row.summary] })
    tip.push({ lines: [description] })
    if (row.dependsOn?.length) tip.push({ heading: 'Depends on', lines: [row.dependsOn.join(', ')] })
    return {
      id: key(root, 'ws', row.id), root, row, errors, label: row.id, description, tip, revisions: snapshot.revisions,
      writes: rowWrites(row, found), launches: launches(row),
    }
  })
}

// --- The Tasks view ---

export type TaskRow = {
  id: string
  root: string
  ws: string
  task: SnapTask
  label: string
  description: string
  badges: string[]
  revisions: Revisions
  writes: Write[]
}

export type Lane = { id: string; phase: number; label: string; description: string; tasks: TaskRow[] }

// A task's badges without "waits on": the row says what it waits on from the snapshot's `waitingOn`.
function badges(task: SnapTask, wave: Wave | undefined, now: number): string[] {
  return badgesOf(task, [], wave, now).map(b => b.text).filter(text => !text.startsWith('waits on '))
}

// A task row's description: its status, its phase and what it is waiting on.
export function taskDescription(task: SnapTask): string {
  const waiting = task.waitingOn ?? []
  return [task.status, `Phase ${task.phase}`, waiting.length ? `waiting on ${waiting.join(', ')}` : ''].filter(Boolean).join(' · ')
}

// The workstream's tasks phase by phase, each phase in priority order.
export function taskLanes(root: string, ws: string, snapshot: WsSnapshot, now: number): Lane[] {
  const found = health(snapshot)
  return lanes(snapshot.tasks ?? []).map(lane => ({
    id: key(root, ws, 'phase', lane.phase),
    phase: lane.phase,
    label: `Phase ${lane.phase}`,
    description: `${lane.tasks.filter(t => t.status === 'done').length}/${lane.tasks.length}`,
    tasks: lane.tasks.map(task => ({
      id: key(root, ws, 'task', task.id), root, ws, task, label: task.title ? `${task.id} ${task.title}` : task.id,
      description: taskDescription(task), badges: badges(task, snapshot.wave, now), revisions: snapshot.revisions,
      writes: taskWrites(found, ws, task.id),
    })),
  }))
}

// The Tasks view's rows in its order: phase by phase.
export function taskRows(root: string, ws: string, snapshot: WsSnapshot, now: number): TaskRow[] {
  return taskLanes(root, ws, snapshot, now).flatMap(lane => lane.tasks)
}

// --- Sections: the Task view and the Overview ---

// One line of a section: text, a jump to a task of this workstream (`workstreams.selectTask`), or a
// file that opens (`vscode.open`). A link shows its label; every string is plain text.
export type Item =
  | { kind: 'line'; id: string; text: string }
  | { kind: 'task'; id: string; task: string; label: string }
  | { kind: 'file'; id: string; path: string; label: string }

// A section's heading is the extension's own constant; its items are repo text.
export type Section = { id: string; heading?: string; items: Item[] }

type Strip<T> = T extends unknown ? Omit<T, 'id'> : never
type Bare = Strip<Item>
type Draft = { heading?: string; items: Bare[] }

const line = (text: string): Bare => ({ kind: 'line', text })

// Stable ids for every section and item, from `base` and their place, so expanded state survives a reload.
function finish(base: string, drafts: Draft[]): Section[] {
  return drafts.map((d, s) => ({
    id: key(base, s, d.heading ?? ''),
    ...(d.heading ? { heading: d.heading } : {}),
    items: d.items.map((item, i) => ({ ...item, id: key(base, s, i) }) as Item),
  }))
}

// An id is a link only when it names a task the workstream holds; else it is shown as text.
function idItems(ids: string[], known: Set<string>): Bare[] {
  return ids.map(id => (known.has(id) ? { kind: 'task', task: id, label: id } : line(id)))
}

// Where a task's `files` entry sits: under the snapshot's repo root, unless it is already absolute.
export function filePath(root: string | undefined, path: string): string {
  if (!root || path.startsWith('/') || /^[A-Za-z]:[\\/]/.test(path) || path.startsWith('\\\\')) return path
  return `${root.replace(/[\\/]+$/, '')}/${path}`
}

function claimAge(startedAt: string | null | undefined, now: number): string {
  if (!startedAt) return ''
  return Number.isNaN(Date.parse(startedAt)) ? startedAt : `${ageOf(startedAt, now)} ago`
}

const verifyLine = (v: { label: string; command: string }) => (v.label === v.command ? v.command : `${v.label}: ${v.command}`)

// The Task view, top to bottom: the task, its state, summary, claim and age, what it depends on and
// unblocks, its files, acceptance, verify commands and notes. A section with nothing to say is left
// out. `known` is the ids the workstream holds; `repoRoot` is what `files` are relative to.
export function taskSections(row: TaskRow, known: Set<string>, repoRoot: string | undefined, now: number): Section[] {
  const t = row.task
  const found: Draft[] = [
    { items: [line(t.title ? `${t.id}: ${t.title}` : t.id)] },
    { items: [line([taskDescription(t), ...row.badges].join(' · '))] },
  ]
  const blocked = blockedLine(t)
  if (blocked) found.push({ items: [line(blocked)] })
  if (t.summary) found.push({ heading: 'Summary', items: [line(t.summary)] })
  if (t.status === 'in-progress' && (t.claimedBy || t.startedAt)) {
    found.push({ heading: 'Claim', items: [line([t.claimedBy ?? '', claimAge(t.startedAt, now)].filter(Boolean).join(' · '))] })
  }
  if (t.blockedBy.length) found.push({ heading: 'Depends on', items: idItems(t.blockedBy, known) })
  if (t.unblocks?.length) found.push({ heading: 'Unblocks', items: idItems(t.unblocks, known) })
  if (t.files?.length) {
    found.push({ heading: 'Files', items: t.files.map(f => ({ kind: 'file', path: filePath(repoRoot, f), label: f })) })
  }
  if (t.acceptanceText?.length) found.push({ heading: 'Acceptance', items: t.acceptanceText.map(line) })
  if (t.verifyCommands?.length) found.push({ heading: 'Verify', items: t.verifyCommands.map(v => line(verifyLine(v))) })
  if (t.notes) found.push({ heading: 'Notes', items: [line(t.notes)] })
  return finish(key(row.id, 'section'), found)
}

// The Overview, top to bottom: the workstream's documents, its registry row, its open claims, its
// scope, the verify commands its tasks name, and its baseline. `row` is the list's row for it.
export function overviewSections(root: string, ws: string, row: DetailRow | undefined, snapshot: WsSnapshot, now: number): Section[] {
  const found: Draft[] = []
  const paths = snapshot.paths ?? {}
  const docs = DOC_NAMES.filter(name => typeof paths[name] === 'string')
  if (docs.length) {
    found.push({ heading: 'Documents', items: docs.map(name => ({ kind: 'file', path: paths[name] as string, label: DOC_LABELS[name] })) })
  }
  if (row) {
    const lines = [row.title ? `${row.id}: ${row.title}` : row.id]
    if (row.summary) lines.push(row.summary)
    lines.push([row.status, row.tier ? `${row.tier} tier` : ''].filter(Boolean).join(' · '))
    const p = row.progress
    if (p) {
      const claimed = p['in-progress'] ?? 0
      lines.push([`${p.done ?? 0}/${p.total} done`, claimed > 0 ? `${claimed} claimed` : ''].filter(Boolean).join(' · '))
    }
    if (row.dependsOn?.length) lines.push(`Depends on ${row.dependsOn.join(', ')}`)
    lines.push([row.created ? `created ${row.created}` : '', row.startedAt ? `started ${row.startedAt}` : '',
                row.completedAt ? `completed ${row.completedAt}` : ''].filter(Boolean).join(' · '))
    if (row.baseCommit) lines.push(`Base ${row.baseCommit}`)
    if (row.notes) lines.push(row.notes)
    found.push({ heading: 'Registry', items: lines.filter(Boolean).map(line) })
  }
  const tasks = snapshot.tasks ?? []
  const claims = tasks.filter(t => t.status === 'in-progress').map(t => (
    { kind: 'task' as const, task: t.id, label: [t.id, t.claimedBy ?? '', claimAge(t.startedAt, now)].filter(Boolean).join(' · ') }
  ))
  found.push({ heading: 'Open claims', items: claims.length ? claims : [line('None')] })
  const scope = snapshot.scope
  if (scope) {
    if (scope.rule) found.push({ heading: 'Scope', items: [line(scope.rule)] })
    if (scope.inScope?.length) found.push({ heading: 'In scope', items: scope.inScope.map(line) })
    if (scope.outOfScope?.length) found.push({ heading: 'Out of scope', items: scope.outOfScope.map(line) })
  }
  const verify = [...new Set(tasks.flatMap(t => t.verifyCommands ?? []).map(verifyLine))]
  if (verify.length) found.push({ heading: 'Verify', items: verify.map(line) })
  const baseline = snapshot.baseline
  const keys = (baseline?.keys ?? []).map(k => line([
    k.command && k.command !== k.key ? `${k.key}: ${k.command}` : k.key,
    k.source ?? '', typeof k.exit === 'number' ? `exit ${k.exit}` : '', plural(k.findings ?? 0, 'finding'),
    k.recordedAt ?? '', k.commit ? k.commit.slice(0, 10) : '',
  ].filter(Boolean).join(' · ')))
  const errors = (baseline?.errors ?? []).map(e => line(`Error: ${e}`))
  const recorded = [...keys, ...errors]
  found.push({ heading: 'Baseline', items: recorded.length ? recorded : [line('None recorded')] })
  return finish(key(root, ws, 'overview'), found)
}

// --- The Graph view ---

// A node of the Graph: a task, then the tasks its `unblocks` names, in the Tasks view's order. A task
// is expanded where it first appears; a later appearance is a leaf marked `repeat`, so a task two
// others wait on, or a cycle, never grows the tree without end. `id` is the node's path, so it is
// distinct even where a task appears twice, and stable across reloads.
export type GraphNode = { id: string; row: TaskRow; children: GraphNode[]; repeat: boolean }

// The dependency tree from the snapshot's `blockedBy` and `unblocks`: its roots are the tasks whose
// `blockedBy` names none of the workstream's tasks; a task no root reaches (a cycle) becomes a root
// after them. `rows` is the Tasks view's rows, in its order.
export function graph(rows: TaskRow[]): GraphNode[] {
  const known = new Set(rows.map(r => r.task.id))
  const expanded = new Set<string>()
  const grow = (row: TaskRow, parent: string): GraphNode => {
    const id = key(parent, row.task.id)
    if (expanded.has(row.task.id)) return { id, row, children: [], repeat: true }
    expanded.add(row.task.id)
    const next = new Set(row.task.unblocks ?? [])
    return { id, row, children: rows.filter(r => next.has(r.task.id)).map(r => grow(r, id)), repeat: false }
  }
  const base = rows.length ? key(rows[0].root, rows[0].ws, 'graph') : 'graph'
  const roots = rows.filter(r => !r.task.blockedBy.some(b => known.has(b))).map(r => grow(r, base))
  for (const r of rows) if (!expanded.has(r.task.id)) roots.push(grow(r, base))
  return roots
}

// What a Graph node shows: its id and title, and its status and badges (or that it is shown above).
export function graphLabel(node: GraphNode): { label: string; description: string } {
  const t = node.row.task
  return {
    label: t.title ? `${t.id} ${t.title}` : t.id,
    description: node.repeat ? `${t.status} · shown above` : [t.status, ...node.row.badges].join(' · '),
  }
}
