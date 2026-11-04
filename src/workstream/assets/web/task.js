// One task: everything the queue says about it, and the way to its review.
import { urls } from './api.js'
import { button, crumbs, dl, h, link, mono, pill, section } from './dom.js'
import { badgesOf, blockedLine, hrefs, offers, statusKind } from './logic.js'

export const fetches = route => ({ ws: urls.snapshot(route.ws) })

const list = items => (items?.length ? h('ul', { class: 'plain' }, items.map(item => h('li', null, item))) : null)

export function view(ctx) {
  const { ws, task: id } = ctx.route
  const snap = ctx.data.ws
  const task = snap.tasks.find(t => t.id === id)
  if (!task) return h('div', null, crumbs(['Workstreams', hrefs.registry()], [ws, hrefs.lanes(ws)], [id]), h('p', null, `No task ${id} in ${ws}.`))
  const badges = badgesOf(task, snap.tasks, snap.wave, ctx.now)
  const blocked = blockedLine(task)
  return h(
    'div',
    null,
    crumbs(['Workstreams', hrefs.registry()], [ws, hrefs.lanes(ws)], [id]),
    h('div', { class: 'title-row' }, h('h1', null, task.title), pill(task.status, statusKind(task.status))),
    h('div', { class: 'badges spaced' }, mono(id), badges.map(b => pill(b.text, b.kind))),
    blocked && h('p', { class: 'note warn' }, blocked),
    task.summary && h('p', { class: 'lede' }, task.summary),
    h(
      'div',
      { class: 'toolbar' },
      h('a', { class: 'button primary', href: hrefs.review(ws, id), key: 'open-review' }, 'Review'),
      offers(snap.health, ws, 'unclaim', id) && button('Unclaim', () => ctx.ask({ ws, action: 'unclaim', task: id }), { key: 'act:unclaim' }),
    ),
    section('Acceptance', task.acceptanceText?.length ? h('ol', { class: 'plain-ol' }, task.acceptanceText.map(item => h('li', null, item))) : h('p', { class: 'dim' }, 'None listed.')),
    section('Verify', task.verifyCommands?.length ? h('pre', { class: 'code' }, h('code', null, task.verifyCommands.map(c => (c.label === c.command ? c.command : `${c.label}: ${c.command}`)).join('\n'))) : h('p', { class: 'dim' }, 'None listed.')),
    task.files?.length > 0 && section('Files', list(task.files.map(f => mono(f)))),
    task.docs?.length > 0 && section('Docs', list(task.docs.map(f => mono(f)))),
    task.notes && section('Notes', h('p', null, task.notes)),
    section(
      'Facts',
      dl([
        ['Kind', task.kind],
        ['Phase', task.phase],
        ['Priority', task.priority],
        ['Mode', task.mode],
        ['Cites', task.findings?.join(', ')],
        ['Requires', task.requires?.join(', ')],
        ['Blocked by', task.blockedBy?.length ? task.blockedBy.flatMap((b, i) => [i > 0 && ', ', link(hrefs.task(ws, b), b)]) : null],
        ['Branch', task.branch && mono(task.branch)],
        ['Commit', task.commit && mono(task.commit.slice(0, 10))],
        ['Base', task.baseCommit && mono(task.baseCommit.slice(0, 10))],
        ['Claimed by', task.claimedBy],
        ['Started', task.startedAt],
        ['Finished', task.completedAt],
      ]),
    ),
  )
}
