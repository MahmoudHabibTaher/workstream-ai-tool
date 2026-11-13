// One workstream: the wave line, then its tasks by phase in priority order.
// Every fact here comes from the snapshot; nothing is recomputed.
import type { Confirm, FeedTab, Launch, Preflight, RegistryRow, Snapshot, Sub, Task, View, Wave } from '../../types'
import { Graph } from './graph'
import { Overview } from './overview'
import { LaunchSlot, PreflightBox, preflightFor } from './preflight'
import { badgeColor, GAP, Section, statusColor, Title, Toolbar } from './style'

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

// What a prompt button leaves in the box: the launch's own text, and a placeholder for
// what it asks. Never submitted.
export function launchFill(launch: Launch): string {
  return launch.ask ? `${launch.prompt}<${launch.ask}>` : launch.prompt
}

const LABELS: Record<string, string> = { run: 'Run', coordinate: 'Coordinate', close: 'Close…', abandon: 'Abandon…' }

export function launchLabel(launch: Launch): string {
  return LABELS[launch.kind] ?? launch.kind
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
  // Runs the launch's pre-flight, then fills the box if nothing blocks.
  onPrompt: (launch: Launch) => void
  preflight: Preflight | null
  onRecheck: () => void
  onAct: (confirm: Confirm) => void
  onSub: (sub: Sub) => void
  onDocument: (tab: FeedTab) => void
}

const SUBS: { sub: Sub; label: string }[] = [
  { sub: 'tasks', label: 'Tasks' },
  { sub: 'graph', label: 'Graph' },
  { sub: 'overview', label: 'Overview' },
]

function SubRow(ui: any, current: Sub, props: DetailProps) {
  const { Button } = ui
  return Toolbar(
    ui,
    ...SUBS.map(s => (
      <Button key={`sub:${s.sub}`} variant={s.sub === current ? 'primary' : undefined} onPress={() => props.onSub(s.sub)}>
        {s.label}
      </Button>
    )),
  )
}

function Tasks(ui: any, props: DetailProps) {
  return lanes(props.snapshot.tasks ?? []).map(lane =>
    Section(ui, `Phase ${lane.phase}`, 'promptBorder', lane.tasks.map(task => TaskRow(ui, task, props))),
  )
}

function TaskRow(ui: any, task: Task, props: DetailProps) {
  const { Box, Text, Button } = ui
  const { snapshot, now } = props
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
    </Box>
  )
}

function LaunchButton(ui: any, launch: Launch, props: DetailProps) {
  return LaunchSlot(ui, {
    key: launch.kind,
    label: launchLabel(launch),
    isPrimary: launch.kind === 'run',
    pf: preflightFor(props.preflight, props.ws, launch.kind, null),
    onPress: () => props.onPrompt(launch),
  })
}

// The row's launches, with the status writes after run and coordinate. The snapshot gives a
// closed row no launches, so nothing here decides which are offered.
function Actions(ui: any, row: RegistryRow | undefined, props: DetailProps) {
  const { Button } = ui
  const status = row?.status
  const launches = row?.launches ?? []
  const first = launches.filter(l => l.kind === 'run' || l.kind === 'coordinate')
  const rest = launches.filter(l => !first.includes(l))
  return Toolbar(
    ui,
    ...first.map(l => LaunchButton(ui, l, props)),
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
    ...rest.map(l => LaunchButton(ui, l, props)),
  )
}

// `ui` is the surface's element table, from $.ui.resolve(e).
export function Detail(ui: any, props: DetailProps) {
  const { Box, Text, Button } = ui
  const { snapshot } = props
  const row = snapshot.registry.find(r => r.id === props.ws)
  const status = row?.status
  // A view stored before sub-screens existed has none; it shows Tasks.
  const sub: Sub = props.view.sub ?? 'tasks'
  const shown = props.preflight && props.preflight.ws === props.ws && props.preflight.task === null ? props.preflight : null

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
      {Actions(ui, row, props)}
      {shown && PreflightBox(ui, shown, launchLabel(shown.launch ?? { kind: shown.kind, prompt: '' }), props.onRecheck)}
      {SubRow(ui, sub, props)}
      {sub === 'tasks' && Tasks(ui, props)}
      {sub === 'graph' && Graph(ui, { tasks: snapshot.tasks ?? [], onJump: props.onTask })}
      {sub === 'overview' && Overview(ui, { snapshot, now: props.now, onDocument: props.onDocument })}
    </Box>
  )
}
