// Every call the pane makes outside itself, all to the `ws` CLI, which stays the only source of
// truth: the pane draws what it returns and writes only through `ws act`.
import type { EngineInterface } from 'claude-code'

import type { Confirm, ReviewData, Snapshot } from '../types'

const WS = 'ws'
const NO_WS = 'ws is not on the PATH this app runs commands with. Install it, then run /workstreams again.'

export type Loaded = { snapshot: Snapshot; error?: undefined } | { snapshot?: undefined; error: string }

// `ws root` knows which checkout holds the integration branch, so a session in a task's worktree
// still reads the live queue, and a project in a linked checkout still finds itself. An explicit
// root (`/workstreams <path>`) asks from there, which is how a scratch clone is pointed at.
export async function resolveRoot(
  $: EngineInterface,
  arg: string,
): Promise<{ root: string; problem?: undefined } | { root?: undefined; problem: string }> {
  const asked = arg.trim().replace(/\/+$/, '')
  const where = asked || 'this checkout'
  let ran
  try {
    ran = await $.process.run([WS, 'root'], asked ? { cwd: asked, timeoutMs: 60_000 } : { timeoutMs: 60_000 })
  } catch {
    return { problem: NO_WS }
  }
  if (ran.exitCode === 127) return { problem: NO_WS }
  if (ran.exitCode !== 0) return { problem: `${where} is not a workstream project (\`ws init\` sets one up); nothing opened.` }
  return { root: ran.stdout.trim() }
}

// The pane's only write: `ws act` refuses, writes and commits in one call. A refusal is its one
// stderr line, drawn as given.
export async function runAct(
  $: EngineInterface,
  root: string,
  ws: string,
  confirm: Confirm,
  revisions: Snapshot['revisions'],
): Promise<{ line: string; refused: boolean }> {
  const argv = [WS, 'act', confirm.action, '-w', ws]
  if (confirm.task) argv.push('--task', confirm.task)
  argv.push('--expect-registry', revisions.registry)
  const tasks = revisions.tasks[ws]
  if (tasks) argv.push('--expect-tasks', tasks)
  try {
    const ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
    if (ran.exitCode === 0) return { line: ran.stdout.trim(), refused: false }
    return { line: ran.stderr.trim() || `act exited ${ran.exitCode}`, refused: true }
  } catch (err) {
    return { line: `act did not run: ${String(err)}`, refused: true }
  }
}

// One task's review data; `file` adds that file's capped hunks. A git failure comes back inside
// the JSON as `error`, an unknown id as a non-zero exit.
export async function loadReview(
  $: EngineInterface,
  root: string,
  ws: string,
  task: string,
  file?: string,
): Promise<{ review?: ReviewData; error?: string }> {
  const argv = [WS, 'review', task, '-w', ws, ...(file ? ['--file', file] : [])]
  try {
    const ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
    if (ran.exitCode !== 0) return { error: ran.stderr.trim() || `review exited ${ran.exitCode}` }
    return { review: JSON.parse(ran.stdout) as ReviewData }
  } catch (err) {
    return { error: `review did not run: ${String(err)}` }
  }
}

// `$.fs.read` rejects a missing file and one over 4 MiB.
export async function readText($: EngineInterface, path: string): Promise<{ text: string | null; error: string | null }> {
  try {
    return { text: String(await $.fs.read(path)), error: null }
  } catch (err) {
    return { text: null, error: `could not read ${path}: ${String(err)}` }
  }
}

// Runs with cwd set to the root, so a worktree session still reads the integration branch's files.
export async function loadSnapshot($: EngineInterface, root: string, id?: string): Promise<Loaded> {
  const argv = [WS, 'snapshot', ...(id ? ['-w', id] : [])]
  let ran
  try {
    ran = await $.process.run(argv, { cwd: root, timeoutMs: 60_000 })
  } catch (err) {
    return { error: `snapshot did not run: ${String(err)}` }
  }
  if (ran.exitCode !== 0) {
    return { error: ran.stderr.trim() || `snapshot exited ${ran.exitCode}` }
  }
  try {
    const parsed = JSON.parse(ran.stdout) as Snapshot
    if (parsed.snapshotVersion !== 1) {
      return { error: `snapshot version ${String(parsed.snapshotVersion)}; the pane reads 1` }
    }
    return { snapshot: parsed }
  } catch {
    return { error: 'snapshot printed no JSON' }
  }
}
