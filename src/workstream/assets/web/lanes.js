// One workstream: the wave, then its tasks in a lane per phase, with what can be done about it.
import { urls } from './api.js'
import { button, crumbs, h, link, mono, pill } from './dom.js'
import { DOC_NAMES, badgesOf, hrefs, lanes, promptText, statusActions, statusKind, waveLine } from './logic.js'

export const fetches = route => ({ ws: urls.snapshot(route.ws) })

function card(ctx, task, snap) {
  const badges = badgesOf(task, snap.tasks, snap.wave, ctx.now)
  const ready = snap.wave?.ids.includes(task.id)
  return h(
    'a',
    { class: `task-card ${ready ? 'ready' : ''} ${task.status === 'done' ? 'landed' : ''}`, href: hrefs.task(ctx.route.ws, task.id), key: `task:${task.id}` },
    h('div', { class: 'row-head' }, mono(task.id), pill(task.status, statusKind(task.status))),
    h('div', { class: 'task-title' }, task.title),
    badges.length > 0 && h('div', { class: 'badges' }, badges.map(b => pill(b.text, b.kind))),
  )
}

function waveNotes(wave) {
  const notes = []
  for (const pair of wave?.overlaps ?? []) notes.push(`${pair.join(' and ')} touch the same files, so they can't run together.`)
  if (wave?.leftovers?.length) notes.push(`Left over from earlier phases: ${wave.leftovers.join(', ')}.`)
  return notes
}

function actions(ctx, row) {
  const ws = ctx.route.ws
  const isOpen = row && row.status !== 'done' && row.status !== 'abandoned'
  return h(
    'div',
    { class: 'toolbar' },
    statusActions(row?.status).map(action =>
      button(action === 'pause' ? 'Pause' : 'Resume', () => ctx.ask({ ws, action, task: null }), { key: `act:${action}` }),
    ),
    row?.progressStale && button('Sync progress', () => ctx.ask({ ws, action: 'sync', task: null }), { key: 'act:sync' }),
    isOpen && h('span', { class: 'gap' }),
    isOpen && [
      button('Copy run prompt', () => ctx.copy(promptText('run', ws)), { key: 'copy:run', title: 'For your own agent. Nothing is sent.' }),
      button('Copy coordinate prompt', () => ctx.copy(promptText('coordinate', ws)), { key: 'copy:coordinate', title: 'For your own agent. Nothing is sent.' }),
      button('Copy close prompt', () => ctx.copy(promptText('close', ws)), { key: 'copy:close', title: 'For your own agent. Nothing is sent.' }),
      button('Copy abandon prompt', () => ctx.copy(promptText('abandon', ws)), { key: 'copy:abandon', title: 'For your own agent. Nothing is sent.' }),
    ],
  )
}


export function view(ctx) {
  const snap = ctx.data.ws
  const ws = ctx.route.ws
  const row = snap.registry.find(r => r.id === ws)
  return h(
    'div',
    null,
    crumbs(['Workstreams', hrefs.registry()], [ws]),
    h('div', { class: 'title-row' }, h('h1', null, row?.title || ws), row && pill(row.status, statusKind(row.status))),
    row?.summary && h('p', { class: 'dim lede' }, row.summary),
    actions(ctx, row),
    h(
      'nav',
      { class: 'tabs', 'aria-label': 'Documents' },
      h('a', { href: hrefs.lanes(ws), class: 'on' }, 'Tasks'),
      DOC_NAMES.filter(name => snap.paths?.[name]).map(name => link(hrefs.doc(ws, name), name[0].toUpperCase() + name.slice(1))),
    ),
    h('div', { class: 'wave-line' }, h('strong', null, waveLine(snap.wave))),
    waveNotes(snap.wave).map(note => h('p', { class: 'note warn' }, note)),
    snap.tasks.length === 0 && h('p', { class: 'dim' }, 'No tasks yet.'),
    h(
      'div',
      { class: 'lanes' },
      lanes(snap.tasks).map(lane =>
        h(
          'section',
          { class: `lane ${snap.wave?.phase === lane.phase ? 'current' : ''}`, 'aria-label': `Phase ${lane.phase}` },
          h('h2', null, `Phase ${lane.phase}`),
          h('div', { class: 'lane-cards' }, lane.tasks.map(task => card(ctx, task, snap))),
        ),
      ),
    ),
  )
}
