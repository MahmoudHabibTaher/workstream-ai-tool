// Markdown to a tree of plain objects, with no DOM, so it can be tested without a browser. The
// subset the workstream files use: headings, lists, tables, fences, quotes, rules and inline
// code, bold, italic and links. A link is kept only for http and https; any other stays as text,
// so a `javascript:` link in a repo file can't become one.

const FENCE = /^\s*(`{3,}|~{3,})\s*(.*)$/
const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/
const RULE = /^\s*([-*_])(\s*\1){2,}\s*$/
const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/
const TABLE_RULE = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/
const SAFE_LINK = /^https?:\/\//i

function cells(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map(c => parseInline(c.trim().replace(/\\\|/g, '|')))
}

export function parseInline(text) {
  const out = []
  let plain = ''
  const flush = () => {
    if (plain) out.push({ t: 'text', v: plain })
    plain = ''
  }
  let i = 0
  while (i < text.length) {
    const rest = text.slice(i)
    let m
    if ((m = /^(`+)([\s\S]+?)\1(?!`)/.exec(rest))) {
      flush()
      out.push({ t: 'code', v: m[2] })
    } else if ((m = /^\*\*(?=\S)([\s\S]+?)\*\*/.exec(rest))) {
      flush()
      out.push({ t: 'b', c: parseInline(m[1]) })
    } else if ((m = /^\*(?=\S)([^*]+?)\*/.exec(rest))) {
      flush()
      out.push({ t: 'i', c: parseInline(m[1]) })
    } else if ((m = /^\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))*)\)/.exec(rest))) {
      flush()
      if (SAFE_LINK.test(m[2])) out.push({ t: 'a', href: m[2], c: parseInline(m[1]) })
      else out.push(...parseInline(m[1]))
    } else {
      plain += text[i]
      i += 1
      continue
    }
    i += m[0].length
  }
  flush()
  return out
}

export function parseMarkdown(text) {
  const lines = (text ?? '').split(/\r?\n/)
  const blocks = []
  let n = 0
  while (n < lines.length) {
    const line = lines[n]
    if (!line.trim()) {
      n += 1
      continue
    }
    const fence = FENCE.exec(line)
    if (fence) {
      const body = []
      n += 1
      while (n < lines.length && !lines[n].trim().startsWith(fence[1])) body.push(lines[n++])
      n += 1
      blocks.push({ t: 'code', lang: fence[2].trim(), v: body.join('\n') })
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ t: 'h', level: heading[1].length, c: parseInline(heading[2]) })
      n += 1
      continue
    }
    if (RULE.test(line)) {
      blocks.push({ t: 'hr' })
      n += 1
      continue
    }
    if (line.includes('|') && n + 1 < lines.length && TABLE_RULE.test(lines[n + 1]) && lines[n + 1].includes('-')) {
      const head = cells(line)
      const rows = []
      n += 2
      while (n < lines.length && lines[n].includes('|') && lines[n].trim()) rows.push(cells(lines[n++]))
      blocks.push({ t: 'table', head, rows })
      continue
    }
    if (ITEM.test(line)) {
      const items = []
      const isOrdered = text => /\d/.test(ITEM.exec(text)[2])
      const ordered = isOrdered(line)
      while (n < lines.length) {
        const item = ITEM.exec(lines[n])
        if (item) {
          if (isOrdered(lines[n]) !== ordered && !item[1]) break
          items.push({ depth: Math.floor(item[1].length / 2), raw: [item[3]] })
          n += 1
        } else if (lines[n].trim() && /^\s+/.test(lines[n])) {
          items[items.length - 1].raw.push(lines[n].trim())
          n += 1
        } else if (!lines[n].trim() && n + 1 < lines.length && ITEM.test(lines[n + 1]) && isOrdered(lines[n + 1]) === ordered) {
          n += 1
        } else break
      }
      blocks.push({ t: 'list', ordered, items: items.map(it => ({ depth: it.depth, c: parseInline(it.raw.join(' ')) })) })
      continue
    }
    if (line.startsWith('>')) {
      const body = []
      while (n < lines.length && lines[n].startsWith('>')) body.push(lines[n++].replace(/^>\s?/, ''))
      blocks.push({ t: 'quote', c: parseMarkdown(body.join('\n')) })
      continue
    }
    const para = []
    while (
      n < lines.length && lines[n].trim() && !FENCE.test(lines[n]) && !HEADING.test(lines[n]) &&
      !ITEM.test(lines[n]) && !lines[n].startsWith('>') && !RULE.test(lines[n])
    ) para.push(lines[n++].trim())
    blocks.push({ t: 'p', c: parseInline(para.join(' ')) })
  }
  return blocks
}
