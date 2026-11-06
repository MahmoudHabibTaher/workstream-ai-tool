// What activation does before anything is drawn: find each folder's project, then read its
// snapshot. A missing `ws` or a window with no project ends here with one message.
import { type Cli, loadSnapshot, resolveRoots, type Snapshot } from '../cli.ts'

export type Started = {
  roots: string[]
  snapshots: Record<string, Snapshot>
  errors: Record<string, string>
  // Shown once, in place of everything else; `level` picks the notification.
  message?: { level: 'error' | 'info'; text: string }
}

export async function start(cli: Cli, folders: string[]): Promise<Started> {
  const found = await resolveRoots(cli, folders)
  if (found.problem !== undefined) {
    const level = found.missing ? 'error' : 'info'
    return { roots: [], snapshots: {}, errors: {}, message: { level, text: found.problem } }
  }
  const snapshots: Record<string, Snapshot> = {}
  const errors: Record<string, string> = {}
  for (const root of found.roots) {
    const got = await loadSnapshot(cli, root)
    if (got.error !== undefined) errors[root] = got.error
    else snapshots[root] = got.value
  }
  return { roots: found.roots, snapshots, errors }
}
