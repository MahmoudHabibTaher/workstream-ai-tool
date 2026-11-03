// The page: read the address, fetch what that screen draws, draw it, and fetch again when the
// server says something changed. A redraw only happens when what came back differs, so a live
// update can't take away someone's place on the page.
import { act, getJson, urls } from './api.js'
import * as budget from './budget.js'
import * as doc from './doc.js'
import { button, h, link, mono } from './dom.js'
import * as health from './health.js'
import * as lanes from './lanes.js'
import { commitLine, hrefs, parseRoute } from './logic.js'
import * as queue from './queue.js'
import * as registry from './registry.js'
import * as review from './review.js'
import { unseenCount } from './seen.js'
import * as task from './task.js'

const SCREENS = { registry, lanes, task, doc, queue, review, health, budget }
const SAFETY_REFETCH_MS = 60_000

const state = {
  route: parseRoute(location.hash),
  snapshot: null,
  queue: null,
  data: {},
  error: null,
  flash: null, // { kind, text }: stays until replaced or dismissed
  confirm: null, // { ws, action, task, revisions }: revisions are pinned when the box opens
  live: false,
  ui: {},
  drawn: '',
}

let sequence = 0

// --- what a screen gets -------------------------------------------------------------------

function context() {
  return {
    route: state.route,
    snapshot: state.snapshot,
    queue: state.queue,
    data: state.data,
    ui: state.ui,
    now: Date.now(),
    setUi(patch) {
      Object.assign(state.ui, patch)
      draw()
    },
    ask,
    copy,
    go: href => {
      location.hash = href
    },
    redraw: draw,
    refetch: refresh,
    fetchInto,
  }
}

async function fetchInto(key, url) {
  state.ui[key] = await getJson(url)
  draw()
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    setFlash('good', `Copied: ${text}`)
  } catch {
    setFlash('warn', `Copy this yourself: ${text}`)
  }
}

function setFlash(kind, text) {
  state.flash = text ? { kind, text } : null
  drawFlash()
}

// What the person is looking at is what the write's guard must hold, so its hashes are taken now
// and kept, whatever a live update draws while the box is open.
function ask({ ws, action, task }) {
  state.confirm = { ws, action, task, revisions: drawnRevisions() }
  setFlash()
  drawOverlay(true)
}

function drawnRevisions() {
  return state.data.ws?.revisions ?? state.snapshot.revisions
}

async function confirmWrite() {
  const { ws, action, task: id, revisions } = state.confirm
  state.confirm = null
  drawOverlay()
  try {
    const result = await act({ action, ws, task: id, revisions })
    if (result.refused) setFlash('bad', `Refused: ${result.refused}`)
    else setFlash('good', result.line)
  } catch (err) {
    setFlash('bad', String(err.message ?? err))
  }
  await refresh()
}

// --- fetching -----------------------------------------------------------------------------

async function refresh() {
  const mine = ++sequence
  const route = state.route
  const screen = SCREENS[route.screen]
  const wanted = screen.fetches(route)
  try {
    const [snapshot, queueData, ...values] = await Promise.all([
      getJson(urls.snapshot()),
      getJson(urls.queue()),
      ...Object.values(wanted).map(getJson),
    ])
    if (mine !== sequence) return
    state.snapshot = snapshot
    state.queue = queueData
    state.data = Object.fromEntries(Object.keys(wanted).map((key, i) => [key, values[i]]))
    state.error = null
  } catch (err) {
    if (mine !== sequence) return
    state.error = String(err.message ?? err)
  }
  draw()
}

// --- drawing ------------------------------------------------------------------------------

function draw(force) {
  drawTop()
  drawOverlay()
  const view = document.getElementById('view')
  const fingerprint = JSON.stringify([state.route, state.data, state.snapshot, state.queue, state.ui, state.error])
  if (fingerprint === state.drawn && force !== true) return
  state.drawn = fingerprint
  const scrolls = new Map([...view.querySelectorAll('[data-scroll-key]')].map(el => [el.dataset.scrollKey, el.scrollTop]))
  const focused = document.activeElement?.dataset?.key
  const y = window.scrollY
  view.replaceChildren(body())
  for (const el of view.querySelectorAll('[data-scroll-key]')) {
    const top = scrolls.get(el.dataset.scrollKey)
    if (top) el.scrollTop = top
  }
  if (focused) view.querySelector(`[data-key="${CSS.escape(focused)}"]`)?.focus()
  window.scrollTo(0, y)
}

function body() {
  if (state.error) {
    return h('div', { class: 'note bad' }, h('p', null, state.error), h('p', null, link(hrefs.registry(), 'Back to the workstreams')))
  }
  if (!state.snapshot) return h('p', { class: 'dim' }, 'Loading…')
  return SCREENS[state.route.screen].view(context())
}

function drawTop() {
  const top = document.getElementById('top')
  const snap = state.snapshot
  if (!snap) return
  const errors = snap.health.filter(f => f.level === 'error').length
  const warnings = snap.health.length - errors
  const unseen = state.queue ? unseenCount(snap.repoRoot, state.queue.tasks) : 0
  const screen = state.route.screen
  const on = names => (names.includes(screen) ? 'on' : null)
  const wrongBranch = snap.git.branch && snap.git.branch !== snap.integrationBranch
  top.replaceChildren(
    h(
      'div',
      { class: 'bar-inner' },
      h('a', { class: 'brand', href: hrefs.registry() }, 'Workstreams'),
      h(
        'nav',
        { class: 'main-nav', 'aria-label': 'Screens' },
        h('a', { href: hrefs.registry(), class: on(['registry', 'lanes', 'task', 'doc']) }, 'Queues'),
        h('a', { href: hrefs.queue(), class: on(['queue', 'review']) }, 'Review', unseen > 0 && h('span', { class: 'count' }, unseen)),
        h('a', { href: hrefs.health(), class: on(['health']) }, 'Health', errors > 0 ? h('span', { class: 'count bad' }, errors) : warnings > 0 && h('span', { class: 'count warn' }, warnings)),
        h('a', { href: hrefs.budget(), class: on(['budget']) }, 'Budget'),
      ),
      h(
        'div',
        { class: 'where' },
        mono(snap.repoRoot.split('/').pop(), { title: snap.repoRoot }),
        h('span', { class: wrongBranch ? 'branch warn-text' : 'branch dim' }, snap.git.branch ?? 'git unavailable'),
        h('span', { class: `live ${state.live ? 'up' : 'down'}`, title: state.live ? 'Updates as files change' : 'Lost the server; retrying' }, state.live ? 'Live' : 'Reconnecting…'),
      ),
    ),
  )
}

function drawFlash() {
  const flash = document.getElementById('flash')
  flash.replaceChildren(
    ...(state.flash
      ? [h('div', { class: `note ${state.flash.kind}` }, h('span', null, state.flash.text), button('Dismiss', () => setFlash(), { class: 'quiet' }))]
      : []),
  )
}

function drawOverlay(focus) {
  const overlay = document.getElementById('overlay')
  const box = state.confirm
  if (!box) {
    overlay.replaceChildren()
    return
  }
  const latest = state.snapshot?.revisions
  const moved = latest && (latest.registry !== box.revisions.registry || latest.tasks[box.ws] !== box.revisions.tasks[box.ws])
  const yes = button('Confirm', confirmWrite, { class: 'primary', key: 'confirm-yes' })
  overlay.replaceChildren(
    h(
      'div',
      { class: 'scrim' },
      h(
        'div',
        { class: 'dialog', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Confirm this write' },
        h('h2', null, 'Confirm this write'),
        h('p', null, 'This commits ', h('strong', null, commitLine(box.ws, box.action, box.task)), ` on ${state.snapshot.integrationBranch}.`),
        moved && h('p', { class: 'note warn' }, 'This has changed since you opened this box, so the write will be refused.'),
        h('div', { class: 'toolbar' }, yes, button('Cancel', cancelConfirm, { key: 'confirm-no' })),
      ),
    ),
  )
  if (focus) yes.focus()
}

function cancelConfirm() {
  state.confirm = null
  drawOverlay()
}

// --- events -------------------------------------------------------------------------------

function listen() {
  const events = new EventSource('/api/events')
  events.addEventListener('hello', () => {
    state.live = true
    refresh()
  })
  events.addEventListener('change', refresh)
  events.addEventListener('error', () => {
    state.live = false
    drawTop()
  })
}

window.addEventListener('hashchange', () => {
  state.route = parseRoute(location.hash)
  state.data = {}
  state.error = null
  window.scrollTo(0, 0)
  document.getElementById('view').replaceChildren(h('p', { class: 'dim' }, 'Loading…'))
  state.drawn = ''
  refresh()
})

window.addEventListener('keydown', event => {
  if (event.key === 'Escape' && state.confirm) cancelConfirm()
  if (state.confirm || event.metaKey || event.ctrlKey || event.altKey) return
  SCREENS[state.route.screen].onKey?.(event, context())
})

setInterval(() => (state.live ? refresh() : undefined), SAFETY_REFETCH_MS)
// Ages on the page move on their own, so they get a redraw now and then, unless someone's selecting.
setInterval(() => {
  if (!state.confirm && !String(window.getSelection?.() ?? '')) draw(true)
}, SAFETY_REFETCH_MS)

listen()
refresh()
