# -*- coding: utf-8 -*-
"""检测拼音书名书的重复(书库内是否有同书中文名版)。"""
import os,re,json
LIB=r'F:\Users\Calibre 书库\书库'
rows=json.load(open(r'F:\jalon\deepseek\.tmp\yuelan_pinyin_files.json',encoding='utf-8'))
# 书库所有书
files=[f for f in os.listdir(LIB) if os.path.splitext(f)[1].lower() in {'.epub','.mobi','.azw3','.pdf','.fb2','.txt'}]

def norm(t):
    t=re.sub(r'\s*[\(（\[【][^\)）\]】]*[\)）\]】]','',t)
    t=re.sub(r'\s*\(\d+\)\s*$','',t)
    return t.strip().lower()

for r in rows:
    mt=r['meta_title']
    mt_short=re.split(r'[（(：:]', mt)[0].strip()  # 取主标题
    # 在书库找同主标题的中文书名文件
    cands=[]
    for f in files:
        if f==r['file']: continue
        fb=os.path.splitext(f)[0].split(' - ')[0].strip()
        if norm(fb)==norm(mt_short) or norm(fb) in norm(mt_short) or norm(mt_short) in norm(fb):
            if fb:  # 非空
                cn=sum(1 for c in fb if '\u4e00'<=c<='\u9fff')
                if cn>0:
                    cands.append(f)
    print(f"[{r['file']}]")
    print(f"   主标题: {mt_short}")
    if cands:
        for c in cands: print(f"   ★重复候选: {c} ({os.path.getsize(os.path.join(LIB,c))/1024:.0f}KB)")
    else:
        print("   (无中文名重复)")
