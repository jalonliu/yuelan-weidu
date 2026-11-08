/**
 * The subset of Cordis this plugin is written against.
 * @module dsh-yuelan/src/cordis
 */

/** A disposable callback: disposing withdraws the contribution. */
export type Disposer = () => void

/** A named logger facade. */
export interface Logger {
  info(message: string, ...rest: unknown[]): void
  warn(message: string, ...rest: unknown[]): void
  error(message: string, ...rest: unknown[]): void
  debug(message: string, ...rest: unknown[]): void
}

/** The host plugin context surface this plugin uses. */
export interface PluginContext {
  logger(name: string): Logger
  effect(factory: () => Disposer | Promise<Disposer>, name?: string): unknown
  inject(deps: readonly string[], callback: (scope: PluginScope) => void): unknown
}

/** A resolved dependency scope. */
export interface PluginScope {
  get<T = unknown>(name: string): T | undefined
}
