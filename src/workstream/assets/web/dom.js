// The one way this page makes elements. Children are always text nodes or elements, so repo text
// can't become markup: nothing here, or anywhere in these files, parses a string as HTML.

export function h(tag, props, ...children) {
  const el = document.createElement(tag)
  for (const [name, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined || value === false) continue
    if (name === 'class') el.className = value
    else if (name === 'key') el.dataset.key = value
    else if (name === 'scrollKey') el.dataset.scrollKey = value
    else if (name === 'width') el.style.width = value
    else if (name.startsWith('on')) el.addEventListener(name.slice(2), value)
    else if (value === true) el.setAttribute(name, '')
    else el.setAttribute(name, String(value))
  }
  append(el, children)
  return el
}

function append(el, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue
    if (Array.isArray(child)) append(el, child)
    else el.append(child instanceof Node ? child : document.createTextNode(String(child)))
  }
}

export const link = (href, ...children) => h('a', { href }, ...children)

export const button = (label, onclick, props) => h('button', { type: 'button', onclick, ...props }, label)

export const pill = (text, kind) => h('span', { class: `pill ${kind ?? ''}` }, text)

export const mono = (text, props) => h('code', props, text)

export function section(title, ...children) {
  return h('section', { class: 'block' }, title && h('h2', null, title), ...children)
}

export function dl(rows) {
  const kept = rows.filter(([, value]) => value !== null && value !== undefined && value !== '' && value !== false)
  return h('dl', { class: 'facts' }, kept.map(([name, value]) => [h('dt', null, name), h('dd', null, value)]))
}

// The way back up, with the current screen last.
export function crumbs(...parts) {
  return h(
    'nav',
    { class: 'crumbs', 'aria-label': 'Where you are' },
    parts.map(([label, href], i) => [i > 0 && h('span', { class: 'dim' }, ' / '), href ? link(href, label) : h('span', null, label)]),
  )
}
