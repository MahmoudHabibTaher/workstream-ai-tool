// A workstream's narrative files, by name.
import { urls } from './api.js'
import { crumbs, h, link } from './dom.js'
import { DOC_NAMES, hrefs } from './logic.js'
import { markdown } from './mdview.js'

export const fetches = route => ({ ws: urls.snapshot(route.ws), doc: urls.doc(route.ws, route.doc) })

export function view(ctx) {
  const { ws, doc } = ctx.route
  const snap = ctx.data.ws
  return h(
    'div',
    null,
    crumbs(['Workstreams', hrefs.registry()], [ws, hrefs.lanes(ws)], [doc]),
    h(
      'nav',
      { class: 'tabs', 'aria-label': 'Documents' },
      link(hrefs.lanes(ws), 'Tasks'),
      DOC_NAMES.filter(name => snap.paths?.[name]).map(name => h('a', { href: hrefs.doc(ws, name), class: doc === name ? 'on' : null }, name[0].toUpperCase() + name.slice(1))),
    ),
    ctx.data.doc.text === null ? h('p', { class: 'dim' }, `This workstream has no ${doc} file.`) : h('article', { class: 'doc' }, markdown(ctx.data.doc.text)),
  )
}
