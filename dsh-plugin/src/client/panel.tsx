/**
 * The dsh-yuelan panel: the full 阅览围读 UI in an iframe.
 *
 * The reader server binds `127.0.0.1:8766` only, and dsh's web shell runs on
 * the same machine, so the browser may load it directly — every feature (three
 * shelves, foliate reader, WeChat Reading, today/retrospect, TTS, streaming AI)
 * works without any proxy. The host half guarantees the server is awake.
 * @module dsh-yuelan/client/panel
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'

/** The reader base URL. Same constant as the host half. */
export const BASE_URL = 'http://127.0.0.1:8766'

/** localStorage key for sidebar icon visibility. */
const SIDEBAR_HIDDEN_KEY = 'dsh-yuelan:sidebar-hidden'

/**
 * The center-column panel body: a compact header (title, open-in-browser,
 * reload, sidebar-toggle) over an iframe that carries the whole reader app.
 */
export function YuelanPanel(): ReactNode {
  const [ready, setReady] = useState<boolean | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const [sidebarHidden, setSidebarHidden] = useState(
    () => localStorage.getItem(SIDEBAR_HIDDEN_KEY) === '1',
  )
  const frameRef = useRef<HTMLIFrameElement | null>(null)

  const probe = useCallback(async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(1500) })
      setReady(res.ok)
    } catch {
      setReady(false)
    }
  }, [])

  useEffect(() => { void probe() }, [probe])

  const wake = useCallback(async () => {
    setReady(null)
    // The host spawns the server on activation; give a cold start a moment.
    const deadline = Date.now() + 20_000
    for (;;) {
      try {
        const res = await fetch(`${BASE_URL}/api/health`, { signal: AbortSignal.timeout(1500) })
        if (res.ok) { setReady(true); setReloadKey((n) => n + 1); return }
      } catch { /* retry */ }
      if (Date.now() > deadline) { setReady(false); return }
      await new Promise((r) => setTimeout(r, 900))
    }
  }, [])

  const openExternal = useCallback(() => {
    window.open(`${BASE_URL}/`, '_blank', 'noopener')
  }, [])

  const toggleSidebar = useCallback(() => {
    setSidebarHidden((prev) => {
      const next = !prev
      localStorage.setItem(SIDEBAR_HIDDEN_KEY, next ? '1' : '0')
      // Reload the page so the sidebar row re-registers with the shell.
      window.location.reload()
      return next
    })
  }, [])

  return (
    <div className="yuelan-panel">
      <header className="yuelan-panel-head">
        <span className="yuelan-panel-name">阅览围读</span>
        <span className="yuelan-panel-sub">Calibre 书库 · 微信读书 · 听书 · AI 总结</span>
        <div className="yuelan-panel-actions">
          <button type="button" className="yuelan-btn" title="用系统浏览器打开" onClick={openExternal}>↗ 浏览器</button>
          <button type="button" className="yuelan-btn" title="重新加载" onClick={() => setReloadKey((n) => n + 1)}>⟳</button>
          <button
            type="button"
            className="yuelan-btn"
            title={sidebarHidden ? '显示侧栏图标' : '隐藏侧栏图标'}
            onClick={toggleSidebar}
          >
            {sidebarHidden ? '👁 显示图标' : '🚫 隐藏图标'}
          </button>
        </div>
      </header>
      <div className="yuelan-panel-body">
        {ready === false ? (
          <div className="yuelan-wake">
            <p>本地阅读服务未响应（127.0.0.1:8766）。</p>
            <button type="button" className="yuelan-btn yuelan-btn-primary" onClick={() => void wake()}>唤醒服务</button>
          </div>
        ) : (
          <iframe
            key={reloadKey}
            ref={frameRef}
            className="yuelan-frame"
            src={ready === null ? 'about:blank' : `${BASE_URL}/`}
            title="阅览围读"
          />
        )}
      </div>
    </div>
  )
}
