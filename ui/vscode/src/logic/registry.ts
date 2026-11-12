// The snapshot's shapes the views share, and the status bar's line. The views' own builders are in
// detail.ts; nothing here imports `vscode`, so `node --test` covers it.
import type { Snapshot } from '../cli.ts'
import { type DocName, errorCount, type Finding, type Row, type Task, type Wave, waveLine } from './format.ts'

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

// A tooltip as sections: each heading is the extension's own constant, each line is repo text,
// which the view appends as text, never as markup.
export type Tip = { heading?: string; lines: string[] }[]

export const DOC_LABELS: Record<DocName, string> = { plan: 'Plan', progress: 'Progress', decisions: 'Decisions', handoff: 'Handoff' }

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? '' : 's'}`

function rows(snapshot: Snapshot): Row[] {
  return (snapshot.registry as Row[] | undefined) ?? []
}

function health(snapshot: Snapshot): Finding[] {
  return (snapshot.health as Finding[] | undefined) ?? []
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
