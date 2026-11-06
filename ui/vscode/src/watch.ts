// File system watchers on the snapshot's `refresh` paths. Any event pokes `onEvent`, which the
// caller debounces. The set is rebuilt when the paths change, or when one of them comes into
// being, since a watcher on a path that doesn't exist yet may never fire.
import { existsSync } from 'node:fs'
import { basename, dirname } from 'node:path'

import * as vscode from 'vscode'

import type { Refresh } from './logic/store.ts'

export class Watchers implements vscode.Disposable {
  private watchers: vscode.FileSystemWatcher[] = []
  private key = ''

  private onEvent: (uri: vscode.Uri) => void

  constructor(onEvent: (uri: vscode.Uri) => void) {
    this.onEvent = onEvent
  }

  watch(paths: Refresh[]): void {
    const key = JSON.stringify(paths.map(p => [p.path, p.recursive, existsSync(p.path)]))
    if (key === this.key) return
    this.dispose()
    this.key = key
    for (const entry of paths) {
      const pattern = entry.recursive
        ? new vscode.RelativePattern(vscode.Uri.file(entry.path), '**')
        : new vscode.RelativePattern(vscode.Uri.file(dirname(entry.path)), basename(entry.path))
      const watcher = vscode.workspace.createFileSystemWatcher(pattern)
      watcher.onDidCreate(this.onEvent)
      watcher.onDidChange(this.onEvent)
      watcher.onDidDelete(this.onEvent)
      this.watchers.push(watcher)
    }
  }

  get count(): number {
    return this.watchers.length
  }

  dispose(): void {
    for (const watcher of this.watchers) watcher.dispose()
    this.watchers = []
    this.key = ''
  }
}
