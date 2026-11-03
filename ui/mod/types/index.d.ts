// The pane's state contract and the shape of the read model it draws.
// Snapshot mirrors `ws snapshot` (snapshotVersion 1). The CLI owns it, in
// schema/snapshot.schema.json, and this file only names what the pane reads.

export type Progress = {
  total: number
  todo: number
  'in-progress': number
  blocked: number
  done: number
  deferred: number
}

export type RegistryRow = {
  id: string
  title: string
  summary: string
  status: 'planned' | 'active' | 'paused' | 'done' | 'abandoned'
  dependsOn: string[]
  progress: Progress
  progressStale: boolean
}

export type ActAction = 'pause' | 'resume' | 'unclaim' | 'sync'

export type Confirm = { action: ActAction; task: string | null }

export type FindingAction = {
  action: ActAction
  workstream: string | null
  task: string | null
}

export type Finding = {
  kind: string
  level: 'error' | 'warning'
  workstream: string | null
  task: string | null
  message: string
  actions: FindingAction[]
}

export type Snapshot = {
  snapshotVersion: 1
  repoRoot: string
  integrationBranch: string
  registry: RegistryRow[]
  revisions: { registry: string; tasks: Record<string, string> }
  watch: string[]
  health: Finding[]
  git: { branch?: string; error?: string }
  // Present only for `snapshot -w <id>`.
  tasks?: Task[]
  wave?: Wave
  paths?: Paths
}

export type Task = {
  id: string
  phase: number
  priority: number
  status: 'todo' | 'in-progress' | 'blocked' | 'done' | 'deferred'
  title: string
  summary: string
  acceptanceText: string[]
  verifyCommands: { label: string; command: string }[]
  files: string[]
  notes: string
  mode: 'background' | 'foreground'
  requires: string[]
  blockedBy: string[]
  needsUserDecision: boolean
  startedAt: string | null
}

export type Wave = {
  state: 'ready' | 'finished' | 'stuck'
  phase: number | null
  ids: string[]
  open: string[]
  leftovers: string[]
}

export type ReviewRange = { from: string | null; to: string | null; kind: 'merge' | 'commit' | 'branch' | 'none' }

export type ReviewFile = { path: string; added: number | null; removed: number | null }

export type ReviewData = {
  task: string
  evidence: string | null
  range: ReviewRange
  files: ReviewFile[]
  hunks?: { path: string; text: string; truncated: boolean }
  error?: string
}

export type ReviewScreen = { review: ReviewData; evidence: string | null }

export type FeedTab = 'handoff' | 'progress' | 'decisions' | 'plan'

export type Paths = Partial<Record<FeedTab, string>>

export type Feed = { tab: FeedTab; text: string | null; error: string | null }

export type View = {
  screen: 'registry' | 'detail' | 'feed' | 'health' | 'review'
  confirm: Confirm | null
  ws: string | null
  task: string | null
  tab: FeedTab
  page: number
  showDone: boolean
}

declare module 'claude-code' {
  interface PluginState {
    'ws-pane': {
      view: Shaped<View>
      snapshot: Shaped<Snapshot | null>
      feed: Shaped<Feed | null>
      review: Shaped<ReviewScreen | null>
      root: string | null
      error: string | null
      actError: string | null
      isOpen: boolean
    }
  }
}
