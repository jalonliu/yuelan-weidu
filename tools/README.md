# tools/ — 书库运维辅助脚本

> **唯一真理源**：书库整理的核心能力全部内建于 `server.py`，通过界面按钮或 HTTP API 调用。
> 本目录**只放内建能力未覆盖的辅助脚本**，避免同一功能两套实现、日后不一致。

## 界面按钮（推荐用法，无需跑脚本）

| 按钮 | 后端 API | 能力 |
|---|---|---|
| 📝 整理书名（拼音/去副本） | `POST /api/tools/rename-pinyin` `{"apply":true}` | ①拼音/ASCII 文件名 → 内嵌元数据中文书名；②去除文件名结尾副本标记 `(n)`/`副本`（保留书名中间括号）；两阶段改名防撞名 |
| 🧹 同书去重（优先保 epub） | `POST /api/tools/dedup` `{"apply":true}` | 同书名+作者归组，epub>azw3>mobi>pdf>txt 优先、体积降序保留；远大于保留本(>2.5x)判为不同版本自动保护；删除移入 `_trash_dedup` 可恢复 |
| 🖼 无封面批量匹配 | `/api/covers/search/<id>` + `/api/covers/apply/<id>` | 在线豆瓣搜封面逐本应用 |
| ↻ 重新扫描书库 | `/api/rescan` | 重建索引 |

> 只预览不执行：对应 API 传 `{}`（不带 `apply`）即返回计划，供确认。

## 本目录保留的脚本（内建能力未覆盖的）

| 脚本 | 用途 | 为何不在内建里 |
|---|---|---|
| `scan_books.py` | 用 Calibre `ebook-meta` 提取每个电子书内部元数据（书名/作者），导出 TSV 供分析 | 一次性审计工具，非日常操作 |
| `gen_covers.py` | 为无封面书籍生成 600x800 渐变+书名占位封面（Pillow） | 内建只做在线搜封面，不做占位生成 |

依赖：Python 3.14 + Calibre(ebook-meta) + Pillow。字体默认 `C:\Windows\Fonts\msyhbd.ttc`。
