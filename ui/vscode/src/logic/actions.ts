// Which writes a tree item offers, and what the confirm box says. The snapshot decides what is
// offered: a row's `actions` and a finding's `actions`. Nothing here holds act's status rule, and
// `ws act` still decides when the write runs.
import type { Revisions } from '../cli.ts'
import { CLOSED_STATUSES, type Finding, type Row } from './format.ts'

// The writes the extension can ask `ws act` for, in the order a menu shows them.
export const WRITES = ['pause', 'resume', 'sync', 'unclaim'] as const
export type Write = (typeof WRITES)[number]

const known = (action: string): action is Write => (WRITES as readonly string[]).includes(action)

function offered(found: string[]): Write[] {
  return WRITES.filter(w => found.includes(w))
}

// A workstream row's writes: the row's own `actions`, and any a finding offers for the whole row.
export function rowWrites(row: Row, health: Finding[]): Write[] {
  const fromFindings = health.flatMap(f => f.actions ?? [])
    .filter(a => a.workstream === row.id && !a.task).map(a => a.action)
  return offered([...(row.actions ?? []), ...fromFindings].filter(known))
}

// A task's writes: only what a finding offers for that task, `unclaim` on a stale claim today.
export function taskWrites(health: Finding[], ws: string, task: string): Write[] {
  return offered(health.flatMap(f => f.actions ?? []).filter(a => a.workstream === ws && a.task === task).map(a => a.action))
}

// Run, Coordinate, Close and Abandon are offered on an open workstream, as in the web UI.
export function launches(row: Row): boolean {
  return !CLOSED_STATUSES.has(row.status)
}

// A tree item's contextValue: its kind, then `act:<write>` for each write offered, then `launch`.
// The menus in package.json match these words, so a command shows only where it is offered.
export function contextValue(kind: string, writes: readonly string[] = [], launch = false): string {
  return [kind, ...writes.map(w => `act:${w}`), ...(launch ? ['launch'] : [])].join(' ')
}

export function commitLine(ws: string, action: string, task?: string): string {
  return `${ws}: ${action}${task ? ` ${task}` : ''}`
}

// Whether what the person saw is behind the latest snapshot the extension holds: the write will
// then be refused, and the box says so before they confirm.
export function moved(pinned: Revisions, latest: Revisions | undefined, ws: string): boolean {
  if (!latest) return false
  return latest.registry !== pinned.registry || latest.tasks[ws] !== pinned.tasks[ws]
}

export type ConfirmText = { message: string; detail: string }

export function confirmText(ws: string, action: string, task: string | undefined, branch: string, behind: boolean): ConfirmText {
  const lines = [`This commits "${commitLine(ws, action, task)}" on ${branch}.`]
  if (behind) lines.push('This has changed since the tree drew it, so the write will be refused.')
  return { message: `${action[0].toUpperCase()}${action.slice(1)} ${task ?? ws}?`, detail: lines.join('\n\n') }
}
