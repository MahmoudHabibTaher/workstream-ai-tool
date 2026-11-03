// One task's review, which is what this UI is for: what the CLI already checked, each acceptance
// item beside its proof, and the diff a file at a time. What's left is what only a person can
// judge. It reads only: landing a task stays `ws settle`, so the button copies the command.
import { urls } from './api.js'
import { button, crumbs, h, mono, pill, section } from './dom.js'
import { fileNote, gateSummary, hrefs, neighbourFile, neighbours, parseDiff, parseRoute, rangeLine, statLine, statusKind } from './logic.js'
import { inlineMarkdown, markdown } from './mdview.js'
import { isSeen, setSeen } from './seen.js'

const WHOLE_FILE = 200000

export const fetches = (route, ui) => ({
  review: urls.review(route.ws, route.task, route.file, ui.wholeFile === route.file && route.file ? WHOLE_FILE : null),
})

// --- the left side: what's claimed and checked ----------------------------------------------

function gatesView(checks) {
  if (checks.state === 'landed') {
    return h('p', null, 'Landed as ', mono((checks.commit ?? '').slice(0, 10)), '. Its gates ran when it landed.')
  }
  if (checks.state === 'none') return h('p', { class: 'dim' }, 'Not started, so nothing has been checked.')
  const summary = gateSummary(checks.gates)
  return [
    h('p', { class: `note ${summary.kind}` }, summary.text),
    h(
      'ul',
      { class: 'gates' },
      checks.gates.map(g =>
        h(
          'li',
          { class: g.ok ? 'ok' : g.blocking ? 'stop' : 'warned' },
          h('span', { class: 'mark', 'aria-label': g.ok ? 'passes' : g.blocking ? 'fails' : 'warning' }, g.ok ? '✓' : g.blocking ? '✗' : '!'),
          h('span', null, g.name, !g.ok && g.detail && h('span', { class: 'gate-detail' }, g.detail)),
        ),
      ),
    ),
  ]
}

function itemsView(checks) {
  if (checks.items.length === 0) return h('p', { class: 'dim' }, 'This task lists no acceptance items.')
  return h(
    'ol',
    { class: 'proofs' },
    checks.items.map(item =>
      h(
        'li',
        { class: item.proof ? '' : 'missing' },
        h('div', { class: 'claim' }, item.item),
        item.proof ? h('div', { class: 'proof' }, inlineMarkdown(item.proof)) : h('div', { class: 'proof none' }, 'Nothing quoted.'),
      ),
    ),
  )
}

function evidenceView(ctx, checks) {
  if (checks.evidenceText === null) return section('Evidence', h('p', { class: 'dim' }, 'No evidence file yet.'))
  const blocked = checks.evidenceStatus === 'blocked'
  return [
    blocked && h('p', { class: 'note bad' }, `Blocked: ${checks.reason}`),
    section('Acceptance and proof', itemsView(checks)),
    checks.proposals.length > 0 &&
      section(
        'Proposed decisions',
        checks.proposals.map(p => h('div', { class: 'proposal' }, h('strong', null, `${p.id}: ${p.title}`), markdown(p.body))),
      ),
    checks.gotchas && checks.gotchas !== 'None.' && section('Gotchas and follow-ups', markdown(checks.gotchas)),
    h(
      'div',
      { class: 'toolbar' },
      button(ctx.ui.wholeEvidence ? 'Hide the whole file' : 'Read the whole evidence file', () => ctx.setUi({ wholeEvidence: !ctx.ui.wholeEvidence }), { key: 'toggle-evidence' }),
    ),
    ctx.ui.wholeEvidence && h('div', { class: 'block' }, markdown(checks.evidenceText)),
  ]
}

// --- the right side: the diff ---------------------------------------------------------------

function filesView(ctx, data) {
  const { ws, task, file } = ctx.route
  if (data.files.length === 0) return h('p', { class: 'dim pad' }, rangeLine(data.range))
  return h(
    'nav',
    { class: 'file-list', 'aria-label': 'Files changed' },
    data.files.map(f =>
      h(
        'a',
        { class: f.path === file ? 'on' : null, href: hrefs.review(ws, task, f.path), key: `file:${f.path}`, 'aria-current': f.path === file ? 'true' : null },
        h('span', { class: 'path' }, f.path),
        h('span', { class: 'num stat' }, statLine(f)),
      ),
    ),
  )
}

function diffView(ctx, hunks) {
  const { header, hunks: parsed } = parseDiff(hunks.text)
  const note = fileNote(header)
  return h(
    'div',
    { class: 'diff-wrap' },
    h('div', { class: 'diff-head' }, mono(hunks.path), note && pill(note, '')),
    parsed.length === 0 && !note && h('p', { class: 'dim pad' }, 'No changes to show in this file.'),
    parsed.length > 0 &&
      h(
        'table',
        { class: 'diff' },
        h('colgroup', null, h('col', { class: 'ln-col' }), h('col', { class: 'ln-col' }), h('col')),
        parsed.map(hunk =>
          h(
            'tbody',
            null,
            h('tr', { class: 'hunk' }, h('td', { colspan: 3 }, hunk.header)),
            hunk.lines.map(line =>
              h(
                'tr',
                { class: line.kind },
                h('td', { class: 'ln num' }, line.old ?? ''),
                h('td', { class: 'ln num' }, line.new ?? ''),
                h('td', { class: 'text' }, line.text),
              ),
            ),
          ),
        ),
      ),
    hunks.truncated &&
      h(
        'div',
        { class: 'note warn' },
        "Cut at a hunk boundary: the rest of this file's diff isn't shown. ",
        button('Show the whole file', () => {
          ctx.setUi({ wholeFile: ctx.route.file })
          ctx.refetch()
        }, { key: 'whole-file' }),
      ),
  )
}

// --- the screen -----------------------------------------------------------------------------

function toggleSeen(ctx, entry) {
  const root = ctx.snapshot.repoRoot
  setSeen(root, entry.revision, !isSeen(root, entry.revision))
  ctx.setUi({ seenTick: (ctx.ui.seenTick ?? 0) + 1 })
}

export function view(ctx) {
  const { ws, task, file } = ctx.route
  const data = ctx.data.review
  // A review opens on its first file, so the diff is there without a click.
  if (!file && data.files.length > 0) {
    queueMicrotask(() => location.replace(hrefs.review(ws, task, data.files[0].path)))
  }
  const { checks } = data
  const { previous, next, entry } = neighbours(ctx.queue.tasks, ws, task)
  const seen = entry && isSeen(ctx.snapshot.repoRoot, entry.revision)
  return h(
    'div',
    null,
    crumbs(['Workstreams', hrefs.registry()], [ws, hrefs.lanes(ws)], [task, hrefs.task(ws, task)], ['review']),
    h(
      'div',
      { class: 'title-row' },
      h('h1', null, checks.title || task),
      pill(checks.status, statusKind(checks.status)),
      checks.state === 'branch' && pill('on its branch', 'accent'),
    ),
    h('p', { class: 'dim range' }, mono(task), ' ', rangeLine(data.range)),
    data.error && h('p', { class: 'note bad' }, data.error),
    h(
      'div',
      { class: 'toolbar' },
      entry && button(seen ? 'Mark unseen' : 'Mark seen', () => toggleSeen(ctx, entry), { key: 'toggle-seen', class: seen ? 'on' : null, title: 'Shortcut: s. Kept in this browser only.' }),
      h('a', { class: `button ${previous ? '' : 'off'}`, href: previous ? hrefs.review(previous.workstream, previous.task) : null, key: 'prev-task', title: 'Shortcut: p' }, '← Previous'),
      h('a', { class: `button ${next ? '' : 'off'}`, href: next ? hrefs.review(next.workstream, next.task) : null, key: 'next-task', title: 'Shortcut: n' }, 'Next →'),
      h('span', { class: 'gap' }),
      checks.state === 'branch' && button('Copy settle command', () => ctx.copy(`ws settle ${task} -w ${ws}`), { key: 'copy-settle', title: 'Landing is for your terminal or your agent. Nothing is sent.' }),
      button('Copy review prompt', () => ctx.copy(`Use the ws-review skill on task ${task} of workstream ${ws}.`), { key: 'copy-review', title: 'For your own agent. Nothing is sent.' }),
      h('span', { class: 'dim keys' }, 'j / k files · n / p tasks · s seen'),
    ),
    h(
      'div',
      { class: 'review-grid' },
      h(
        'div',
        { class: 'review-side', scrollKey: `side:${ws}:${task}` },
        section('What the CLI checked', gatesView(checks)),
        evidenceView(ctx, checks),
      ),
      h(
        'div',
        { class: 'review-diff', scrollKey: `diff:${ws}:${task}:${file ?? ''}` },
        filesView(ctx, data),
        data.hunks && diffView(ctx, data.hunks),
      ),
    ),
  )
}

export function onKey(event, ctx) {
  // The address, not the last draw: two quick presses land before the first one's redraw.
  const { ws, task, file } = parseRoute(location.hash)
  const data = ctx.data.review
  if (!data) return
  const { previous, next, entry } = neighbours(ctx.queue.tasks, ws, task)
  if (event.key === 'j' || event.key === 'k') {
    const path = neighbourFile(data.files, file, event.key === 'j' ? 1 : -1)
    if (path) ctx.go(hrefs.review(ws, task, path))
  } else if (event.key === 'n' && next) ctx.go(hrefs.review(next.workstream, next.task))
  else if (event.key === 'p' && previous) ctx.go(hrefs.review(previous.workstream, previous.task))
  else if (event.key === 's' && entry) toggleSeen(ctx, entry)
}
