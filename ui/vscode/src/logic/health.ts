// Health and Budget as plain data: the snapshot's `health` findings grouped by level, what each
// one offers, where its diagnostic goes, and `ws audit context --json`'s rows. The views turn
// these into TreeItems and diagnostics; nothing here imports `vscode`, so `node --test` covers
// it. It arranges what the CLI printed and decides nothing.
import type { Revisions, Snapshot } from '../cli.ts'
import { type Write, WRITES } from './actions.ts'
import type { Finding } from './format.ts'
import type { Tip, WsSnapshot } from './registry.ts'

export const LEVELS = [
  { level: 'error', label: 'Errors' },
  { level: 'warning', label: 'Warnings' },
] as const

// A finding keeps the revisions of the snapshot it came from, which its write pins (plan T7),
// and the writes its own `actions` offer, in menu order.
export type FindingNode = { kind: 'finding'; id: string; root: string; finding: Finding; revisions: Revisions; writes: Write[] }

export type HealthNode =
  | { kind: 'root'; id: string; root: string }
  | { kind: 'level'; id: string; root: string; level: string; label: string; findings: FindingNode[] }
  | FindingNode
  | { kind: 'message'; id: string; text: string; error: boolean }

const key = (...parts: (string | number | null | undefined)[]) => JSON.stringify(['health', ...parts])

export function findingsOf(snapshot: Snapshot): Finding[] {
  return (snapshot.health as Finding[] | undefined) ?? []
}

// The writes a finding's `actions` list, that the extension knows, without repeats.
export function findingWrites(finding: Finding): Write[] {
  const found = (finding.actions ?? []).map(a => a.action)
  return WRITES.filter(w => found.includes(w))
}

// The workstream and task a finding's write is for: the first of its offers with that action.
export function offerOf(finding: Finding, action: string): { ws: string; task?: string } | undefined {
  const offer = (finding.actions ?? []).find(a => a.action === action)
  return offer ? { ws: offer.workstream, task: offer.task ?? undefined } : undefined
}

export function findingNodes(root: string, snapshot: Snapshot): FindingNode[] {
  return findingsOf(snapshot).map((finding, i) => ({
    kind: 'finding', id: key(root, i, finding.kind, finding.workstream, finding.task, finding.message), root, finding,
    revisions: snapshot.revisions, writes: findingWrites(finding),
  }))
}

// Errors, then warnings, then any other level in the order it first came, each in the CLI's
// order. A level with nothing in it is left out, and no findings says so. The snapshot's git
// error, when it has one, comes first.
export function healthNodes(root: string, snapshot: Snapshot): HealthNode[] {
  const found: HealthNode[] = []
  const gitError = (snapshot.git as { error?: string } | undefined)?.error
  if (gitError) found.push({ kind: 'message', id: key(root, 'git'), text: gitError, error: true })
  const all = findingNodes(root, snapshot)
  const levels: { level: string; label: string }[] = [...LEVELS]
  for (const node of all) {
    if (!levels.some(l => l.level === node.finding.level)) levels.push({ level: node.finding.level, label: node.finding.level })
  }
  for (const { level, label } of levels) {
    const findings = all.filter(n => n.finding.level === level)
    if (findings.length) found.push({ kind: 'level', id: key(root, 'level', level), root, level, label, findings })
  }
  if (!all.length) found.push({ kind: 'message', id: key(root, 'none'), text: 'Nothing to report.', error: false })
  return found
}

export type Shown = { label: string; description?: string; tip?: Tip; collapsible: boolean }

export function findingLabel(finding: Finding): string {
  return finding.message || finding.kind || finding.level
}

export function healthShown(node: HealthNode): Shown {
  switch (node.kind) {
    case 'root':
      return { label: node.root, collapsible: true }
    case 'level':
      return { label: node.label, description: String(node.findings.length), collapsible: true }
    case 'finding': {
      const f = node.finding
      const where = [f.workstream, f.task].filter(Boolean).join(' ')
      const description = [f.kind, where].filter(Boolean).join(' · ')
      const tip: Tip = [{ lines: [findingLabel(f)] }, { lines: [[f.level, description].filter(Boolean).join(' · ')] }]
      return { label: findingLabel(f), description, tip, collapsible: false }
    }
    case 'message':
      return { label: node.text, collapsible: false }
  }
}

// The workstreams whose findings go in the Problems panel: every finding that names one.
export function workstreamsWithFindings(nodes: FindingNode[]): string[] {
  return [...new Set(nodes.map(n => n.finding.workstream).filter((w): w is string => !!w))]
}

// A workstream's tasks file: the `paths.tasks` its own snapshot names. Undefined when the
// snapshot names none, and the finding then shows only in the tree.
export function tasksFileOf(wsSnapshot: WsSnapshot): string | undefined {
  const tasks = wsSnapshot.paths?.tasks
  return typeof tasks === 'string' ? tasks : undefined
}

export function quickFixTitle(action: Write, finding: Finding): string {
  const offer = offerOf(finding, action)
  return `${action[0].toUpperCase()}${action.slice(1)} ${offer?.task ?? offer?.ws ?? ''}`.trim()
}

// One row of `ws audit context --json`: a role's tokens against its limit.
export type BudgetRow = { role: string; tokens: number; budget: number; ok: boolean }

export type BudgetNode =
  | { kind: 'root'; id: string; root: string }
  | { kind: 'row'; id: string; root: string; row: BudgetRow }
  | { kind: 'message'; id: string; text: string; error: boolean }

export function budgetNodes(root: string, rows: BudgetRow[]): BudgetNode[] {
  if (!rows.length) return [{ kind: 'message', id: JSON.stringify(['budget', root, 'none']), text: 'No roles measured.', error: false }]
  return rows.map(row => ({ kind: 'row', id: JSON.stringify(['budget', root, row.role]), root, row }))
}

export function percentOf(row: BudgetRow): number {
  return row.budget > 0 ? Math.round((row.tokens / row.budget) * 100) : 0
}

export function budgetShown(node: BudgetNode): Shown {
  switch (node.kind) {
    case 'root':
      return { label: node.root, collapsible: true }
    case 'row': {
      const { row } = node
      const used = `${row.tokens.toLocaleString('en-US')} / ${row.budget.toLocaleString('en-US')}`
      const description = [used, `${percentOf(row)}%`, row.ok ? '' : 'over'].filter(Boolean).join(' · ')
      const tip: Tip = [{ lines: [row.role] }, { lines: [`${row.tokens} of ${row.budget} tokens, ${row.ok ? 'within its limit' : 'over its limit'}`] }]
      return { label: row.role, description, tip, collapsible: false }
    }
    case 'message':
      return { label: node.text, collapsible: false }
  }
}
