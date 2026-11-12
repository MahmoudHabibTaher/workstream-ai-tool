// Where a launch goes. The launch flow (launchFlow.ts) lets the person pick a target from those
// that can take the launch now, and `launch` starts it; with no pick, the first that can starts
// it. Today the targets are the terminal, which runs an agent's argv, then the clipboard. A chat
// target would join TARGETS here, and callers would not change: they only call `launch`.
import * as vscode from 'vscode'

import { argvOptions, terminalOptions } from './logic/launch.ts'

export const AGENT_SETTING = 'agentCommand'

// `argv` is the whole command line the terminal runs, prompt included, as `ws launch argv` built
// it. Without it the terminal runs `workstreams.agentCommand` with the prompt appended.
export type Request = { title: string; prompt: string; root: string; argv?: string[] }
// What the target did, in a line the caller shows.
export type Started = { target: string; said: string; terminal?: vscode.Terminal }

export type Target = {
  id: string
  label: string
  // Whether the flow asks for an agent before this target starts.
  needsAgent: boolean
  // Returns undefined when this target can't take the request, so the next one is tried.
  start(request: Request): Promise<Started | undefined>
}

export function agentCommand(): string[] {
  return vscode.workspace.getConfiguration('workstreams').get<string[]>(AGENT_SETTING, []) ?? []
}

// How a terminal is made. The integration test swaps `create` for one that records the options and
// runs a harmless command, so a preset's agent never really starts there.
export const terminalHost = {
  create: (options: vscode.TerminalOptions): vscode.Terminal => vscode.window.createTerminal(options),
}

const terminal: Target = {
  id: 'terminal',
  label: 'Terminal',
  needsAgent: true,
  async start(request) {
    const name = `Workstreams: ${request.title}`
    const options = request.argv ? argvOptions(request.argv, request.root, name) : terminalOptions(agentCommand(), request.prompt, request.root, name)
    if (!options) return undefined
    const created = terminalHost.create(options)
    created.show()
    return { target: 'terminal', said: `Started ${options.shellPath} in a terminal: ${request.title}`, terminal: created }
  },
}

const clipboard: Target = {
  id: 'clipboard',
  label: 'Copy the prompt',
  needsAgent: false,
  async start(request) {
    await vscode.env.clipboard.writeText(request.prompt)
    return { target: 'clipboard', said: `Copied: ${request.prompt} (set workstreams.${AGENT_SETTING} or pick an agent to start one instead)` }
  },
}

export const TARGETS: Target[] = [terminal, clipboard]

export async function launch(request: Request, targets: Target[] = TARGETS): Promise<Started> {
  for (const target of targets) {
    const started = await target.start(request)
    if (started) return started
  }
  throw new Error('no launch target took the prompt')
}
