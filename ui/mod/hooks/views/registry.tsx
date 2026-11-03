// The registry screen: open workstreams first, done ones behind a toggle.
// Buttons and text only, so it draws on every surface.
import type { RegistryRow, Snapshot, View } from '../../types'
import { Caption, GAP, Section, statusColor, Title, Toolbar } from './style'

const CLOSED = new Set(['done', 'abandoned'])

export type RegistryProps = {
  snapshot: Snapshot
  view: View
  onToggleDone: () => void
  onRefresh: () => void
  onOpen: (id: string) => void
}

export function visibleRows(snapshot: Snapshot, showDone: boolean): RegistryRow[] {
  const open = snapshot.registry.filter(row => !CLOSED.has(row.status))
  const closed = snapshot.registry.filter(row => CLOSED.has(row.status))
  return showDone ? [...open, ...closed] : open
}

export function errorCount(snapshot: Snapshot, id: string): number {
  return snapshot.health.filter(f => f.level === 'error' && f.workstream === id).length
}

function rowMeta(row: RegistryRow): string {
  const deps = row.dependsOn.length > 0 ? ` · after ${row.dependsOn.join(', ')}` : ''
  return ` · ${row.progress.done}/${row.progress.total}${deps}`
}

function Row(ui: any, snapshot: Snapshot, row: RegistryRow, onOpen: (id: string) => void) {
  const { Text, Button } = ui
  const errors = errorCount(snapshot, row.id)
  return (
    <Button key={`ws:${row.id}`} plain onPress={() => onOpen(row.id)}>
      <Text weight="semibold">{row.id}</Text> <Text color={statusColor(row.status)}>{row.status}</Text>
      <Text dimColor>{rowMeta(row)}</Text>
      {errors > 0 && <Text color="error"> {errors} error{errors === 1 ? '' : 's'}</Text>}
    </Button>
  )
}

// `ui` is the surface's element table, from $.ui.resolve(e).
export function Registry(ui: any, props: RegistryProps) {
  const { Box, Text, Button } = ui
  const { snapshot, view } = props
  const open = visibleRows(snapshot, false)
  const closed = visibleRows(snapshot, true).slice(open.length)
  const globalErrors = snapshot.health.filter(f => f.level === 'error' && f.workstream === null)

  return (
    <Box flexDirection="column" gap={GAP.screen}>
      <Box flexDirection="column" gap={GAP.row}>
        {Title(ui, 'Workstreams')}
        {Caption(ui, `${snapshot.repoRoot} · ${snapshot.git.branch ?? 'git unavailable'}`)}
      </Box>
      {globalErrors.map(f => (
        <Text color="error">{f.message}</Text>
      ))}
      {Section(
        ui,
        'Open',
        'promptBorder',
        open.length === 0 && <Text dimColor>No open workstreams.</Text>,
        open.map(row => Row(ui, snapshot, row, props.onOpen)),
      )}
      {view.showDone &&
        closed.length > 0 &&
        Section(ui, 'Closed', 'subtle', closed.map(row => Row(ui, snapshot, row, props.onOpen)))}
      {Toolbar(
        ui,
        <Button key="refresh" onPress={props.onRefresh}>
          Refresh
        </Button>,
        <Button key="toggle-done" onPress={props.onToggleDone}>
          {view.showDone ? 'Hide done' : `Show done (${closed.length})`}
        </Button>,
      )}
    </Box>
  )
}
