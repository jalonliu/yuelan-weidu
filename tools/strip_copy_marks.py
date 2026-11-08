# -*- coding: utf-8 -*-
"""去掉文件名结尾的副本标记 (n)/（n）/ - 副本/副本，保留扩展名。两阶段改名，同步sidecar。"""
import os, re

LIB = r'F:\Users\Calibre 书库'
EXTS = {'.epub','.mobi','.azw3','.pdf','.txt','.fb2'}

def clean_stem(stem):
    s = stem
    # 反复去除结尾副本标记
    prev=None
    while prev!=s:
        prev=s
        s = re.sub(r'\s*[\(（]\d+[\)）]\s*$','',s)      # (2) （2）
        s = re.sub(r'\s*[-－—_]?\s*副本\s*$','',s)       # - 副本 / 副本
        s = s.rstrip()
    return s

def is_copy(stem):
    return clean_stem(stem) != stem.rstrip()

total=0
for shelf in ['书库','杂书架','18+']:
    d=os.path.join(LIB,shelf)
    if not os.path.isdir(d): continue
    files=sorted(os.listdir(d))
    for f in files:
        stem,ext=os.path.splitext(f)
        if ext.lower() not in EXTS: continue
        if not is_copy(stem): continue
        newstem=clean_stem(stem)
        newname=newstem+ext
        if newname==f: continue
        src=os.path.join(d,f)
        dst=os.path.join(d,newname)
        if os.path.exists(dst) and dst!=src:
            # 目标已存在（可能是另一份）→ 跳过避免覆盖
            print(f"  !跳过(目标已存在): {f}  ->  {newname}")
            continue
        if not os.path.isfile(src): continue
        # 两阶段防撞名
        tmp=os.path.join(d, f"__cc_{total}{ext}")
        os.rename(src,tmp)
        os.rename(tmp,dst)
        # sidecar
        oldside=os.path.join(d, stem+'.cover.jpg')
        newside=os.path.join(d, newstem+'.cover.jpg')
        if os.path.isfile(oldside) and oldside!=newside:
            if not os.path.exists(newside):
                os.rename(oldside,newside)
        print(f"  改名: {f}  ->  {newname}")
        total+=1
print(f"\n共改名: {total}")
