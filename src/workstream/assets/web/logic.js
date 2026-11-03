// Pure helpers, with no DOM, so they can be tested without a browser. They arrange what the server
// sends and decide nothing: a rule about what may happen belongs in Python.

export const CLOSED_STATUSES = new Set(['done', 'abandoned'])
export const DOC_NAMES = ['plan', 'progress', 'decisions', 'handoff']

export function waveLine(wave) {
  if (!wave) return ''
  if (wave.state === 'finished') return 'Queue finished'
  if (wave.state === 'stuck') return `Stuck: ${wave.open.length} open, none actionable`
  const leftovers = wave.leftovers.length > 0 ? ` · ${wave.leftovers.length} left over` : ''
  return `Phase ${wave.phase}: ${wave.ids.length} ready${leftovers}`
}

export function ageOf(startedAt, now) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return hours < 48 ? `${hours}h` : `${Math.floor(hours / 24)}d`
}

export function badgesOf(task, tasks, wave, now) {
  const statusOf = new Map(tasks.map(t => [t.id, t.status]))
  const waitsOn = task.blockedBy.filter(id => statusOf.get(id) !== 'done')
  const badges = []
  if (wave?.ids.includes(task.id)) badges.push({ text: '★ ready', kind: 'good' })
  if (task.mode === 'foreground') badges.push({ text: 'foreground', kind: '' })
  if (task.needsUserDecision) badges.push({ text: 'needs decision', kind: 'warn' })
  if (task.status === 'todo' && waitsOn.length > 0) badges.push({ text: `waits on ${waitsOn.join(', ')}`, kind: '' })
  if (task.status === 'in-progress' && task.startedAt) badges.push({ text: `claimed ${ageOf(task.startedAt, now)}`, kind: 'accent' })
  return badges
}

export function lanes(tasks) {
  const phases = [...new Set(tasks.map(t => t.phase))].sort((a, b) => a - b)
  return phases.map(phase => ({
    phase,
    tasks: tasks.filter(t => t.phase === phase).sort((a, b) => a.priority - b.priority),
  }))
}

export function splitRows(registry) {
  return {
    open: registry.filter(row => !CLOSED_STATUSES.has(row.status)),
    closed: registry.filter(row => CLOSED_STATUSES.has(row.status)),
  }
}

export function errorCount(health, id) {
  return health.filter(f => f.level === 'error' && f.workstream === id).length
}

export function findingsFor(health, ws) {
  return health.filter(f => f.workstream === ws || f.workstream === null)
}

// Whether a finding offers this write for this task: the snapshot decides.
export function offers(health, ws, action, task) {
  return health.some(f => f.actions.some(a => a.action === action && a.workstream === ws && a.task === task))
}

// The writes a workstream's status allows, on the rule `ws act` holds. It's only which button to
// draw: `ws act` still decides.
export function statusActions(status) {
  if (status === 'planned' || status === 'active') return ['pause']
  if (status === 'paused') return ['resume']
  return []
}

export function commitLine(ws, action, task) {
  return `${ws}: ${action}${task ? ` ${task}` : ''}`
}

// What each prompt button copies, for the user to paste into their own agent. Never sent.
export function promptText(kind, ws) {
  if (kind === 'run') return `Use the ws-run skill to run workstream ${ws}.`
  if (kind === 'coordinate') return `Use the ws-coordinate skill on workstream ${ws}.`
  if (kind === 'close') return `Use the ws-coordinate skill to close workstream ${ws}.`
  return `Use the ws-coordinate skill to abandon workstream ${ws}: <why>`
}

export function statusKind(status) {
  return {
    active: 'accent', 'in-progress': 'accent', planned: '', todo: '', paused: 'warn', blocked: 'bad',
    deferred: 'warn', done: 'good', abandoned: 'dim',
  }[status] ?? ''
}

export function percent(part, whole) {
  return whole > 0 ? Math.min(100, Math.round((part / whole) * 100)) : 0
}

// --- review --------------------------------------------------------------------------------

export function rangeLine(range) {
  if (range.kind === 'none') return 'No diff: this task has no commit or branch yet.'
  const short = rev => (/^[0-9a-f]{40}/.test(rev) ? rev.slice(0, 10) + rev.slice(40) : rev)
  return `${range.kind}: ${short(range.from)}${range.kind === 'branch' ? '...' : '..'}${short(range.to)}`
}

export function statLine(file) {
  if (file.added === null || file.removed === null) return 'binary'
  return `+${file.added} −${file.removed}`
}

// What the gates add up to, in a line. settle decides; this says what it would say.
export function gateSummary(gates) {
  const stopping = gates.filter(g => !g.ok && g.blocking).length
  const warnings = gates.filter(g => !g.ok && !g.blocking).length
  if (stopping > 0) return { kind: 'bad', text: `${stopping} check${stopping === 1 ? '' : 's'} would stop this landing` }
  if (warnings > 0) return { kind: 'warn', text: `Would land, with ${warnings} warning${warnings === 1 ? '' : 's'}` }
  return { kind: 'good', text: 'Every check passes' }
}

// A file's unified diff as lines with their numbers on each side.
export function parseDiff(text) {
  const header = []
  const hunks = []
  let oldLine = 0
  let newLine = 0
  for (const raw of (text ?? '').split('\n')) {
    const at = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$/.exec(raw)
    if (at) {
      oldLine = Number(at[1])
      newLine = Number(at[2])
      hunks.push({ header: raw, lines: [] })
    } else if (!hunks.length) {
      if (raw) header.push(raw)
    } else if (raw.startsWith('+')) {
      hunks.at(-1).lines.push({ kind: 'add', old: null, new: newLine++, text: raw })
    } else if (raw.startsWith('-')) {
      hunks.at(-1).lines.push({ kind: 'del', old: oldLine++, new: null, text: raw })
    } else if (raw.startsWith('\\')) {
      hunks.at(-1).lines.push({ kind: 'meta', old: null, new: null, text: raw })
    } else if (raw.startsWith(' ')) {
      hunks.at(-1).lines.push({ kind: 'ctx', old: oldLine++, new: newLine++, text: raw })
    }
  }
  return { header, hunks }
}

// Whether the diff's header says the file came or went, or that git can't show it as text.
export function fileNote(header) {
  if (header.some(line => line.startsWith('new file'))) return 'new file'
  if (header.some(line => line.startsWith('deleted file'))) return 'deleted file'
  if (header.some(line => line.startsWith('Binary files'))) return 'binary, no text diff'
  return null
}

export function neighbours(tasks, ws, task) {
  const at = tasks.findIndex(t => t.workstream === ws && t.task === task)
  if (at < 0) return { previous: null, next: null, entry: null }
  return { previous: tasks[at - 1] ?? null, next: tasks[at + 1] ?? null, entry: tasks[at] }
}

export function neighbourFile(files, current, step) {
  const at = files.findIndex(f => f.path === current)
  return files[at + step]?.path ?? null
}

// --- the address ---------------------------------------------------------------------------

export function parseRoute(hash) {
  const parts = hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
  const [first, ws, kind, id, ...rest] = parts
  if (first === 'review') return { screen: 'queue' }
  if (first === 'health') return { screen: 'health' }
  if (first === 'budget') return { screen: 'budget' }
  if (first !== 'w' || !ws) return { screen: 'registry' }
  if (kind === 'doc' && DOC_NAMES.includes(id)) return { screen: 'doc', ws, doc: id }
  if (kind === 'review' && id) return { screen: 'review', ws, task: id, file: rest.length ? rest.join('/') : null }
  if (kind === 't' && id) return { screen: 'task', ws, task: id }
  return { screen: 'lanes', ws }
}

const part = encodeURIComponent

export const hrefs = {
  registry: () => '#/',
  queue: () => '#/review',
  health: () => '#/health',
  budget: () => '#/budget',
  lanes: ws => `#/w/${part(ws)}`,
  task: (ws, task) => `#/w/${part(ws)}/t/${part(task)}`,
  doc: (ws, doc) => `#/w/${part(ws)}/doc/${doc}`,
  review: (ws, task, file) =>
    `#/w/${part(ws)}/review/${part(task)}${file ? `/${file.split('/').map(part).join('/')}` : ''}`,
}
