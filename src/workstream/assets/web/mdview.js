// Draws markdown.js's tree. Text only ever becomes text nodes.
import { h } from './dom.js'
import { parseMarkdown } from './markdown.js'

function inline(nodes) {
  return nodes.map(node => {
    if (node.t === 'text') return node.v
    if (node.t === 'code') return h('code', null, node.v)
    if (node.t === 'b') return h('strong', null, inline(node.c))
    if (node.t === 'i') return h('em', null, inline(node.c))
    return h('a', { href: node.href, rel: 'noopener noreferrer', target: '_blank' }, inline(node.c))
  })
}

function block(node) {
  if (node.t === 'h') return h(`h${Math.min(node.level + 1, 6)}`, null, inline(node.c))
  if (node.t === 'p') return h('p', null, inline(node.c))
  if (node.t === 'hr') return h('hr')
  if (node.t === 'quote') return h('blockquote', null, node.c.map(block))
  if (node.t === 'code') return h('pre', { class: 'code' }, h('code', null, node.v))
  if (node.t === 'list') {
    return h(node.ordered ? 'ol' : 'ul', null, node.items.map(it => h('li', { class: it.depth ? `depth-${Math.min(it.depth, 3)}` : null }, inline(it.c))))
  }
  return h(
    'div',
    { class: 'table-wrap' },
    h(
      'table',
      null,
      h('thead', null, h('tr', null, node.head.map(c => h('th', null, inline(c))))),
      h('tbody', null, node.rows.map(row => h('tr', null, row.map(c => h('td', null, inline(c)))))),
    ),
  )
}

export function markdown(text) {
  return h('div', { class: 'prose' }, parseMarkdown(text).map(block))
}

export function inlineMarkdown(text) {
  const blocks = parseMarkdown(text)
  return h('span', { class: 'prose-inline' }, blocks.map(b => (b.t === 'p' ? inline(b.c) : block(b))))
}
