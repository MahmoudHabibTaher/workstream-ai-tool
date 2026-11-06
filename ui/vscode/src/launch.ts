// Where a launch goes. Each target says whether it can take the launch now; the first that can
// starts it. Today that is the terminal, when `workstreams.agentCommand` is set, then the
// clipboard. A chat target would join TARGETS here, and callers would not change: they only call
// `launch`.
import * as vscode from 'vscode'

import { terminalOptions } from './logic/launch.ts'

export const AGENT_SETTING = 'agentCommand'

export type Request = { title: string; prompt: string; root: string }
// What the target did, in a line the caller shows.
export type Started = { target: string; said: string; terminal?: vscode.Terminal }

export type Target = {
  id: string
  // Returns undefined when this target can't take the request, so the next one is tried.
  start(request: Request): Promise<Started | undefined>
}

function agentCommand(): string[] {
  return vscode.workspace.getConfiguration('workstreams').get<string[]>(AGENT_SETTING, []) ?? []
}

const terminal: Target = {
  id: 'terminal',
  async start(request) {
    const options = terminalOptions(agentCommand(), request.prompt, request.root, `Workstreams: ${request.title}`)
    if (!options) return undefined
    const created = vscode.window.createTerminal(options)
    created.show()
    return { target: 'terminal', said: `Started ${options.shellPath} in a terminal: ${request.title}`, terminal: created }
  },
}

const clipboard: Target = {
  id: 'clipboard',
  async start(request) {
    await vscode.env.clipboard.writeText(request.prompt)
    return { target: 'clipboard', said: `Copied: ${request.prompt} (set workstreams.${AGENT_SETTING} to start an agent instead)` }
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
