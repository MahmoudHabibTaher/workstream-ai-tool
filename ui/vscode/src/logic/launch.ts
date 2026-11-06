// What a launch starts: one table of prompts, the same text as the web UI's `promptText`, and the
// terminal a configured agent runs in. Nothing here imports `vscode`, so `node --test` covers it.

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
