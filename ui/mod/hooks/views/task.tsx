// One task's page: what it is, what it waits on and unblocks (each a button to that task),
// files, acceptance, verify, notes and the claim, then Review and Unclaim.
import type { Confirm, Snapshot, Task } from '../../types'
import { ageOf } from './detail'
import { offers } from './health'
import { Caption, GAP, Heading, Section, statusColor, Title, Toolbar } from './style'

export type TaskPageProps = {
  ws: string
  id: string
  snapshot: Snapshot
  now: number
  onBack: () => void
  onTask: (id: string) => void
  onReview: (id: string) => void
  onAct: (confirm: Confirm) => void
}

export function claimLine(task: Task, now: number): string {
  if (task.status !== 'in-progress' && !task.claimedBy) return 'not claimed'
  const by = task.claimedBy ? `claimed by ${task.claimedBy}` : 'claimed'
  return task.startedAt ? `${by}, ${ageOf(task.startedAt, now)} ago` : by
}

function Jumps(ui: any, prefix: string, ids: string[], byId: Map<string, Task>, props: TaskPageProps) {
  const { Button, Text } = ui
  if (ids.length === 0) return Caption(ui, 'none')
  return Toolbar(
    ui,
    ...ids.map(id => {
      const other = byId.get(id)
      return (
        <Button key={`${prefix}:${id}`} onPress={() => props.onTask(id)}>
          {id}
          {other && <Text color={statusColor(other.status)}> {other.status}</Text>}
        </Button>
      )
    }),
  )
}

export function TaskPage(ui: any, props: TaskPageProps) {
  const { Box, Text, Button, Code } = ui
  const tasks = props.snapshot.tasks ?? []
  const byId = new Map(tasks.map(t => [t.id, t]))
  const task = byId.get(props.id)
  const back = (
    <Button key="back" onPress={props.onBack}>
      Back
    </Button>
  )
  if (!task) {
    return (
      <Box flexDirection="column" gap={GAP.screen}>
        {Toolbar(ui, back)}
        {Caption(ui, `${props.id} is not in ${props.ws}'s snapshot`)}
      </Box>
    )
  }
  return (
    <Box flexDirection="column" gap={GAP.screen}>
      {Toolbar(ui, back)}
      <Box flexDirection="column" gap={GAP.row}>
        {Title(ui, task.id, <Text color={statusColor(task.status)}>{task.status}</Text>)}
        <Text weight="medium">{task.title}</Text>
        {Caption(ui, `phase ${task.phase} · priority ${task.priority} · ${task.mode} · ${claimLine(task, props.now)}`)}
      </Box>
      {Section(
        ui,
        null,
        'suggestion',
        <Text>{task.summary}</Text>,
        Heading(ui, 'Depends on'),
        Jumps(ui, 'dep', task.blockedBy, byId, props),
        Heading(ui, 'Unblocks'),
        Jumps(ui, 'unblocks', task.unblocks ?? [], byId, props),
        task.files.length > 0 && Heading(ui, 'Files'),
        task.files.map(file => Caption(ui, file)),
        Heading(ui, 'Acceptance'),
        task.acceptanceText.map(item => <Text>- {item}</Text>),
        Heading(ui, 'Verify'),
        <Code source={task.verifyCommands.map(c => c.command).join('\n')} language="sh" />,
        task.notes !== '' && <Text>Notes: {task.notes}</Text>,
        task.requires.length > 0 && <Text>Requires: {task.requires.join(', ')}</Text>,
      )}
      {Toolbar(
        ui,
        <Button key={`review:${task.id}`} onPress={() => props.onReview(task.id)}>
          Review
        </Button>,
        offers(props.snapshot, props.ws, 'unclaim', task.id) && (
          <Button key={`act:unclaim:${task.id}`} onPress={() => props.onAct({ action: 'unclaim', task: task.id })}>
            Unclaim
          </Button>
        ),
      )}
    </Box>
  )
}
