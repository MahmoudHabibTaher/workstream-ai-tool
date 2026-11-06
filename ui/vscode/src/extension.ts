// Activation: read the `ws` argv setting, find the window's projects, load their snapshots. Every
// fact comes from the CLI through cli.ts; nothing here works one out.
import * as vscode from 'vscode'

import { type Cli, execRun, makeCli, type Run } from './cli.ts'
import { start, type Started } from './logic/start.ts'

// What activate returns: the state the views will draw, every argv run and every message shown,
// so the integration test can see what the extension did.
export type Api = { ready: Promise<Started>; ran: string[][]; shown: string[] }

export function activate(_context: vscode.ExtensionContext): Api {
  const ran: string[][] = []
  const recorded: Run = (argv, cwd) => {
    ran.push(argv)
    return execRun(argv, cwd)
  }
  const command = vscode.workspace.getConfiguration('workstreams').get<string[]>('wsCommand', ['ws'])
  const cli: Cli = makeCli(command, recorded)
  const folders = (vscode.workspace.workspaceFolders ?? []).map(f => f.uri.fsPath)
  const shown: string[] = []
  const show = (started: Started): Started => {
    const message = started.message
    if (message) shown.push(message.text)
    if (message?.level === 'error') void vscode.window.showErrorMessage(message.text)
    else if (message) void vscode.window.showInformationMessage(message.text)
    for (const [root, error] of Object.entries(started.errors)) {
      shown.push(`${root}: ${error}`)
      void vscode.window.showErrorMessage(`${root}: ${error}`)
    }
    return started
  }
  const ready = folders.length ? start(cli, folders).then(show) : Promise.resolve<Started>({ roots: [], snapshots: {}, errors: {} })
  return { ready, ran, shown }
}

export function deactivate(): void {}
