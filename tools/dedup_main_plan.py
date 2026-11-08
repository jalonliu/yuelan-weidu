# -*- coding: utf-8 -*-
"""分析书库(main)与杂书架重复书，生成去重计划。重点：xxx(n) 后缀副本、跨格式同书。"""
import os, re, unicodedata, json
from collections import defaultdict

LIB = r'F:\Users\Calibre 书库'
SHELVES = {'书库':'main','杂书架':'misc','18+':'adult'}
EXTS = {'.epub','.mobi','.azw3','.pdf','.fb2','.txt'}
PRIORITY = {'.epub':0,'.azw3':1,'.mobi':2,'.pdf':3,'.fb2':4,'.txt':5}

def base_title(fname):
    base = os.path.splitext(fname)[0]
    # 去尾部 (n) / （n）副本标记
    base = re.sub(r'\s*[\(（]\d+[\)）]\s*$','',base).strip()
    # 书名 = ' - ' 前
    title = base.split(' - ')[0].strip()
    return title

def norm(t):
    t = unicodedata.normalize('NFKC', t)
    t = re.sub(r'\s+','',t).lower()
    return t

groups = defaultdict(list)
for shelf,key in SHELVES.items():
    d = os.path.join(LIB, shelf)
    if not os.path.isdir(d): continue
    for f in os.listdir(d):
        ext = os.path.splitext(f)[1].lower()
        if ext not in EXTS: continue
        full = os.path.join(d,f)
        if not os.path.isfile(full): continue
        t = base_title(f)
        gk = norm(t)
        groups[gk].append(dict(shelf=shelf,file=f,ext=ext,title=t,size=os.path.getsize(full),path=os.path.join(shelf,f)))

plan=[]
for gk,items in groups.items():
    if len(items)<2: continue
    # 排序: 优先epub, 再体积降序, 再(无副本后缀优先)
    def sortkey(it):
        has_copy = 1 if re.search(r'[\(（]\d+[\)）]\s*$', os.path.splitext(it['file'])[0]) else 0
        return (PRIORITY.get(it['ext'],9), -it['size'], has_copy)
    items_sorted = sorted(items,key=sortkey)
    keep = items_sorted[0]
    for it in items_sorted[1:]:
        plan.append(dict(delete=it['path'],keep=keep['path'],del_ext=it['ext'],keep_ext=keep['ext'],
                         title=gk,del_size=it['size'],keep_size=keep['size']))

print("重复组数(有删除):", len(set(p['title'] for p in plan)))
print("计划删除条数:", len(plan))
print()
for p in sorted(plan,key=lambda x:x['title']):
    print(f"删 [{p['del_ext']:5s} {p['del_size']/1024/1024:6.1f}MB] {p['delete']}")
    print(f"  留 [{p['keep_ext']:5s} {p['keep_size']/1024/1024:6.1f}MB] {p['keep']}")
json.dump(plan,open(r'F:\jalon\deepseek\.tmp\dedup_main_plan.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
