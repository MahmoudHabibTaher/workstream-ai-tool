// What the views draw: each root's snapshot, and each workstream's own snapshot, read when first
// asked for and dropped on every reload. All of it comes from the CLI through cli.ts.
import { type Cli, type Loaded, loadQueue, loadReview, loadSnapshot, type Snapshot } from '../cli.ts'
import type { Queue, Review } from './review.ts'
import type { Started } from './start.ts'
import type { WsSnapshot } from './registry.ts'

export type Refresh = { path: string; recursive: boolean }

export class Store {
  roots: string[]
  snapshots: Record<string, Snapshot>
  errors: Record<string, string>
  showDone = false
  private perWs = new Map<string, Promise<Loaded<WsSnapshot>>>()
  private queues = new Map<string, Promise<Loaded<Queue>>>()
  private reviews = new Map<string, Promise<Loaded<Review>>>()
  private listeners: (() => void)[] = []

  private cli: Cli

  constructor(cli: Cli, started: Started) {
    this.cli = cli
    this.roots = started.roots
    this.snapshots = started.snapshots
    this.errors = started.errors
  }

  onChange(listener: () => void): void {
    this.listeners.push(listener)
  }

  private changed(): void {
    for (const listener of this.listeners) listener()
  }

  // One workstream's snapshot, shared by every caller until the next reload.
  workstream(root: string, id: string): Promise<Loaded<WsSnapshot>> {
    const k = JSON.stringify([root, id])
    let got = this.perWs.get(k)
    if (!got) {
      got = loadSnapshot(this.cli, root, id) as Promise<Loaded<WsSnapshot>>
      this.perWs.set(k, got)
    }
    return got
  }

  // A root's review queue, shared until the next reload.
  queue(root: string): Promise<Loaded<Queue>> {
    let got = this.queues.get(root)
    if (!got) {
      got = loadQueue(this.cli, root) as Promise<Loaded<Queue>>
      this.queues.set(root, got)
    }
    return got
  }

  // One task's review with its checks, shared until the next reload.
  review(root: string, ws: string, task: string): Promise<Loaded<Review>> {
    const k = JSON.stringify([root, ws, task])
    let got = this.reviews.get(k)
    if (!got) {
      got = loadReview(this.cli, root, ws, task, { checks: true }) as Promise<Loaded<Review>>
      this.reviews.set(k, got)
    }
    return got
  }

  // Reads every root's snapshot again; a root that fails keeps its error, not its old snapshot.
  async reload(): Promise<void> {
    const snapshots: Record<string, Snapshot> = {}
    const errors: Record<string, string> = {}
    for (const root of this.roots) {
      const got = await loadSnapshot(this.cli, root)
      if (got.error !== undefined) errors[root] = got.error
      else snapshots[root] = got.value
    }
    this.snapshots = snapshots
    this.errors = errors
    this.perWs.clear()
    this.queues.clear()
    this.reviews.clear()
    this.changed()
  }

  setShowDone(on: boolean): void {
    this.showDone = on
    this.changed()
  }

  // Every path whose change alters a view, from each root's snapshot, without repeats.
  refreshPaths(): Refresh[] {
    const seen = new Map<string, Refresh>()
    for (const snapshot of Object.values(this.snapshots)) {
      for (const entry of (snapshot.refresh as Refresh[] | undefined) ?? []) {
        const k = JSON.stringify([entry.path, entry.recursive])
        if (!seen.has(k)) seen.set(k, { path: entry.path, recursive: entry.recursive })
      }
    }
    return [...seen.values()]
  }
}
