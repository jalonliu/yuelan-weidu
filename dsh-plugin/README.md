# dsh-yuelan · 阅览围读 (dsh 插件)

DeepSeek Harness（dsh）插件版「阅览围读」：在 dsh Web 侧栏一键进入完整阅读器——Calibre 本地书库、foliate 阅读、微信读书在线书架与统计、今日/回顾、TTS 听书、AI 流式总结，全部功能与 Hermes 插件版一致。

## 架构

- **Host 半边**（`lib/index.js`，Cordis 插件）：激活时探活 `http://127.0.0.1:8766/api/health`，未运行则以 detached 方式唤醒 `server.py`（冷启动约 9 秒）；不动数据面。
- **Client 半边**（`lib/client.js`，Web 面板）：注册 dsh 侧栏图标 + 中央面板，内嵌 iframe 直载本机阅览围读完整 UI（服务只绑 127.0.0.1，同机浏览器直连即全功能）。
- 服务本体与全部功能来自 [yuelan-weidu](https://github.com/jalonliu/yuelan-weidu)（默认目录 `D:\jalon\yuelan-weidu`，可用 `QMU_SERVER_DIR` 环境变量覆盖）。

## 安装

```bash
# 构建（需要 esbuild / typescript）
cd dsh-yuelan && pnpm install && node scripts/build.mjs

# 装进 profile（构建产物按 package.json files 白名单拷贝）
dsh plugin --profile web add --save-prod "file:D:/jalon/dsh-yuelan"
```

然后在 dsh Web GUI → Settings → Plugins 启用 **dsh-yuelan** 并刷新页面；侧栏出现书本图标即入口。

前置：`D:\jalon\yuelan-weidu\server.py` 存在（或 `QMU_SERVER_DIR` 指向含 `server.py` 的目录），Python 3.10+ 可用（`py -3.14`）。

## 代码改动后更新

`dsh plugin add` 是拷贝安装：改完代码需重新 build 并再次 add。

## License

MIT
