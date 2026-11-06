// One call per burst: each poke restarts the wait, and `fn` runs once the pokes stop for `ms`.
// A poke while `fn` runs queues exactly one more run after it.
export type Timers = { set: (fn: () => void, ms: number) => unknown; clear: (handle: unknown) => void }

const realTimers: Timers = {
  set: (fn, ms) => setTimeout(fn, ms),
  clear: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
}

export function debounce(fn: () => Promise<void>, ms: number, timers: Timers = realTimers): { poke: () => void; dispose: () => void } {
  let handle: unknown
  let running = false
  let again = false
  let disposed = false
  const fire = async () => {
    handle = undefined
    if (disposed) return
    if (running) {
      again = true
      return
    }
    running = true
    try {
      await fn()
    } finally {
      running = false
      if (again && !disposed) {
        again = false
        poke()
      }
    }
  }
  const poke = () => {
    if (disposed) return
    if (handle !== undefined) timers.clear(handle)
    handle = timers.set(() => void fire(), ms)
  }
  return {
    poke,
    dispose: () => {
      disposed = true
      if (handle !== undefined) timers.clear(handle)
    },
  }
}
