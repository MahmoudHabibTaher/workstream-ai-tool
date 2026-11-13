// Routing, the /workstreams command and the pane's one render hook.
// State lives in $.state atoms: module variables die on a reload. The atoms
// and the flows that write them share this file because the engine's scan reads
// an atom only from a const of the file using it.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, Timer } from 'claude-code'

import type { Confirm, Feed, FeedTab, ReviewScreen, Snapshot, View } from '../types'
import { loadReview, loadSnapshot, readText, resolveRoot, runAct } from './data'
import { Detail, launchFill } from './views/detail'
import { FeedScreen, lastPage } from './views/feed'
import { ConfirmBox, Health } from './views/health'
import { Registry } from './views/registry'
import { Review } from './views/review'
import { GAP } from './views/style'

const PANE = 'workstreams'
const TITLE = 'Workstreams'
const POLL_MS = 3000
const INITIAL_VIEW: View = { screen: 'registry', sub: 'tasks', ws: null, task: null, tab: 'handoff', page: 0, showDone: false, confirm: null }

// Bump a shape tag whenever its value's fields change: a stored value under
// another tag is then read as the initial one.
const view = atom({ plugin: 'workstreams-pane', key: 'view' } as const, INITIAL_VIEW, { shape: 'view-5' })
const snapshot = atom({ plugin: 'workstreams-pane', key: 'snapshot' } as const, null as Snapshot | null, { shape: 'snapshot-4' })
const feed = atom({ plugin: 'workstreams-pane', key: 'feed' } as const, null as Feed | null, { shape: 'feed-1' })
const review = atom({ plugin: 'workstreams-pane', key: 'review' } as const, null as ReviewScreen | null, { shape: 'review-1' })
const root = atom({ plugin: 'workstreams-pane', key: 'root' } as const, null)
const error = atom({ plugin: 'workstreams-pane', key: 'error' } as const, null)
const actError = atom({ plugin: 'workstreams-pane', key: 'actError' } as const, null)
const isOpen = atom({ plugin: 'workstreams-pane', key: 'isOpen' } as const, false)

// Reports whether a snapshot landed, so a caller can hold a navigation back.
async function refresh($: EngineInterface, at: string, ws: string | null): Promise<boolean> {
  const loaded = await loadSnapshot($, at, ws ?? undefined)
  await update($, root, () => at)
  await update($, error, () => loaded.error ?? null)
  if (loaded.snapshot) await update($, snapshot, () => loaded.snapshot)
  return Boolean(loaded.snapshot)
}

async function loadTab($: EngineInterface, tab: FeedTab): Promise<Feed> {
  const snap = await read($, snapshot)
  const path = snap?.paths?.[tab]
  const loaded: Feed = path ? { tab, ...(await readText($, path)) } : { tab, text: null, error: `no ${tab} file` }
  await update($, feed, () => loaded)
  return loaded
}

async function openTab($: EngineInterface, tab: FeedTab) {
  const loaded = await loadTab($, tab)
  const page = tab === 'decisions' ? lastPage(loaded.text ?? '') : 0
  await update($, view, v => ({ ...v, screen: 'feed' as const, tab, page }))
}

async function reloadOpenScreen($: EngineInterface) {
  const at = await read($, root)
  const v = await read($, view)
  if (!at) return
  await refresh($, at, v.ws)
  if (v.screen === 'feed') await loadTab($, v.tab)
}

// Holds the screen until the data lands, as openWorkstream does.
async function openReview($: EngineInterface, ws: string, task: string) {
  const at = await read($, root)
  if (!at) return
  const loaded = await loadReview($, at, ws, task)
  await update($, actError, () => loaded.error ?? null)
  if (!loaded.review) return
  const path = loaded.review.evidence
  const evidence = path ? ((await readText($, path)).text ?? null) : null
  const screen: ReviewScreen = { review: loaded.review, evidence }
  await update($, review, () => screen)
  await update($, view, v => ({ ...v, screen: 'review' as const, task }))
}

async function openReviewFile($: EngineInterface, ws: string, task: string, file: string) {
  const at = await read($, root)
  if (!at) return
  const loaded = await loadReview($, at, ws, task, file)
  await update($, actError, () => loaded.error ?? null)
  if (loaded.review) await update($, review, s => (s && loaded.review ? { ...s, review: loaded.review } : s))
}

// A success toasts its line, a refusal stays on screen; both re-snapshot, as a
// refusal usually means the view was stale. Revisions are the last
// snapshot's, the one the pane drew.
async function confirmAct($: EngineInterface, ws: string, confirm: Confirm) {
  const at = await read($, root)
  const snap = await read($, snapshot)
  await update($, view, v => ({ ...v, confirm: null }))
  if (!at || !snap) return
  const { line, refused } = await runAct($, at, ws, confirm, snap.revisions)
  await update($, actError, () => (refused ? line : null))
  if (!refused) await $.ui.toast(line)
  await refresh($, at, ws)
}

// Module variables on purpose: a reload drops the old timer with them, and
// session.start starts a new one while the pane is open.
let cancelPoll: Timer | undefined
let seen = new Map<string, number>()
let isTicking = false

async function mtimeOf($: EngineInterface, path: string): Promise<number> {
  try {
    return (await $.fs.stat(path)).mtimeMs
  } catch {
    return -1
  }
}

async function tick($: EngineInterface) {
  if (isTicking) return
  isTicking = true
  try {
    const snap = await read($, snapshot)
    if (!snap) return
    let changed = false
    for (const path of snap.watch) {
      const mtime = await mtimeOf($, path)
      const before = seen.get(path)
      if (before !== undefined && before !== mtime) changed = true
      seen.set(path, mtime)
    }
    if (changed) await reloadOpenScreen($)
  } finally {
    isTicking = false
  }
}

function startPoll($: EngineInterface) {
  stopPoll()
  seen = new Map()
  cancelPoll = $.clock.every(POLL_MS, () => void tick($))
}

function stopPoll() {
  cancelPoll?.cancel()
  cancelPoll = undefined
}

// Holds the screen until its snapshot lands, so it never draws another
// workstream's tasks; a failure shows on the screen the person is on.
async function openWorkstream($: EngineInterface, id: string) {
  const at = await read($, root)
  if (!at || !(await refresh($, at, id))) return
  await update($, view, v => ({ ...v, screen: 'detail' as const, sub: 'tasks' as const, ws: id, task: null }))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'workstreams',
      description: "Open the workstreams pane for this project (or a given clone's root)",
      argumentHint: '[root]',
    })
    const started = await next(e)
    if (await read($, isOpen)) startPoll($)
    return started
  })

  on('command.run', { command: 'workstreams' }, async ($, e) => {
    const found = await resolveRoot($, e.args)
    if (!found.root) return { text: found.problem }
    const at = found.root
    await update($, view, v => ({ ...v, screen: 'registry' as const, ws: null, task: null }))
    await refresh($, at, null)
    await $.ui.open({ id: PANE, title: TITLE })
    await update($, isOpen, () => true)
    startPoll($)
    return { text: `Workstreams pane opened for ${at}.` }
  })

  on('ui.close', { id: PANE }, async ($, e, next) => {
    stopPoll()
    if (e.origin.kind !== 'unload') await update($, isOpen, () => false)
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const ui = $.ui.resolve(e)
    const { Box, Text } = ui
    const snap = await read($, snapshot)
    const failed = await read($, error)
    const at = await read($, root)
    const state = await read($, view)
    const text = await read($, feed)
    const now = await $.clock.now()
    const refusal = await read($, actError)
    const reviewing = await read($, review)
    const leave = () => void update($, actError, () => null)
    const toRegistry = () => {
      leave()
      void update($, view, v => ({ ...v, screen: 'registry' as const, ws: null, task: null }))
    }
    const toDetail = () => {
      leave()
      void update($, view, v => ({ ...v, screen: 'detail' as const }))
    }
    const ask = (confirm: Confirm) => {
      void update($, actError, () => null)
      void update($, view, v => ({ ...v, confirm }))
    }

    return (
      <Box flexDirection="column" gap={GAP.screen} padding={GAP.section}>
        {failed && <Text color="error">{failed}</Text>}
        {refusal && <Text color="error">{refusal}</Text>}
        {state.confirm &&
          state.ws &&
          ConfirmBox(ui, {
            ws: state.ws,
            branch: snap?.integrationBranch ?? 'the integration branch',
            confirm: state.confirm,
            onConfirm: () => {
              if (state.ws && state.confirm) void confirmAct($, state.ws, state.confirm)
            },
            onCancel: () => void update($, view, v => ({ ...v, confirm: null })),
          })}
        {!snap && !failed && <Text dimColor>Run /workstreams to load the registry.</Text>}
        {!state.confirm && (
          <Box flexDirection="column">
        {snap &&
          state.screen === 'registry' &&
          Registry(ui, {
            snapshot: snap,
            view: state,
            onToggleDone: () => void update($, view, v => ({ ...v, showDone: !v.showDone })),
            onRefresh: () => {
              if (at) void refresh($, at, null)
            },
            onOpen: id => void openWorkstream($, id),
          })}
        {snap &&
          state.screen === 'detail' &&
          state.ws &&
          Detail(ui, {
            ws: state.ws,
            snapshot: snap,
            view: state,
            now,
            onBack: toRegistry,
            onFeed: () => void openTab($, state.tab),
            onTask: id => void update($, view, v => ({ ...v, task: v.task === id ? null : id })),
            onHealth: () => void update($, view, v => ({ ...v, screen: 'health' as const })),
            onReview: id => {
              if (state.ws) void openReview($, state.ws, id)
            },
            onPrompt: launch => void $.prompt.fill({ text: launchFill(launch) }),
            onAct: ask,
            onSub: sub => void update($, view, v => ({ ...v, sub })),
            onJump: id => void update($, view, v => ({ ...v, sub: 'tasks' as const, task: id })),
            onDocument: tab => void openTab($, tab),
          })}
        {snap &&
          state.screen === 'health' &&
          state.ws &&
          Health(ui, { ws: state.ws, snapshot: snap, onBack: toDetail, onAct: ask })}
        {reviewing &&
          state.screen === 'review' &&
          state.ws &&
          Review(ui, {
            screen: reviewing,
            onBack: toDetail,
            onEvidence: () =>
              void update($, review, s => {
                if (!s) return s
                const { hunks: _hunks, ...rest } = s.review
                return { ...s, review: rest }
              }),
            onFile: path => {
              if (state.ws && state.task) void openReviewFile($, state.ws, state.task, path)
            },
          })}
        {state.screen === 'feed' &&
          state.ws &&
          FeedScreen(ui, {
            ws: state.ws,
            feed: text,
            view: state,
            onTab: tab => void openTab($, tab),
            onPage: page => void update($, view, v => ({ ...v, page })),
            onBack: toDetail,
          })}
          </Box>
        )}
      </Box>
    )
  })
}
