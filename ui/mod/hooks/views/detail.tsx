// One workstream: the wave line, then its tasks by phase in priority order.
// Every fact here comes from the snapshot; nothing is recomputed.
import type { Confirm, Snapshot, Task, View, Wave } from '../../types'
import { offers } from './health'
import { badgeColor, Caption, GAP, Heading, Section, statusColor, Title, Toolbar } from './style'

export function waveLine(wave: Wave | undefined): string {
  if (!wave) return ''
  if (wave.state === 'finished') return 'queue finished'
  if (wave.state === 'stuck') return `stuck: ${wave.open.length} open, none actionable`
  const leftovers = wave.leftovers.length > 0 ? ` · ${wave.leftovers.length} leftover` : ''
  return `phase ${String(wave.phase)}: ${wave.ids.length} ready${leftovers}`
}

export function ageOf(startedAt: string, now: number): string {
  const minutes = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 60_000))
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  return hours < 48 ? `${hours}h` : `${Math.floor(hours / 24)}d`
}

export function badgesOf(task: Task, tasks: Task[], wave: Wave | undefined, now: number): string[] {
  const statusOf = new Map(tasks.map(t => [t.id, t.status]))
  const waitsOn = task.blockedBy.filter(id => statusOf.get(id) !== 'done')
  const badges: string[] = []
  if (wave?.ids.includes(task.id)) badges.push('★ ready')
  if (task.mode === 'foreground') badges.push('FG')
  if (task.needsUserDecision) badges.push('needs decision')
  if (task.status === 'todo' && waitsOn.length > 0) badges.push(`waits on ${waitsOn.join(', ')}`)
  if (task.status === 'in-progress' && task.startedAt) badges.push(`claimed ${ageOf(task.startedAt, now)}`)
  return badges
}

export function lanes(tasks: Task[]): { phase: number; tasks: Task[] }[] {
  const phases = [...new Set(tasks.map(t => t.phase))].sort((a, b) => a - b)
  return phases.map(phase => ({
    phase,
    tasks: tasks.filter(t => t.phase === phase).sort((a, b) => a.priority - b.priority),
  }))
}

function Expanded(ui: any, task: Task, props: DetailProps) {
  const { Box, Text, Button, Code } = ui
  return (
    <Box marginLeft={GAP.section}>
      {Section(
        ui,
        task.title,
        'suggestion',
        <Text>{task.summary}</Text>,
        Heading(ui, 'Acceptance'),
        task.acceptanceText.map(item => <Text>- {item}</Text>),
        Heading(ui, 'Verify'),
        <Code source={task.verifyCommands.map(c => c.command).join('\n')} language="sh" />,
        task.files.length > 0 && Heading(ui, 'Files'),
        task.files.map(file => Caption(ui, file)),
        task.notes !== '' && <Text>Notes: {task.notes}</Text>,
        task.requires.length > 0 && <Text>Requires: {task.requires.join(', ')}</Text>,
        Toolbar(
          ui,
          <Button key={`review:${task.id}`} onPress={() => props.onReview(task.id)}>
            Review
          </Button>,
          offers(props.snapshot, props.ws, 'unclaim', task.id) && (
            <Button key={`act:unclaim:${task.id}`} onPress={() => props.onAct({ action: 'unclaim', task: task.id })}>
              Unclaim
            </Button>
          ),
        ),
      )}
    </Box>
  )
}

export type PromptKind = 'run' | 'coordinate' | 'close' | 'abandon'

// What each prompt button leaves in the box. Never submitted.
export function promptText(kind: PromptKind, ws: string): string {
  if (kind === 'run') return `Use the ws-run skill to run workstream ${ws}.`
  if (kind === 'coordinate') return `Use the ws-coordinate skill on workstream ${ws}.`
  if (kind === 'close') return `Use the ws-coordinate skill to close workstream ${ws}.`
  return `Use the ws-coordinate skill to abandon workstream ${ws}: <why>`
}

export type DetailProps = {
  ws: string
  snapshot: Snapshot
  view: View
  now: number
  onBack: () => void
  onFeed: () => void
  onTask: (id: string) => void
  onHealth: () => void
  onReview: (id: string) => void
  onPrompt: (kind: PromptKind) => void
  onAct: (confirm: Confirm) => void
}

function TaskRow(ui: any, task: Task, props: DetailProps) {
  const { Box, Text, Button } = ui
  const { snapshot, view, now } = props
  const badges = badgesOf(task, snapshot.tasks ?? [], snapshot.wave, now)
  return (
    <Box flexDirection="column" gap={GAP.row}>
      <Button key={`task:${task.id}`} plain onPress={() => props.onTask(task.id)}>
        <Text weight="semibold">{task.id}</Text> <Text color={statusColor(task.status)}>{task.status}</Text>
        <Text dimColor> · priority {task.priority}</Text>
        {badges.map(badge => (
          <Text color={badgeColor(badge)}> {badge}</Text>
        ))}
      </Button>
      {view.task === task.id && Expanded(ui, task, props)}
    </Box>
  )
}

function Actions(ui: any, status: string | undefined, props: DetailProps) {
  const { Button } = ui
  const isOpen = status !== 'done' && status !== 'abandoned'
  return Toolbar(
    ui,
    isOpen && (
      <Button key="run" variant="primary" onPress={() => props.onPrompt('run')}>
        Run
      </Button>
    ),
    isOpen && (
      <Button key="coordinate" onPress={() => props.onPrompt('coordinate')}>
        Coordinate
      </Button>
    ),
    (status === 'planned' || status === 'active') && (
      <Button key="act:pause" onPress={() => props.onAct({ action: 'pause', task: null })}>
        Pause
      </Button>
    ),
    status === 'paused' && (
      <Button key="act:resume" onPress={() => props.onAct({ action: 'resume', task: null })}>
        Resume
      </Button>
    ),
    isOpen && (
      <Button key="close" onPress={() => props.onPrompt('close')}>
        Close…
      </Button>
    ),
    isOpen && (
      <Button key="abandon" onPress={() => props.onPrompt('abandon')}>
        Abandon…
      </Button>
    ),
  )
}

// `ui` is the surface's element table, from $.ui.resolve(e).
export function Detail(ui: any, props: DetailProps) {
  const { Box, Text, Button } = ui
  const { snapshot } = props
  const row = snapshot.registry.find(r => r.id === props.ws)
  const status = row?.status

  return (
    <Box flexDirection="column" gap={GAP.screen}>
      {Toolbar(
        ui,
        <Button key="back" onPress={props.onBack}>
          Back
        </Button>,
        <Button key="feed" onPress={props.onFeed}>
          Feed
        </Button>,
        <Button key="health" onPress={props.onHealth}>
          Health
        </Button>,
      )}
      <Box flexDirection="column" gap={GAP.row}>
        {Title(ui, props.ws, status && <Text color={statusColor(status)}>{status}</Text>)}
        <Text weight="medium">{waveLine(snapshot.wave)}</Text>
      </Box>
      {Actions(ui, status, props)}
      {lanes(snapshot.tasks ?? []).map(lane =>
        Section(ui, `Phase ${lane.phase}`, 'promptBorder', lane.tasks.map(task => TaskRow(ui, task, props))),
      )}
    </Box>
  )
}
