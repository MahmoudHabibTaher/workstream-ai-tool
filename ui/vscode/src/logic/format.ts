// Pure helpers ported from the web UI's logic.js, with the same cases in their tests. They arrange
// what the snapshot says and decide nothing: a rule about what may happen belongs to the CLI.

export const CLOSED_STATUSES = new Set(['done', 'abandoned'])
export const DOC_NAMES = ['plan', 'progress', 'decisions', 'handoff'] as const
export type DocName = (typeof DOC_NAMES)[number]

export type Wave = {
  state: 'ready' | 'finished' | 'stuck' | string
  phase?: number | null
  ids?: string[]
  open?: string[]
  leftovers?: string[]
}

export type Task = {
  id: string
  title?: string
  summary?: string
  phase: number
  priority: number
  status: string
  blockedBy: string[]
  mode?: string
  needsUserDecision?: boolean
  startedAt?: string | null
  blockedReason?: string | null
  acceptanceText?: string[]
  verifyCommands?: { label: string; command: string }[]
}

export type Row = {
  id: string
  title?: string
  summary?: string
  status: string
  progress?: { total: number; done: number }
  dependsOn?: string[]
  // The status writes `ws act` would accept for this row now, as the snapshot drew them.
  actions?: string[]
}

export type Offer = { action: string; workstream: string; task?: string | null }
export type Finding = { level: string; workstream: string | null; task?: string | null; message?: string; actions?: Offer[] }
export type Badge = { text: string; kind: string }
export type Gate = { ok: boolean; blocking: boolean }
export type Range = { kind: string; from?: string; to?: string }

export function waveLine(wave: Wave | undefined | null): string {
  if (!wave) return ''
  if (wave.state === 'finished') return 'Queue finished'
  if (wave.state === 'stuck') return `Stuck: ${(wave.open ?? []).length} open, none actionable`
  const leftovers = (wave.leftovers ?? []).length > 0 ? ` · ${(wave.leftovers ?? []).length} left over` : ''
  return `Phase ${wave.phase}: ${(wave.ids ?? []).length} ready${leftovers}`
}

export function ageOf(startedAt: string, now: number): string {
  const minutes = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return hours < 48 ? `${hours}h` : `${Math.floor(hours / 24)}d`
}

export function badgesOf(task: Task, tasks: Task[], wave: Pick<Wave, 'ids'> | undefined | null, now: number): Badge[] {
  const statusOf = new Map(tasks.map(t => [t.id, t.status]))
  const waitsOn = task.blockedBy.filter(id => statusOf.get(id) !== 'done')
  const badges: Badge[] = []
  if (wave?.ids?.includes(task.id)) badges.push({ text: '★ ready', kind: 'good' })
  if (task.mode === 'foreground') badges.push({ text: 'foreground', kind: '' })
  if (task.needsUserDecision) badges.push({ text: 'needs decision', kind: 'warn' })
  if (task.status === 'todo' && waitsOn.length > 0) badges.push({ text: `waits on ${waitsOn.join(', ')}`, kind: '' })
  if (task.status === 'in-progress' && task.startedAt) badges.push({ text: `claimed ${ageOf(task.startedAt, now)}`, kind: 'accent' })
  return badges
}

export function blockedLine(task: Pick<Task, 'blockedReason'>): string {
  return task.blockedReason ? `Blocked: ${task.blockedReason}` : ''
}

export function lanes<T extends Pick<Task, 'phase' | 'priority'>>(tasks: T[]): { phase: number; tasks: T[] }[] {
  const phases = [...new Set(tasks.map(t => t.phase))].sort((a, b) => a - b)
  return phases.map(phase => ({
    phase,
    tasks: tasks.filter(t => t.phase === phase).sort((a, b) => a.priority - b.priority),
  }))
}

export function splitRows<T extends { status: string }>(registry: T[]): { open: T[]; closed: T[] } {
  return {
    open: registry.filter(row => !CLOSED_STATUSES.has(row.status)),
    closed: registry.filter(row => CLOSED_STATUSES.has(row.status)),
  }
}

export function errorCount(health: Finding[], id: string): number {
  return health.filter(f => f.level === 'error' && f.workstream === id).length
}

export function rangeLine(range: Range): string {
  if (range.kind === 'none') return 'No diff: this task has no commit or branch yet.'
  const short = (rev = '') => (/^[0-9a-f]{40}/.test(rev) ? rev.slice(0, 10) + rev.slice(40) : rev)
  return `${range.kind}: ${short(range.from)}${range.kind === 'branch' ? '...' : '..'}${short(range.to)}`
}

// What the gates add up to, in a line. settle decides; this says what it would say.
export function gateSummary(gates: Gate[]): Badge {
  const stopping = gates.filter(g => !g.ok && g.blocking).length
  const warnings = gates.filter(g => !g.ok && !g.blocking).length
  if (stopping > 0) return { kind: 'bad', text: `${stopping} check${stopping === 1 ? '' : 's'} would stop this landing` }
  if (warnings > 0) return { kind: 'warn', text: `Would land, with ${warnings} warning${warnings === 1 ? '' : 's'}` }
  return { kind: 'good', text: 'Every check passes' }
}
