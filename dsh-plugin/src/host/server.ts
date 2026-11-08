/**
 * Local server lifecycle for dsh-yuelan.
 *
 * The panel embeds the full 阅览围读 UI served by `server.py` on
 * `http://127.0.0.1:8766`. The host half owns only the lifecycle: probe the
 * health endpoint, spawn the stdlib server on demand (detached, so it
 * survives this plugin's reload), and expose readiness to the browser half.
 * @module dsh-yuelan/src/host/server
 */

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { join } from 'node:path'

/** Where the reader server lives. Override with `QMU_SERVER_DIR`. */
export function serverDir(): string {
  const fromEnv = process.env.QMU_SERVER_DIR
  if (fromEnv && existsSync(join(fromEnv, 'server.py'))) return fromEnv
  const fallback = 'D:\\jalon\\yuelan-weidu'
  if (existsSync(join(fallback, 'server.py'))) return fallback
  return ''
}

export const BASE_URL = 'http://127.0.0.1:8766'

/** True when the reader server answers `/api/health`. */
export async function probe(timeoutMs = 1200): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/api/health`, {
      signal: AbortSignal.timeout(timeoutMs),
    })
    return res.ok
  } catch {
    return false
  }
}

/**
 * Start the stdlib server detached. `py -3.14` with `-I` keeps the reader's
 * stdlib-only contract; `detached + unref` lets it outlive this plugin.
 */
export function startDetached(logger?: { info(m: string): void; error(m: string): void }): boolean {
  const dir = serverDir()
  if (dir === '') return false
  const exe = process.platform === 'win32' ? 'py' : 'python3'
  const child = spawn(exe, ['-3.14', '-I', '-u', 'server.py'], {
    cwd: dir,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  })
  child.on('error', (err) => logger?.error(`dsh-yuelan: spawn failed: ${err.message}`))
  child.unref()
  logger?.info(`dsh-yuelan: spawned reader server (pid ${child.pid}) from ${dir}`)
  return true
}

/**
 * Ensure the server is reachable, spawning and waiting when it is not.
 * Returns true once `/api/health` answers (cold start is ~9 s).
 */
export async function ensureRunning(
  logger?: { info(m: string): void; error(m: string): void },
  timeoutMs = 25_000,
): Promise<boolean> {
  if (await probe(800)) return true
  startDetached(logger)
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 800))
    if (await probe(800)) return true
  }
  return false
}
