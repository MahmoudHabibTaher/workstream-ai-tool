// The narrative files as paged Markdown .
import type { Feed, FeedTab, View } from '../../types'
import { Caption, GAP, Toolbar } from './style'

export const PAGE_LINES = 120
const TABS: { tab: FeedTab; label: string }[] = [
  { tab: 'handoff', label: 'Handoff' },
  { tab: 'progress', label: 'Progress' },
  { tab: 'decisions', label: 'Decisions' },
  { tab: 'plan', label: 'Plan' },
]

export function pageCount(text: string): number {
  return Math.max(1, Math.ceil(text.split('\n').length / PAGE_LINES))
}

export function lastPage(text: string): number {
  return pageCount(text) - 1
}

export function pageOf(text: string, page: number): { body: string; page: number; pages: number } {
  const pages = pageCount(text)
  const at = Math.min(Math.max(0, page), pages - 1)
  const body = text.split('\n').slice(at * PAGE_LINES, (at + 1) * PAGE_LINES).join('\n')
  return { body, page: at, pages }
}

export type FeedProps = {
  ws: string
  feed: Feed | null
  view: View
  onTab: (tab: FeedTab) => void
  onPage: (page: number) => void
  onBack: () => void
}

// `ui` is the surface's element table, from $.ui.resolve(e).
export function FeedScreen(ui: any, props: FeedProps) {
  const { Box, Text, Button, Markdown } = ui
  const { feed, view } = props
  const paged = feed?.text == null ? null : pageOf(feed.text, view.page)

  return (
    <Box flexDirection="column" gap={GAP.screen}>
      {Toolbar(
        ui,
        <Button key="back" onPress={props.onBack}>
          Back
        </Button>,
        TABS.map(({ tab, label }) => (
          <Button key={`tab:${tab}`} variant={view.tab === tab ? 'primary' : 'secondary'} onPress={() => props.onTab(tab)}>
            {label}
          </Button>
        )),
      )}
      {Caption(ui, props.ws)}
      {feed?.error && <Text color="error">{feed.error}</Text>}
      {paged && <Markdown text={paged.body} />}
      {paged &&
        paged.pages > 1 &&
        Toolbar(
          ui,
          paged.page > 0 && (
            <Button key="page-prev" onPress={() => props.onPage(paged.page - 1)}>
              Previous
            </Button>
          ),
          Caption(ui, `page ${paged.page + 1} of ${paged.pages}`),
          paged.page < paged.pages - 1 && (
            <Button key="page-next" onPress={() => props.onPage(paged.page + 1)}>
              More
            </Button>
          ),
        )}
    </Box>
  )
}
