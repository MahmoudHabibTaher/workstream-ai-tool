// What's waiting to be read, across the open workstreams: work still on a branch first, then what
// has landed, newest first. "Seen" is this browser's own note.
import { button, h, mono, pill } from './dom.js'
import { ageOf, hrefs } from './logic.js'
import { isSeen } from './seen.js'

export const fetches = () => ({})

function rowView(ctx, entry) {
  const seen = isSeen(ctx.snapshot.repoRoot, entry.revision)
  return h(
    'a',
    { class: `row card queue-row ${seen ? 'seen' : ''}`, href: hrefs.review(entry.workstream, entry.task), key: `q:${entry.workstream}:${entry.task}` },
    h(
      'div',
      { class: 'row-main' },
      h('div', { class: 'row-head' }, mono(entry.task), h('strong', null, entry.title), seen && pill('seen', 'dim'), !entry.hasEvidence && pill('no evidence', 'warn')),
      h('div', { class: 'row-meta dim' }, h('span', null, entry.workstream), entry.when && h('span', null, `${entry.state === 'branch' ? 'claimed' : 'landed'} ${ageOf(entry.when, ctx.now)} ago`)),
    ),
    h(
      'div',
      { class: 'size num', title: `${entry.files} files changed` },
      h('span', { class: 'added' }, `+${entry.added}`),
      h('span', { class: 'removed' }, `−${entry.removed}`),
      h('span', { class: 'dim' }, `${entry.files} file${entry.files === 1 ? '' : 's'}`),
    ),
  )
}

function group(ctx, title, entries, empty) {
  const shown = ctx.ui.hideSeen ? entries.filter(e => !isSeen(ctx.snapshot.repoRoot, e.revision)) : entries
  return h(
    'section',
    { class: 'queue-group' },
    h('h2', null, `${title} (${shown.length})`),
    shown.length === 0 ? h('p', { class: 'dim' }, empty) : h('div', { class: 'rows' }, shown.map(e => rowView(ctx, e))),
  )
}

export function view(ctx) {
  const entries = ctx.queue.tasks
  return h(
    'div',
    null,
    h('div', { class: 'title-row' }, h('h1', null, 'Review')),
    h('p', { class: 'dim lede' }, "Work still on a branch comes first, then what has landed, newest first. A closed workstream's tasks are reached from its queue."),
    h('div', { class: 'toolbar' }, button(ctx.ui.hideSeen ? 'Show seen' : 'Hide seen', () => ctx.setUi({ hideSeen: !ctx.ui.hideSeen }), { key: 'toggle-seen' })),
    group(ctx, 'On a branch', entries.filter(e => e.state === 'branch'), 'Nothing is waiting to land.'),
    group(ctx, 'Landed', entries.filter(e => e.state === 'landed'), 'Nothing here.'),
  )
}
