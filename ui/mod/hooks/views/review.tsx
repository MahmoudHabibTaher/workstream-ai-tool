// One task's review: its evidence, then its diff one file at a time. The
// range and the capped hunks come from `ws review`.
import type { ReviewFile, ReviewScreen, ReviewRange } from '../../types'
import { GAP, Section, Title, Toolbar } from './style'

export function rangeLine(range: ReviewRange): string {
  if (range.kind === 'none') return 'No diff: this task has no commit or branch yet.'
  const between = range.kind === 'branch' ? '...' : '..'
  return `${range.kind}: ${range.from}${between}${range.to}`
}

export function statLine(file: ReviewFile): string {
  if (file.added === null || file.removed === null) return 'binary'
  return `+${file.added} -${file.removed}`
}

// `Code format="diff"` parses hunks, so the `diff --git` header goes; the path is
// already on screen. A header with no hunk (the first hunk over the cap) stays,
// drawn as plain code beside the cut note.
export function hunksOnly(text: string): string {
  const at = text.startsWith('@@') ? 0 : text.indexOf('\n@@') + 1
  return at > 0 ? text.slice(at) : text
}

export type ReviewProps = {
  screen: ReviewScreen
  onBack: () => void
  onEvidence: () => void
  onFile: (path: string) => void
}

// `ui` is the surface's element table, from $.ui.resolve(e). A picked file's diff
// takes the evidence's place: one tree draws 100,000 characters in all.
export function Review(ui: any, props: ReviewProps) {
  const { Box, Text, Button, Markdown, Code } = ui
  const { review, evidence } = props.screen
  const hunks = review.hunks

  return (
    <Box flexDirection="column" gap={GAP.screen}>
      {Toolbar(
        ui,
        <Button key="back" onPress={props.onBack}>
          Back
        </Button>,
        hunks && (
          <Button key="evidence" onPress={props.onEvidence}>
            Evidence
          </Button>
        ),
      )}
      <Box flexDirection="column" gap={GAP.row}>
        {Title(ui, review.task)}
        <Text mono dimColor>
          {rangeLine(review.range)}
        </Text>
      </Box>
      {review.error && <Text color="error">{review.error}</Text>}
      {review.files.length > 0 &&
        Section(
          ui,
          'Files',
          'promptBorder',
          review.files.map(file => (
            <Button key={`file:${file.path}`} plain onPress={() => props.onFile(file.path)}>
              {file.path} <Text dimColor>{statLine(file)}</Text>
            </Button>
          )),
        )}
      {hunks && <Code source={hunksOnly(hunks.text)} format="diff" path={hunks.path} />}
      {hunks?.truncated && <Text color="warning">Cut at a hunk boundary: the rest of this file's diff isn't shown.</Text>}
      {!hunks && (evidence === null ? <Text dimColor>No evidence file.</Text> : <Markdown text={evidence} />)}
    </Box>
  )
}
