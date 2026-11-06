// The trees' context-menu commands, which the Health quick fixes call too. Pause, Resume, Sync and Unclaim ask first, then write through
// `ws act` against the revisions the item was drawn with. Run, Coordinate, Close and Abandon hand
// a prompt to launch.ts. package.json shows each command only where the item's contextValue
// offers it, and the handler checks the item again, so a write the snapshot didn't offer never
// reaches act.
import * as vscode from 'vscode'

import { type Cli, runAct } from './cli.ts'
import { launch, type Started } from './launch.ts'
import { type ConfirmText, confirmText, moved, type Write, WRITES } from './logic/actions.ts'
import { type Launch, LAUNCHES, launchTitle, needsReason, promptText } from './logic/launch.ts'
import { type FindingNode, offerOf } from './logic/health.ts'
import type { Node } from './logic/registry.ts'
import type { Store } from './logic/store.ts'

// The two questions a command asks. The integration test swaps these for answers, because a
// modal can't be clicked from the extension API.
export type Ui = {
  confirm(text: ConfirmText): Promise<boolean>
  reason(ws: string): Promise<string | undefined>
}

export const nativeUi: Ui = {
  async confirm(text) {
    const yes = 'Confirm'
    return (await vscode.window.showWarningMessage(text.message, { modal: true, detail: text.detail }, yes)) === yes
  },
  async reason(ws) {
    return vscode.window.showInputBox({
      title: `Abandon ${ws}`, prompt: 'Why is this workstream being abandoned? The prompt carries it.', ignoreFocusOut: true,
      validateInput: value => (value.trim() ? undefined : 'A reason is needed.'),
    })
  },
}

export type Recorder = { ui: Ui; asked: ConfirmText[]; launched: Started[]; say(text: string, error?: boolean): void }

type Target = Extract<Node, { kind: 'workstream' } | { kind: 'task' }> | FindingNode

// The workstream and task a write is for: the item's own, or a finding's offer for that write.
function targetOf(action: Write, node: Target): { ws: string; task?: string } | undefined {
  if (node.kind === 'finding') return offerOf(node.finding, action)
  return node.kind === 'workstream' ? { ws: node.row.id } : { ws: node.ws, task: node.task.id }
}

export const commandOf = (name: Write | Launch) => `workstreams.${name}`

export function registerCommands(cli: Cli, store: Store, reload: () => Promise<void>, rec: Recorder): vscode.Disposable[] {
  const write = async (action: Write, node?: Target) => {
    const target = node && node.writes.includes(action) ? targetOf(action, node) : undefined
    if (!node || !target) return rec.say(`${action} isn't offered here.`, true)
    const { ws, task } = target
    // Pinned now, from the snapshot the item was drawn with: a reload while the box is open
    // changes the tree, not what this write expects.
    const pinned = node.revisions
    const latest = store.snapshots[node.root]
    const text = confirmText(ws, action, task, String(latest?.integrationBranch ?? 'the integration branch'), moved(pinned, latest?.revisions, ws))
    rec.asked.push(text)
    if (!(await rec.ui.confirm(text))) return
    const result = await runAct(cli, node.root, ws, { action, task }, pinned)
    rec.say(result.line, result.refused)
    await reload()
  }

  const start = async (kind: Launch, node?: Target) => {
    if (!node || node.kind !== 'workstream' || !node.launch) return rec.say(`${kind} isn't offered here.`, true)
    const ws = node.row.id
    let why: string | undefined
    if (needsReason(kind)) {
      why = (await rec.ui.reason(ws))?.trim()
      if (!why) return
    }
    const started = await launch({ title: launchTitle(kind, ws), prompt: promptText(kind, ws, why), root: node.root })
    rec.launched.push(started)
    rec.say(started.said)
  }

  return [
    ...WRITES.map(action => vscode.commands.registerCommand(commandOf(action), (node?: Target) => write(action, node))),
    ...LAUNCHES.map(kind => vscode.commands.registerCommand(commandOf(kind), (node?: Target) => start(kind, node))),
  ]
}
