// `make test-vscode`: runs the suite in the VS Code installed on this machine, never a downloaded
// one, once per case. Each case gets its own folder, profile and settings. The `ws` argv runs this
// checkout's CLI from its own `src`, so a task's worktree tests its branch, not the `ws` on PATH.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'

import { runTests } from '@vscode/test-electron'

const PACKAGE = resolve(__dirname, '..', '..', '..')
const CHECKOUT = resolve(PACKAGE, '..', '..')
const SRC = join(CHECKOUT, 'src')
const APP = process.env.VSCODE_EXECUTABLE ?? '/Applications/Visual Studio Code.app/Contents/MacOS/Code'
const BRANCH_CLI = ['python3', '-B', '-m', 'workstream']
const GIT_ENV = { GIT_AUTHOR_NAME: 'test', GIT_AUTHOR_EMAIL: 'test@example.com', GIT_COMMITTER_NAME: 'test', GIT_COMMITTER_EMAIL: 'test@example.com' }

type Case = { name: string; folder: string; wsCommand: string[] }

function sh(argv: string[], cwd: string): string {
  const [file, ...args] = argv
  return execFileSync(file, args, { cwd, encoding: 'utf8', env: { ...process.env, ...GIT_ENV, PYTHONPATH: SRC } })
}

const SEED = [
  { id: 'A-3', phase: 2, priority: 30, title: 'Third', blockedBy: ['A-1'] },
  { id: 'A-2', phase: 1, priority: 20, title: 'Second', mode: 'foreground', needsUserDecision: true },
  { id: 'A-1', phase: 1, priority: 10, title: 'First', summary: 'see [x](command:workbench.action.quit) <b>now</b>', acceptance: ['it works'], files: ['notes.txt'] },
]

// A project made by the branch's own CLI: `ws init`, then `alpha`, active with three tasks over two
// phases (A-1 names notes.txt, which the Task view opens), and `beta`, abandoned, which only Show
// done draws.
function sampleProject(under: string): string {
  const root = join(under, 'project')
  mkdirSync(root)
  sh(['git', 'init', '-q', '-b', 'main'], root)
  sh([...BRANCH_CLI, 'init', '--integration', 'main'], root)
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'init'], root)
  const base = sh(['git', 'rev-parse', '--short', 'HEAD'], root).trim()
  sh([...BRANCH_CLI, 'new', 'alpha', '--title', 'Alpha', '--summary', 'sample', '--base', base], root)
  sh([...BRANCH_CLI, 'new', 'beta', '--title', 'Beta', '--summary', 'dropped', '--base', base], root)
  const seed = join(under, 'seed.json')
  writeFileSync(seed, JSON.stringify(SEED))
  sh([...BRANCH_CLI, 'seed', '-w', 'alpha', seed], root)
  sh([...BRANCH_CLI, 'set-status', '-w', 'alpha', 'active'], root)
  sh([...BRANCH_CLI, 'set-status', '-w', 'beta', 'abandoned', '--notes', 'dropped'], root)
  writeFileSync(join(root, 'notes.txt'), 'notes\n')
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'alpha and beta'], root)
  return root
}

const REVIEW_SEED = [
  { id: 'R-1', phase: 1, priority: 10, title: 'On a branch', acceptance: ['the sides match', 'a binary file says so'] },
  { id: 'R-2', phase: 1, priority: 20, title: 'Landed', acceptance: ['it landed'] },
]

const evidence = (id: string, items: string[]) => [
  `# ${id} evidence`, '', '- **Status:** done', '', '## Acceptance', '', ...items, '', '## Proposed decisions', '', 'None.', '',
  '## Gotchas and follow-ups', '', 'None.', '', '## Text to apply', '', 'None.', '',
].join('\n')

// A project with one task on a branch and one landed. R-1's branch edits shared.txt, adds
// added.txt and blob.bin, and writes its evidence; main then moves, editing shared.txt too, so
// the branch's merge base and main's tip disagree about that file. R-2 landed as a commit on main.
function reviewProject(under: string): string {
  const root = join(under, 'review')
  mkdirSync(root)
  const write = (path: string, text: string | Buffer) => {
    mkdirSync(dirname(join(root, path)), { recursive: true })
    writeFileSync(join(root, path), text)
  }
  sh(['git', 'init', '-q', '-b', 'main'], root)
  sh([...BRANCH_CLI, 'init', '--integration', 'main'], root)
  write('shared.txt', 'one\ntwo\nthree\n')
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'init'], root)
  const base = sh(['git', 'rev-parse', '--short', 'HEAD'], root).trim()
  sh([...BRANCH_CLI, 'new', 'alpha', '--title', 'Alpha', '--summary', 'review', '--base', base], root)
  const seed = join(under, 'review-seed.json')
  writeFileSync(seed, JSON.stringify(REVIEW_SEED))
  sh([...BRANCH_CLI, 'seed', '-w', 'alpha', seed], root)
  sh([...BRANCH_CLI, 'set-status', '-w', 'alpha', 'active'], root)
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'seeded'], root)
  sh([...BRANCH_CLI, 'claim', 'R-1', 'R-2', '-w', 'alpha'], root)
  sh(['git', 'commit', '-qam', 'claim R-1 and R-2'], root)
  const queue = JSON.parse(readFileSync(join(root, 'workstreams', 'alpha', 'tasks_list.json'), 'utf8')) as { tasks: { id: string; branch: string }[] }
  const branch = queue.tasks.find(t => t.id === 'R-1')?.branch ?? ''
  sh(['git', 'checkout', '-qb', branch], root)
  write('shared.txt', 'one\nTWO\nthree\n')
  write('added.txt', 'a new file\n')
  write('blob.bin', Buffer.from([0, 1, 2, 3, 0xff]))
  write('workstreams/alpha/evidence/R-1.md', evidence('R-1', [
    '1. the sides match -> `diff` printed "same" <b>bold</b> [x](command:workbench.action.quit)',
    '2. a binary file says so ->',
  ]))
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'R-1 work'], root)
  sh(['git', 'checkout', '-q', 'main'], root)
  write('shared.txt', 'zero\none\ntwo\nthree\n')
  write('landed.txt', 'landed\n')
  write('workstreams/alpha/evidence/R-2.md', evidence('R-2', ['1. it landed -> `git log` shows it']))
  sh(['git', 'add', '-A'], root)
  sh(['git', 'commit', '-qm', 'R-2 work'], root)
  sh([...BRANCH_CLI, 'update', 'R-2', '-w', 'alpha', '--status', 'done', '--commit', sh(['git', 'rev-parse', 'HEAD'], root).trim()], root)
  sh(['git', 'commit', '-qam', 'R-2 done'], root)
  return root
}

async function main(): Promise<void> {
  const scratch = mkdtempSync(join(tmpdir(), 'ws-vscode-'))
  try {
    const plain = join(scratch, 'plain')
    mkdirSync(plain)
    const cases: Case[] = [
      { name: 'project', folder: sampleProject(scratch), wsCommand: BRANCH_CLI },
      { name: 'review', folder: reviewProject(scratch), wsCommand: BRANCH_CLI },
      { name: 'plain', folder: plain, wsCommand: BRANCH_CLI },
      { name: 'missing', folder: plain, wsCommand: [join(scratch, 'no-such-ws')] },
    ]
    for (const c of cases) {
      const profile = join(scratch, `profile-${c.name}`)
      mkdirSync(join(profile, 'User'), { recursive: true })
      writeFileSync(join(profile, 'User', 'settings.json'), JSON.stringify({ 'workstreams.wsCommand': c.wsCommand }))
      console.log(`-- ${c.name}`)
      await runTests({
        vscodeExecutablePath: APP,
        extensionDevelopmentPath: PACKAGE,
        extensionTestsPath: join(__dirname, 'suite.js'),
        extensionTestsEnv: { ...GIT_ENV, PYTHONPATH: SRC, WS_TEST_CASE: c.name, WS_TEST_FOLDER: c.folder, WS_TEST_SRC: SRC },
        launchArgs: [c.folder, '--user-data-dir', profile, '--extensions-dir', join(scratch, 'extensions'),
          '--disable-extensions', '--disable-workspace-trust', '--skip-welcome', '--skip-release-notes'],
      })
    }
  } finally {
    rmSync(scratch, { recursive: true, force: true })
  }
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
