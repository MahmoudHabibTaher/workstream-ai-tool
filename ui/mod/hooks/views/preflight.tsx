// Pre-flight: what `ws launch check` said about the launch the person pressed, and the
// launch button itself, which a blocking failure replaces with its message.
import type { Check, Preflight } from '../../types'
import { Caption, Section } from './style'

// The pre-flight that belongs to this launch, on this workstream and task, or null.
export function preflightFor(pf: Preflight | null, ws: string, kind: string, task: string | null): Preflight | null {
  return pf && pf.ws === ws && pf.kind === kind && pf.task === task ? pf : null
}

// Why the launch is held: the first blocking check that failed, or the error that kept the
// check or the prompt from coming back.
export function blockedBy(pf: Preflight | null): string | null {
  if (!pf || !pf.blocked) return null
  if (pf.error) return pf.error
  return pf.checks.find(c => c.blocking && !c.ok)?.message ?? 'a blocking check failed'
}

export function checkWord(check: Check): string {
  if (check.ok) return 'ok'
  return check.blocking ? 'BLOCKS' : 'warn'
}

function checkColor(check: Check): string {
  if (check.ok) return 'success'
  return check.blocking ? 'error' : 'warning'
}

export type LaunchControl = {
  key: string
  label: string
  isPrimary: boolean
  pf: Preflight | null
  onPress: () => void
}

// The surface's Button has no disabled state, so a held launch draws as text, not a button.
export function LaunchSlot(ui: any, control: LaunchControl) {
  const { Button, Text } = ui
  const held = blockedBy(control.pf)
  if (held) {
    return (
      <Text key={control.key} dimColor>
        {control.label.replace(/…$/, '')} (blocked: {held})
      </Text>
    )
  }
  return (
    <Button key={control.key} variant={control.isPrimary ? 'primary' : undefined} onPress={control.onPress}>
      {control.label}
    </Button>
  )
}

// Every check, with what came of it: the box filled, or nothing filled and why.
export function PreflightBox(ui: any, pf: Preflight, label: string, onRecheck: () => void) {
  const { Button, Text } = ui
  const held = blockedBy(pf)
  return Section(
    ui,
    `Pre-flight: ${label}`,
    held ? 'error' : 'promptBorder',
    pf.checks.map(c => (
      <Text key={`check:${c.id}`}>
        <Text color={checkColor(c)}>{checkWord(c)}</Text> {c.id} · {c.message}
      </Text>
    )),
    pf.error && <Text color="error">{pf.error}</Text>,
    Caption(ui, held ? 'Blocked: nothing was filled.' : pf.filled ? 'Filled the prompt box; nothing was sent.' : ''),
    <Button key="preflight:recheck" onPress={onRecheck}>
      Check again
    </Button>,
  )
}
