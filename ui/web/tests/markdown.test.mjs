import assert from 'node:assert/strict'
import { test } from 'node:test'

import { parseInline, parseMarkdown } from '../../../src/workstream/assets/web/markdown.js'

const kinds = text => parseMarkdown(text).map(b => b.t)

test('blocks are told apart', () => {
  assert.deepEqual(
    kinds('# H\n\npara\nmore\n\n- a\n- b\n\n1. c\n\n> q\n\n---\n\n```sh\nx\n```\n\n| a | b |\n|---|---|\n| 1 | 2 |\n'),
    ['h', 'p', 'list', 'list', 'quote', 'hr', 'code', 'table'],
  )
})

test('a # inside a fence is not a heading', () => {
  const [block] = parseMarkdown('```\n# not one\n```')
  assert.deepEqual([block.t, block.v], ['code', '# not one'])
})

test('an unclosed fence takes the rest', () => {
  assert.deepEqual(parseMarkdown('```\na\nb'), [{ t: 'code', lang: '', v: 'a\nb' }])
})

test('a list item keeps its continuation', () => {
  const [list] = parseMarkdown('1. first\n   more\n2. second\n')
  assert.equal(list.ordered, true)
  assert.deepEqual(list.items[0].c, [{ t: 'text', v: 'first more' }])
  assert.equal(list.items.length, 2)
})

test('a table splits on bars, but not an escaped one', () => {
  const [table] = parseMarkdown('| a |\n|---|\n| x \\| y |\n')
  assert.deepEqual(table.rows[0][0], [{ t: 'text', v: 'x | y' }])
})

test('inline marks nest', () => {
  assert.deepEqual(parseInline('a `b` **c `d`** *e*'), [
    { t: 'text', v: 'a ' }, { t: 'code', v: 'b' }, { t: 'text', v: ' ' },
    { t: 'b', c: [{ t: 'text', v: 'c ' }, { t: 'code', v: 'd' }] }, { t: 'text', v: ' ' },
    { t: 'i', c: [{ t: 'text', v: 'e' }] },
  ])
})

test('a star on its own is text', () => {
  assert.deepEqual(parseInline('2 * 3 * 4'), [{ t: 'text', v: '2 * 3 * 4' }])
})

test('only http and https become links', () => {
  assert.deepEqual(parseInline('[a](https://example.com/x)'), [{ t: 'a', href: 'https://example.com/x', c: [{ t: 'text', v: 'a' }] }])
  for (const href of ['javascript:alert(1)', 'data:text/html,x', 'vbscript:x', '../file.md', '//evil.example']) {
    assert.deepEqual(parseInline(`[a](${href})`), [{ t: 'text', v: 'a' }], href)
  }
})

test('markup in repo text stays text', () => {
  const nodes = parseInline('<img src=x onerror=alert(1)> <script>x</script>')
  assert.deepEqual(nodes, [{ t: 'text', v: '<img src=x onerror=alert(1)> <script>x</script>' }])
})

test('empty text has no blocks', () => {
  assert.deepEqual(parseMarkdown(''), [])
  assert.deepEqual(parseMarkdown(null), [])
})
