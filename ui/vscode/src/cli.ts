// Every call the extension makes outside itself, all to the `ws` CLI, which stays the only source
// of truth: the extension arranges what it returns and writes only through `ws act`. It never
// imports `vscode`, so `node --test` runs it with a stub in place of `execFile`.
import { execFile } from 'node:child_process'

export const SETTING = 'workstreams.wsCommand'
const TIMEOUT_MS = 60_000
const MAX_BUFFER = 64 * 1024 * 1024

export type Ran = { exitCode: number; stdout: string; stderr: string; missing?: boolean }
// Runs `argv` (the whole command, `wsCommand` first) in `cwd`. Never through a shell, and with git's
// optional locks off, as `ws serve` runs: a read must not touch the index the watchers watch.
export type Run = (argv: string[], cwd: string) => Promise<Ran>
export type Cli = { command: string[]; run: Run }

export type Revisions = { registry: string; tasks: Record<string, string> }
export type Snapshot = { snapshotVersion: number; revisions: Revisions; [key: string]: unknown }
export type Confirm = { action: string; task?: string }

export function noWs(command: string[]): string {
  return `The ws CLI did not start (${JSON.stringify(command)}). Install it, or set ${SETTING} to the argv that runs it.`
}

export function notAProject(folder: string): string {
  return `${folder} is not a workstream project (\`ws init\` sets one up); nothing opened.`
}

export const execRun: Run = (argv, cwd) =>
  new Promise(resolve => {
    const [file, ...args] = argv
    execFile(file, args, { cwd, env: { ...process.env, GIT_OPTIONAL_LOCKS: '0' }, timeout: TIMEOUT_MS, maxBuffer: MAX_BUFFER, shell: false, encoding: 'utf8' },
      (err, stdout, stderr) => {
        if (!err) return resolve({ exitCode: 0, stdout, stderr })
        const code = (err as NodeJS.ErrnoException).code
        if (code === 'ENOENT' || code === 'EACCES') return resolve({ exitCode: 127, stdout, stderr, missing: true })
        if (typeof code === 'number') return resolve({ exitCode: code, stdout, stderr })
        const why = (err as { killed?: boolean }).killed ? `timed out after ${TIMEOUT_MS / 1000}s` : String(err)
        resolve({ exitCode: -1, stdout, stderr: stderr || why })
      })
  })

export function makeCli(command: string[], run: Run = execRun): Cli {
  return { command: command.length ? command : ['ws'], run }
}

async function ws(cli: Cli, args: string[], cwd: string): Promise<Ran> {
  return cli.run([...cli.command, ...args], cwd)
}

export type Roots =
  | { roots: string[]; problem?: undefined; missing?: undefined }
  | { roots?: undefined; problem: string; missing: boolean }

// `ws root` per workspace folder, deduplicated: two folders in one project are one root, and a
// task's worktree still finds the checkout that holds the integration branch. A missing `ws` stops
// everything at the first folder. Folders that aren't projects are skipped, and only when none is
// one does that become the problem.
export async function resolveRoots(cli: Cli, folders: string[]): Promise<Roots> {
  const roots: string[] = []
  for (const folder of folders) {
    const ran = await ws(cli, ['root'], folder)
    if (ran.missing) return { problem: noWs(cli.command), missing: true }
    if (ran.exitCode !== 0) continue
    const root = ran.stdout.trim()
    if (root && !roots.includes(root)) roots.push(root)
  }
  if (!roots.length) return { problem: notAProject(folders.join(', ') || 'This window'), missing: false }
  return { roots }
}

export type Loaded<T> = { value: T; error?: undefined } | { value?: undefined; error: string }

function failed(what: string, ran: Ran, command: string[]): string {
  if (ran.missing) return noWs(command)
  return ran.stderr.trim() || `${what} exited ${ran.exitCode}`
}

function parsed<T>(what: string, ran: Ran, command: string[]): Loaded<T> {
  if (ran.exitCode !== 0) return { error: failed(what, ran, command) }
  try {
    return { value: JSON.parse(ran.stdout) as T }
  } catch {
    return { error: `${what} printed no JSON` }
  }
}

// Runs with cwd set to the root, so a worktree window still reads the integration branch's files.
export async function loadSnapshot(cli: Cli, root: string, id?: string): Promise<Loaded<Snapshot>> {
  const got = parsed<Snapshot>('snapshot', await ws(cli, ['snapshot', ...(id ? ['-w', id] : [])], root), cli.command)
  if (got.error !== undefined) return got
  if (got.value.snapshotVersion !== 1) {
    return { error: `snapshot version ${String(got.value.snapshotVersion)}; the extension reads 1` }
  }
  return got
}

export type ReviewAsk = { checks?: boolean; file?: string }

// One task's review data: `checks` adds the gates, acceptance beside proof and the evidence, and
// `file` adds that file's capped hunks. A git failure comes back inside the JSON as `error`.
export async function loadReview(cli: Cli, root: string, wsId: string, task: string, ask: ReviewAsk = {}): Promise<Loaded<unknown>> {
  const args = ['review', task, '-w', wsId, ...(ask.checks ? ['--checks'] : []), ...(ask.file ? ['--file', ask.file] : [])]
  return parsed('review', await ws(cli, args, root), cli.command)
}

// What can be reviewed across the open workstreams.
export async function loadQueue(cli: Cli, root: string): Promise<Loaded<unknown>> {
  return parsed('review queue', await ws(cli, ['review', '--queue'], root), cli.command)
}

export async function loadBudget(cli: Cli, root: string): Promise<Loaded<unknown>> {
  return parsed('audit', await ws(cli, ['audit', 'context', '--json'], root), cli.command)
}

// The extension's only write: `ws act` refuses, writes and commits in one call, against the
// revisions of the snapshot the person saw. A refusal is its stderr, shown as given.
export async function runAct(cli: Cli, root: string, wsId: string, confirm: Confirm, revisions: Revisions): Promise<{ line: string; refused: boolean }> {
  const args = ['act', confirm.action, '-w', wsId]
  if (confirm.task) args.push('--task', confirm.task)
  args.push('--expect-registry', revisions.registry)
  const tasks = revisions.tasks[wsId]
  if (tasks) args.push('--expect-tasks', tasks)
  const ran = await ws(cli, args, root)
  if (ran.exitCode === 0) return { line: ran.stdout.trim(), refused: false }
  return { line: failed('act', ran, cli.command), refused: true }
}
