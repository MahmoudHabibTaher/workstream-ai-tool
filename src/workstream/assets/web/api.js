// Every call the page makes. It reads what `ws snapshot` and `ws review` report and writes only
// through /api/act, which runs `ws act`.

async function getJson(url) {
  const response = await fetch(url, { headers: { Accept: 'application/json' } })
  const data = await response.json().catch(() => ({ error: `${response.status} from ${url}` }))
  if (!response.ok) throw new Error(data.error ?? `${response.status} from ${url}`)
  return data
}

const q = encodeURIComponent

export const urls = {
  snapshot: ws => (ws ? `/api/snapshot?w=${q(ws)}` : '/api/snapshot'),
  queue: () => '/api/queue',
  review: (ws, task, file, max) =>
    `/api/review?w=${q(ws)}&task=${q(task)}${file ? `&file=${q(file)}` : ''}${max ? `&max=${max}` : ''}`,
  doc: (ws, name) => `/api/doc?w=${q(ws)}&name=${q(name)}`,
  budget: () => '/api/budget',
}

export { getJson }

// { line } when it landed, { refused } when `ws act` said no, thrown when it never got that far.
export async function act({ action, ws, task, revisions }) {
  const response = await fetch('/api/act', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action,
      workstream: ws,
      task,
      expectRegistry: revisions.registry,
      expectTasks: revisions.tasks[ws] ?? null,
    }),
  })
  const data = await response.json().catch(() => ({}))
  if (response.status === 200 || response.status === 409) return data
  throw new Error(data.error ?? `act answered ${response.status}`)
}
