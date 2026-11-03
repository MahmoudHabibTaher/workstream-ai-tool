// What each role costs against its limit, from `ws audit context`. Limits cover only what this
// tool adds to an agent's context. The numbers are the content, so it's a table with a bar in it,
// and a row says in words when it's over.
import { urls } from './api.js'
import { h } from './dom.js'
import { percent } from './logic.js'

export const fetches = () => ({ budget: urls.budget() })

function rowView(row) {
  const used = percent(row.tokens, row.budget)
  return h(
    'tr',
    { class: row.ok ? null : 'over' },
    h('td', null, row.role),
    h('td', { class: 'num-cell' }, row.tokens.toLocaleString()),
    h('td', { class: 'num-cell dim' }, row.budget.toLocaleString()),
    h('td', { class: 'meter-cell', title: `${row.tokens} of ${row.budget} tokens` }, h('div', { class: 'bar' }, h('div', { class: 'fill', width: `${used}%` }))),
    h('td', { class: 'num-cell' }, `${Math.round((row.tokens / row.budget) * 100)}%`),
    h('td', null, row.ok ? h('span', { class: 'dim' }, 'within') : h('span', { class: 'pill bad' }, 'over')),
  )
}

export function view(ctx) {
  const rows = ctx.data.budget.rows
  const over = rows.filter(r => !r.ok)
  return h(
    'div',
    null,
    h('div', { class: 'title-row' }, h('h1', null, 'Context budget')),
    h('p', { class: 'dim lede' }, 'Tokens this tool adds to each role, estimated at four characters each, measured against the limit that fails the build. It leaves out the agent’s own system prompt and the project’s instructions.'),
    over.length > 0 ? h('p', { class: 'note bad' }, `Over budget: ${over.map(r => r.role).join(', ')}`) : h('p', { class: 'note good' }, 'Every role is within its limit.'),
    h(
      'div',
      { class: 'table-wrap block' },
      h(
        'table',
        { class: 'budget' },
        h('thead', null, h('tr', null, ['Role', 'Tokens', 'Limit', 'Used', '', ''].map((t, i) => h('th', { class: i === 1 || i === 2 ? 'num-cell' : null }, t)))),
        h('tbody', null, rows.map(rowView)),
      ),
    ),
  )
}
