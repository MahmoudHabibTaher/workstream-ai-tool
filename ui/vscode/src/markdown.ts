// The one place a MarkdownString is made. A title or proof in the repo could hold a command link
// or HTML, so repo text only ever goes in through appendText, and neither trust nor HTML is on.
// Headings are the extension's own constants; a source test holds both rules.
import * as vscode from 'vscode'

import type { Tip } from './logic/registry.ts'

export function tooltip(tip: Tip): vscode.MarkdownString {
  const md = new vscode.MarkdownString()
  md.isTrusted = false
  md.supportHtml = false
  md.supportThemeIcons = false
  tip.forEach((section, i) => {
    if (i > 0) md.appendMarkdown('\n\n')
    if (section.heading) {
      md.appendMarkdown('**')
      md.appendText(section.heading)
      md.appendMarkdown('**\n\n')
    }
    section.lines.forEach((line, j) => {
      if (j > 0) md.appendMarkdown('\n\n')
      md.appendText(line)
    })
  })
  return md
}
