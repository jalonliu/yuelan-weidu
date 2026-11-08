/**
 * Host half of dsh-yuelan.
 *
 * Owns the local reader server lifecycle. On activation it probes
 * http://127.0.0.1:8766/api/health and spawns server.py when the reader is
 * cold. The browser half embeds the full UI from the same base URL, so no data
 * routes need to be proxied here.
 * @module dsh-yuelan
 */

import type { PluginContext } from '../cordis.js'
import { BASE_URL, ensureRunning } from './server.js'

export { name } from './constants.js'

/**
 * No-op inject for Cordis compatibility.
 * This plugin does not register child plugins but must export inject
 * because the package entry lib/index.js re-exports { apply, inject, name }.
 */
export function inject(): void {}

/**
 * Kick the local reader server on plugin activation.
 * @param ctx - the host plugin context.
 */
export function apply(ctx: PluginContext): void {
  const logger = ctx.logger('dsh-yuelan')
  void ensureRunning(logger).then((ok) => {
    if (ok) logger.info(`dsh-yuelan: reader server ready at ${BASE_URL}`)
    else logger.warn('dsh-yuelan: reader server not reachable; the panel offers a retry button')
  })
}
