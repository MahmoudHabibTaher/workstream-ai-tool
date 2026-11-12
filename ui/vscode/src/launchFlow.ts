// Plan D-LAUNCH: what Run, Coordinate, Close and Abandon ask before they launch, as a chain of quick
// picks. 1. the checks from `ws launch check`, where a blocking one ends the flow with its message;
// 2. the target, from those that can take it; 3. for a terminal, the agent (`ws launch agents`, or
// the agentCommand setting), then a preset's effort and permissions; 4. an input box holding the
// prompt. A preset's command line comes from `ws launch argv`. The last choices are kept in the
// workspace's state and offered first next time. Every fact comes from the CLI; this file writes
// nothing but that state.
import * as vscode from 'vscode'

import { type Check, type Cli, loadAgents, loadArgv, loadChecks } from './cli.ts'
import { agentCommand, type Target, TARGETS } from './launch.ts'
import {
  type Agent, agents, blockedLine, type Last, LAST_KEY, lastFirst, lastOf, type Launch, launchTitle, levels, promptText, verdict,
} from './logic/launch.ts'

export type Step = 'checks' | 'target' | 'agent' | 'effort' | 'permissions'
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
export type Ask = { kind: Launch; ws: string; root: string; why?: string }
// What the person settled on: the target, the prompt, and for a terminal its whole command line.
export type Settled = { target: Target; title: string; prompt: string; argv?: string[] }

const NONE = 'none (no flag)'

function checkChoice(c: Check): Choice<true> {
  return { label: `${c.ok ? '$(pass)' : '$(warning)'} ${c.id}`, description: c.message, value: true }
}

// Passes when nothing new blocks: says the blocking message and ends, or shows the warnings and
// goes on when the person picks any line.
async function passes(flow: Flow, title: string, checks: Check[], seen: Set<string>): Promise<boolean> {
  const fresh = checks.filter(c => !seen.has(c.id))
  fresh.forEach(c => seen.add(c.id))
  const { blocking, warnings } = verdict(fresh)
  if (blocking.length) {
    flow.say(blockedLine(title, blocking), true)
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
  if (!(await passes(flow, title, checked.value.checks, seen))) return undefined

  // 2. The target, from those that can take it: the terminal needs an agent to run.
  const presets = await loadAgents(flow.cli, ask.root)
  if (presets.error !== undefined) flow.say(presets.error, true)
  const offered = agents(presets.value?.agents ?? [], agentCommand())
  const targets = TARGETS.filter(t => !t.needsAgent || offered.length)
  const target = await pickOne(flow, 'target', `${title}: where`,
    lastFirst(targets, t => t.id, last.target).map(t => ({ label: t.label, description: t.id === last.target ? 'last used' : undefined, value: t })))
  if (!target) return undefined
  now.target = target.id

  // 3. For a terminal, the agent, and a preset's effort and permissions.
  let agent: Agent | undefined
  let effort: string | undefined
  let permissions: string | undefined
  if (target.needsAgent) {
    agent = await pickOne(flow, 'agent', `${title}: agent`,
      lastFirst(offered, a => a.id, last.agent).map(a => ({ label: a.label, description: a.detail, detail: a.id === last.agent ? 'last used' : undefined, value: a })))
    if (!agent) return undefined
    now.agent = agent.id
    const preset = agent.preset
    if (preset) {
      for (const [step, values, remembered] of [['effort', preset.effortLevels, last.effort], ['permissions', preset.permissionChoices, last.permissions]] as const) {
        if (!values.length) continue
        const chosen = await flow.ui.pick(step, `${title}: ${preset.label} ${step}`,
          lastFirst(levels(values), v => v, remembered).map(v => ({ label: v || NONE, description: v === remembered ? 'last used' : undefined, value: v })))
        if (chosen === undefined) return undefined
        now[step] = chosen
        if (step === 'effort') effort = chosen || undefined
        else permissions = chosen || undefined
      }
      // The agent's own check (its skills are installed), shown the same way.
      const again = await loadChecks(flow.cli, ask.root, ask.ws, ask.kind, preset.agent)
      if (again.error !== undefined) return void flow.say(again.error, true)
      if (!(await passes(flow, title, again.value.checks, seen))) return undefined
    }
  }

  // 4. The prompt, editable.
  const prompt = (await flow.ui.prompt(title, promptText(ask.kind, ask.ws, ask.why)))?.trim()
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
