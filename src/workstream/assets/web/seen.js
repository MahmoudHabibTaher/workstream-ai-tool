// "Seen" in the review queue: this browser's own note of what its reader has looked at, keyed by
// the revision the queue reports, so a new commit reads as unseen again. It isn't project state:
// nothing else reads it, and clearing it loses nothing but the marks.

const key = (root, revision) => `ws-seen:${root}:${revision}`

export function isSeen(root, revision) {
  try {
    return localStorage.getItem(key(root, revision)) !== null
  } catch {
    return false
  }
}

export function setSeen(root, revision, seen) {
  try {
    if (seen) localStorage.setItem(key(root, revision), '1')
    else localStorage.removeItem(key(root, revision))
  } catch {
    // No storage here, as in a private window. The marks just don't stick.
  }
}

export function unseenCount(root, tasks) {
  return tasks.filter(t => !isSeen(root, t.revision)).length
}
