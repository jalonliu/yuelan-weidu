# dsh-yuelan 启动崩溃排查与修复记录（2026-11-07）

> 本文档记录 dsh-yuelan（阅览围读）插件导致 DeepSeek Harness 无法启动的完整排查过程、
> 三个根本原因、修复方案，以及从中提炼的 **dsh 客户端插件正确契约**，供以后"蒸馏"其他
> 插件时参考。

## 一、问题现象

插件安装后，DeepSeek Harness 启动即崩溃，错误对话框：

```
应用无法启动或已意外停止。
web boot: 1 entry did not activate
dsh-yuelan: loading        ← 或 failed
诊断报告: C:\Users\jalon\AppData\Roaming\@deepseek-ai\dsh-desktop\logs\crash-*.log
```

异常点：

- 桌面端的失败状态是 **`loading`（静默挂起约 3 分钟后审计超时崩溃）**，没有任何具体报错；
- web profile（`dsh --profile web`）同样的插件，浏览器里表现为 **`failed`**；
- 崩溃日志的 renderer console 只有审计错误本身，没有原因。

## 二、三个根本原因

### R1：宿主端入口导出了不存在的绑定（构建错误）

`lib/index.js`：

```js
export { apply, inject, name } from './host/index.js'
```

但 `host/index.js` 只实现并导出了 `apply` 和 `name`，没有 `inject`。
Node ESM 对"声明的导出不存在"直接抛 SyntaxError，宿主端插件导入失败。

**修复**：`src/host/index.ts` 增加空实现并导出（Cordis 兼容占位）：

```ts
export function inject(): void {}
```

> 教训：ESM 的 `export { x } from` 是静态绑定校验，声明了就必须存在；
> 本地构建后建议先跑一次 `node --input-type=module -e "import('file:///…/lib/index.js')"` 自检。

### R2：客户端模块没有导出 `inject` 服务声明

dsh 客户端插件契约（参考 `dsh-at-file`、`dsh-guizang-design`）：

```js
// 模块必须导出三件套
module.exports = {
  name: 'dsh-yuelan',
  inject: ['slots'],   // ← 声明插件需要的客户端服务，runner 依此把服务挂到 ctx
  apply(ctx) { /* ctx.slots 可用 */ },
}
```

蒸馏版只在 `module.exports` 上发布了 `name` 和 `apply`，**漏了 `inject`**，
runner 因此不会把 `slots` 服务挂到插件上下文。

**修复**：`src/client/index.ts` 增加 `const inject = ['slots']` 并发布到 `module.exports.inject`。

### R3：用 `require` 拿 slots 模块，而不是从 ctx 取服务实例

错误写法（蒸馏版）：

```ts
const slots = require('@deepseek-ai/dsh-client-ui-slots') as SlotsService
slots.inject('main', ...)   // TypeError: slots.inject is not a function
```

`require` 返回的是 **模块命名空间**（esbuild 打包产物），不是运行时服务实例。
正确写法（`dsh-at-file` 的模式）：

```ts
const inject = ['slots']

function apply(ctx: ClientContext): void {
  ctx.effect(() => {
    const slots = ctx.slots            // ← 服务实例由 runner 注入
    const disposePanel = slots.inject('main', () =>
      slots.register({ name: 'main', key: PANEL_ID }, YuelanPanel),
    )
    let disposeRow: (() => void) | null = null
    if (!sidebarHidden) {
      disposeRow = slots.inject('sidebar.panellist', () =>
        slots.register({ name: 'sidebar.panellist', id: PANEL_ID, order: PANEL_ORDER, label: '阅览围读' },
          (props) => createElement(YuelanIcon, props)),
      )
    }
    return () => { disposePanel(); disposeRow?.() }   // 清理函数交给 shell
  }, 'yuelan: sidebar row + panel')
}
```

**修复**：`src/client/index.ts` 重写 `apply` 为上述模式。

## 三、排查过程与方法（时间线）

| 时间 | 动作 | 结论 |
|---|---|---|
| 17:50 | 读宿主启动日志 `.dsh\logs\startup-*.log` | 定位 R1：`SyntaxError: does not provide an export named 'inject'` |
| 20:04 | 重建插件（修复 R1） | 桌面端仍崩，错误从"导入失败"变为"loading 挂起" |
| 20:35–00:19 | 多次重启 + CDP（Chrome DevTools 协议）网络捕获 | 关键发现：**renderer 根本没有发起过 dsh-yuelan 的模块请求**，也无任何报错 → 问题在调度而非传输 |
| — | 用 Node 直接运行 renderer 的模块加载器（`client-modules` client.js）+ 真实 boot 图 | 模拟里 `import("dsh-yuelan")` 一切正常 → 排除 Host 端与图数据 |
| — | 发现桌面 profile 与 web profile 的插件组成不同，改用 **web profile + 真实浏览器复现** | 失败状态从 `loading` 变为 `failed`（可观察！） |
| — | 浏览器 CDP 注入钩子捕获模块系统内部状态 | `hasFactory: true`、`importError: null` → 模块已加载注册，**失败发生在 cordis 激活（apply）阶段** |
| — | 在页面里手动调用 `apply(mockCtx)` | **`TypeError: slots.inject is not a function`** → R3 实锤 |
| — | 对照 `dsh-at-file` 的产物 | R2 实锤（契约缺 `inject` 导出） |

### 关键调试手段（按性价比排序）

1. **web profile + 浏览器复现**（最高性价比）：`dsh --profile web --no-open --port 8799`
   用同一套加载代码、同一个插件在浏览器里复现，开发者工具全程可用，
   且失败状态比桌面端更有信息量（`failed` vs 静默 `loading`）。
2. **模块系统内部状态**：通过 CDP `Page.addScriptToEvaluateOnNewDocument` 包一层
   `__ModuleLoader__.create`，把模块系统实例挂到 `window.__DSH_SYS__`，即可直接读
   `importErrors / factories / graphRows`，甚至手动 `import("dsh-yuelan")` 复现。
3. **对照正常插件**：`dsh-at-file` 等本地 file: 插件的 `lib/client.js` 是最好的契约参考。
4. 桌面端 crash 日志只记 error 级 console，且审计错误会吞掉真实原因——不要只看它。

## 四、修复涉及的三处声明（缺一不可）

```jsonc
// package.json —— 图行级服务依赖（cordis 入口激活顺序）
"dsh": {
  "client": {
    "platform": "web",
    "inject": ["@deepseek-ai/dsh-client-ui-slots"]   // 包名形态
  }
}
```

```ts
// src/client/index.ts —— 模块级服务声明（runner 注入 ctx 用，短服务名形态）
const inject = ['slots']        // 服务名形态，与 ctx.slots 对应
function apply(ctx) { /* ctx.slots */ }
// 构建脚本会剥掉 ESM 导出，必须手动发布：
module.exports.name = name
module.exports.inject = inject  // ← v1.1.3 漏了它
module.exports.apply = apply
```

> 两种 `inject` 形态不同：package.json 用**包名**（`@deepseek-ai/dsh-client-ui-slots`），
> 模块导出用**短服务名**（`slots`），不要混淆。

## 五、经验教训

1. **蒸馏插件时以能正常工作的同类插件为契约模板**，不要凭直觉使用 `require` 取服务。
2. dsh 构建脚本（aurora `scripts/build.mjs`）会把 ESM 导出剥掉（`collapseBlocks` 处理
   export 列表），客户端插件的导出面必须手动发布到 `module.exports`。
3. 桌面端 web boot 的 `loading` ≠ 没报错，而是"审计超时前模块还没就位"；
   `failed` 才有可查的错误。web profile 是更好的复现环境。
4. 重启（重启按钮）只刷新 web shell；替换宿主/插件代码后要**完全退出应用再启动**。
