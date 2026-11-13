// Detail's Graph: the tasks as an indented list, each under the tasks it waits on.
// The edges are the snapshot's blockedBy and unblocks; nothing is recomputed.
import type { Task } from '../../types'
import { Caption, GAP, statusColor } from './style'

export type GraphLine = { id: string; depth: number; isRepeat: boolean }

// Roots are the tasks that wait on nothing here. A task under two parents is drawn in
// full the first time and as a repeat after, so the list stays finite and each edge shows.
export function graphLines(tasks: Task[]): GraphLine[] {
  const byId = new Map(tasks.map(t => [t.id, t]))
  const order = (ids: string[]) =>
    ids.filter(id => byId.has(id)).sort((a, b) => byId.get(a)!.priority - byId.get(b)!.priority)
  const roots = order(tasks.filter(t => !t.blockedBy.some(id => byId.has(id))).map(t => t.id))
  const lines: GraphLine[] = []
  const drawn = new Set<string>()
  const walk = (id: string, depth: number) => {
    if (drawn.has(id)) {
      lines.push({ id, depth, isRepeat: true })
      return
    }
    drawn.add(id)
    lines.push({ id, depth, isRepeat: false })
    for (const next of order(byId.get(id)!.unblocks ?? [])) walk(next, depth + 1)
  }
  for (const id of roots) walk(id, 0)
  // A cycle has no root; draw what is left at the top so no task goes missing.
  for (const t of tasks) if (!drawn.has(t.id)) walk(t.id, 0)
  return lines
}

export type GraphProps = { tasks: Task[]; onJump: (id: string) => void }

export function Graph(ui: any, props: GraphProps) {
  const { Box, Text, Button } = ui
  const byId = new Map(props.tasks.map(t => [t.id, t]))
  const lines = graphLines(props.tasks)
  if (lines.length === 0) return Caption(ui, 'no tasks')
  return (
    <Box flexDirection="column" gap={GAP.row}>
      {Caption(ui, 'Each task sits under the tasks it waits on.')}
      {lines.map((line, n) => {
        const task = byId.get(line.id)!
        const indent = '  '.repeat(line.depth) + (line.depth > 0 ? '└ ' : '')
        return (
          <Button key={`graph:${line.id}:${n}`} plain onPress={() => props.onJump(line.id)}>
            <Text dimColor>{indent}</Text>
            <Text weight="semibold">{line.id}</Text> <Text color={statusColor(task.status)}>{task.status}</Text>
            <Text dimColor>{line.isRepeat ? ' (shown above)' : ` · ${task.title}`}</Text>
          </Button>
        )
      })}
    </Box>
  )
}
