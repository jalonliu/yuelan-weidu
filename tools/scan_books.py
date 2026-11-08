# -*- coding: utf-8 -*-
"""扫描书库：读取每个电子书内部元数据（书名/作者/标题排序），导出 TSV 供分析。"""
import os, subprocess, sys, json, csv

LIB = r'F:\Users\Calibre 书库\杂书架'
META = r'C:\Program Files\Calibre2\ebook-meta.exe'
EXTS = {'.mobi', '.azw3', '.epub', '.pdf', '.txt'}

def get_meta(path):
    try:
        out = subprocess.run([META, path], capture_output=True, timeout=60)
        text = out.stdout.decode('utf-8', 'replace')
    except Exception as e:
        return None, None, f'ERR:{e}'
    title = author = ''
    for line in text.splitlines():
        if line.startswith('Title'):
            title = line.split(':', 1)[1].strip() if ':' in line else ''
        elif line.startswith('Author(s)'):
            author = line.split(':', 1)[1].strip() if ':' in line else ''
    return title, author, None

rows = []
for name in sorted(os.listdir(LIB)):
    full = os.path.join(LIB, name)
    if not os.path.isfile(full):
        continue
    ext = os.path.splitext(name)[1].lower()
    if ext not in EXTS:
        continue
    title, author, err = get_meta(full)
    rows.append({
        'filename': name,
        'ext': ext,
        'title': title or '',
        'author': author or '',
        'err': err or '',
        'has_cn_title': 'Y' if title and any('\u4e00' <= c <= '\u9fff' for c in title) else 'N',
    })

with open(r'F:\jalon\deepseek\.tmp\book_meta.tsv', 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['filename','ext','title','author','err','has_cn_title'], delimiter='\t')
    w.writeheader()
    w.writerows(rows)

total = len(rows)
cn = sum(1 for r in rows if r['has_cn_title'] == 'Y')
print(f'TOTAL={total}  CN_TITLE={cn}  NO_CN={total-cn}')
print('--- 无中文书名的条目 ---')
for r in rows:
    if r['has_cn_title'] != 'Y':
        print(f"[{r['ext']}] {r['filename']}  ||  title={r['title']!r}  author={r['author']!r} {r['err']}")
