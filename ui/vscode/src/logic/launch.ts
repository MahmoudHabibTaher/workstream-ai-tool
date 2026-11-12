// What a launch starts: one table of prompts, the same text as the web UI's `promptText`, and the
// terminal a configured agent runs in. Nothing here imports `vscode`, so `node --test` covers it.
import type { Check, Preset } from '../cli.ts'

export const LAUNCHES = ['run', 'coordinate', 'close', 'abandon'] as const
export type Launch = (typeof LAUNCHES)[number]

// The abandon prompt's `<why>` is filled with the reason the person gives first.
export const WHY = '<why>'

const PROMPTS: Record<Launch, (ws: string) => string> = {
  run: ws => `Use the ws-run skill to run workstream ${ws}.`,
  coordinate: ws => `Use the ws-coordinate skill on workstream ${ws}.`,
  close: ws => `Use the ws-coordinate skill to close workstream ${ws}.`,
  abandon: ws => `Use the ws-coordinate skill to abandon workstream ${ws}: <why>`,
}

export function promptText(kind: Launch, ws: string, why?: string): string {
  const text = PROMPTS[kind](ws)
  return why === undefined ? text : text.replace(WHY, why)
}

export function needsReason(kind: Launch): boolean {
  return PROMPTS[kind]('').includes(WHY)
}

export type TerminalOptions = { name: string; shellPath: string; shellArgs: string[]; cwd: string }

// The agent's argv with the prompt as its last argument, started as the terminal's own process,
// so no shell parses the prompt. Undefined when no agent command is set.
export function terminalOptions(agent: readonly string[] | undefined, prompt: string, root: string, name: string): TerminalOptions | undefined {
  const argv = (agent ?? []).filter(a => typeof a === 'string')
  if (!argv.length || !argv[0]) return undefined
  return { name, shellPath: argv[0], shellArgs: [...argv.slice(1), prompt], cwd: root }
}

export function launchTitle(kind: Launch, ws: string): string {
  return `${kind[0].toUpperCase()}${kind.slice(1)} ${ws}`
}

// A whole command line from `ws launch argv`, prompt included, as the terminal's own process.
export function argvOptions(argv: readonly string[], root: string, name: string): TerminalOptions | undefined {
  if (!argv.length || !argv[0]) return undefined
  return { name, shellPath: argv[0], shellArgs: argv.slice(1), cwd: root }
}

// --- the launch flow's choices (launchFlow.ts asks them) ----------------------------------------

// The failing checks, split: any blocking one ends the flow, warnings are shown and passed.
export function verdict(checks: readonly Check[]): { blocking: Check[]; warnings: Check[] } {
  const failing = checks.filter(c => !c.ok)
  return { blocking: failing.filter(c => c.blocking), warnings: failing.filter(c => !c.blocking) }
}

export function blockedLine(title: string, blocking: readonly Check[]): string {
  return `${title} is blocked: ${blocking.map(c => `${c.id}: ${c.message}`).join('; ')}`
}

// An agent the terminal can run: a preset from `ws launch agents`, or the agentCommand setting.
export type Agent = { id: string; label: string; detail: string; preset?: Preset; argv?: string[] }

export const SETTING_AGENT = 'setting'

export function agents(presets: readonly Preset[], setting: readonly string[]): Agent[] {
  const out: Agent[] = presets.map(p => ({ id: p.agent, label: p.label, detail: p.command, preset: p }))
  const argv = setting.filter(a => typeof a === 'string')
  if (argv.length && argv[0]) out.push({ id: SETTING_AGENT, label: 'workstreams.agentCommand', detail: argv.join(' '), argv })
  return out
}

// What the flow remembers per workspace: the last target, agent, effort and permissions. An
// empty effort or permissions means the person picked none.
export type Last = { target?: string; agent?: string; effort?: string; permissions?: string }
export const LAST_KEY = 'workstreams.launch.last'

export function lastOf(stored: unknown): Last {
  if (!stored || typeof stored !== 'object') return {}
  const out: Last = {}
  for (const key of ['target', 'agent', 'effort', 'permissions'] as const) {
    const value = (stored as Record<string, unknown>)[key]
    if (typeof value === 'string') out[key] = value
  }
  return out
}

// The choices in their order, with the last one used moved to the front, so Enter repeats it.
export function lastFirst<T>(items: readonly T[], idOf: (item: T) => string, last: string | undefined): T[] {
  const at = last === undefined ? -1 : items.findIndex(i => idOf(i) === last)
  return at <= 0 ? [...items] : [items[at], ...items.slice(0, at), ...items.slice(at + 1)]
}

// An effort or permissions pick: none first (no flag), then the preset's own.
export function levels(values: readonly string[]): string[] {
  return ['', ...values]
}
