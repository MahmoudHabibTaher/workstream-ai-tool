// Findings by level, with only the actions the snapshot lists, and
// the confirm box every pane write passes through.
import type { ActAction, Confirm, Finding, Snapshot } from '../../types'
import { GAP, Section, Title, Toolbar } from './style'

export function findingsFor(snapshot: Snapshot, ws: string): Finding[] {
  return snapshot.health.filter(f => f.workstream === ws || f.workstream === null)
}

// Whether a finding offers this write for this task: the snapshot decides.
export function offers(snapshot: Snapshot, ws: string, action: ActAction, task: string): boolean {
  return snapshot.health.some(f => f.actions.some(a => a.action === action && a.workstream === ws && a.task === task))
}

export function commitLine(ws: string, confirm: Confirm): string {
  return `${ws}: ${confirm.action}${confirm.task ? ` ${confirm.task}` : ''}`
}

export type HealthProps = {
  ws: string
  snapshot: Snapshot
  onBack: () => void
  onAct: (confirm: Confirm) => void
}

function FindingRow(ui: any, finding: Finding, color: string, props: HealthProps) {
  const { Box, Text, Button } = ui
  return (
    <Box flexDirection="column" gap={GAP.row}>
      <Text>
        <Text color={color} weight="semibold">
          {finding.kind}
        </Text>
        : {finding.message}
      </Text>
      {finding.actions.map(a => (
        <Button key={`act:${a.action}:${a.task ?? ''}`} onPress={() => props.onAct({ action: a.action, task: a.task })}>
          {a.action} {a.task ?? ''}
        </Button>
      ))}
    </Box>
  )
}

// `ui` is the surface's element table, from $.ui.resolve(e).
export function Health(ui: any, props: HealthProps) {
  const { Box, Text, Button } = ui
  const { snapshot, ws } = props
  const findings = findingsFor(snapshot, ws)
  const row = snapshot.registry.find(r => r.id === ws)

  const group = (level: Finding['level'], color: string, title: string) => {
    const items = findings.filter(f => f.level === level)
    return items.length > 0 && Section(ui, title, color, items.map(f => FindingRow(ui, f, color, props)))
  }

  return (
    <Box flexDirection="column" gap={GAP.screen}>
      {Toolbar(
        ui,
        <Button key="back" onPress={props.onBack}>
          Back
        </Button>,
        row?.progressStale && (
          <Button key="act:sync" onPress={() => props.onAct({ action: 'sync', task: null })}>
            Sync
          </Button>
        ),
      )}
      {Title(ui, `${ws} health`)}
      {findings.length === 0 && <Text dimColor>Nothing to report.</Text>}
      {group('error', 'error', 'Errors')}
      {group('warning', 'warning', 'Warnings')}
    </Box>
  )
}

export type ConfirmProps = {
  ws: string
  branch: string
  confirm: Confirm
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmBox(ui: any, props: ConfirmProps) {
  const { Text, Button } = ui
  return Section(
    ui,
    'Confirm this write',
    'warning',
    <Text>
      This commits <Text bold>{commitLine(props.ws, props.confirm)}</Text> on {props.branch}.
    </Text>,
    Toolbar(
      ui,
      <Button key="confirm" variant="primary" onPress={props.onConfirm}>
        Confirm
      </Button>,
      <Button key="cancel" onPress={props.onCancel}>
        Cancel
      </Button>,
    ),
  )
}
