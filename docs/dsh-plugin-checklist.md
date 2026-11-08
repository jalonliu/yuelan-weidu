# dsh 客户端插件易错点清单与修复检查（阅览围读实战沉淀）

> 适用范围：任何"把既有项目蒸馏成 dsh 插件"的场景。每一条都来自
> dsh-yuelan v1.1.0–v1.1.4 的真实翻车，见 [FIXLOG-2026-11-07-dsh-plugin.md](./FIXLOG-2026-11-07-dsh-plugin.md)。

## 一、易错点（按踩坑频率排序）

### ① ESM 静态导出与实际产物不一致（宿主端）
- `lib/index.js` 写了 `export { apply, inject, name } from './host/index.js'`，
  但 `host/index.ts` 只实现了其中一部分 → Node ESM 直接抛
  `SyntaxError: does not provide an export named 'xxx'`。
- **要点**：入口 re-export 列表里的每个名字都必须真实存在；占位也要写空实现。

### ② 客户端模块漏发 `inject` 服务声明
- `module.exports` 只发布了 `name` 和 `apply`，没有 `inject`，
  runner 不会把声明的服务（如 `slots`）挂到插件上下文。
- **要点**：插件面三件套缺一不可：`name` / `inject`（短服务名数组）/ `apply(ctx)`。

### ③ 用 `require(包名)` 当服务用（最容易犯）
- `require("@deepseek-ai/dsh-client-ui-slots")` 返回的是 **esbuild 打包的模块命名空间**，
  不是运行时服务实例——上面没有 `inject/register` 方法。
- **要点**：服务一律走 `ctx.slots` / `ctx.get("服务名")`；`require` 只用于 react 等种子模块。

### ④ `package.json` 与模块导出的两种 `inject` 形态混淆
- `package.json → dsh.client.inject` 用**完整包名**：
  `["@deepseek-ai/dsh-client-ui-slots"]`（cordis 图行级依赖，决定入口激活顺序）。
- 模块 `module.exports.inject` 用**短服务名**：
  `["slots"]`（runner 挂 ctx 属性用）。
- **要点**：两处都要写，且各自用对形态。

### ⑤ 构建脚本会剥掉 ESM 导出
- aurora `scripts/build.mjs` 的 `wrapClient`/`collapseBlocks` 会删除
  `export { … }` 列表与顶层 `export`，产出经典脚本。
- **要点**：客户端导出面必须手动发布到 `module.exports`，构建后必须自检产物。

### ⑥ 侧栏图标注册时机
- 注册包在 `ctx.effect` 内（随 fiber 生命周期清理）并不会导致图标"错过首帧"；
  真正让图标消失的是 apply 抛异常。**先保证 apply 不抛，再谈时机优化。**

### ⑦ file: 本地路径安装不可移植

- `dsh plugin add --save-prod "file:D:/jalon/xxx"` 是**绝对路径**，换机器/换盘符即失效。
- **要点**：源码推到 GitHub 后改用 git 形态安装：

  ```
  dsh plugin --profile web add --save-prod "github:<user>/<repo>#path:/<子目录>"
  ```

  并在 package.json 加 `"prepare": "node scripts/build.mjs"`
  （pnpm 从 git 安装时会自动构建 lib/）。本仓库即用
  `github:jalonliu/yuelan-weidu#path:/dsh-plugin`。

### ⑩ 用 PowerShell 写 JSON 会带 BOM（宿主启动直接崩）

- Windows PowerShell 5.1 的 `Set-Content -Encoding UTF8` / `Out-File` 会写入
  **带 BOM 的 UTF-8**。profile 的 package.json 一旦带 BOM，宿主启动时
  `readProfileManifest → JSON.parse` 立即抛
  `Unexpected token '', "{\"name\"... is not valid JSON"`（host.log，不是 web-boot）。
- 症状识别：崩溃日志 source 是 **host**、错误是 JSON 解析、且报错文本以
  不可见字符开头——九成是 BOM。
- **要点**：改 JSON 用 node（`JSON.parse` + `fs.writeFileSync`，默认无 BOM），
  或 `Set-Content -Encoding utf8NoBOM`（PowerShell 7+）。
  排查命令：

  ```js
  const b = fs.readFileSync(f); console.log(b[0] === 0xEF) // true = 有 BOM
  ```

### ⑨ 改完宿主/插件代码只点"重启"
- 重启按钮只刷新 web shell；宿主端与插件代码要**完全退出应用再启动**才会重新加载。

## 二、修复检查清单（发布前逐项打勾）

### 构建 / 静态自检
- [ ] `node --input-type=module -e "import('file:///<绝对路径>/lib/index.js')"` 不抛错（R1 检查）
- [ ] `lib/client.js` 里 `module.exports` 被赋了 `name`、`inject`、`apply` 三个属性
      （grep `shared.inject` 或对应变量）
- [ ] `lib/client.js` 不包含 `require("@deepseek-ai/dsh-client-ui-slots")` 之类的服务 require
- [ ] `package.json` 的 `dsh.client.inject` 与模块 `inject` 声明一一对应（包名 ↔ 短服务名）
- [ ] 版本号已递增（rev 由 mtime/ctime/size 计算，内容变了版本没变会混用缓存语义）

### 部署
- [ ] 新构建已同步到**所有**启用它的 profile（desktop / web / …）的 `node_modules`，
      或在 profile 里重跑 `pnpm install`（file: 依赖是 injected 拷贝，不会自动跟随源码）
- [ ] 应用完全退出后冷启动

### 运行验证（web profile 优先）
- [ ] `dsh --profile web --no-open --port 8799` 启动无 `Failed plugins`
- [ ] 浏览器打开后不出现 "Failed to load plugins"；
      若出现 `failed` 状态，F12 控制台必有具体 TypeError——按报错修
- [ ] `loading` 状态 = 静默挂起，检查清单前三项；`failed` 状态 = apply 阶段抛错，看控制台
- [ ] 侧栏图标出现、点击能打开面板、面板 iframe 能连上本地服务
- [ ] 桌面端冷启动通过 3 分钟审计（web boot 审计超时约 3 分钟）
- [ ] 插件停用（`disabled: true`）对照一次，确认崩溃确实来自本插件

## 三、一句话契约

```js
// package.json
"dsh": { "client": { "platform": "web", "inject": ["@deepseek-ai/dsh-client-ui-slots"] } }

// client 模块（构建后手动发布到 module.exports）
module.exports = {
  name: 'my-plugin',
  inject: ['slots'],                    // 短服务名 → ctx.slots
  apply(ctx) {
    ctx.effect(() => {
      const dispose = ctx.slots.inject('sidebar.panellist', () =>
        ctx.slots.register({ name: 'sidebar.panellist', id: 'my-plugin', order: 62 }, Icon))
      return () => dispose()
    }, 'my-plugin: sidebar')
  },
}
```
