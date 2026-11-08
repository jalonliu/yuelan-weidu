/**
 * Panel + icon styles for dsh-yuelan. Injected once into the document head;
 * all selectors are prefixed `yuelan-` to stay out of the shell's way.
 * @module dsh-yuelan/client/styles
 */

const CSS = `
.yuelan-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.yuelan-panel-head { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-bottom: 1px solid var(--border, #e5e5e5); flex: none; }
.yuelan-panel-name { font-weight: 700; font-size: 15px; }
.yuelan-panel-sub { color: var(--muted-foreground, #888); font-size: 12px; flex: 1; }
.yuelan-panel-actions { display: flex; gap: 6px; }
.yuelan-btn { border: 1px solid var(--border, #e5e5e5); background: transparent; color: inherit; border-radius: 8px; padding: 5px 12px; font-size: 12px; cursor: pointer; }
.yuelan-btn:hover { border-color: var(--accent, #2fa88f); color: var(--accent, #2fa88f); }
.yuelan-btn-primary { padding: 8px 20px; font-size: 13px; }
.yuelan-panel-body { flex: 1; min-height: 0; position: relative; }
.yuelan-frame { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; background: #faf9f7; }
.yuelan-wake { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; color: var(--muted-foreground, #888); }
.yuelan-wake p { margin: 0; font-size: 13px; }
`

/** Inject the stylesheet once per document. */
export function injectStyles(): void {
  if (document.getElementById('yuelan-styles') !== null) return
  const el = document.createElement('style')
  el.id = 'yuelan-styles'
  el.textContent = CSS
  document.head.appendChild(el)
}
