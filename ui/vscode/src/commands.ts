// The trees' context-menu commands, which the Health quick fixes call too. Pause, Resume, Sync and Unclaim ask first, then write through
// `ws act` against the revisions the item was drawn with. Run, Coordinate, Close and Abandon run
// the launch flow (launchFlow.ts), then hand its prompt to launch.ts. package.json shows each command only where the item's contextValue
// offers it, and the handler checks the item again, so a write the snapshot didn't offer never
// reaches act.
import * as vscode from 'vscode'

import { type Cli, runAct } from './cli.ts'
import { launch, type Started } from './launch.ts'
import { type ConfirmText, confirmText, moved, openCommandOf, OPENS, type Picked, pickedTarget, type Write, WRITES } from './logic/actions.ts'
import type { DocName } from './logic/format.ts'
import { type Launch, LAUNCHES, needsReason, offerPrompt } from './logic/launch.ts'
import { type FlowUi, launchFlow } from './launchFlow.ts'
import { type FindingNode, offerOf } from './logic/health.ts'
import type { Store } from './logic/store.ts'
import type { TaskNode } from './views/tasks.ts'
import type { WorkstreamNode } from './views/workstreams.ts'

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

// `picked` is what a linked view's title menu acts on, since a title passes no item.
export type Recorder = {
  ui: Ui; asked: ConfirmText[]; launched: Started[]; say(text: string, error?: boolean): void
  picked(): Picked<WorkstreamNode, TaskNode>
  // The launch flow's questions, and where it keeps the last choices.
  flowUi: FlowUi; state: vscode.Memento
}

type Target = WorkstreamNode | TaskNode | FindingNode

// The workstream and task a write is for: the item's own, or a finding's offer for that write.
function targetOf(action: Write, node: Target): { ws: string; task?: string } | undefined {
  if (node.kind === 'finding') return offerOf(node.finding, action)
  return node.kind === 'workstream' ? { ws: node.row.id } : { ws: node.ws, task: node.task.id }
}

export const commandOf = (name: Write | Launch) => `workstreams.${name}`

export function registerCommands(cli: Cli, store: Store, reload: () => Promise<void>, rec: Recorder): vscode.Disposable[] {
  const write = async (action: Write, item?: Target) => {
    const node = item ?? pickedTarget(action, rec.picked())
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

  const start = async (kind: Launch, item?: Target) => {
    const node = item ?? rec.picked().workstream
    // The offer and its prompt come from the snapshot the item was drawn with.
    const offer = node?.kind === 'workstream' && node.launches.includes(kind) ? node.row.launches?.find(l => l.kind === kind) : undefined
    if (!node || node.kind !== 'workstream' || !offer) return rec.say(`${kind} isn't offered here.`, true)
    const ws = node.row.id
    let why: string | undefined
    if (needsReason(offer)) {
      why = (await rec.ui.reason(ws))?.trim()
      if (!why) return
    }
    const settled = await launchFlow({ cli, state: rec.state, ui: rec.flowUi, say: rec.say }, { kind, ws, root: node.root, prompt: offerPrompt(offer, why) })
    if (!settled) return
    const started = await launch({ title: settled.title, prompt: settled.prompt, root: node.root, argv: settled.argv }, [settled.target])
    rec.launched.push(started)
    rec.say(started.said)
  }

  // A document of the workstream's own snapshot, opened in an editor.
  const open = async (name: DocName, item?: Target) => {
    const node = item ?? rec.picked().workstream
    if (!node || node.kind !== 'workstream') return rec.say(`Open ${name} isn't offered here.`, true)
    const got = await store.workstream(node.root, node.row.id)
    if (got.error !== undefined) return rec.say(got.error, true)
    const path = got.value.paths?.[name]
    if (typeof path !== 'string') return rec.say(`${node.row.id} has no ${name} file.`, true)
    await vscode.commands.executeCommand('vscode.open', vscode.Uri.file(path))
  }

  return [
    ...OPENS.map(name => vscode.commands.registerCommand(openCommandOf(name), (node?: Target) => open(name, node))),
    ...WRITES.map(action => vscode.commands.registerCommand(commandOf(action), (node?: Target) => write(action, node))),
    ...LAUNCHES.map(kind => vscode.commands.registerCommand(commandOf(kind), (node?: Target) => start(kind, node))),
  ]
}
