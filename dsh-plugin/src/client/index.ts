/**
 * Browser half of dsh-yuelan (阅览围读).
 *
 * Targets the dsh 0.2.2 sidebar contract: a global panel is a pair of
 * registrations sharing one id — an icon in the root-scoped `sidebar.panellist`
 * list, and the panel body in the root-scoped `main` keyed slot under the same
 * key. Selecting the icon swaps the center column to the panel.
 * @module dsh-yuelan/client
 */

import { createElement, type ReactNode } from 'react'
import { YuelanPanel } from './panel.js'
import { YuelanIcon } from './icon.js'
import { injectStyles } from './styles.js'

/** Stable Cordis plugin name. */
const name = 'dsh-yuelan'

/** The panel id shared by the sidebar row and the main panel key. */
const PANEL_ID = 'dsh-yuelan'

/** Sidebar rail order: after the core pages, before late third-party rows. */
const PANEL_ORDER = 62

/** localStorage key for sidebar icon visibility (default: visible). */
const SIDEBAR_HIDDEN_KEY = 'dsh-yuelan:sidebar-hidden'

/**
 * Client services this plugin requires. The shell runner resolves each id and
 * attaches the instance to the plugin context (`ctx.slots`). Short service ids,
 * exactly as the working reference plugins (dsh-at-file et al.) declare them.
 */
const inject = ['slots']

/** The slice of the slots service this plugin uses. */
interface SlotsService {
  register(options: Record<string, unknown>, component: unknown): () => void
  inject(seat: string, callback: () => unknown): () => void
}

/** Minimal client context surface used here. */
interface ClientContext {
  slots: SlotsService
  effect: (factory: () => () => void, name?: string) => unknown
}

/**
 * Client plugin body: register the sidebar row and the panel for this
 * plugin's lifetime.
 *
 * The slots service MUST come from the plugin context (`ctx.slots`) — the raw
 * module `@deepseek-ai/dsh-client-ui-slots` is a namespace without the service
 * face, and calling `.inject` on it throws `slots.inject is not a function`,
 * which fails the whole web boot.
 *
 * Registrations live inside `ctx.effect` so the shell disposes them together
 * with the plugin fiber.
 * @param ctx - the client plugin context with the declared services.
 */
function apply(ctx: ClientContext): void {
  ctx.effect(() => {
    const slots = ctx.slots
    injectStyles()

    // Center-column panel body — always registered so the panel can be opened
    // directly when the user navigates to the URL hash, even if the icon is hidden.
    const disposePanel = slots.inject('main', () =>
      slots.register({ name: 'main', key: PANEL_ID }, YuelanPanel),
    )

    // Sidebar nav row (icon only) — registered only when not hidden.
    const sidebarHidden = localStorage.getItem(SIDEBAR_HIDDEN_KEY) === '1'
    let disposeRow: (() => void) | null = null
    if (!sidebarHidden) {
      disposeRow = slots.inject('sidebar.panellist', () =>
        slots.register(
          { name: 'sidebar.panellist', id: PANEL_ID, order: PANEL_ORDER, label: '阅览围读' },
          (props: Record<string, unknown>) => createElement(YuelanIcon, props) as ReactNode,
        ),
      )
    }

    return () => {
      disposePanel()
      disposeRow?.()
    }
  }, 'yuelan: sidebar row + panel')
}

/**
 * The build wraps the client as a classic script (`window.__ModuleLoader__.load`)
 * where inline ESM exports are stripped by the wrapper's export-list handling;
 * publish the plugin face manually. The face MUST carry `inject` — the runner
 * reads it to wire `ctx.slots` (and any other declared service) before apply.
 */
declare const module: { exports: Record<string, unknown> }
const shared = module.exports as Record<string, unknown>
shared.name = name
shared.inject = inject
shared.apply = apply
