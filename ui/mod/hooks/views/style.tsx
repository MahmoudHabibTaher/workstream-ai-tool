// The pane's look in one place: spacing steps, type levels, theme colours (so light
// and dark both hold) and the section box. The terminal has one text size and
// ignores `size` and `weight`, so hierarchy there rests on colour, bold and borders.
export const GAP = { screen: 'md', section: 'sm', row: 'xs' } as const

// `ui` is the surface's element table, from $.ui.resolve(e).
export function Title(ui: any, text: string, meta?: unknown) {
  const { Text } = ui
  return (
    <Text size="title" weight="semibold">
      {text} {meta}
    </Text>
  )
}

export function Caption(ui: any, text: string) {
  const { Text } = ui
  return (
    <Text size="caption" dimColor>
      {text}
    </Text>
  )
}

export function Heading(ui: any, text: string) {
  const { Text } = ui
  return (
    <Text size="heading" weight="semibold">
      {text}
    </Text>
  )
}

export function Toolbar(ui: any, ...children: unknown[]) {
  const { Box } = ui
  return (
    <Box flexDirection="row" flexWrap="wrap" gap={GAP.row}>
      {children}
    </Box>
  )
}

// A bordered block with a heading; `color` tints the border by what's inside.
export function Section(ui: any, title: string | null, color: string, ...children: unknown[]) {
  const { Box } = ui
  return (
    <Box flexDirection="column" gap={GAP.row} padding={GAP.section} borderStyle="round" borderColor={color}>
      {title && Heading(ui, title)}
      {children}
    </Box>
  )
}

export function statusColor(status: string): string {
  if (status === 'active' || status === 'done') return 'success'
  if (status === 'in-progress' || status === 'paused') return 'warning'
  if (status === 'blocked') return 'error'
  if (status === 'planned') return 'suggestion'
  return 'inactive'
}

export function badgeColor(badge: string): string {
  if (badge.startsWith('★')) return 'success'
  if (badge === 'needs decision') return 'error'
  if (badge === 'FG') return 'suggestion'
  return 'warning'
}
