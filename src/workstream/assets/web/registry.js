// Every workstream: open ones first, closed behind a toggle.
import { button, h, link, mono, pill } from './dom.js'
import { errorCount, hrefs, percent, splitRows, statusKind } from './logic.js'

export const fetches = () => ({})

function progress(row) {
  const { done, total } = row.progress
  return h(
    'div',
    { class: 'progress', title: `${done} of ${total} done` },
    h('div', { class: 'bar' }, h('div', { class: 'fill', width: `${percent(done, total)}%` })),
    h('span', { class: 'dim num' }, `${done}/${total}`),
  )
}

function rowView(ctx, row) {
  const errors = errorCount(ctx.snapshot.health, row.id)
  return h(
    'a',
    { class: 'row card', href: hrefs.lanes(row.id), key: `ws:${row.id}` },
    h(
      'div',
      { class: 'row-main' },
      h('div', { class: 'row-head' }, h('strong', null, row.title || row.id), pill(row.status, statusKind(row.status)), errors > 0 && pill(`${errors} error${errors === 1 ? '' : 's'}`, 'bad'), row.progressStale && pill('progress out of date', 'warn')),
      row.summary && h('p', { class: 'dim clamp' }, row.summary),
      h('div', { class: 'row-meta dim' }, mono(row.id), row.dependsOn?.length > 0 && h('span', null, `after ${row.dependsOn.join(', ')}`)),
    ),
    progress(row),
  )
}

export function view(ctx) {
  const { snapshot, ui } = ctx
  const { open, closed } = splitRows(snapshot.registry)
  return h(
    'div',
    null,
    h('div', { class: 'title-row' }, h('h1', null, 'Workstreams')),
    open.length === 0 && h('p', { class: 'dim' }, 'No open workstreams.'),
    h('div', { class: 'rows' }, open.map(row => rowView(ctx, row))),
    closed.length > 0 &&
      h(
        'div',
        { class: 'toolbar spaced' },
        button(ui.showClosed ? 'Hide closed' : `Show closed (${closed.length})`, () => ctx.setUi({ showClosed: !ui.showClosed }), { key: 'toggle-closed' }),
      ),
    ui.showClosed && h('div', { class: 'rows' }, closed.map(row => rowView(ctx, row))),
    snapshot.registry.length === 0 && h('p', null, 'Start one with ', mono('ws new'), '. See ', link('#/budget', 'the budget'), ' for what the tool costs.'),
  )
}

