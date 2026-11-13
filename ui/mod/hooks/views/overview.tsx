// Detail's Overview: the workstream's documents, claims, scope, verify commands and
// baseline, each as the snapshot gives it.
import type { FeedTab, Snapshot } from '../../types'
import { ageOf } from './detail'
import { Caption, GAP, Section } from './style'

const DOCUMENTS: { tab: FeedTab; label: string }[] = [
  { tab: 'plan', label: 'Plan' },
  { tab: 'progress', label: 'Progress' },
  { tab: 'decisions', label: 'Decisions' },
  { tab: 'handoff', label: 'Handoff' },
]

// Each command once, by label, in the order tasks first name it.
export function verifyCommands(snapshot: Snapshot): { label: string; command: string }[] {
  const seen = new Map<string, string>()
  for (const task of snapshot.tasks ?? []) for (const c of task.verifyCommands) if (!seen.has(c.label)) seen.set(c.label, c.command)
  return [...seen].map(([label, command]) => ({ label, command }))
}

export type OverviewProps = { snapshot: Snapshot; now: number; onDocument: (tab: FeedTab) => void }

export function Overview(ui: any, props: OverviewProps) {
  const { Box, Text, Button, Code } = ui
  const { snapshot } = props
  const docs = DOCUMENTS.filter(d => snapshot.paths?.[d.tab])
  const claims = (snapshot.tasks ?? []).filter(t => t.status === 'in-progress')
  const scope = snapshot.scope
  const commands = verifyCommands(snapshot)
  const baseline = snapshot.baseline
  return (
    <Box flexDirection="column" gap={GAP.section}>
      {Section(
        ui,
        'Documents',
        'promptBorder',
        docs.length === 0
          ? Caption(ui, 'no documents')
          : (
              <Box flexDirection="row" flexWrap="wrap" gap={GAP.row}>
                {docs.map(d => (
                  <Button key={`doc:${d.tab}`} onPress={() => props.onDocument(d.tab)}>
                    {d.label}
                  </Button>
                ))}
              </Box>
            ),
      )}
      {Section(
        ui,
        'Claims',
        'promptBorder',
        claims.length === 0
          ? Caption(ui, 'nothing claimed')
          : claims.map(t => (
              <Text key={`claim:${t.id}`}>
                <Text weight="semibold">{t.id}</Text>
                {t.claimedBy ? ` by ${t.claimedBy}` : ''}
                {t.startedAt ? `, ${ageOf(t.startedAt, props.now)} ago` : ''}
              </Text>
            )),
      )}
      {Section(
        ui,
        'Scope',
        'promptBorder',
        !scope
          ? Caption(ui, 'no scope recorded')
          : [
              scope.rule !== '' && <Text key="scope:rule">{scope.rule}</Text>,
              scope.inScope.length > 0 && <Text key="scope:in">In: {scope.inScope.join(', ')}</Text>,
              scope.outOfScope.length > 0 && <Text key="scope:out">Out: {scope.outOfScope.join('; ')}</Text>,
            ],
      )}
      {Section(
        ui,
        'Verify commands',
        'promptBorder',
        commands.length === 0
          ? Caption(ui, 'no verify commands')
          : <Code source={commands.map(c => (c.label === c.command ? c.command : `${c.label}: ${c.command}`)).join('\n')} language="sh" />,
      )}
      {Section(
        ui,
        'Baseline',
        'promptBorder',
        !baseline || baseline.keys.length === 0
          ? Caption(ui, 'no baseline recorded')
          : baseline.keys.map(k => (
              <Text key={`baseline:${k.key}`}>
                <Text weight="semibold">{k.key}</Text>
                {` exit ${k.exit ?? '?'}, ${k.findings ?? 0} known finding${k.findings === 1 ? '' : 's'}`}
                <Text dimColor>{k.commit ? ` · at ${k.commit.slice(0, 7)}` : ''}</Text>
              </Text>
            )),
        (baseline?.errors ?? []).map(e => (
          <Text key={`baseline-error:${e}`} color="error">
            {e}
          </Text>
        )),
      )}
    </Box>
  )
}
