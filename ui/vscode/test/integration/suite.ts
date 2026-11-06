// Runs inside VS Code's extension host. No test framework: `run` throws on the first failure,
// which @vscode/test-electron reports as a failed run.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { realpathSync } from 'node:fs'
import { sep } from 'node:path'

import * as vscode from 'vscode'

import type { Api } from '../../src/extension.ts'

const BRANCH_CLI = ['python3', '-B', '-m', 'workstream']

export async function run(): Promise<void> {
  const which = process.env.WS_TEST_CASE
  const folder = realpathSync(process.env.WS_TEST_FOLDER ?? '')
  const extension = vscode.extensions.getExtension<Api>('workstream.workstreams')
  assert.ok(extension, 'the extension is installed in this window')
  const api = await extension.activate()
  const started = await api.ready
  const folders = (vscode.workspace.workspaceFolders ?? []).map(f => realpathSync(f.uri.fsPath))
  assert.deepEqual(folders, [folder])

  if (which === 'project') {
    // The branch's CLI, not the `ws` on PATH: the configured argv ran, and that interpreter,
    // given this host's environment, imports `workstream` from this checkout's src.
    const src = realpathSync(process.env.WS_TEST_SRC ?? '')
    const imported = execFileSync('python3', ['-B', '-c', 'import workstream; print(workstream.__file__)'], { encoding: 'utf8' })
    assert.ok(realpathSync(imported.trim()).startsWith(src + sep), `workstream came from ${imported.trim()}, not ${src}`)
    assert.deepEqual(api.ran, [[...BRANCH_CLI, 'root'], [...BRANCH_CLI, 'snapshot']])
    assert.deepEqual(api.shown, [])
    assert.deepEqual(started.roots.map(r => realpathSync(r)), [folder])
    const snapshot = started.snapshots[started.roots[0]]
    assert.equal(snapshot.snapshotVersion, 1)
    const registry = snapshot.registry as { id: string }[]
    assert.deepEqual(registry.map(row => row.id), ['alpha'])
    assert.match(snapshot.revisions.registry, /^[0-9a-f]{64}$/)
  } else if (which === 'plain') {
    assert.deepEqual(api.ran, [[...BRANCH_CLI, 'root']])
    assert.equal(api.shown.length, 1)
    assert.match(api.shown[0], /is not a workstream project/)
    assert.equal(started.message?.level, 'info')
    assert.deepEqual(started.roots, [])
  } else if (which === 'missing') {
    assert.equal(api.ran.length, 1)
    assert.deepEqual(api.ran[0].slice(1), ['root'])
    assert.equal(api.shown.length, 1)
    assert.match(api.shown[0], /did not start.*workstreams\.wsCommand/)
    assert.equal(started.message?.level, 'error')
  } else {
    assert.fail(`unknown case ${String(which)}`)
  }
  console.log(`ok ${which}: ran ${JSON.stringify(api.ran)}, shown ${JSON.stringify(api.shown)}`)
}
