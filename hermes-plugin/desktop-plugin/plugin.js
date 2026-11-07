/**
 * 阅览围读 · Hermes 桌面插件
 * 侧栏导航入口（看板下方）→ 全页 iframe 指向本地书库服务 127.0.0.1:8766
 */
import { cn, host } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useState, useEffect } from 'react'

const ID = 'qiaomu-reader'
const BOOK_SERVER = 'http://127.0.0.1:8766/'

function ReaderPage() {
  return jsx('div', {
    style: { display: 'flex', flexDirection: 'column', height: '100%' },
    children: jsx('iframe', {
      src: BOOK_SERVER,
      style: { flex: 1, width: '100%', border: 'none', background: '#f7f6f3' },
      title: '阅览围读',
      allow: 'clipboard-write'
    })
  })
}

function ServerDown({ err }) {
  return jsxs('div', {
    className: 'flex h-full flex-col items-center justify-center gap-3 text-sm',
    children: [
      jsx('div', { className: 'font-medium text-(--ui-text-secondary)', children: '书库服务未启动' }),
      jsx('div', { className: 'text-(--ui-text-tertiary)', children: '点击重试或手动运行: py -3.14 -I D:\\jalon\\qiaomu-reader-tab\\server.py' }),
      err ? jsx('div', { className: 'text-[11px] text-(--ui-text-quaternary)', children: `细节: ${err}` }) : null,
      jsx('button', {
        className: cn('rounded-md px-3 py-1.5 text-xs border border-(--ui-stroke-secondary)', 'hover:bg-(--chrome-action-hover)'),
        type: 'button',
        onClick: () => window.open(BOOK_SERVER, '_blank'),
        children: '浏览器打开'
      })
    ]
  })
}

let pluginCtx = null

async function pingServer() {
  try {
    const r = await fetch('http://127.0.0.1:8766/api/health', { signal: AbortSignal.timeout(1500) })
    return r.ok
  } catch { return false }
}

function ReaderGate() {
  const [state, setState] = useState('connecting') // connecting | starting | up | down
  const [err, setErr] = useState('')
  useEffect(() => {
    let dead = false
    ;(async () => {
      if (await pingServer()) { if (!dead) setState('up'); return }
      // 唤醒：走插件 Python 后端 spawn server.py
      try {
        const r = await pluginCtx.rest('/start', { method: 'POST', timeoutMs: 25000 })
        const d = await r.json?.() ?? r
        if (d && d.ok) { if (!dead) setState('up'); return }
        setErr(d?.error || '后端未返回 ok')
      } catch (e) {
        setErr(String(e?.message || e))
      }
      if (!dead) setState('down')
    })()
    return () => { dead = true }
  }, [])
  if (state === 'up') return jsx(ReaderPage, {})
  if (state === 'down') return jsx(ServerDown, { err })
  return jsx('div', { className: 'p-4 text-sm text-(--ui-text-tertiary)', children: state === 'connecting' ? '连接书库服务…' : '正在唤醒书库服务…' })
}

export default {
  id: ID,
  name: '阅览围读',
  register(ctx) {
    pluginCtx = ctx
    // 全页路由
    ctx.register({
      id: 'page',
      area: 'routes',
      order: 100,
      title: '阅览围读',
      data: { path: '/reading' },
      render: () => jsx(ReaderGate, {})
    })
    // 侧栏导航行（排在看板下方）
    ctx.register({
      id: 'nav',
      area: 'sidebar.nav',
      order: 1000,
      data: { path: '/reading', label: '阅览围读', codicon: 'book' }
    })
  }
}
