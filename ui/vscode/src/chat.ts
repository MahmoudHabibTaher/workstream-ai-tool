// The chat targets: the launch's prompt goes to an agent extension's chat instead of a terminal.
// This is the one file that names those extensions (tests/test_vscode_files.py lets it). Each
// target is offered only while its extension is enabled, and neither asks for an agent: the chat
// is the agent.
//
// - Copilot Chat: `workbench.action.chat.open` with `{ query, mode: 'agent' }`. The command only
//   exists while the Copilot Chat extension is enabled, so both are checked. The engine is
//   ^1.100.0, where the agent mode is called `agent` (an older build called it `edit`).
// - Claude Code: its URI handler, `vscode://anthropic.claude-code/open?prompt=<text>`, opens a new
//   panel with the prompt filled in. The query is built by URLSearchParams, so no prompt text can
//   add or break a parameter.
import * as vscode from 'vscode'

import type { Target } from './launch.ts'

export const COPILOT_CHAT = 'github.copilot-chat'
export const CHAT_OPEN = 'workbench.action.chat.open'
export const CHAT_MODE = 'agent'
export const CLAUDE_CODE = 'anthropic.claude-code'

// What the chat targets ask of VS Code. The integration test swaps these, so it sees each call
// without either extension installed.
export const chatHost = {
  enabled: (id: string): boolean => vscode.extensions.getExtension(id) !== undefined,
  commands: (): Thenable<string[]> => vscode.commands.getCommands(true),
  execute: (command: string, ...args: unknown[]): Thenable<unknown> => vscode.commands.executeCommand(command, ...args),
  openExternal: (uri: vscode.Uri): Thenable<boolean> => vscode.env.openExternal(uri),
}

// The Claude Code URI holding the prompt. `query` holds URLSearchParams' text, which is exactly what
// the extension's handler reads back with `new URLSearchParams(uri.query)`.
export function claudeCodeUri(prompt: string): vscode.Uri {
  return vscode.Uri.from({ scheme: vscode.env.uriScheme, authority: CLAUDE_CODE, path: '/open', query: new URLSearchParams({ prompt }).toString() })
}

const copilotChat: Target = {
  id: 'copilot-chat',
  label: 'Copilot Chat (agent mode)',
  needsAgent: false,
  async offered() {
    return chatHost.enabled(COPILOT_CHAT) && (await chatHost.commands()).includes(CHAT_OPEN)
  },
  async start(request) {
    if (!(await this.offered?.())) return undefined
    await chatHost.execute(CHAT_OPEN, { query: request.prompt, mode: CHAT_MODE })
    return { target: 'copilot-chat', said: `Opened Copilot Chat in agent mode: ${request.title}` }
  },
}

const claudeCode: Target = {
  id: 'claude-code',
  label: 'Claude Code panel',
  needsAgent: false,
  async offered() {
    return chatHost.enabled(CLAUDE_CODE)
  },
  async start(request) {
    if (!(await this.offered?.())) return undefined
    if (!(await chatHost.openExternal(claudeCodeUri(request.prompt)))) return undefined
    return { target: 'claude-code', said: `Opened a Claude Code panel with the prompt: ${request.title}` }
  },
}

export const CHAT_TARGETS: Target[] = [copilotChat, claudeCode]
