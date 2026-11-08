# tools/ — 书库整理运维脚本归档

这些脚本是 yuelan 书库批量清理时使用的一次性/可复用工具。
**注意**：其中「去重」「整理书名(拼音转中文/去副本标记)」「封面匹配」的核心能力
已内建进 `server.py` 的 `/api/tools/dedup` 与 `/api/tools/rename-pinyin` 接口
（前端工具栏按钮"🧹 同书去重" "📝 整理书名"），**优先用界面按钮**。以下脚本仅作归档参考。

| 脚本 | 用途 |
|---|---|
| scan_books.py | 扫描电子书，用 Calibre ebook-meta 提取内部元数据(标题/作者)到 TSV |
| dedup_main_plan.py / dedup_main_exec.py | 去重分析与执行（同书名+作者，epub优先、体积保护，移入 _trash_dedup） |
| yuelan_scan_pinyin.py / yuelan_pinyin_dup.py / yuelan_pinyin_exec.py | 拼音文件名扫描、拼音重复检测、改为中文书名 |
| strip_copy_marks.py | 去掉文件名结尾的副本标记 (n)/副本，保留书名中间括号 |
| gen_covers.py | 为无封面书籍生成 600x800 渐变占位封面（PIL） |

依赖：Python 3.14 + Calibre(ebook-meta) + Pillow。字体默认 C:\Windows\Fonts\msyhbd.ttc。
