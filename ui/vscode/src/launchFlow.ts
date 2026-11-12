// Plan D-LAUNCH: what Run, Coordinate, Close and Abandon ask before they launch, as a chain of quick
// picks. 1. the checks from `ws launch check`, where a blocking one ends the flow on a read-only list
// (beside a read-only tab of `ws validate -w <id>`'s output when validate is one of them);
// 2. the target, from those that can take it, led by a repeat of the last terminal launch while it
// is still offered; 3. for a terminal picked fresh, one preset pick of every agent (`ws launch
// agents`, or the agentCommand setting) x effort x permissions, then the agent's own check; 4. an
// input box holding the prompt. A preset's command line comes from `ws launch argv`. The last
// choices are kept in the workspace's state and offered first next time. Every fact comes from the
// CLI; this file writes nothing but that state.
import * as vscode from 'vscode'

import { type Check, type Cli, loadAgents, loadArgv, loadChecks } from './cli.ts'
import { agentCommand, offeredTargets, type Target } from './launch.ts'
import {
  agents, blockedByValidate, blockedChoices, blockedLine, type Combo, combos, HEALTH_CHECKS, type Last, LAST_KEY, lastCombo, lastFirst, lastOf, type Launch, launchTitle,
  repeatChoice, validateArgs, validateText, verdict,
} from './logic/launch.ts'

export type Step = 'blocked' | 'checks' | 'target' | 'preset'
// A target pick's row: a target alone, or the repeat row, which carries its combo too.
type Picked = { id: string; target: Target; combo?: Combo }
export type Choice<T> = { label: string; description?: string; detail?: string; value: T }

// The flow's questions. The integration test swaps these for scripted answers, since a quick pick
// can't be clicked from the extension API. Undefined is the person pressing Escape.
export type FlowUi = {
  pick<T>(step: Step, title: string, choices: Choice<T>[]): Promise<T | undefined>
  prompt(title: string, value: string): Promise<string | undefined>
}

export const nativeFlowUi: FlowUi = {
  async pick(_step, title, choices) {
    const items = choices.map(c => ({ label: c.label, description: c.description, detail: c.detail, value: c.value }))
    return (await vscode.window.showQuickPick(items, { title, ignoreFocusOut: true, matchOnDescription: true }))?.value
  },
  async prompt(title, value) {
    return vscode.window.showInputBox({
      title, value, prompt: 'The prompt the agent starts on. Edit it, or press Enter.', ignoreFocusOut: true,
      validateInput: text => (text.trim() ? undefined : 'A prompt is needed.'),
    })
  },
}

export type Flow = { cli: Cli; state: vscode.Memento; ui: FlowUi; say(text: string, error?: boolean): void }
export type Ask = { kind: Launch; ws: string; root: string; prompt: string }
// What the person settled on: the target, the prompt, and for a terminal its whole command line.
export type Settled = { target: Target; title: string; prompt: string; argv?: string[] }

function checkChoice(c: Check): Choice<true> {
  return { label: `${c.ok ? '$(pass)' : '$(warning)'} ${c.id}`, description: c.message, value: true }
}

// D011: the read-only documents that hold `ws validate -w <id>`'s whole output, one per root and
// workstream. A content provider's document can't be edited or saved, and a rerun refreshes it.
export const VALIDATE_SCHEME = 'workstreams-validate'

export class ValidateDocuments implements vscode.TextDocumentContentProvider {
  private readonly texts = new Map<string, string>()
  private readonly changed = new vscode.EventEmitter<vscode.Uri>()
  readonly onDidChange = this.changed.event
  // Each tab's URI, in the order the flow opened them; the integration test reads it.
  readonly opened: string[] = []

  provideTextDocumentContent(uri: vscode.Uri): string {
    return this.texts.get(uri.toString()) ?? ''
  }

  async show(flow: Flow, root: string, ws: string): Promise<void> {
    const args = validateArgs(ws)
    const text = validateText(await flow.cli.run([...flow.cli.command, ...args], root), flow.cli.command, ws)
    const uri = vscode.Uri.from({ scheme: VALIDATE_SCHEME, path: `/${ws}/ws ${args.join(' ')}`, query: root })
    this.texts.set(uri.toString(), text)
    this.changed.fire(uri)
    this.opened.push(uri.toString())
    const doc = await vscode.workspace.openTextDocument(uri)
    await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: true })
  }

  dispose(): void {
    this.changed.dispose()
  }
}

export const validateDocuments = new ValidateDocuments()

// Passes when nothing new blocks: says the blocking message and ends, or shows the warnings and
// goes on when the person picks any line.
async function passes(flow: Flow, ask: Ask, title: string, checks: Check[], seen: Set<string>): Promise<boolean> {
  const fresh = checks.filter(c => !seen.has(c.id))
  fresh.forEach(c => seen.add(c.id))
  const { blocking, warnings } = verdict(fresh)
  if (blocking.length) {
    // A read-only list: picking a health-backed check shows Health; nothing launches either way.
    // Validate's errors open in a tab first, so the list opens over it (D011).
    const line = blockedLine(title, blocking)
    flow.say(line, true)
    if (blockedByValidate(blocking)) await validateDocuments.show(flow, ask.root, ask.ws)
    const picked = await flow.ui.pick('blocked', line, blockedChoices(fresh))
    if (picked !== undefined && HEALTH_CHECKS.includes(picked)) await vscode.commands.executeCommand('workstreams.health.focus')
    return false
  }
  if (!warnings.length) return true
  const pickTitle = `${title}: ${warnings.length} warning${warnings.length === 1 ? '' : 's'}. Pick a line to go on, Escape to stop.`
  return (await flow.ui.pick('checks', pickTitle, [...warnings, ...fresh.filter(c => c.ok)].map(checkChoice))) === true
}

async function pickOne<T>(flow: Flow, step: Step, title: string, choices: Choice<T>[]): Promise<T | undefined> {
  if (choices.length === 1) return choices[0].value
  return flow.ui.pick(step, title, choices)
}

export async function launchFlow(flow: Flow, ask: Ask): Promise<Settled | undefined> {
  const title = launchTitle(ask.kind, ask.ws)
  const last = lastOf(flow.state.get(LAST_KEY))
  const now: Last = {}

  // 1. The checks.
  const checked = await loadChecks(flow.cli, ask.root, ask.ws, ask.kind)
  if (checked.error !== undefined) return void flow.say(checked.error, true)
  const seen = new Set<string>()
  if (!(await passes(flow, ask, title, checked.value.checks, seen))) return undefined

  // 2. The target, from those offered now (a chat target's extension is enabled) that can take
  // it: the terminal needs an agent to run.
  const presets = await loadAgents(flow.cli, ask.root)
  if (presets.error !== undefined) flow.say(presets.error, true)
  const offered = agents(presets.value?.agents ?? [], agentCommand())
  const targets = (await offeredTargets()).filter(t => !t.needsAgent || offered.length)
  const all = combos(offered)
  // The last terminal launch whole leads the pick, while every part of it is still offered (plan T6).
  const repeat = repeatChoice(last, targets, all)
  const targetRows: Choice<Picked>[] = lastFirst(targets, t => t.id, last.target).map(t => ({
    label: t.label, description: !repeat && t.id === last.target ? 'last used' : undefined, value: { id: t.id, target: t },
  }))
  const picked = await pickOne(flow, 'target', `${title}: where`,
    repeat ? [{ label: repeat.label, description: repeat.description, value: { id: 'repeat', target: repeat.target, combo: repeat.combo } }, ...targetRows] : targetRows)
  if (!picked) return undefined
  const target = picked.target
  now.target = target.id

  // 3. For a terminal, one preset pick of every agent x effort x permissions, the remembered first;
  // the repeat row has already settled it.
  let combo: Combo | undefined
  if (target.needsAgent) {
    const remembered = lastCombo(all, last)
    combo = picked.combo ?? await pickOne(flow, 'preset', `${title}: agent, effort and permissions`,
      lastFirst(all, c => c.id, remembered?.id).map(c => ({ label: c.label, description: c.agent.detail, detail: c === remembered ? 'last used' : undefined, value: c })))
    if (!combo) return undefined
    Object.assign(now, { agent: combo.agent.id, effort: combo.effort, permissions: combo.permissions })
    // The agent's own check (its skills are installed), shown the same way, repeated or not.
    const preset = combo.agent.preset
    if (preset) {
      const again = await loadChecks(flow.cli, ask.root, ask.ws, ask.kind, preset.agent)
      if (again.error !== undefined) return void flow.say(again.error, true)
      if (!(await passes(flow, ask, title, again.value.checks, seen))) return undefined
    }
  }
  const agent = combo?.agent
  const effort = combo?.effort || undefined
  const permissions = combo?.permissions || undefined

  // 4. The prompt, editable.
  const prompt = (await flow.ui.prompt(title, ask.prompt))?.trim()
  if (!prompt) return undefined

  let argv: string[] | undefined
  if (agent?.preset) {
    const built = await loadArgv(flow.cli, ask.root, ask.ws, { agent: agent.preset.agent, kind: ask.kind, prompt, effort, permissions })
    if (built.error !== undefined) return void flow.say(built.error, true)
    argv = built.value.argv
  } else if (agent?.argv) {
    argv = [...agent.argv, prompt]
  }
  await flow.state.update(LAST_KEY, { ...last, ...now })
  return { target, title, prompt, argv }
}
