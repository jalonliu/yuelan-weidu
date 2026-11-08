# -*- coding: utf-8 -*-
"""扫描整个书库根，找出文件名书名部分是拼音的书，读其内部元数据中文名。"""
import os, re, subprocess, json
LIB = r'F:\Users\Calibre 书库'
META = r'C:\Program Files\Calibre2\ebook-meta.exe'
EXTS = {'.epub','.mobi','.azw3','.pdf','.fb2'}
SKIP = {'_trash','_trash_dedup','_trash_dedup_18','_trash_covers','.calibre','.Trash','Calibre'}

def title_part(name):
    base=os.path.splitext(name)[0]
    return base.split(' - ')[0].strip()

def is_pinyin_title(tp):
    # 书名部分：中文数为0 且 拉丁字母>=5
    cn=sum(1 for c in tp if '\u4e00'<=c<='\u9fff')
    latin=sum(1 for c in tp if c.isascii() and c.isalpha())
    return cn==0 and latin>=5

def meta_title_author(full):
    try:
        r=subprocess.run([META,full],capture_output=True,timeout=40)
        txt=r.stdout.decode('utf-8',errors='ignore')
        t=a=''
        for line in txt.splitlines():
            line=line.strip()
            if line.startswith('Title') and not t and ':' in line: t=line.split(':',1)[1].strip()
            if line.startswith('Author') and not a and ':' in line: a=line.split(':',1)[1].strip()
        return t,a
    except: return '',''

rows=[]
for dirpath,dirs,files in os.walk(LIB):
    dirs[:]=[d for d in dirs if d not in SKIP]
    for f in sorted(files):
        ext=os.path.splitext(f)[1].lower()
        if ext not in EXTS: continue
        tp=title_part(f)
        if is_pinyin_title(tp):
            full=os.path.join(dirpath,f)
            mt,ma=meta_title_author(full)
            mc=sum(1 for c in mt if '\u4e00'<=c<='\u9fff')
            rows.append(dict(file=f,path=os.path.relpath(full,LIB),ext=ext,
                             meta_title=mt,meta_author=ma,meta_has_cn=mc>0,
                             size=os.path.getsize(full)))

print("拼音文件名书: %d 本\n"%len(rows))
for r in rows:
    flag='✔中文元数据' if r['meta_has_cn'] else '✘无中文'
    print(f"[{flag}] {r['path']}")
    print(f"    文件名: {r['file']}")
    print(f"    内部元数据: title='{r['meta_title']}' author='{r['meta_author']}'")
json.dump(rows,open(r'F:\jalon\deepseek\.tmp\yuelan_pinyin_files.json','w',encoding='utf-8'),ensure_ascii=False,indent=1)
