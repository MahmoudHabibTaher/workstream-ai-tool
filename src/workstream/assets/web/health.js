// What's wrong, by level, with only the actions each finding lists. Sync shows where a registry
// row says its progress is out of date. `ws act` still decides.
import { button, h, link, mono, pill, section } from './dom.js'
import { hrefs } from './logic.js'

export const fetches = () => ({})

function findingView(ctx, f) {
  return h(
    'li',
    { class: `finding ${f.level}` },
    h(
      'div',
      { class: 'row-head' },
      pill(f.level, f.level === 'error' ? 'bad' : 'warn'),
      mono(f.kind),
      f.workstream && link(hrefs.lanes(f.workstream), f.workstream),
      f.task && f.workstream && link(hrefs.task(f.workstream, f.task), f.task),
    ),
    h('p', { class: 'finding-text' }, f.message),
    f.actions.length > 0 &&
      h(
        'div',
        { class: 'toolbar' },
        f.actions.map(a =>
          button(`${a.action[0].toUpperCase()}${a.action.slice(1)} ${a.task ?? ''}`.trim(), () => ctx.ask({ ws: a.workstream, action: a.action, task: a.task }), {
            key: `act:${a.action}:${a.workstream}:${a.task}`,
          }),
        ),
      ),
  )
}

function group(ctx, title, findings) {
  return findings.length > 0 && section(`${title} (${findings.length})`, h('ul', { class: 'findings' }, findings.map(f => findingView(ctx, f))))
}

export function view(ctx) {
  const { health, registry, git } = ctx.snapshot
  const stale = registry.filter(row => row.progressStale)
  return h(
    'div',
    null,
    h('div', { class: 'title-row' }, h('h1', null, 'Health')),
    git.error && h('p', { class: 'note bad' }, git.error),
    health.length === 0 && stale.length === 0 && h('p', { class: 'note good' }, 'Nothing to report.'),
    group(ctx, 'Errors', health.filter(f => f.level === 'error')),
    group(ctx, 'Warnings', health.filter(f => f.level === 'warning')),
    stale.length > 0 &&
      section(
        `Progress out of date (${stale.length})`,
        h(
          'ul',
          { class: 'findings' },
          stale.map(row =>
            h(
              'li',
              { class: 'finding' },
              h('div', { class: 'row-head' }, link(hrefs.lanes(row.id), row.id)),
              h('div', { class: 'toolbar' }, button('Sync', () => ctx.ask({ ws: row.id, action: 'sync', task: null }), { key: `act:sync:${row.id}` })),
            ),
          ),
        ),
      ),
    section(
      'This checkout',
      h('p', null, 'On ', mono(git.branch ?? 'unknown'), `, with ${git.taskBranches?.length ?? 0} task branch${git.taskBranches?.length === 1 ? '' : 'es'} and ${git.worktrees?.length ?? 0} worktree${git.worktrees?.length === 1 ? '' : 's'}.`),
    ),
  )
}
